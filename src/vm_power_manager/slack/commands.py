"""Slack slash command handler — /vm start|stop|status|extend|pause|resume|config."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from vm_power_manager.models import CloudProvider, Config, ResolvedVMConfig
from vm_power_manager.slack.access_control import check_access, get_denied_message
from vm_power_manager.slack.messages import MessageBuilder
from vm_power_manager.state import StateBackend

logger = logging.getLogger(__name__)


def handle_command(
    command_text: str,
    user_id: str,
    user_name: str,
    channel_id: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """
    Parse and handle a /vm slash command.

    Returns Slack Block Kit response payload.
    """
    parts = command_text.strip().split()
    if not parts:
        return _help_response()

    action = parts[0].lower()
    args = parts[1:]

    if action == "status":
        return _handle_status(config, state_backend)
    elif action == "start":
        return _handle_start(args, user_id, user_name, config, state_backend)
    elif action == "stop":
        return _handle_stop(args, user_id, user_name, config, state_backend)
    elif action == "extend":
        return _handle_extend(args, user_id, user_name, config, state_backend)
    elif action == "pause":
        return _handle_pause(args, user_id, user_name, config, state_backend)
    elif action == "resume":
        return _handle_resume(args, user_id, user_name, config, state_backend)
    elif action == "config":
        return _handle_config(config)
    elif action == "help":
        return _help_response()
    else:
        return {"text": f"Unknown command: `{action}`. Try `/vm help`."}


def _handle_status(config: Config, state_backend: StateBackend) -> dict:
    """Get status of all VMs."""
    import concurrent.futures

    statuses = []
    defaults = config.defaults

    def _check_vm(vm_cfg):
        resolved = vm_cfg.get_effective_config(defaults)
        try:
            adapter = _get_adapter(resolved)
            info = adapter.get_status()
            state = state_backend.get(resolved.name)
            metrics = state.last_metrics if state else {}

            uptime = "—"
            if state and state.session_started and info.status == "RUNNING":
                delta = datetime.now(timezone.utc) - state.session_started
                hours = int(delta.total_seconds() / 3600)
                minutes = int((delta.total_seconds() % 3600) / 60)
                if hours > 0:
                    uptime = f"{hours}h {minutes}m"
                else:
                    uptime = f"{minutes}m"

            return {
                "name": resolved.name,
                "running": info.status == "RUNNING",
                "gpu": metrics.get("gpu_utilization"),
                "cpu": metrics.get("cpu_utilization"),
                "memory": metrics.get("memory_utilization"),
                "disk": metrics.get("disk_utilization"),
                "processes": metrics.get("active_process_count", 0),
                "ip": info.external_ip,
                "gpu_type": resolved.gpu_type,
                "uptime": uptime,
            }
        except Exception as e:
            return {"name": resolved.name, "running": False, "error": str(e)[:100], "gpu_type": vm_cfg.gpu_type}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_check_vm, vm): vm for vm in config.vms}
        for future in concurrent.futures.as_completed(futures, timeout=25):
            try:
                statuses.append(future.result())
            except Exception as e:
                vm = futures[future]
                statuses.append({"name": vm.name, "running": False, "error": str(e)[:100], "gpu_type": vm.gpu_type})

    return MessageBuilder.status_response(statuses)


def _handle_start(
    args: list[str],
    user_id: str,
    user_name: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Start a VM with GPU protection (retry + fallback zones)."""
    if not args:
        return {"text": "Usage: `/vm start <vm-name>`"}

    vm_name = args[0]
    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM not found: `{vm_name}`. Use `/vm status` to see available VMs."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    adapter = _get_adapter(resolved)

    if adapter.is_running():
        return {"text": f"`{vm_name}` is already running."}

    # Use GPU-protected start if available
    gpu_enabled = resolved.gpu_protection.enabled and resolved.gpu_type
    if gpu_enabled and hasattr(adapter, "start_with_gpu_protection"):
        start_result = adapter.start_with_gpu_protection()

        if not start_result["success"]:
            return MessageBuilder.gpu_start_result(resolved, start_result)

        # If migrated, update the zone in state for future reference
        if start_result.get("migrated"):
            state = state_backend.get_or_create(vm_name)
            state.last_metrics["_zone_migrated_to"] = start_result["zone"]
            state.last_metrics["_zone_migrated_from"] = start_result["original_zone"]
            state.session_started = datetime.now(timezone.utc)
            state.idle_since = None
            state.idle_minutes = 0
            state.warning_sent = False
            state_backend.set(vm_name, state)
            return MessageBuilder.gpu_start_result(resolved, start_result)
    else:
        success = adapter.start()
        if not success:
            return {"text": f"Failed to start `{vm_name}`. Check logs."}

    # Wait for VM and run post-start hooks
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

    # Update state
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


