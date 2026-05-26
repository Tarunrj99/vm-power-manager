"""Abstract interfaces for cloud VM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VMInfo:
    """Basic info about a VM instance."""

    name: str
    status: str  # "RUNNING", "TERMINATED", "STOPPED", etc.
    external_ip: str | None = None
    internal_ip: str | None = None
    machine_type: str | None = None
    zone: str | None = None


class VMAdapter(ABC):
    """Interface for VM lifecycle actions (start/stop/status)."""

    @abstractmethod
    def get_status(self) -> VMInfo:
        """Get current VM status and info."""
        ...

    @abstractmethod
    def start(self) -> bool:
        """Start the VM. Returns True on success."""
        ...

    @abstractmethod
    def stop(self) -> bool:
        """Stop the VM. Returns True on success."""
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Quick check: is the VM currently running?"""
        ...

    @abstractmethod
    def wait_until_running(self, timeout_seconds: int = 120) -> bool:
        """Wait until VM is running and reachable. Returns True if ready."""
        ...


class MetricAdapter(ABC):
    """Interface for collecting metrics from a VM."""

    @abstractmethod
    def get_gpu_utilization(self) -> float | None:
        """GPU utilization percentage (0-100). None if not available."""
        ...

    @abstractmethod
    def get_cpu_utilization(self) -> float | None:
        """CPU utilization percentage (0-100). None if not available."""
        ...

    @abstractmethod
    def get_memory_utilization(self) -> float | None:
        """Memory utilization percentage (0-100). None if not available."""
        ...
