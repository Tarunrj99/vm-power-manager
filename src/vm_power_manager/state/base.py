"""Abstract state backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from vm_power_manager.models import VMState


class StateBackend(ABC):
    """Base class for all state backends. Each VM gets its own isolated state."""

    @abstractmethod
    def get(self, vm_name: str) -> VMState | None:
        """Retrieve state for a VM. Returns None if no state exists."""
        ...

    @abstractmethod
    def set(self, vm_name: str, state: VMState) -> None:
        """Persist state for a VM (full overwrite)."""
        ...

    @abstractmethod
    def delete(self, vm_name: str) -> None:
        """Delete state for a VM."""
        ...

    @abstractmethod
    def list_all(self) -> dict[str, VMState]:
        """List all VM states. Returns {vm_name: VMState}."""
        ...

    def get_or_create(self, vm_name: str) -> VMState:
        """Get existing state or create a fresh one."""
        state = self.get(vm_name)
        if state is None:
            state = VMState(vm_name=vm_name)
            self.set(vm_name, state)
        return state
