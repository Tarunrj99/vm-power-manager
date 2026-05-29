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

    def get_gpu_memory(self) -> tuple[float | None, float | None]:
        """GPU memory (used_mb, total_mb) via nvidia-smi."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits"
            )
            if exit_code != 0:
                return None, None
            line = stdout.strip().split("\n")[0]
            parts = [float(v.strip()) for v in line.split(",")]
            if len(parts) >= 2:
                return parts[0], parts[1]
            return None, None
        except Exception as e:
            logger.warning(f"SSH GPU memory failed for {self._config.name}: {e}")
            return None, None

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

    def get_cpu_cores(self) -> int | None:
        """Number of CPU cores via nproc."""
        try:
            stdout, _, exit_code = self._ssh.run_command("nproc")
            if exit_code != 0:
                return None
            return int(stdout.strip()) if stdout.strip() else None
        except Exception as e:
            logger.warning(f"SSH CPU cores failed for {self._config.name}: {e}")
            return None

    def get_memory_info(self) -> tuple[float | None, float | None, float | None]:
        """Memory info (utilization%, used_mb, total_mb) via free."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "free -m | awk '/Mem:/ {print $2, $3}'"
            )
            if exit_code != 0:
                return None, None, None
            parts = stdout.strip().split()
            if len(parts) >= 2:
                total = float(parts[0])
                used = float(parts[1])
                pct = (used / total * 100) if total > 0 else 0
                return round(pct, 1), used, total
            return None, None, None
        except Exception as e:
            logger.warning(f"SSH memory metric failed for {self._config.name}: {e}")
            return None, None, None

    def get_memory_utilization(self) -> float | None:
        """Memory utilization % only (backward compat)."""
        pct, _, _ = self.get_memory_info()
        return pct

    def get_disk_info(self) -> tuple[float | None, float | None, float | None]:
        """Disk info (utilization%, used_gb, total_gb) for root partition."""
        try:
            stdout, _, exit_code = self._ssh.run_command(
                "df / --output=pcent,used,size --block-size=1G | tail -1"
            )
            if exit_code != 0:
                return None, None, None
            parts = stdout.strip().split()
            if len(parts) >= 3:
                pct = float(parts[0].replace("%", ""))
                used = float(parts[1])
                total = float(parts[2])
                return pct, used, total
            return None, None, None
        except Exception as e:
            logger.warning(f"SSH disk metric failed for {self._config.name}: {e}")
            return None, None, None

    def get_disk_utilization(self) -> float | None:
        """Root partition disk utilization % only (backward compat)."""
        pct, _, _ = self.get_disk_info()
        return pct

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
