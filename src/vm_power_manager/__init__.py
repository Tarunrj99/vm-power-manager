"""VM Power Manager — Cloud-agnostic VM lifecycle automation with Slack integration."""

from vm_power_manager.api import check_idle, handle_slack

__version__ = "1.0.0"
__all__ = ["check_idle", "handle_slack"]
