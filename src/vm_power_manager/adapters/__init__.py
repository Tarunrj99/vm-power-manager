from vm_power_manager.adapters.base import VMAdapter, MetricAdapter

__all__ = ["VMAdapter", "MetricAdapter"]


def get_gcp_adapter():
    from vm_power_manager.adapters.gcp import GCPAdapter
    return GCPAdapter


def get_ssh_adapter():
    from vm_power_manager.adapters.ssh import SSHAdapter
    return SSHAdapter
