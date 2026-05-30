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
        """Status overview of all VMs — detailed multi-line format."""
        gpu_vms = [v for v in vm_statuses if v.get("gpu_type")]
        other_vms = [v for v in vm_statuses if not v.get("gpu_type")]

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "VM Status Overview"},
            },
            {"type": "divider"},
        ]

        if gpu_vms:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": ":zap: *GPU VMs*"}],
            })
            for vm in gpu_vms:
                blocks.extend(_build_status_vm_block(vm, is_gpu=True))
                blocks.append({"type": "divider"})

        if other_vms:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": ":desktop_computer: *Standard VMs*"}],
            })
            for vm in other_vms:
                blocks.extend(_build_status_vm_block(vm, is_gpu=False))
                blocks.append({"type": "divider"})

        if not vm_statuses:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No VMs configured._"},
            })

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":clock1: Updated at <!date^{int(datetime.now(timezone.utc).timestamp())}^{{date_short_pretty}} {{time}}|just now>"}],
        })

        return {"blocks": blocks}

    @staticmethod
    def daily_summary(vm_summaries: list[dict]) -> dict:
        """Daily full report — all VMs with detailed metrics, clean format."""
        now = datetime.now(timezone.utc)
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":bar_chart:  Daily VM Report"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":speech_balloon: _Daily overview of all managed VMs. "
                        "If you're using a VM listed here, please review and stop it "
                        "if not actively in use — to save costs._"
                    ),
                },
            },
            {"type": "divider"},
        ]

        gpu_vms = [v for v in vm_summaries if v.get("gpu_type")]
        other_vms = [v for v in vm_summaries if not v.get("gpu_type")]

        if gpu_vms:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": ":zap: *GPU VMs*"}],
            })
            for vm in gpu_vms:
                blocks.extend(_build_detailed_vm_block(vm, is_gpu=True))
                blocks.append({"type": "divider"})

        if other_vms:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": ":desktop_computer: *Standard VMs*"}],
            })
            for vm in other_vms:
                blocks.extend(_build_detailed_vm_block(vm, is_gpu=False))
                blocks.append({"type": "divider"})

        if not vm_summaries:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No VMs configured._"}})

        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": (
                    f":calendar: <!date^{int(now.timestamp())}^{{date_long_pretty}} {{time}}|{now.strftime('%b %d, %Y')}>\n"
                    ":next_track_button: GPU status check in 12 hours\n"
                    ":bulb: `/vm status` for real-time metrics"
                )},
            ],
        })

        return {"blocks": blocks}

    @staticmethod
    def gpu_status_report(gpu_vm_data: list[dict]) -> dict:
        """Consolidated GPU VMs status report — sent every 12h, only running GPU VMs."""
        now = datetime.now(timezone.utc)
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":bell:  GPU VMs Status"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":speech_balloon: _This is a periodic reminder. GPU VMs are expensive "
                        "when idle. If you are not using this VM, please stop it. "
                        "Ignore if actively working._"
                    ),
                },
            },
            {"type": "divider"},
        ]

        for vm in gpu_vm_data:
            blocks.extend(_build_detailed_vm_block(vm, is_gpu=True))
            blocks.append({"type": "divider"})

        if not gpu_vm_data:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No GPU VMs currently running._"}})

        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": (
                    f":calendar: <!date^{int(now.timestamp())}^{{date_long_pretty}} {{time}}|{now.strftime('%b %d, %Y')}>\n"
                    ":next_track_button: Full daily report in 12 hours\n"
                    ":bulb: `/vm status` for real-time metrics"
                )},
            ],
        })

        return {"blocks": blocks}

    @staticmethod
    def gpu_running_alert(vm_config, metrics: dict, uptime: str) -> dict:
        """Legacy single-VM alert — kept for backward compatibility."""
        gpu = _fmt_pct(metrics.get("gpu_utilization"))
        gpu_mem = _fmt_mem_mb(metrics.get("gpu_memory_used_mb"), metrics.get("gpu_memory_total_mb"))
        cpu = _fmt_pct(metrics.get("cpu_utilization"))
        cores = metrics.get("cpu_cores")
        cpu_str = f"{cpu} ({cores} cores)" if cores else cpu
        mem = _fmt_mem(metrics.get("memory_utilization"), metrics.get("memory_used_mb"), metrics.get("memory_total_mb"))
        disk = _fmt_disk(metrics.get("disk_utilization"), metrics.get("disk_used_gb"), metrics.get("disk_total_gb"))
        procs = metrics.get("active_process_count", 0)
        gpu_type = vm_config.gpu_type or "—"

        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":rotating_light: *GPU VM Running:* `{vm_config.name}`\n"
                            f"Running for: *{uptime}*\n"
                            f"GPU: `{gpu_type}` | Util: `{gpu}` | VRAM: `{gpu_mem}`\n"
                            f"CPU: `{cpu_str}` | RAM: `{mem}`\n"
                            f"Disk: `{disk}` | Procs: `{procs}` active"
                        ),
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"cc: {' '.join(vm_config.notify_users)}"},
                        {"type": "mrkdwn", "text": "_Use `/vm stop " + vm_config.name + "` to shut down._"},
                    ],
                },
            ]
        }


    @staticmethod
    def gpu_stop_warning(vm_config, gpu_check: dict) -> dict:
        """Warning before stopping: GPU may not be available on restart."""
        gpu_type = gpu_check.get("gpu_type", "unknown")
        zone = gpu_check.get("zone", "unknown")
        has_reservation = gpu_check.get("has_reservation", False)

        if has_reservation:
            risk_text = ":white_check_mark: *Low risk* — GPU reservation detected in this zone."
        else:
            risk_text = (
                ":warning: *High risk* — No GPU reservation found.\n"
                f"GPU type `{gpu_type}` may not be available in `{zone}` when you try to restart.\n"
                "You may need to migrate the VM to a different zone."
            )

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "GPU Availability Warning"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*VM:* `{vm_config.name}`\n"
                            f"*GPU:* `{gpu_type}`\n"
                            f"*Zone:* `{zone}`\n\n"
                            f"{risk_text}\n\n"
                            "_Stopping this VM releases the GPU back to the shared pool. "
                            "If the zone runs out of GPU capacity, you won't be able to restart "
                            "without migrating to another zone._"
                        ),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Stop Anyway"},
                            "style": "danger",
                            "action_id": "vm_gpu_stop_confirm",
                            "value": vm_config.name,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Keep Running"},
                            "style": "primary",
                            "action_id": "vm_gpu_stop_cancel",
                            "value": vm_config.name,
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                ":bulb: *Tip:* Create a GPU reservation to guarantee capacity: "
                                "`gcloud compute reservations create ...` "
                                "— see docs/GPU_AVAILABILITY.md"
                            ),
                        },
                    ],
                },
            ]
        }

    @staticmethod
    def gpu_start_result(vm_config, start_result: dict) -> dict:
        """Result of a start attempt with GPU protection (may include zone migration info)."""
        success = start_result.get("success", False)
        migrated = start_result.get("migrated", False)
        zone = start_result.get("zone", "unknown")
        original_zone = start_result.get("original_zone", zone)
        attempts = start_result.get("attempts", 0)
        error = start_result.get("error")

        if success and not migrated:
            return {
                "text": f":large_green_circle: `{vm_config.name}` started in `{zone}` (attempt {attempts})."
            }

        if success and migrated:
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f":large_green_circle: *VM Started (Zone Changed)*\n\n"
                                f"*VM:* `{vm_config.name}`\n"
                                f"*Original zone:* `{original_zone}` (GPU unavailable)\n"
                                f"*New zone:* `{zone}`\n"
                                f"*Attempts:* {attempts}\n\n"
                                f":warning: The VM was migrated to `{zone}` because GPU capacity "
                                f"was exhausted in `{original_zone}`."
                            ),
                        },
                    },
                ]
            }

        # Failed
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":x: *Failed to Start VM*\n\n"
                            f"*VM:* `{vm_config.name}`\n"
                            f"*Zone:* `{original_zone}`\n"
                            f"*Attempts:* {attempts}\n"
                            f"*Error:* {error or 'GPU unavailable in all configured zones'}\n\n"
                            "*Solutions:*\n"
                            "1. Try again later (GPU capacity fluctuates)\n"
                            "2. Add `fallback_zones` + `auto_migrate: true` in config\n"
                            "3. Create a GPU reservation: `gcloud compute reservations create ...`\n"
                            "4. Manually migrate: `/vm migrate <name> <zone>`"
                        ),
                    },
                },
            ]
        }


