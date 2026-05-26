"""Local file state backend — stores each VM state as a JSON file on disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from vm_power_manager.models import VMState
from vm_power_manager.state.base import StateBackend

logger = logging.getLogger(__name__)


class FileState(StateBackend):
    """State stored as local JSON files: {path}/{vm_name}.json — ideal for dev/testing."""

    def __init__(self, path: str = "./state/"):
        self._dir = Path(path)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, vm_name: str) -> Path:
        return self._dir / f"{vm_name}.json"

    def get(self, vm_name: str) -> VMState | None:
        fp = self._file_path(vm_name)
        if not fp.exists():
            return None
        data = json.loads(fp.read_text())
        return VMState.model_validate(data)

    def set(self, vm_name: str, state: VMState) -> None:
        fp = self._file_path(vm_name)
        fp.write_text(state.model_dump_json(indent=2))

    def delete(self, vm_name: str) -> None:
        fp = self._file_path(vm_name)
        if fp.exists():
            fp.unlink()

    def list_all(self) -> dict[str, VMState]:
        results = {}
        for fp in self._dir.glob("*.json"):
            vm_name = fp.stem
            try:
                data = json.loads(fp.read_text())
                results[vm_name] = VMState.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to parse state for {vm_name}: {e}")
        return results
