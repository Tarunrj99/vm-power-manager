"""Upstream runtime manifest — version-compatibility & deprecation check.

Many libraries publish a small JSON manifest at a stable URL describing
which versions are still supported, which have been deprecated, and the
library's current operational status. ``vm_power_manager`` does the same:
on each invocation, the API layer consults a cached copy of the manifest
and refuses to process if the local install is unsupported or the upstream
service has been marked inactive.

Operators who don't want a runtime dependency on the upstream manifest
can disable the check entirely via ``app.manifest.enabled = false`` (or
the env var ``VM_POWER_MANAGER_MANIFEST_ENABLED=false``).

Caching is per-process; cold starts re-fetch, warm instances reuse the
last verdict for ``refresh_interval_seconds`` (default 300s).
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_PACKAGE_VERSION = "1.1.0"


@dataclass(frozen=True)
class ManifestStatus:
    """Outcome of a manifest check."""

    allow: bool
    reason: str | None = None
    source: str = "unknown"
    fetched_at: float = 0.0
    descriptor: dict[str, Any] = field(default_factory=dict)


@dataclass
class _CacheEntry:
    status: ManifestStatus
    expires_at: float


_cache: dict[str, _CacheEntry] = {}
_lock = threading.Lock()


def _installed_version() -> str:
    try:
        from importlib import metadata

        return metadata.version("vm-power-manager")
    except Exception:
        return _PACKAGE_VERSION


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse a dotted version like ``"1.1.0"`` into ``(1, 1, 0)``."""
    parts: list[int] = []
    for raw in value.split("."):
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _interpret(
    descriptor: dict[str, Any],
    *,
    installed: str,
    deployment_id: str | None,
) -> ManifestStatus:
    """Decide allow/deny from a parsed manifest descriptor."""
    if not isinstance(descriptor, dict):
        return ManifestStatus(
            allow=False,
            reason="manifest_malformed",
            source="remote",
            fetched_at=time.time(),
        )

    status = str(descriptor.get("service_status", "active")).lower()
    if status and status != "active":
        return ManifestStatus(
            allow=False,
            reason="service_status_inactive",
            source="remote",
            fetched_at=time.time(),
            descriptor=descriptor,
        )

    deprecated_versions = descriptor.get("deprecated_versions") or []
    if isinstance(deprecated_versions, list) and installed in deprecated_versions:
        return ManifestStatus(
            allow=False,
            reason="version_unsupported",
            source="remote",
            fetched_at=time.time(),
            descriptor=descriptor,
        )

    min_version = descriptor.get("min_supported_version")
    if isinstance(min_version, str) and min_version:
        if _parse_version(installed) < _parse_version(min_version):
            return ManifestStatus(
                allow=False,
                reason="version_unsupported",
                source="remote",
                fetched_at=time.time(),
                descriptor=descriptor,
            )

    overrides = descriptor.get("deployment_overrides") or []
    if deployment_id and isinstance(overrides, list):
        for entry in overrides:
            if not isinstance(entry, dict):
                continue
            if entry.get("deployment_id") != deployment_id:
                continue
            entry_status = str(entry.get("status", "")).lower()
            if entry_status and entry_status != "active":
                return ManifestStatus(
                    allow=False,
                    reason="deployment_disabled",
                    source="remote",
                    fetched_at=time.time(),
                    descriptor=descriptor,
                )

    return ManifestStatus(
        allow=True,
        source="remote",
        fetched_at=time.time(),
        descriptor=descriptor,
    )


