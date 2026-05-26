"""Slack Block Kit message builders for all notification types."""

from __future__ import annotations

from datetime import datetime, timezone

from vm_power_manager.models import MetricSnapshot, ResolvedVMConfig, VMState


class MessageBuilder:
    """Builds Slack Block Kit JSON for all message types."""

    @staticmethod
    def idle_warning(
        vm_config: ResolvedVMConfig,
        metrics: MetricSnapshot,
        state: VMState,
    ) -> dict:
        """Warning message: VM will shut down in N minutes."""
        mentions = " ".join(vm_config.notify_users)
        gpu_str = f"{metrics.gpu_utilization:.0f}%" if metrics.gpu_utilization is not None else "N/A"
        cpu_str = f"{metrics.cpu_utilization:.0f}%" if metrics.cpu_utilization is not None else "N/A"
        mem_str = f"{metrics.memory_utilization:.0f}%" if metrics.memory_utilization is not None else "N/A"

        process_info = ""
        if metrics.active_process_count == 0:
            process_info = "\n_No application processes detected._"
        else:
            procs = "\n".join(
                f"  • `{p.get('user', '?')}`: `{p.get('cmd', '?')[:60]}`"
                for p in metrics.active_processes[:5]
            )
            process_info = f"\n*Active processes ({metrics.active_process_count}):*\n{procs}"

        return {
            "channel": vm_config.channel,
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"⚠️ VM Shutting Down in {vm_config.warning_minutes} min",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*VM Name:*\n{vm_config.name}"},
                        {"type": "mrkdwn", "text": f"*Cloud:*\n{vm_config.cloud.value.upper()}"},
                        {"type": "mrkdwn", "text": f"*Zone:*\n{vm_config.zone or 'N/A'}"},
                        {"type": "mrkdwn", "text": f"*GPU Type:*\n{vm_config.gpu_type or 'N/A'}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Metrics (idle for {state.idle_minutes} min):*\n"
                            f"  GPU: `{gpu_str}`  |  CPU: `{cpu_str}`  |  RAM: `{mem_str}`\n"
                            f"  Processes: `{metrics.active_process_count}`  |  "
                            f"Sessions: `{metrics.active_sessions}`"
                            f"{process_info}"
                        ),
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"cc: {mentions}"},
                    ],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Keep Running"},
                            "style": "primary",
                            "action_id": "vm_keep_running",
                            "value": vm_config.name,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Stop Now"},
                            "style": "danger",
                            "action_id": "vm_stop_now",
                            "value": vm_config.name,
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def vm_stopped(
        vm_config: ResolvedVMConfig,
        reason: str = "auto",
        stopped_by: str | None = None,
        metrics: MetricSnapshot | None = None,
        state: VMState | None = None,
    ) -> dict:
        """Notification: VM has been stopped."""
        mentions = " ".join(vm_config.notify_users)
        reason_text = {
            "auto": "Auto-stopped (idle timeout)",
            "manual": f"Manually stopped by {stopped_by or 'user'}",
            "slash_command": f"Stopped via /vm stop by {stopped_by or 'user'}",
        }.get(reason, reason)

        uptime = ""
        if state and state.session_started:
            delta = datetime.now(timezone.utc) - state.session_started
            hours = int(delta.total_seconds() / 3600)
            minutes = int((delta.total_seconds() % 3600) / 60)
            uptime = f"\n*Session uptime:* {hours}h {minutes}m"

        return {
            "channel": vm_config.channel,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🔴 VM Stopped: {vm_config.name}"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Reason:* {reason_text}{uptime}",
                    },
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"cc: {mentions}"}],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Start VM"},
                            "style": "primary",
                            "action_id": "vm_start",
                            "value": vm_config.name,
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def vm_started(
        vm_config: ResolvedVMConfig,
        started_by: str = "system",
        ip: str | None = None,
        hook_result: dict | None = None,
    ) -> dict:
        """Notification: VM has been started."""
        mentions = " ".join(vm_config.notify_users)
        ip_text = f"\n*External IP:* `{ip}`" if ip else ""

        hook_text = ""
        if hook_result and not hook_result.get("all_success", True):
            failures = hook_result.get("failed", [])
            if failures:
                hook_text = "\n\n:warning: *Some post-start hooks failed:*\n" + "\n".join(
                    f"  • `{f.get('cmd', '?')[:50]}` — {f.get('error', 'unknown')[:50]}"
                    for f in failures[:3]
                )

        return {
            "channel": vm_config.channel,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🟢 VM Started: {vm_config.name}"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Started by:* {started_by}\n"
                            f"*GPU:* {vm_config.gpu_type or 'N/A'}"
                            f"{ip_text}{hook_text}"
                        ),
                    },
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"cc: {mentions}"}],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Stop VM"},
                            "style": "danger",
                            "action_id": "vm_stop_now",
                            "value": vm_config.name,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Status"},
                            "action_id": "vm_status",
                            "value": vm_config.name,
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def shutdown_cancelled(vm_config: ResolvedVMConfig, cancelled_by: str) -> dict:
        """Notification: Shutdown was cancelled."""
        return {
            "channel": vm_config.channel,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":white_check_mark: *Shutdown Cancelled* — `{vm_config.name}`\n"
                            f"Cancelled by {cancelled_by}. VM will keep running."
                        ),
                    },
                },
            ],
        }

    @staticmethod
    def status_response(vm_statuses: list[dict]) -> dict:
        """Status overview of all VMs (response to /vm status)."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "VM Status Overview"},
            },
            {"type": "divider"},
        ]

        for vm in vm_statuses:
            status_emoji = ":large_green_circle:" if vm.get("running") else ":red_circle:"
            status_text = "Running" if vm.get("running") else "Stopped"

            gpu = _fmt_pct(vm.get("gpu"))
            cpu = _fmt_pct(vm.get("cpu"))
            mem = _fmt_pct(vm.get("memory"))
            procs = vm.get("processes", 0)
            ip = vm.get("ip") or "—"
            error = vm.get("error")

            if error:
                detail = f"_Error: {error[:80]}_"
            else:
                detail = (
                    f"  GPU: `{gpu}`  |  CPU: `{cpu}`  |  MEM: `{mem}`  |  Procs: `{procs}`\n"
                    f"  IP: `{ip}`"
                )

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{status_emoji}  *{vm['name']}*  — _{status_text}_\n{detail}",
                },
            })

        if not vm_statuses:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No VMs configured._"},
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":clock1: Updated at <!date^{int(datetime.now(timezone.utc).timestamp())}^{{date_short_pretty}} {{time}}|just now>"}],
        })

        return {"blocks": blocks}

    @staticmethod
    def daily_summary(vm_summaries: list[dict]) -> dict:
        """Daily summary of all VMs."""
        rows = []
        for vm in vm_summaries:
            status = ":large_green_circle: Running" if vm.get("running") else ":red_circle: Stopped"
            idle_flag = " :zzz:" if vm.get("idle") else ""
            row = (
                f"• *{vm['name']}* — {status}{idle_flag}\n"
                f"  Uptime: {vm.get('uptime', 'N/A')} | "
                f"GPU avg: {vm.get('gpu_avg', 'N/A')}%"
            )
            rows.append(row)

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "📊 Daily VM Summary"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n\n".join(rows) or "_No VMs._"},
                },
            ]
        }


def _fmt_pct(value) -> str:
    """Format a percentage value for display."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"
