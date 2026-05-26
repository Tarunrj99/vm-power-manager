"""GCP Cloud Monitoring API metric collector — uses Ops Agent metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from google.cloud import monitoring_v3

from vm_power_manager.models import ResolvedVMConfig

logger = logging.getLogger(__name__)


class MonitoringAPICollector:
    """Collects metrics from GCP Cloud Monitoring API (requires Ops Agent on VMs)."""

    def __init__(self, vm_config: ResolvedVMConfig):
        self._config = vm_config
        self._project = vm_config.project
        self._instance_name = vm_config.gcp_name or vm_config.name
        self._zone = vm_config.zone
        self._client = monitoring_v3.MetricServiceClient()
        self._project_name = f"projects/{self._project}"

    def _query_metric(self, metric_type: str, minutes: int = 10) -> float | None:
        """Query a single metric and return the latest value."""
        now = datetime.now(timezone.utc)
        interval = monitoring_v3.TimeInterval(
            end_time=now,
            start_time=now - timedelta(minutes=minutes),
        )

        instance_filter = (
            f'metric.type = "{metric_type}" AND '
            f'resource.labels.instance_id = "{self._get_instance_id()}"'
        )

        try:
            results = self._client.list_time_series(
                request={
                    "name": self._project_name,
                    "filter": instance_filter,
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )

            for series in results:
                if series.points:
                    point = series.points[0]
                    return point.value.double_value
            return None
        except Exception as e:
            logger.warning(f"Failed to query {metric_type} for {self._instance_name}: {e}")
            return None

    def _get_instance_id(self) -> str:
        """Get the numeric instance ID for monitoring queries.

        Falls back to instance name if ID lookup fails.
        """
        try:
            from google.cloud import compute_v1

            client = compute_v1.InstancesClient()
            instance = client.get(
                project=self._project,
                zone=self._zone,
                instance=self._instance_name,
            )
            return str(instance.id)
        except Exception:
            return self._instance_name

    def get_gpu_utilization(self) -> float | None:
        """GPU utilization from Ops Agent (custom/gpu/utilization)."""
        # Ops Agent reports GPU metrics under these paths
        for metric in [
            "custom.googleapis.com/gpu/utilization",
            "agent.googleapis.com/gpu/utilization",
            "custom.googleapis.com/instance/gpu/utilization",
        ]:
            value = self._query_metric(metric)
            if value is not None:
                return value
        return None

    def get_cpu_utilization(self) -> float | None:
        """CPU utilization from Compute Engine built-in metric."""
        value = self._query_metric(
            "compute.googleapis.com/instance/cpu/utilization"
        )
        if value is not None:
            return value * 100  # Built-in metric is 0.0-1.0
        return None

    def get_memory_utilization(self) -> float | None:
        """Memory utilization from Ops Agent."""
        value = self._query_metric(
            "agent.googleapis.com/memory/percent_used"
        )
        return value
