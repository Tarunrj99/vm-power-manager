"""Slack access control — determines who can control which VMs."""

from __future__ import annotations

import logging

from vm_power_manager.models import AccessControlMode, ResolvedVMConfig

logger = logging.getLogger(__name__)


def check_access(
    user_id: str,
    user_name: str,
    vm_config: ResolvedVMConfig,
    channel_members: list[str] | None = None,
) -> bool:
    """
    Check if a Slack user has permission to control a VM.

    Args:
        user_id: Slack user ID (e.g., U12345)
        user_name: Slack username (e.g., @john.doe)
        vm_config: Resolved VM configuration
        channel_members: List of user IDs in the channel (for channel_members mode)

    Returns:
        True if user has access, False otherwise.
    """
    mode = vm_config.access_control

    if mode == AccessControlMode.MENTIONED_ONLY:
        normalized = _normalize_username(user_name)
        allowed = [_normalize_username(u) for u in vm_config.notify_users]
        return normalized in allowed

    elif mode == AccessControlMode.CHANNEL_MEMBERS:
        if channel_members is None:
            logger.warning(
                f"Channel members not provided for {vm_config.name}, "
                "falling back to notify_users"
            )
            normalized = _normalize_username(user_name)
            allowed = [_normalize_username(u) for u in vm_config.notify_users]
            return normalized in allowed
        return user_id in channel_members

    elif mode == AccessControlMode.SPECIFIC_USERS:
        normalized = _normalize_username(user_name)
        allowed = [_normalize_username(u) for u in vm_config.allowed_users]
        return normalized in allowed

    return False


def get_denied_message(vm_config: ResolvedVMConfig) -> dict:
    """Build Slack Block Kit message for permission denied."""
    mode = vm_config.access_control
    if mode == AccessControlMode.MENTIONED_ONLY:
        authorized = ", ".join(vm_config.notify_users)
    elif mode == AccessControlMode.SPECIFIC_USERS:
        authorized = ", ".join(vm_config.allowed_users)
    else:
        authorized = "all channel members"

    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":no_entry: *Permission Denied*\n\n"
                    f"You don't have access to control *{vm_config.name}*.\n\n"
                    f"*Authorized:* {authorized}\n\n"
                    f"Contact them or your admin to request access.",
                },
            }
        ]
    }


def _normalize_username(username: str) -> str:
    """Normalize username: remove @ prefix, lowercase."""
    return username.lstrip("@").lower()