def _build_gpu_vm_status_block(vm: dict) -> dict:
    """Build a rich status block for a GPU-enabled VM (legacy, kept for compatibility)."""
    status_emoji = ":large_green_circle:" if vm.get("running") else ":red_circle:"
    status_text = "Running" if vm.get("running") else "Stopped"
    error = vm.get("error")

    if error:
        detail = f"_Error: {error[:80]}_"
    else:
        gpu_type = vm.get("gpu_type", "—")
        gpu = _fmt_pct(vm.get("gpu"))
        gpu_mem = _fmt_mem_mb(vm.get("gpu_memory_used_mb"), vm.get("gpu_memory_total_mb"))
        cpu = _fmt_pct(vm.get("cpu"))
        cores = vm.get("cpu_cores")
        cpu_str = f"{cpu} ({cores} cores)" if cores else cpu
        mem = _fmt_mem(vm.get("memory"), vm.get("memory_used_mb"), vm.get("memory_total_mb"))
        disk = _fmt_disk(vm.get("disk"), vm.get("disk_used_gb"), vm.get("disk_total_gb"))
        procs = vm.get("processes", 0)
        ip = vm.get("ip") or "—"
        uptime = vm.get("uptime", "—")

        detail = (
            f"  GPU: `{gpu_type}` | Util: `{gpu}` | VRAM: `{gpu_mem}`\n"
            f"  CPU: `{cpu_str}` | RAM: `{mem}`\n"
            f"  Disk: `{disk}` | Procs: `{procs}` | Uptime: `{uptime}`\n"
            f"  IP: `{ip}`"
        )

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"{status_emoji}  *{vm['name']}*  — _{status_text}_\n{detail}"},
    }


