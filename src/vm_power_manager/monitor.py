"""Idle detection engine — the core monitoring loop logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from vm_power_manager.adapters.base import VMAdapter
from vm_power_manager.models import (
    CloudProvider,
    Config,
    IdleMetric,
    MetricSnapshot,
    MetricSource,
    ResolvedVMConfig,
    VMState,
)
from vm_power_manager.process_detector import detect_processes
from vm_power_manager.state import StateBackend

logger = logging.getLogger(__name__)


def check_all_vms(config: Config, state_backend: StateBackend) -> list[dict]:
    """
    Main monitoring loop: check each VM for idle state.

    Always collects metrics and stores state. Only takes stop action
    if auto_stop_enabled is true for the VM.

    Returns a list of actions taken (for reporting/logging):
    [{"vm": name, "action": "warning"|"stop"|"reset"|"skip", "metrics": {...}}]
    """
    actions = []
    defaults = config.defaults

    for vm_cfg in config.vms:
        resolved = vm_cfg.get_effective_config(defaults)

        try:
            result = _check_single_vm(resolved, config, state_backend)
            actions.append(result)
        except Exception as e:
            logger.error(f"Error checking VM {resolved.name}: {e}", exc_info=True)
            actions.append({"vm": resolved.name, "action": "error", "error": str(e)})

    return actions


def _check_single_vm(
    vm_config: ResolvedVMConfig,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Check a single VM and take appropriate action."""
    now = datetime.now(timezone.utc)

    # Get VM adapter
    adapter = _get_vm_adapter(vm_config)

    # Skip if VM is not running
    if not adapter.is_running():
        return {"vm": vm_config.name, "action": "skip", "reason": "not_running"}

    # Get current state
    state = state_backend.get_or_create(vm_config.name)

    # Check if monitoring is paused
    if state.paused:
        return {"vm": vm_config.name, "action": "skip", "reason": "paused"}

    # Check if user extended the keep-alive
    if state.keep_running_until and now < state.keep_running_until:
        return {
            "vm": vm_config.name,
            "action": "skip",
            "reason": "keep_running",
            "until": state.keep_running_until.isoformat(),
        }

    # Collect metrics
    metrics = _collect_metrics(vm_config)

    # Determine if idle
    is_idle = _evaluate_idle(metrics, vm_config)

    # Always update state with metrics
    state.last_checked = now
    state.last_metrics = metrics.model_dump()

    if is_idle:
        # Increment idle counter
        check_interval = vm_config.check_interval_minutes if hasattr(vm_config, 'check_interval_minutes') else 10
        state.idle_minutes += check_interval
        if state.idle_since is None:
            state.idle_since = now

        # Only take auto-stop actions if enabled
        if not vm_config.auto_stop_enabled:
            state_backend.set(vm_config.name, state)
            return {
                "vm": vm_config.name,
                "action": "idle_monitoring_only",
                "metrics": metrics.model_dump(),
                "idle_minutes": state.idle_minutes,
            }

        # Decision tree (auto-stop enabled)
        if state.warning_sent:
            warning_age = (now - state.warning_sent_at).total_seconds() / 60
            if warning_age >= vm_config.warning_minutes:
                action = _stop_vm(vm_config, adapter, state)
                state_backend.set(vm_config.name, state)
                return {
                    "vm": vm_config.name,
                    "action": "stop",
                    "metrics": metrics.model_dump(),
                    "idle_minutes": state.idle_minutes,
                    **action,
                }
            else:
                state_backend.set(vm_config.name, state)
                return {
                    "vm": vm_config.name,
                    "action": "waiting",
                    "reason": "warning_countdown",
                    "minutes_remaining": vm_config.warning_minutes - warning_age,
                }
        elif state.idle_minutes >= vm_config.idle_duration_minutes:
            state.warning_sent = True
            state.warning_sent_at = now
            state_backend.set(vm_config.name, state)
            return {
                "vm": vm_config.name,
                "action": "warning",
                "metrics": metrics.model_dump(),
                "idle_minutes": state.idle_minutes,
            }
        else:
            state_backend.set(vm_config.name, state)
            return {
                "vm": vm_config.name,
                "action": "idle_accumulating",
                "idle_minutes": state.idle_minutes,
                "threshold": vm_config.idle_duration_minutes,
            }
    else:
        # VM is active — reset idle state
        state.idle_since = None
        state.idle_minutes = 0
        state.warning_sent = False
        state.warning_sent_at = None
        state_backend.set(vm_config.name, state)
        return {
            "vm": vm_config.name,
            "action": "active",
            "metrics": metrics.model_dump(),
        }


def _stop_vm(vm_config: ResolvedVMConfig, adapter: VMAdapter, state: VMState) -> dict:
    """Execute VM stop with pre-stop hooks."""
    hook_result = {}

    # Run pre-stop hooks if SSH is available
    if vm_config.pre_stop_commands:
        try:
            from vm_power_manager.adapters.ssh import SSHAdapter
            from vm_power_manager.lifecycle import run_pre_stop_hooks

            ssh = SSHAdapter(vm_config)
            result = run_pre_stop_hooks(vm_config, ssh)
            hook_result["pre_stop_success"] = result.all_success
            if result.failed:
                hook_result["pre_stop_failures"] = [
                    {"cmd": r.command, "error": r.stderr[:100]} for r in result.failed
                ]
        except Exception as e:
            logger.warning(f"Pre-stop hooks failed for {vm_config.name}: {e}")
            hook_result["pre_stop_success"] = False

    # Stop the VM
    success = adapter.stop()

    # Reset state
    state.idle_since = None
    state.idle_minutes = 0
    state.warning_sent = False
    state.warning_sent_at = None
    state.session_started = None

    hook_result["stop_success"] = success
    return hook_result


