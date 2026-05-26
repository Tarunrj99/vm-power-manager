"""GCS Bucket state backend — stores each VM state as a JSON file in a GCS bucket."""

from __future__ import annotations

import json
import logging

from google.cloud import storage

from vm_power_manager.models import VMState
from vm_power_manager.state.base import StateBackend

logger = logging.getLogger(__name__)


class GCSBucketState(StateBackend):
    """State stored as JSON objects in a GCS bucket: {prefix}{vm_name}.json"""

    def __init__(self, project: str, bucket: str, prefix: str = "state/"):
        self._client = storage.Client(project=project)
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix

    def _blob_name(self, vm_name: str) -> str:
        return f"{self._prefix}{vm_name}.json"

    def get(self, vm_name: str) -> VMState | None:
        blob = self._bucket.blob(self._blob_name(vm_name))
        if not blob.exists():
            return None
        data = json.loads(blob.download_as_text())
        return VMState.model_validate(data)

    def set(self, vm_name: str, state: VMState) -> None:
        blob = self._bucket.blob(self._blob_name(vm_name))
        blob.upload_from_string(
            state.model_dump_json(indent=2),
            content_type="application/json",
        )

    def delete(self, vm_name: str) -> None:
        blob = self._bucket.blob(self._blob_name(vm_name))
        if blob.exists():
            blob.delete()

    def list_all(self) -> dict[str, VMState]:
        results = {}
        blobs = self._client.list_blobs(self._bucket, prefix=self._prefix)
        for blob in blobs:
            if blob.name.endswith(".json"):
                vm_name = blob.name[len(self._prefix) :].removesuffix(".json")
                try:
                    data = json.loads(blob.download_as_text())
                    results[vm_name] = VMState.model_validate(data)
                except Exception as e:
                    logger.warning(f"Failed to parse state for {vm_name}: {e}")
        return results
