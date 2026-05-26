__all__ = ["MonitoringAPICollector", "SSHMetricCollector"]


def get_monitoring_api_collector():
    from vm_power_manager.metrics.monitoring_api import MonitoringAPICollector
    return MonitoringAPICollector


def get_ssh_metric_collector():
    from vm_power_manager.metrics.ssh_metrics import SSHMetricCollector
    return SSHMetricCollector
