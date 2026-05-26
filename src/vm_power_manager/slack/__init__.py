__all__ = ["MessageBuilder", "handle_command", "handle_interaction", "check_access"]


def __getattr__(name):
    if name == "MessageBuilder":
        from vm_power_manager.slack.messages import MessageBuilder
        return MessageBuilder
    elif name == "handle_command":
        from vm_power_manager.slack.commands import handle_command
        return handle_command
    elif name == "handle_interaction":
        from vm_power_manager.slack.interactions import handle_interaction
        return handle_interaction
    elif name == "check_access":
        from vm_power_manager.slack.access_control import check_access
        return check_access
    raise AttributeError(f"module 'vm_power_manager.slack' has no attribute {name}")
