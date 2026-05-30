"""VM Power Manager — Cloud-agnostic VM lifecycle automation with Slack integration."""

from vm_power_manager.api import check_idle, handle_slack, send_daily_digest, send_gpu_status_report

__version__ = "1.5.0"
__all__ = ["check_idle", "handle_slack", "send_daily_digest", "send_gpu_status_report"]
