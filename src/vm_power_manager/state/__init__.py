from vm_power_manager.state.base import StateBackend

__all__ = ["StateBackend", "create_state_backend"]


def create_state_backend(config) -> StateBackend:
    """Factory: create the appropriate state backend from config."""
    from vm_power_manager.models import StateBackendType, StateConfig

    state_cfg: StateConfig = config.state
    backend = state_cfg.backend

    if backend == StateBackendType.GCS_BUCKET:
        from vm_power_manager.state.gcs_bucket import GCSBucketState
        return GCSBucketState(
            project=state_cfg.project,
            bucket=state_cfg.bucket,
            prefix=state_cfg.prefix,
        )
    elif backend == StateBackendType.FIRESTORE:
        from vm_power_manager.state.firestore import FirestoreState
        return FirestoreState(
            project=state_cfg.project,
            collection=state_cfg.collection,
        )
    elif backend == StateBackendType.REDIS:
        from vm_power_manager.state.redis_state import RedisState
        return RedisState(
            url_env=state_cfg.url_env or "REDIS_URL",
            key_prefix=state_cfg.key_prefix,
        )
    elif backend == StateBackendType.FILE:
        from vm_power_manager.state.file_state import FileState
        return FileState(path=state_cfg.path)
    elif backend == StateBackendType.S3_BUCKET:
        raise NotImplementedError("S3 backend available in future release. Use gcs_bucket or file.")
    elif backend == StateBackendType.DYNAMODB:
        raise NotImplementedError("DynamoDB backend available in future. Use gcs_bucket or file.")
    else:
        raise ValueError(f"Unknown state backend: {backend}")
