"""VM Power Manager — Cloud-agnostic VM lifecycle automation with Slack integration."""

from vm_power_manager.api import check_idle, handle_slack, send_daily_digest

__version__ = "1.3.1"
__all__ = ["check_idle", "handle_slack", "send_daily_digest"]