def _handle_stop(
    args: list[str],
    user_id: str,
    user_name: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Stop a VM with GPU availability warning if applicable."""
    if not args:
        return {"text": "Usage: `/vm stop <vm-name>`"}

    vm_name = args[0]
    force = "--force" in args

    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM not found: `{vm_name}`."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    adapter = _get_adapter(resolved)

    if not adapter.is_running():
        return {"text": f"`{vm_name}` is already stopped."}

    # GPU protection: warn before stop if GPU type is configured
    gpu_config = resolved.gpu_protection
    if (
        gpu_config.enabled
        and gpu_config.check_before_stop
        and resolved.gpu_type
        and not force
        and hasattr(adapter, "check_gpu_availability")
    ):
        gpu_check = adapter.check_gpu_availability()
        if not gpu_check.get("has_reservation"):
            return MessageBuilder.gpu_stop_warning(resolved, gpu_check)

    # Proceed with stop
    if resolved.pre_stop_commands:
        try:
            from vm_power_manager.adapters.ssh import SSHAdapter
            from vm_power_manager.lifecycle import run_pre_stop_hooks

            ssh = SSHAdapter(resolved)
            run_pre_stop_hooks(resolved, ssh)
        except Exception as e:
            logger.warning(f"Pre-stop hooks failed for {vm_name}: {e}")

    success = adapter.stop()
    if not success:
        return {"text": f"Failed to stop `{vm_name}`. Check logs."}

    # Reset state
    state = state_backend.get_or_create(vm_name)
    state.idle_since = None
    state.idle_minutes = 0
    state.warning_sent = False
    state.warning_sent_at = None
    state_backend.set(vm_name, state)

    return MessageBuilder.vm_stopped(resolved, reason="manual", stopped_by=f"@{user_name}")


def _handle_extend(
    args: list[str],
    user_id: str,
    user_name: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Extend VM keep-alive timer."""
    if len(args) < 2:
        return {"text": "Usage: `/vm extend <vm-name> <minutes>`"}

    vm_name = args[0]
    try:
        minutes = int(args[1])
    except ValueError:
        return {"text": "Minutes must be a number. Usage: `/vm extend <vm-name> <minutes>`"}

    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM not found: `{vm_name}`."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    state = state_backend.get_or_create(vm_name)
    state.keep_running_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    state.warning_sent = False
    state.warning_sent_at = None
    state_backend.set(vm_name, state)

    return {
        "text": f":clock3: `{vm_name}` will keep running for {minutes} more minutes. "
        f"(Extended by @{user_name})"
    }


def _handle_pause(
    args: list[str],
    user_id: str,
    user_name: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Pause monitoring for a VM."""
    if not args:
        return {"text": "Usage: `/vm pause <vm-name>`"}

    vm_name = args[0]
    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM not found: `{vm_name}`."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    state = state_backend.get_or_create(vm_name)
    state.paused = True
    state.paused_at = datetime.now(timezone.utc)
    state_backend.set(vm_name, state)

    return {"text": f":pause_button: Monitoring paused for `{vm_name}`. Use `/vm resume {vm_name}` to re-enable."}


def _handle_resume(
    args: list[str],
    user_id: str,
    user_name: str,
    config: Config,
    state_backend: StateBackend,
) -> dict:
    """Resume monitoring for a VM."""
    if not args:
        return {"text": "Usage: `/vm resume <vm-name>`"}

    vm_name = args[0]
    resolved = _find_vm(vm_name, config)
    if resolved is None:
        return {"text": f"VM not found: `{vm_name}`."}

    if not check_access(user_id, user_name, resolved):
        return get_denied_message(resolved)

    state = state_backend.get_or_create(vm_name)
    state.paused = False
    state.paused_at = None
    state.idle_since = None
    state.idle_minutes = 0
    state_backend.set(vm_name, state)

    return {"text": f":arrow_forward: Monitoring resumed for `{vm_name}`."}


def _handle_config(config: Config) -> dict:
    """Show current configuration summary."""
    vms_text = "\n".join(
        f"  • `{vm.name}` ({vm.cloud}) — "
        f"{'auto-stop ON' if vm.auto_stop_enabled is not False else 'auto-stop OFF'}"
        for vm in config.vms
    )

    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*VM Power Manager Config*\n"
                        f"Environment: `{config.app.environment}`\n"
                        f"Idle threshold: `{config.defaults.idle_threshold_below}%`\n"
                        f"Idle duration: `{config.defaults.idle_duration_minutes} min`\n"
                        f"Warning time: `{config.defaults.warning_minutes} min`\n\n"
                        f"*Managed VMs:*\n{vms_text}"
                    ),
                },
            }
        ]
    }


def _help_response() -> dict:
    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*VM Power Manager Commands:*\n\n"
                        "• `/vm status` — Show all VMs status\n"
                        "• `/vm start <name>` — Start a VM\n"
                        "• `/vm stop <name>` — Stop a VM\n"
                        "• `/vm extend <name> <minutes>` — Delay auto-stop\n"
                        "• `/vm pause <name>` — Pause monitoring\n"
                        "• `/vm resume <name>` — Resume monitoring\n"
                        "• `/vm config` — Show configuration\n"
                        "• `/vm help` — Show this message"
                    ),
                },
            }
        ]
    }


def _find_vm(vm_name: str, config: Config) -> ResolvedVMConfig | None:
    """Find a VM by name and return its resolved config."""
    for vm_cfg in config.vms:
        if vm_cfg.name == vm_name:
            return vm_cfg.get_effective_config(config.defaults)
    return None


def _get_adapter(vm_config: ResolvedVMConfig):
    """Create the appropriate adapter for a VM."""
    if vm_config.cloud == CloudProvider.GCP:
        from vm_power_manager.adapters.gcp import GCPAdapter
        return GCPAdapter(vm_config)
    elif vm_config.cloud == CloudProvider.SSH:
        from vm_power_manager.adapters.ssh import SSHAdapter
        return SSHAdapter(vm_config)
    else:
        raise ValueError(f"Unsupported cloud: {vm_config.cloud}")
