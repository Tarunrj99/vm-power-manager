"""SSH-based metric collector — runs commands on the VM to collect metrics."""

from __future__ import annotations

import logging
import re

from vm_power_manager.adapters.ssh import SSHAdapter
from vm_power_manager.models import ResolvedVMConfig

logger = logging.getLogger(__name__)


class SSHMetricCollector:
    """Collects metrics by running commands over SSH (IAP or direct)."""

    def __init__(self, vm_config: ResolvedVMConfig, ssh_adapter: SSHAdapter | None = None):
        self._config = vm_config
        self._ssh = ssh_adapter or SSHAdapter(vm_config)

    def get_gpu_utilization(self) -> float | None:
        """GPU utilization via nvidia-smi."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits"
            )
            if exit_code != 0:
                return None
            values = [float(v.strip()) for v in stdout.strip().split("\n") if v.strip()]
            return max(values) if values else None
        except Exception as e:
            logger.warning(f"SSH GPU metric failed for {self._config.name}: {e}")
            return None

    def get_cpu_utilization(self) -> float | None:
        """CPU utilization via /proc/stat snapshot."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"
            )
            if exit_code != 0:
                return None
            return float(stdout.strip()) if stdout.strip() else None
        except Exception as e:
            logger.warning(f"SSH CPU metric failed for {self._config.name}: {e}")
            return None

    def get_memory_utilization(self) -> float | None:
        """Memory utilization via free command."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "free | awk '/Mem:/ {printf(\"%.1f\", $3/$2 * 100)}'"
            )
            if exit_code != 0:
                return None
            return float(stdout.strip()) if stdout.strip() else None
        except Exception as e:
            logger.warning(f"SSH memory metric failed for {self._config.name}: {e}")
            return None

    def get_disk_utilization(self) -> float | None:
        """Root partition disk utilization via df."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "df / --output=pcent | tail -1 | tr -d ' %'"
            )
            if exit_code != 0:
                return None
            return float(stdout.strip()) if stdout.strip() else None
        except Exception as e:
            logger.warning(f"SSH disk metric failed for {self._config.name}: {e}")
            return None

    def get_processes(self) -> str:
        """Get full process list for process detection."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "ps aux --no-headers -o user,pid,ppid,comm,args"
            )
            if exit_code != 0:
                return ""
            return stdout
        except Exception as e:
            logger.warning(f"SSH process list failed for {self._config.name}: {e}")
            return ""

    def get_active_sessions(self) -> list[str]:
        """Get list of logged-in users via `who`."""
        try:
            stdout, _, exit_code = self._ssh.run_command("who")
            if exit_code != 0:
                return []
            users = []
            for line in stdout.strip().split("\n"):
                if line.strip():
                    users.append(line.split()[0])
            return list(set(users))
        except Exception as e:
            logger.warning(f"SSH sessions check failed for {self._config.name}: {e}")
            return []
