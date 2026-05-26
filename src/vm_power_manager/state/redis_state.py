"""Redis state backend — stores each VM state as a JSON string under a key."""

from __future__ import annotations

import json
import logging
import os

from vm_power_manager.models import VMState
from vm_power_manager.state.base import StateBackend

logger = logging.getLogger(__name__)


class RedisState(StateBackend):
    """State stored in Redis: key = {prefix}{vm_name}, value = JSON string."""

    def __init__(self, url_env: str = "REDIS_URL", key_prefix: str = "vpm:"):
        import redis

        url = os.environ.get(url_env)
        if not url:
            raise EnvironmentError(f"Redis URL not found in env var: {url_env}")
        self._client = redis.from_url(url)
        self._prefix = key_prefix

    def _key(self, vm_name: str) -> str:
        return f"{self._prefix}{vm_name}"

    def get(self, vm_name: str) -> VMState | None:
        data = self._client.get(self._key(vm_name))
        if data is None:
            return None
        return VMState.model_validate(json.loads(data))

    def set(self, vm_name: str, state: VMState) -> None:
        self._client.set(self._key(vm_name), state.model_dump_json())

    def delete(self, vm_name: str) -> None:
        self._client.delete(self._key(vm_name))

    def list_all(self) -> dict[str, VMState]:
        results = {}
        pattern = f"{self._prefix}*"
        for key in self._client.scan_iter(match=pattern):
            vm_name = key.decode().removeprefix(self._prefix)
            try:
                data = self._client.get(key)
                if data:
                    results[vm_name] = VMState.model_validate(json.loads(data))
            except Exception as e:
                logger.warning(f"Failed to parse state for {vm_name}: {e}")
        return results
