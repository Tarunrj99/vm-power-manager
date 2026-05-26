"""Firestore state backend — stores each VM state as a document."""

from __future__ import annotations

import logging

from google.cloud import firestore

from vm_power_manager.models import VMState
from vm_power_manager.state.base import StateBackend

logger = logging.getLogger(__name__)


class FirestoreState(StateBackend):
    """State stored as Firestore documents: {collection}/{vm_name}"""

    def __init__(self, project: str, collection: str):
        self._db = firestore.Client(project=project)
        self._collection = collection

    def _doc_ref(self, vm_name: str):
        return self._db.collection(self._collection).document(vm_name)

    def get(self, vm_name: str) -> VMState | None:
        doc = self._doc_ref(vm_name).get()
        if not doc.exists:
            return None
        return VMState.model_validate(doc.to_dict())

    def set(self, vm_name: str, state: VMState) -> None:
        self._doc_ref(vm_name).set(state.model_dump(mode="json"))

    def delete(self, vm_name: str) -> None:
        self._doc_ref(vm_name).delete()

    def list_all(self) -> dict[str, VMState]:
        results = {}
        docs = self._db.collection(self._collection).stream()
        for doc in docs:
            try:
                results[doc.id] = VMState.model_validate(doc.to_dict())
            except Exception as e:
                logger.warning(f"Failed to parse state for {doc.id}: {e}")
        return results
