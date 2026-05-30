"""Public API entry points — called by Cloud Function wrappers."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import requests as http_requests

from vm_power_manager.config import get_slack_signing_secret, get_slack_token, load_config
from vm_power_manager.manifest import check_manifest
from vm_power_manager.models import Config, MetricSnapshot, ResolvedVMConfig, VMState
from vm_power_manager.monitor import check_all_vms
from vm_power_manager.slack.commands import handle_command
from vm_power_manager.slack.interactions import handle_interaction
from vm_power_manager.slack.messages import MessageBuilder
from vm_power_manager.state import StateBackend, create_state_backend

logger = logging.getLogger(__name__)


def check_idle(config: str | Path | Config) -> dict:
    """
    Main monitoring entry point. Called by Cloud Scheduler every N minutes.

    Args:
        config: Path to config.yaml or a pre-loaded Config object.

    Returns:
        Summary of actions taken: {"vms_checked": N, "actions": [...]}
    """
    if isinstance(config, (str, Path)):
        config = load_config(config)

    # Runtime manifest check (version compatibility)
    manifest_result = _check_manifest_gate(config)
    if manifest_result is not None:
        return manifest_result

    state_backend = create_state_backend(config)
    actions = check_all_vms(config, state_backend)

    _send_notifications(actions, config, state_backend)

    return {
        "vms_checked": len(config.vms),
        "actions": actions,
    }


def handle_slack(request, config: str | Path | Config) -> dict:
    """
    Slack request handler. Called by HTTP Cloud Function.

    Handles:
    - Slash commands (/vm ...)
    - Interactive components (button clicks)

    Args:
        request: HTTP request object (Flask-like with .form, .json, .headers, .get_data)
        config: Path to config.yaml or a pre-loaded Config object.

    Returns:
        Slack response payload (dict).
    """
    if isinstance(config, (str, Path)):
        config = load_config(config)

    # Runtime manifest check (version compatibility)
    manifest_status = check_manifest(
        config.app.manifest.model_dump() if config.app.manifest else {},
        deployment_id=config.app.deployment_id,
    )
    if not manifest_status.allow:
        logger.warning(f"vm_power_manager: suppressed by manifest ({manifest_status.reason})")
        return {
            "response_type": "ephemeral",
            "text": ":warning: VM Power Manager is temporarily unavailable. Please try again later.",
        }

    # Verify Slack signature
    if not _verify_slack_signature(request, config):
        logger.error("Slack signature verification failed")
        return {"response_type": "ephemeral", "text": ":warning: Signature verification failed. Check SLACK_SIGNING_SECRET."}

    content_type = request.headers.get("Content-Type", "")

    # Interactive component (button click)
    if "application/x-www-form-urlencoded" in content_type:
        form_data = request.form if hasattr(request, "form") else parse_qs(request.get_data(as_text=True))

        # Check if it's an interaction payload
        payload_str = form_data.get("payload")
        if payload_str:
            if isinstance(payload_str, list):
                payload_str = payload_str[0]
            payload = json.loads(payload_str)
            state_backend = create_state_backend(config)
            return handle_interaction(payload, config, state_backend)

        # Otherwise it's a slash command
        command_text = _get_form_value(form_data, "text", "")
        user_id = _get_form_value(form_data, "user_id", "")
        user_name = _get_form_value(form_data, "user_name", "")
        channel_id = _get_form_value(form_data, "channel_id", "")
        response_url = _get_form_value(form_data, "response_url", "")

        # Fast commands respond immediately
        parts = command_text.strip().split()
        action = parts[0].lower() if parts else ""
        fast_commands = {"help", "config", "extend", "pause", "resume", ""}

        if action in fast_commands:
            state_backend = create_state_backend(config)
            return handle_command(
                command_text=command_text,
                user_id=user_id,
                user_name=user_name,
                channel_id=channel_id,
                config=config,
                state_backend=state_backend,
            )

        # Slow commands (status, start, stop) — acknowledge and process async
        if response_url:
            thread = threading.Thread(
                target=_handle_async_command,
                args=(command_text, user_id, user_name, channel_id, config, response_url),
                daemon=True,
            )
            thread.start()
            return {"response_type": "ephemeral", "text": f":hourglass_flowing_sand: Processing `/vm {command_text}`..."}

        # Fallback: no response_url, try inline
        state_backend = create_state_backend(config)
        return handle_command(
            command_text=command_text,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            config=config,
            state_backend=state_backend,
        )

    # JSON payload (rare, but handle it)
    if "application/json" in content_type:
        data = request.get_json() if hasattr(request, "get_json") else json.loads(request.get_data(as_text=True))

        # Slack URL verification challenge
        if data.get("type") == "url_verification":
            return {"challenge": data.get("challenge")}

        return {"text": "Unsupported JSON payload."}

    return {"text": "Unsupported content type."}


def _check_manifest_gate(config: Config) -> dict | None:
    """Check runtime manifest. Returns an error dict if blocked, None if allowed."""
    manifest_status = check_manifest(
        config.app.manifest.model_dump() if config.app.manifest else {},
        deployment_id=config.app.deployment_id,
    )
    if not manifest_status.allow:
        logger.warning(f"vm_power_manager: suppressed by manifest ({manifest_status.reason})")
        return {
            "status": "suppressed",
            "reason": manifest_status.reason,
            "vms_checked": 0,
            "actions": [],
        }
    return None


def _get_form_value(form_data: dict, key: str, default: str = "") -> str:
    """Extract a value from form data, handling list vs string."""
    value = form_data.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value or default


def _handle_async_command(
    command_text: str,
    user_id: str,
    user_name: str,
    channel_id: str,
    config: Config,
    response_url: str,
):
    """Process a slow command in background and POST result to response_url."""
    try:
        # Post a visible header to the channel showing who ran the command
        _post_command_attribution(channel_id, user_name, command_text, config)

        state_backend = create_state_backend(config)
        result = handle_command(
            command_text=command_text,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            config=config,
            state_backend=state_backend,
        )

        payload = {
            "response_type": "in_channel" if "blocks" in result else "ephemeral",
            "replace_original": False,
        }
        payload.update(result)

        resp = http_requests.post(response_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Failed to send async response: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.exception(f"Async command handler failed: {e}")
        try:
            http_requests.post(
                response_url,
                json={"response_type": "ephemeral", "text": f":x: Error: {str(e)[:200]}"},
                timeout=5,
            )
        except Exception:
            pass


def _post_command_attribution(channel_id: str, user_name: str, command_text: str, config: Config):
    """Post a visible message to the channel showing who ran a /vm command."""
    try:
        from slack_sdk import WebClient

        token = get_slack_token(config)
        client = WebClient(token=token)
        client.chat_postMessage(
            channel=channel_id,
            text=f"@{user_name} ran `/vm {command_text}`",
            blocks=[
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f":computer: *@{user_name}* ran `/vm {command_text}`",
                        }
                    ],
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to post command attribution: {e}")


def _verify_slack_signature(request, config: Config) -> bool:
    """Verify that the request came from Slack using signing secret."""
    try:
        signing_secret = get_slack_signing_secret(config)
    except EnvironmentError:
        logger.warning("Slack signing secret not configured — skipping verification")
        return True

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    if not timestamp:
        logger.warning("No X-Slack-Request-Timestamp header")
        return False

    # Reject requests older than 5 minutes
    if abs(time.time() - int(timestamp)) > 300:
        logger.warning(f"Request timestamp too old: {timestamp}")
        return False

    body = request.get_data(as_text=True)
    sig_basestring = f"v0:{timestamp}:{body}"
    expected_sig = "v0=" + hmac.HMAC(
        signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()

    actual_sig = request.headers.get("X-Slack-Signature", "")
    if not hmac.compare_digest(expected_sig, actual_sig):
        logger.warning(f"Signature mismatch")
        return False

    return True


def send_daily_digest(config: str | Path | Config) -> dict:
    """
    Daily digest entry point. Called by Cloud Scheduler once per day.

    Collects live metrics for all VMs and posts a comprehensive summary to Slack.
    """
    if isinstance(config, (str, Path)):
        config = load_config(config)

    manifest_result = _check_manifest_gate(config)
    if manifest_result is not None:
        return manifest_result

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from slack_sdk import WebClient

    state_backend = create_state_backend(config)
    defaults = config.defaults
    now = datetime.now(timezone.utc)

    def _collect_vm_summary(vm_cfg):
        resolved = vm_cfg.get_effective_config(defaults)
        try:
            from vm_power_manager.monitor import _get_vm_adapter
            adapter = _get_vm_adapter(resolved)
            info = adapter.get_status()
            is_running = info.status == "RUNNING"

            state = state_backend.get(resolved.name)
            metrics = state.last_metrics if state else {}

            uptime = "—"
            running_since = "—"
            if state and state.session_started and is_running:
                delta = now - state.session_started
                days = int(delta.total_seconds() / 86400)
                hours = int((delta.total_seconds() % 86400) / 3600)
                minutes = int((delta.total_seconds() % 3600) / 60)
                if days > 0:
                    uptime = f"{days}d {hours}h"
                elif hours > 0:
                    uptime = f"{hours}h {minutes}m"
                else:
                    uptime = f"{minutes}m"
                running_since = state.session_started.strftime("%b %d, %I:%M %p")

            mentions = " ".join(resolved.notify_users) if resolved.notify_users else ""

            return {
                "name": resolved.name,
                "running": is_running,
                "gpu": metrics.get("gpu_utilization"),
                "gpu_memory_used_mb": metrics.get("gpu_memory_used_mb"),
                "gpu_memory_total_mb": metrics.get("gpu_memory_total_mb"),
                "cpu": metrics.get("cpu_utilization"),
                "cpu_cores": metrics.get("cpu_cores"),
                "memory": metrics.get("memory_utilization"),
                "memory_used_mb": metrics.get("memory_used_mb"),
                "memory_total_mb": metrics.get("memory_total_mb"),
                "disk": metrics.get("disk_utilization"),
                "disk_used_gb": metrics.get("disk_used_gb"),
                "disk_total_gb": metrics.get("disk_total_gb"),
                "processes": metrics.get("active_process_count", 0),
                "gpu_type": resolved.gpu_type,
                "uptime": uptime,
                "running_since": running_since,
                "notify_users": mentions,
            }
        except Exception as e:
            return {"name": resolved.name, "running": False, "error": str(e)[:100], "gpu_type": vm_cfg.gpu_type}

    summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_collect_vm_summary, vm): vm for vm in config.vms}
        for future in as_completed(futures, timeout=30):
            try:
                summaries.append(future.result())
            except Exception as e:
                vm = futures[future]
                summaries.append({"name": vm.name, "running": False, "gpu_type": vm.gpu_type})

    msg = MessageBuilder.daily_summary(summaries, report_config=config.reports.daily)

    try:
        token = get_slack_token(config)
        client = WebClient(token=token)
        channel = config.slack.default_channel
        _post_message(client, channel, msg)
    except Exception as e:
        logger.error(f"Failed to send daily digest: {e}")

    return {"status": "sent", "vms_reported": len(summaries)}


def send_gpu_status_report(config: str | Path | Config) -> dict:
    """Send a consolidated GPU VMs status report — only running GPU VMs."""
    if isinstance(config, (str, Path)):
        config = load_config(config)

    if not config.reports.gpu.enabled:
        return {"status": "skipped", "reason": "gpu_report_disabled"}

    manifest_result = _check_manifest_gate(config)
    if manifest_result is not None:
        return manifest_result

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from slack_sdk import WebClient

    state_backend = create_state_backend(config)
    defaults = config.defaults
    now = datetime.now(timezone.utc)

    def _collect_gpu_vm(vm_cfg):
        resolved = vm_cfg.get_effective_config(defaults)
        if not resolved.gpu_type:
            return None
        try:
            from vm_power_manager.monitor import _get_vm_adapter
            adapter = _get_vm_adapter(resolved)
            info = adapter.get_status()
            if info.status != "RUNNING":
                return None

            state = state_backend.get(resolved.name)
            metrics = state.last_metrics if state else {}

            uptime = "—"
            running_since = "—"
            if state and state.session_started:
                delta = now - state.session_started
                days = int(delta.total_seconds() / 86400)
                hours = int((delta.total_seconds() % 86400) / 3600)
                minutes = int((delta.total_seconds() % 3600) / 60)
                if days > 0:
                    uptime = f"{days}d {hours}h"
                elif hours > 0:
                    uptime = f"{hours}h {minutes}m"
                else:
                    uptime = f"{minutes}m"
                running_since = state.session_started.strftime("%b %d, %I:%M %p")

            mentions = " ".join(resolved.notify_users) if resolved.notify_users else ""

            return {
                "name": resolved.name,
                "running": True,
                "gpu": metrics.get("gpu_utilization"),
                "gpu_memory_used_mb": metrics.get("gpu_memory_used_mb"),
                "gpu_memory_total_mb": metrics.get("gpu_memory_total_mb"),
                "cpu": metrics.get("cpu_utilization"),
                "cpu_cores": metrics.get("cpu_cores"),
                "memory": metrics.get("memory_utilization"),
                "memory_used_mb": metrics.get("memory_used_mb"),
                "memory_total_mb": metrics.get("memory_total_mb"),
                "disk": metrics.get("disk_utilization"),
                "disk_used_gb": metrics.get("disk_used_gb"),
                "disk_total_gb": metrics.get("disk_total_gb"),
                "processes": metrics.get("active_process_count", 0),
                "gpu_type": resolved.gpu_type,
                "uptime": uptime,
                "running_since": running_since,
                "notify_users": mentions,
            }
        except Exception:
            return None

    gpu_summaries = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_collect_gpu_vm, vm): vm for vm in config.vms}
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    gpu_summaries.append(result)
            except Exception:
                pass

    if not gpu_summaries:
        return {"status": "skipped", "reason": "no_running_gpu_vms"}

    msg = MessageBuilder.gpu_status_report(gpu_summaries, report_config=config.reports.gpu)

    try:
        token = get_slack_token(config)
        client = WebClient(token=token)
        channel = config.slack.default_channel
        _post_message(client, channel, msg)
    except Exception as e:
        logger.error(f"Failed to send GPU status report: {e}")

    return {"status": "sent", "gpu_vms_reported": len(gpu_summaries)}


def _send_notifications(actions: list[dict], config: Config, state_backend: StateBackend):
    """Send Slack messages for actions that require notification."""
    try:
        from slack_sdk import WebClient

        token = get_slack_token(config)
        client = WebClient(token=token)
    except Exception as e:
        logger.error(f"Failed to create Slack client: {e}")
        return

    defaults = config.defaults

    for action_result in actions:
        vm_name = action_result.get("vm")
        action_type = action_result.get("action")

        vm_cfg = next((v for v in config.vms if v.name == vm_name), None)
        if not vm_cfg:
            continue

        resolved = vm_cfg.get_effective_config(defaults)
        channel = resolved.channel or config.slack.default_channel

        if action_type == "warning" and resolved.notifications.on_warning:
            state = state_backend.get(vm_name)
            metrics_data = action_result.get("metrics", {})
            metrics = MetricSnapshot.model_validate(metrics_data)
            msg = MessageBuilder.idle_warning(resolved, metrics, state or VMState(vm_name=vm_name))
            _post_message(client, channel, msg)

        elif action_type == "stop" and resolved.notifications.on_stop:
            msg = MessageBuilder.vm_stopped(resolved, reason="auto")
            _post_message(client, channel, msg)

        elif action_type == "gpu_running_alert":
            uptime = action_result.get("uptime", "—")
            metrics_data = action_result.get("metrics", {})
            msg = MessageBuilder.gpu_running_alert(resolved, metrics_data, uptime)
            _post_message(client, channel, msg)


def _post_message(client, channel: str, message: dict):
    """Post a Slack message with error handling."""
    try:
        client.chat_postMessage(
            channel=channel,
            blocks=message.get("blocks", []),
            text=message.get("text", "VM Power Manager notification"),
        )
    except Exception as e:
        logger.error(f"Failed to post Slack message to {channel}: {e}")
