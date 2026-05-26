"""GCP adapter — Compute Engine API for VM actions + GPU protection."""

from __future__ import annotations

import logging
import time

from google.cloud import compute_v1

from vm_power_manager.adapters.base import MetricAdapter, VMAdapter, VMInfo
from vm_power_manager.models import GpuProtectionConfig, ResolvedVMConfig

logger = logging.getLogger(__name__)

_RESOURCE_EXHAUSTED_INDICATORS = [
    "ZONE_RESOURCE_POOL_EXHAUSTED",
    "RESOURCE_POOL_EXHAUSTED",
    "does not have enough resources",
    "resource availability",
    "gpu_availability",
]


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

    def check_gpu_availability(self) -> dict:
        """
        Check if the configured GPU type is available in the VM's zone.

        Returns:
            {
                "available": bool,
                "gpu_type": str,
                "zone": str,
                "has_reservation": bool,
                "error": str | None,
            }
        """
        gpu_type = self._config.gpu_type
        if not gpu_type:
            return {"available": True, "gpu_type": None, "zone": self._zone,
                    "has_reservation": False, "error": None}

        result = {
            "available": True,
            "gpu_type": gpu_type,
            "zone": self._zone,
            "has_reservation": False,
            "error": None,
        }

        try:
            accel_client = compute_v1.AcceleratorTypesClient()
            accel_type = accel_client.get(
                project=self._project,
                zone=self._zone,
                accelerator_type=gpu_type,
            )
            result["available"] = True
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "404" in err_str:
                result["available"] = False
                result["error"] = f"GPU type '{gpu_type}' not found in zone {self._zone}"
            else:
                result["error"] = str(e)[:200]

        # Check for existing reservations
        try:
            reservations_client = compute_v1.ReservationsClient()
            reservations = reservations_client.list(
                project=self._project,
                zone=self._zone,
            )
            for reservation in reservations:
                if reservation.specific_reservation:
                    for accel in (reservation.specific_reservation.instance_properties.guest_accelerators or []):
                        if gpu_type in (accel.accelerator_type or ""):
                            result["has_reservation"] = True
                            break
        except Exception:
            pass

        return result

    def start(self) -> bool:
        """Start the VM in its configured zone."""
        try:
            operation = self._client.start(
                project=self._project,
                zone=self._zone,
                instance=self._instance_name,
            )
            operation.result()
            logger.info(f"Started VM: {self._instance_name} in {self._zone}")
            return True
        except Exception as e:
            logger.error(f"Failed to start VM {self._instance_name}: {e}")
            return False

    def start_with_gpu_protection(self) -> dict:
        """
        Start VM with GPU protection: retry in original zone, then try fallback zones.

        Returns:
            {
                "success": bool,
                "zone": str,           # Zone where VM is now running
                "migrated": bool,      # True if VM was moved to a different zone
                "original_zone": str,
                "attempts": int,
                "error": str | None,
            }
        """
        gpu_config = self._config.gpu_protection
        original_zone = self._zone
        result = {
            "success": False,
            "zone": original_zone,
            "migrated": False,
            "original_zone": original_zone,
            "attempts": 0,
            "error": None,
        }

        # Retry in original zone
        for attempt in range(gpu_config.max_start_retries):
            result["attempts"] += 1
            try:
                operation = self._client.start(
                    project=self._project,
                    zone=self._zone,
                    instance=self._instance_name,
                )
                operation.result()
                logger.info(f"Started VM {self._instance_name} in {self._zone} (attempt {attempt + 1})")
                result["success"] = True
                result["zone"] = self._zone
                return result
            except Exception as e:
                err_str = str(e)
                if _is_resource_exhausted(err_str):
                    logger.warning(
                        f"GPU unavailable in {self._zone} for {self._instance_name} "
                        f"(attempt {attempt + 1}/{gpu_config.max_start_retries})"
                    )
                    if attempt < gpu_config.max_start_retries - 1:
                        time.sleep(gpu_config.retry_delay_seconds)
                else:
                    result["error"] = err_str[:200]
                    return result

        # Original zone exhausted — try fallback zones if auto_migrate enabled
        if not gpu_config.auto_migrate or not gpu_config.fallback_zones:
            result["error"] = (
                f"GPU unavailable in {original_zone} after {result['attempts']} attempts. "
                f"Fallback zones: {'not configured' if not gpu_config.fallback_zones else 'auto_migrate disabled'}."
            )
            return result

        # Try fallback zones via migration
        for fallback_zone in gpu_config.fallback_zones:
            if fallback_zone == original_zone:
                continue

            result["attempts"] += 1
            logger.info(f"Attempting to migrate {self._instance_name} to {fallback_zone}")

            try:
                success = self._migrate_vm(fallback_zone)
                if not success:
                    continue

                # Try starting in new zone
                operation = self._client.start(
                    project=self._project,
                    zone=fallback_zone,
                    instance=self._instance_name,
                )
                operation.result()

                # Update internal zone reference
                self._zone = fallback_zone
                result["success"] = True
                result["zone"] = fallback_zone
                result["migrated"] = True
                logger.info(f"Successfully migrated and started {self._instance_name} in {fallback_zone}")
                return result

            except Exception as e:
                err_str = str(e)
                if _is_resource_exhausted(err_str):
                    logger.warning(f"GPU also unavailable in fallback zone {fallback_zone}")
                    continue
                else:
                    logger.error(f"Error starting in {fallback_zone}: {err_str[:100]}")
                    continue

        result["error"] = (
            f"GPU unavailable in all zones: {original_zone} + {gpu_config.fallback_zones}. "
            f"Consider creating a GPU reservation."
        )
        return result

    def _migrate_vm(self, target_zone: str) -> bool:
        """Migrate a stopped VM to a different zone using moveInstance API."""
        try:
            move_request = compute_v1.MoveInstanceRequest(
                project=self._project,
                move_instance_request_resource=compute_v1.MoveInstanceRequest(
                    destination_zone=f"zones/{target_zone}",
                    target_instance=f"projects/{self._project}/zones/{self._zone}/instances/{self._instance_name}",
                ),
            )
            projects_client = compute_v1.ProjectsClient()
            operation = projects_client.move_instance(
                project=self._project,
                move_instance_request_resource=compute_v1.MoveInstanceRequest(
                    destination_zone=f"zones/{target_zone}",
                    target_instance=f"projects/{self._project}/zones/{self._zone}/instances/{self._instance_name}",
                ),
            )
            operation.result()
            self._zone = target_zone
            logger.info(f"Migrated {self._instance_name} from {self._zone} to {target_zone}")
            return True
        except Exception as e:
            logger.error(f"Migration failed for {self._instance_name} to {target_zone}: {e}")
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


def _is_resource_exhausted(error_message: str) -> bool:
    """Check if an error indicates GPU/resource pool exhaustion."""
    lower = error_message.lower()
    return any(indicator.lower() in lower for indicator in _RESOURCE_EXHAUSTED_INDICATORS)