def _collect_metrics(vm_config: ResolvedVMConfig) -> MetricSnapshot:
    """Collect all relevant metrics for a VM."""
    gpu = None
    cpu = None
    memory = None
    active_processes = []
    active_sessions = []

    from vm_power_manager.adapters.ssh import SSHAdapter
    from vm_power_manager.metrics.monitoring_api import MonitoringAPICollector
    from vm_power_manager.metrics.ssh_metrics import SSHMetricCollector

    # GPU
    source = vm_config.metric_sources.gpu_utilization
    if source == MetricSource.MONITORING_API:
        collector = MonitoringAPICollector(vm_config)
        gpu = collector.get_gpu_utilization()
    elif source == MetricSource.SSH:
        ssh = SSHAdapter(vm_config)
        ssh_collector = SSHMetricCollector(vm_config, ssh)
        gpu = ssh_collector.get_gpu_utilization()

    # CPU
    source = vm_config.metric_sources.cpu_utilization
    if source == MetricSource.MONITORING_API:
        collector = MonitoringAPICollector(vm_config)
        cpu = collector.get_cpu_utilization()
    elif source == MetricSource.SSH:
        ssh = SSHAdapter(vm_config)
        ssh_collector = SSHMetricCollector(vm_config, ssh)
        cpu = ssh_collector.get_cpu_utilization()

    # Memory
    source = vm_config.metric_sources.memory_utilization
    if source == MetricSource.MONITORING_API:
        collector = MonitoringAPICollector(vm_config)
        memory = collector.get_memory_utilization()
    elif source == MetricSource.SSH:
        ssh = SSHAdapter(vm_config)
        ssh_collector = SSHMetricCollector(vm_config, ssh)
        memory = ssh_collector.get_memory_utilization()

    # Process count (always via SSH)
    process_result = None
    if vm_config.metric_sources.process_count == MetricSource.SSH:
        try:
            ssh = SSHAdapter(vm_config)
            ssh_collector = SSHMetricCollector(vm_config, ssh)
            ps_output = ssh_collector.get_processes()
            session_users = ssh_collector.get_active_sessions()

            process_result = detect_processes(
                ps_output, session_users, vm_config.process_monitoring
            )
        except Exception as e:
            logger.warning(f"Process detection failed for {vm_config.name}: {e}")

    return MetricSnapshot(
        gpu_utilization=gpu,
        cpu_utilization=cpu,
        memory_utilization=memory,
        active_process_count=process_result.active_count if process_result else 0,
        active_processes=[
            {"user": p.user, "pid": str(p.pid), "cmd": p.full_command[:100]}
            for p in (process_result.active_processes if process_result else [])
        ],
        active_sessions=process_result.session_count if process_result else 0,
        session_users=process_result.active_sessions if process_result else [],
    )


def _evaluate_idle(metrics: MetricSnapshot, vm_config: ResolvedVMConfig) -> bool:
    """Determine if VM is idle based on configured metric and threshold."""
    threshold = vm_config.idle_threshold_below
    metric = vm_config.idle_metric

    if metric == IdleMetric.GPU_UTILIZATION:
        if metrics.gpu_utilization is None:
            return False  # Can't determine — assume active
        return metrics.gpu_utilization < threshold

    elif metric == IdleMetric.CPU_UTILIZATION:
        if metrics.cpu_utilization is None:
            return False
        return metrics.cpu_utilization < threshold

    elif metric == IdleMetric.MEMORY_UTILIZATION:
        if metrics.memory_utilization is None:
            return False
        return metrics.memory_utilization < threshold

    elif metric == IdleMetric.PROCESS_COUNT:
        return metrics.active_process_count == 0 and metrics.active_sessions == 0

    elif metric == IdleMetric.COMBINED:
        # ALL must be idle for combined mode
        gpu_idle = (metrics.gpu_utilization or 0) < threshold
        cpu_idle = (metrics.cpu_utilization or 0) < threshold
        process_idle = metrics.active_process_count == 0 and metrics.active_sessions == 0
        return gpu_idle and cpu_idle and process_idle

    return False


def _get_vm_adapter(vm_config: ResolvedVMConfig) -> VMAdapter:
    """Create the appropriate VM adapter based on cloud provider."""
    if vm_config.cloud == CloudProvider.GCP:
        from vm_power_manager.adapters.gcp import GCPAdapter
        return GCPAdapter(vm_config)
    elif vm_config.cloud == CloudProvider.SSH:
        from vm_power_manager.adapters.ssh import SSHAdapter
        return SSHAdapter(vm_config)
    else:
        raise ValueError(f"Unsupported cloud provider: {vm_config.cloud}")