def _build_standard_vm_status_block(vm: dict) -> dict:
    """Build a compact status block for a non-GPU VM (legacy, kept for compatibility)."""
    status_emoji = ":large_green_circle:" if vm.get("running") else ":red_circle:"
    status_text = "Running" if vm.get("running") else "Stopped"
    error = vm.get("error")

    if error:
        detail = f"_Error: {error[:80]}_"
    else:
        cpu = _fmt_pct(vm.get("cpu"))
        cores = vm.get("cpu_cores")
        cpu_str = f"{cpu} ({cores} cores)" if cores else cpu
        mem = _fmt_mem(vm.get("memory"), vm.get("memory_used_mb"), vm.get("memory_total_mb"))
        disk = _fmt_disk(vm.get("disk"), vm.get("disk_used_gb"), vm.get("disk_total_gb"))
        ip = vm.get("ip") or "—"
        detail = f"  CPU: `{cpu_str}` | RAM: `{mem}` | Disk: `{disk}` | IP: `{ip}`"

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"{status_emoji}  *{vm['name']}*  — _{status_text}_\n{detail}"},
    }


def _build_status_vm_block(vm: dict, is_gpu: bool = True) -> list[dict]:
    """Build a detailed multi-line status block for /vm status command (includes IP)."""
    status_emoji = ":large_green_circle:" if vm.get("running") else ":red_circle:"
    status_text = "Running" if vm.get("running") else "Stopped"
    error = vm.get("error")

    if error:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": f"{status_emoji}  *{vm['name']}*\n_Error: {error[:80]}_"}}]

    running_since = vm.get("running_since", "—")
    uptime = vm.get("uptime", "—")
    procs = vm.get("processes", 0)
    ip = vm.get("ip") or "—"

    if vm.get("running") and running_since != "—":
        status_line = f"*Status:*           {status_text}\n*Running Since:* {running_since}  _({uptime})_"
    elif vm.get("running"):
        status_line = f"*Status:*           {status_text}\n*Uptime:*          {uptime}"
    else:
        status_line = f"*Status:*           {status_text}"

    lines = [f"{status_emoji}  *{vm['name']}*\n\n{status_line}\n"]

    if is_gpu:
        gpu_type = vm.get("gpu_type", "—")
        gpu = _fmt_pct(vm.get("gpu"))
        gpu_mem = _fmt_mem_mb(vm.get("gpu_memory_used_mb"), vm.get("gpu_memory_total_mb"))
        lines.append(f"*GPU Model:*      `{gpu_type}`")
        lines.append(f"*GPU Util:*         `{gpu}`")
        lines.append(f"*GPU Memory:*   `{gpu_mem}`")
        lines.append("")

    cpu = _fmt_pct(vm.get("cpu"))
    cores = vm.get("cpu_cores")
    cpu_str = f"{cpu}  ({cores} cores)" if cores else cpu
    mem = _fmt_mem(vm.get("memory"), vm.get("memory_used_mb"), vm.get("memory_total_mb"))
    disk = _fmt_disk(vm.get("disk"), vm.get("disk_used_gb"), vm.get("disk_total_gb"))

    lines.append(f"*CPU:*               `{cpu_str}`")
    lines.append(f"*RAM:*              `{mem}`")
    lines.append(f"*Disk:*              `{disk}`")
    lines.append(f"*Processes:*      `{procs} active`")
    lines.append(f"*IP:*                 `{ip}`")

    return [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]


