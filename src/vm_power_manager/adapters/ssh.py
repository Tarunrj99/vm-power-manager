"""Generic SSH adapter — works with any VM reachable via SSH."""

from __future__ import annotations

import logging
import os
import time

import paramiko

from vm_power_manager.adapters.base import VMAdapter, VMInfo
from vm_power_manager.models import ResolvedVMConfig

logger = logging.getLogger(__name__)


class SSHAdapter(VMAdapter):
    """
    Generic SSH adapter for VMs not managed by a cloud API.

    Supports start/stop only if the VM has a cloud API fallback
    or if custom commands are provided. Primarily used for metric
    collection on any reachable VM.

    For GCP VMs without ssh_host set, resolves the external IP from
    the Compute API automatically.
    """

    def __init__(self, vm_config: ResolvedVMConfig):
        self._config = vm_config
        self._host = vm_config.ssh_host or self._resolve_host(vm_config)
        self._user = vm_config.ssh_user
        self._port = vm_config.ssh_port
        self._key_env = vm_config.ssh_key_env

    @staticmethod
    def _resolve_host(vm_config: ResolvedVMConfig) -> str:
        """Resolve SSH host — for GCP VMs, get external IP from Compute API."""
        if vm_config.cloud.value == "gcp" and vm_config.project and vm_config.zone:
            try:
                from google.cloud import compute_v1
                client = compute_v1.InstancesClient()
                instance = client.get(
                    project=vm_config.project,
                    zone=vm_config.zone,
                    instance=vm_config.gcp_name or vm_config.name,
                )
                for iface in instance.network_interfaces:
                    for access in iface.access_configs:
                        if access.nat_i_p:
                            return access.nat_i_p
            except Exception as e:
                logger.warning(f"Could not resolve GCP external IP for {vm_config.name}: {e}")
        return vm_config.gcp_name or vm_config.name

    def _get_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self._host,
            "username": self._user,
            "port": self._port,
            "timeout": 10,
        }

        if self._key_env:
            key_value = os.environ.get(self._key_env)
            if key_value:
                if os.path.isfile(key_value):
                    connect_kwargs["key_filename"] = key_value
                else:
                    import base64
                    import io

                    # Decode base64 if the value doesn't look like a PEM key
                    if not key_value.startswith("-----"):
                        try:
                            key_value = base64.b64decode(key_value).decode("utf-8")
                        except Exception:
                            pass

                    pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_value))
                    connect_kwargs["pkey"] = pkey

        client.connect(**connect_kwargs)
        return client

    def run_command(self, command: str, timeout: int = 30) -> tuple[str, str, int]:
        """Run a command via SSH. Returns (stdout, stderr, exit_code)."""
        client = self._get_client()
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return stdout.read().decode(), stderr.read().decode(), exit_code
        finally:
            client.close()

    def is_reachable(self) -> bool:
        """Check if the VM is reachable via SSH."""
        try:
            client = self._get_client()
            client.close()
            return True
        except Exception:
            return False

    def get_status(self) -> VMInfo:
        status = "RUNNING" if self.is_reachable() else "UNREACHABLE"
        return VMInfo(
            name=self._config.name,
            status=status,
            external_ip=self._host,
        )

    def start(self) -> bool:
        logger.warning(f"SSH adapter cannot start VM {self._config.name} — no cloud API")
        return False

    def stop(self) -> bool:
        logger.warning(f"SSH adapter cannot stop VM {self._config.name} — no cloud API")
        return False

    def is_running(self) -> bool:
        return self.is_reachable()

    def wait_until_running(self, timeout_seconds: int = 120) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_reachable():
                return True
            time.sleep(5)
        return False
