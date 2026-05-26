"""GCP adapter — Compute Engine API for VM actions."""

from __future__ import annotations

import logging
import time

from google.cloud import compute_v1

from vm_power_manager.adapters.base import MetricAdapter, VMAdapter, VMInfo
from vm_power_manager.models import ResolvedVMConfig

logger = logging.getLogger(__name__)


class GCPAdapter(VMAdapter):
    """GCP Compute Engine adapter for VM lifecycle management."""

    def __init__(self, vm_config: ResolvedVMConfig):
        self._config = vm_config
        self._project = vm_config.project
        self._zone = vm_config.zone
        self._instance_name = vm_config.gcp_name or vm_config.name
        self._client = compute_v1.InstancesClient()

    def get_status(self) -> VMInfo:
        instance = self._client.get(
            project=self._project,
            zone=self._zone,
            instance=self._instance_name,
        )
        external_ip = None
        internal_ip = None
        if instance.network_interfaces:
            ni = instance.network_interfaces[0]
            internal_ip = ni.network_i_p
            if ni.access_configs:
                external_ip = ni.access_configs[0].nat_i_p

        return VMInfo(
            name=self._instance_name,
            status=instance.status,
            external_ip=external_ip,
            internal_ip=internal_ip,
            machine_type=instance.machine_type.split("/")[-1] if instance.machine_type else None,
            zone=self._zone,
        )

    def start(self) -> bool:
        try:
            operation = self._client.start(
                project=self._project,
                zone=self._zone,
                instance=self._instance_name,
            )
            operation.result()
            logger.info(f"Started VM: {self._instance_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to start VM {self._instance_name}: {e}")
            return False

    def stop(self) -> bool:
        try:
            operation = self._client.stop(
                project=self._project,
                zone=self._zone,
                instance=self._instance_name,
            )
            operation.result()
            logger.info(f"Stopped VM: {self._instance_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop VM {self._instance_name}: {e}")
            return False

    def is_running(self) -> bool:
        try:
            info = self.get_status()
            return info.status == "RUNNING"
        except Exception as e:
            logger.error(f"Failed to check status of {self._instance_name}: {e}")
            return False

    def wait_until_running(self, timeout_seconds: int = 120) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(5)
        return False