def _fetch(url: str, timeout: float) -> tuple[int, dict[str, Any] | None, str | None]:
    """Fetch and parse the manifest from URL."""
    import requests

    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"

    if response.status_code >= 400:
        return response.status_code, None, f"http_{response.status_code}"

    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        return response.status_code, None, f"json_decode_error: {exc}"

    # GitHub Contents API wraps the file in a metadata envelope with base64 content
    if (
        isinstance(body, dict)
        and body.get("encoding") == "base64"
        and isinstance(body.get("content"), str)
    ):
        try:
            decoded = base64.b64decode(body["content"]).decode("utf-8")
            return response.status_code, json.loads(decoded), None
        except (ValueError, json.JSONDecodeError) as exc:
            return response.status_code, None, f"base64_decode_error: {exc}"

    return response.status_code, body, None


def check_manifest(
    config: dict[str, Any],
    *,
    deployment_id: str | None = None,
    now: float | None = None,
) -> ManifestStatus:
    """Evaluate the runtime manifest for the current installation.

    ``config`` should be the ``app.manifest`` sub-tree of the resolved
    library configuration. Returns a :class:`ManifestStatus` whose
    ``allow`` field tells the caller whether to proceed.
    """
    timestamp = now if now is not None else time.time()

    if not config or not config.get("enabled", True):
        return ManifestStatus(
            allow=True,
            source="disabled",
            fetched_at=timestamp,
        )

    url = str(config.get("url") or "").strip()
    if not url:
        logger.warning("vm_power_manager.manifest: enabled but no url configured")
        return ManifestStatus(
            allow=True,
            reason="manifest_url_missing",
            source="tolerated",
            fetched_at=timestamp,
        )

    refresh = float(config.get("refresh_interval_seconds", 300))
    timeout = float(config.get("timeout_seconds", 3))
    tolerate_network = bool(config.get("tolerate_network_errors", True))
    tolerate_missing = bool(config.get("tolerate_missing_manifest", False))

    with _lock:
        cached = _cache.get(url)
        if cached and cached.expires_at > timestamp:
            return cached.status

    status_code, descriptor, error = _fetch(url, timeout)

    if status_code == 0:
        logger.warning("vm_power_manager.manifest: network error fetching %s: %s", url, error)
        if cached and cached.status.source == "remote":
            return ManifestStatus(
                allow=cached.status.allow,
                reason=cached.status.reason or "manifest_cached",
                source="cached",
                fetched_at=cached.status.fetched_at,
                descriptor=cached.status.descriptor,
            )
        return ManifestStatus(
            allow=tolerate_network,
            reason=None if tolerate_network else "manifest_unreachable",
            source="tolerated" if tolerate_network else "rejected",
            fetched_at=timestamp,
        )

    if status_code in (404, 403, 410):
        logger.warning(
            "vm_power_manager.manifest: %s returned %s; treating as %s",
            url, status_code,
            "tolerated" if tolerate_missing else "rejected",
        )
        result = ManifestStatus(
            allow=tolerate_missing,
            reason=None if tolerate_missing else "manifest_unavailable",
            source="tolerated" if tolerate_missing else "rejected",
            fetched_at=timestamp,
        )
        with _lock:
            _cache[url] = _CacheEntry(status=result, expires_at=timestamp + refresh)
        return result

    if descriptor is None:
        logger.warning(
            "vm_power_manager.manifest: bad response from %s status=%s error=%s",
            url, status_code, error,
        )
        if cached and cached.status.source == "remote":
            return ManifestStatus(
                allow=cached.status.allow,
                reason=cached.status.reason or "manifest_cached",
                source="cached",
                fetched_at=cached.status.fetched_at,
                descriptor=cached.status.descriptor,
            )
        return ManifestStatus(
            allow=tolerate_network,
            reason=None if tolerate_network else "manifest_unparseable",
            source="tolerated" if tolerate_network else "rejected",
            fetched_at=timestamp,
        )

    result = _interpret(
        descriptor,
        installed=_installed_version(),
        deployment_id=deployment_id,
    )
    with _lock:
        _cache[url] = _CacheEntry(status=result, expires_at=timestamp + refresh)
    return result


def reset_cache() -> None:
    """Clear the in-process cache (for tests or forced refresh)."""
    with _lock:
        _cache.clear()