def _build_detailed_vm_block(vm: dict, is_gpu: bool = True) -> list[dict]:
    """Build a detailed multi-line block for a VM (used in daily digest and GPU status report)."""
    status_emoji = ":large_green_circle:" if vm.get("running") else ":red_circle:"
    status_text = "Running" if vm.get("running") else "Stopped"
    error = vm.get("error")

    if error:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": f"{status_emoji}  *{vm['name']}*\n_Error: {error[:80]}_"}}]

    running_since = vm.get("running_since", "—")
    uptime = vm.get("uptime", "—")
    procs = vm.get("processes", 0)
    mentions = vm.get("notify_users", "")

    if vm.get("running") and running_since != "—":
        status_line = f"*Status:*        {status_text}\n*Running Since:*  {running_since}  _({uptime})_"
    elif vm.get("running"):
        status_line = f"*Status:*        {status_text}\n*Uptime:*         {uptime}"
    else:
        status_line = f"*Status:*        {status_text}"

    lines = [f"{status_emoji}  *{vm['name']}*\n\n{status_line}\n"]

    if is_gpu:
        gpu_type = vm.get("gpu_type", "—")
        gpu = _fmt_pct(vm.get("gpu"))
        gpu_mem = _fmt_mem_mb(vm.get("gpu_memory_used_mb"), vm.get("gpu_memory_total_mb"))
        lines.append(f"*GPU Model:*     `{gpu_type}`")
        lines.append(f"*GPU Util:*        `{gpu}`")
        lines.append(f"*GPU Memory:*  `{gpu_mem}`")
        lines.append("")

    cpu = _fmt_pct(vm.get("cpu"))
    cores = vm.get("cpu_cores")
    cpu_str = f"{cpu}  ({cores} cores)" if cores else cpu
    mem = _fmt_mem(vm.get("memory"), vm.get("memory_used_mb"), vm.get("memory_total_mb"))
    disk = _fmt_disk(vm.get("disk"), vm.get("disk_used_gb"), vm.get("disk_total_gb"))

    lines.append(f"*CPU:*              `{cpu_str}`")
    lines.append(f"*RAM:*             `{mem}`")
    lines.append(f"*Disk:*             `{disk}`")
    lines.append(f"*Processes:*     `{procs} active`")

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
    ]

    context_elements = []
    if vm.get("running") and vm.get("name"):
        context_elements.append(
            {"type": "mrkdwn", "text": f":octagonal_sign: To stop this VM: `/vm stop {vm['name']}`"}
        )
    if mentions:
        context_elements.append({"type": "mrkdwn", "text": f"cc: {mentions}"})

    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})

    return blocks


def _fmt_pct(value) -> str:
    """Format a percentage value for display."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_mem(pct, used_mb, total_mb) -> str:
    """Format memory: '4.0% (3.4 / 85.0 GB)' or just percentage."""
    pct_str = _fmt_pct(pct)
    if used_mb is not None and total_mb is not None:
        used_gb = used_mb / 1024
        total_gb = total_mb / 1024
        return f"{pct_str} ({used_gb:.1f}/{total_gb:.1f} GB)"
    return pct_str


def _fmt_mem_mb(used_mb, total_mb) -> str:
    """Format GPU VRAM: '1.2 / 80.0 GB' or '—'."""
    if used_mb is not None and total_mb is not None:
        used_gb = used_mb / 1024
        total_gb = total_mb / 1024
        return f"{used_gb:.1f}/{total_gb:.1f} GB"
    return "—"


def _fmt_disk(pct, used_gb, total_gb) -> str:
    """Format disk: '77% (1155 / 1500 GB)' or just percentage."""
    pct_str = _fmt_pct(pct)
    if used_gb is not None and total_gb is not None:
        return f"{pct_str} ({used_gb:.0f}/{total_gb:.0f} GB)"
    return pct_str
