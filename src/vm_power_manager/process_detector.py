"""Smart process detection — distinguishes application processes from system services."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vm_power_manager.models import ProcessMonitoringConfig, ProcessMonitorStrategy

logger = logging.getLogger(__name__)


@dataclass
class DetectedProcess:
    user: str
    pid: int
    process_name: str
    full_command: str


@dataclass
class ProcessDetectionResult:
    active_processes: list[DetectedProcess]
    ignored_processes: dict[str, int]  # {process_name: count}
    active_sessions: list[str]

    @property
    def is_active(self) -> bool:
        return len(self.active_processes) > 0 or len(self.active_sessions) > 0

    @property
    def active_count(self) -> int:
        return len(self.active_processes)

    @property
    def session_count(self) -> int:
        return len(self.active_sessions)


def detect_processes(
    ps_output: str,
    session_users: list[str],
    config: ProcessMonitoringConfig,
) -> ProcessDetectionResult:
    """
    Analyze process list and determine if real application work is happening.

    Checks ALL users (including root/sudo). Filters out system/infra services.
    Uses configurable strategy: watch_list, exclude_list, or both.
    """
    active = []
    ignored: dict[str, int] = {}

    for line in ps_output.strip().split("\n"):
        if not line.strip():
            continue

        parts = line.split(None, 4)
        if len(parts) < 4:
            continue

        user = parts[0]
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        process_name = parts[3]
        full_command = parts[4] if len(parts) > 4 else parts[3]

        # Skip the ps command itself and common noise
        if process_name in ("ps", "grep", "awk", "wc"):
            continue

        matched = _matches_strategy(process_name, full_command, config)

        if matched:
            active.append(DetectedProcess(
                user=user,
                pid=pid,
                process_name=process_name,
                full_command=full_command,
            ))
        else:
            ignored[process_name] = ignored.get(process_name, 0) + 1

    # Active sessions (SSH/RDP)
    sessions = session_users if config.check_active_sessions else []

    return ProcessDetectionResult(
        active_processes=active,
        ignored_processes=ignored,
        active_sessions=sessions,
    )


def _matches_strategy(
    process_name: str,
    full_command: str,
    config: ProcessMonitoringConfig,
) -> bool:
    """Determine if a process should be counted as 'active work'."""
    strategy = config.strategy

    if strategy == ProcessMonitorStrategy.WATCH_LIST:
        return _matches_watch_list(process_name, full_command, config)

    elif strategy == ProcessMonitorStrategy.EXCLUDE_LIST:
        return process_name not in config.exclude_processes

    elif strategy == ProcessMonitorStrategy.BOTH:
        if process_name in config.exclude_processes:
            return False
        return _matches_watch_list(process_name, full_command, config)

    return False


def _matches_watch_list(
    process_name: str,
    full_command: str,
    config: ProcessMonitoringConfig,
) -> bool:
    """Check if process matches watch_processes or watch_commands."""
    if process_name in config.watch_processes:
        return True

    for keyword in config.watch_commands:
        if keyword in full_command:
            return True

    return False
