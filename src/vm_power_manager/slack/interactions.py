"""Slack interactive component handler — button clicks from messages."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from vm_power_manager.models import CloudProvider, Config, ResolvedVMConfig
from vm_power_manager.slack.access_control import check_access, get_denied_message
from vm_power_manager.slack.messages import MessageBuilder
from vm_power_manager.state import StateBackend

logger = logging.getLogger(__name__)


def handle_interaction(
    payload: dict,
    config: Config,
    state_backend: StateBackend,
) -> dict | None:
    """
    Handle Slack interactive component (button click).

    Returns response payload or None.
    """
    actions = payload.get("actions", [])
    if not actions:
        return None

    action = actions[0]
    action_id = action.get("action_id")
    vm_name = action.get("value")
    user = payload.get("user", {})
    user_id = user.get("id", "")
    user_name = user.get("username", "")

    if not vm_name:
        return {"text": "Error: no VM name in action."}

    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM `{vm_name}` not found in config."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    if action_id == "vm_keep_running":
        return _handle_keep_running(vm_name, user_name, resolved, state_backend)
    elif action_id == "vm_stop_now":
        return _handle_stop_now(vm_name, user_name, resolved, state_backend)
    elif action_id == "vm_start":
        return _handle_start(vm_name, user_name, resolved, state_backend)
    elif action_id == "vm_status":
        return _handle_single_status(vm_name, resolved, state_backend)
    elif action_id == "vm_gpu_stop_confirm":
        return _handle_gpu_stop_confirm(vm_name, user_name, resolved, state_backend)
    elif action_id == "vm_gpu_stop_cancel":
        return {"text": f":white_check_mark: Stop cancelled. `{vm_name}` will keep running."}
    else:
        return {"text": f"Unknown action: `{action_id}`"}


def _handle_keep_running(
    vm_name: str,
    user_name: str,
    resolved: ResolvedVMConfig,
    state_backend: StateBackend,
) -> dict:
    """Cancel shutdown — user clicked 'Keep Running'."""
    state = state_backend.get_or_create(vm_name)
    state.warning_sent = False
    state.warning_sent_at = None
    state.idle_since = None
    state.idle_minutes = 0
    state.keep_running_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    state_backend.set(vm_name, state)

    return MessageBuilder.shutdown_cancelled(resolved, cancelled_by=f"@{user_name}")


def _handle_stop_now(
    vm_name: str,
    user_name: str,
    resolved: ResolvedVMConfig,
    state_backend: StateBackend,
) -> dict:
    """Stop VM immediately — user clicked 'Stop Now'."""
    adapter = _get_adapter(resolved)

    if not adapter.is_running():
        return {"text": f"`{vm_name}` is already stopped."}

    # Pre-stop hooks
    if resolved.pre_stop_commands:
        try:
            from vm_power_manager.adapters.ssh import SSHAdapter
            from vm_power_manager.lifecycle import run_pre_stop_hooks

            ssh = SSHAdapter(resolved)
            run_pre_stop_hooks(resolved, ssh)
        except Exception as e:
            logger.warning(f"Pre-stop hooks failed for {vm_name}: {e}")

    adapter.stop()

    state = state_backend.get_or_create(vm_name)
    state.idle_since = None
    state.idle_minutes = 0
    state.warning_sent = False
    state.warning_sent_at = None
    state_backend.set(vm_name, state)

    return MessageBuilder.vm_stopped(resolved, reason="manual", stopped_by=f"@{user_name}")


def _handle_start(
    vm_name: str,
    user_name: str,
    resolved: ResolvedVMConfig,
    state_backend: StateBackend,
) -> dict:
    """Start VM — user clicked 'Start VM'."""
    adapter = _get_adapter(resolved)

    if adapter.is_running():
        return {"text": f"`{vm_name}` is already running."}

    success = adapter.start()
    if not success:
        return {"text": f"Failed to start `{vm_name}`."}

    adapter.wait_until_running(timeout_seconds=90)

    hook_result = None
    if resolved.post_start_commands:
        try:
            from vm_power_manager.adapters.ssh import SSHAdapter
            from vm_power_manager.lifecycle import run_post_start_hooks

            ssh = SSHAdapter(resolved)
            result = run_post_start_hooks(resolved, ssh)
            hook_result = {"all_success": result.all_success, "failed": [
                {"cmd": r.command, "error": r.stderr[:50]} for r in result.failed
            ]}
        except Exception as e:
            hook_result = {"all_success": False, "failed": [{"cmd": "ssh", "error": str(e)}]}

    state = state_backend.get_or_create(vm_name)
    state.session_started = datetime.now(timezone.utc)
    state.idle_since = None
    state.idle_minutes = 0
    state.warning_sent = False
    state_backend.set(vm_name, state)

    info = adapter.get_status()
    return MessageBuilder.vm_started(
        resolved,
        started_by=f"@{user_name}",
        ip=info.external_ip,
        hook_result=hook_result,
    )


def _handle_gpu_stop_confirm(
    vm_name: str,
    user_name: str,
    resolved: ResolvedVMConfig,
    state_backend: StateBackend,
) -> dict:
    """User confirmed stop despite GPU availability warning."""
    adapter = _get_adapter(resolved)

    if not adapter.is_running():
        return {"text": f"`{vm_name}` is already stopped."}

    if resolved.pre_stop_commands:
        try:
            from vm_power_manager.adapters.ssh import SSHAdapter
            from vm_power_manager.lifecycle import run_pre_stop_hooks

            ssh = SSHAdapter(resolved)
            run_pre_stop_hooks(resolved, ssh)
        except Exception as e:
            logger.warning(f"Pre-stop hooks failed for {vm_name}: {e}")

    adapter.stop()

    state = state_backend.get_or_create(vm_name)
    state.idle_since = None
    state.idle_minutes = 0
    state.warning_sent = False
    state.warning_sent_at = None
    state_backend.set(vm_name, state)

    return MessageBuilder.vm_stopped(resolved, reason="manual", stopped_by=f"@{user_name}")


def _handle_single_status(
    vm_name: str,
    resolved: ResolvedVMConfig,
    state_backend: StateBackend,
) -> dict:
    """Get status of a single VM."""
    adapter = _get_adapter(resolved)
    info = adapter.get_status()
    state = state_backend.get(vm_name)
    metrics = state.last_metrics if state else {}

    return MessageBuilder.status_response([{
        "name": vm_name,
        "running": info.status == "RUNNING",
        "gpu": metrics.get("gpu_utilization"),
        "cpu": metrics.get("cpu_utilization"),
        "processes": metrics.get("active_process_count", 0),
        "ip": info.external_ip,
    }])


def _find_vm(vm_name: str, config: Config) -> ResolvedVMConfig | None:
    for vm_cfg in config.vms:
        if vm_cfg.name == vm_name:
            return vm_cfg.get_effective_config(config.defaults)
    return None


def _get_adapter(vm_config: ResolvedVMConfig):
    if vm_config.cloud == CloudProvider.GCP:
        from vm_power_manager.adapters.gcp import GCPAdapter
        return GCPAdapter(vm_config)
    elif vm_config.cloud == CloudProvider.SSH:
        from vm_power_manager.adapters.ssh import SSHAdapter
        return SSHAdapter(vm_config)
    else:
        raise ValueError(f"Unsupported cloud: {vm_config.cloud}")
