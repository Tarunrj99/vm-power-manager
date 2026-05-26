"""VM lifecycle hooks — pre-stop/post-start commands and auto-upgrade management."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vm_power_manager.adapters.ssh import SSHAdapter
from vm_power_manager.models import ResolvedVMConfig

logger = logging.getLogger(__name__)

DISABLE_AUTO_UPGRADES_COMMANDS = [
    "sudo systemctl stop unattended-upgrades 2>/dev/null || true",
    "sudo systemctl disable unattended-upgrades 2>/dev/null || true",
    "sudo apt-mark hold nvidia-driver-* 2>/dev/null || true",
    "sudo apt-mark hold cuda-* 2>/dev/null || true",
]


@dataclass
class HookResult:
    success: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


@dataclass
class LifecycleResult:
    all_success: bool
    results: list[HookResult]

    @property
    def failed(self) -> list[HookResult]:
        return [r for r in self.results if not r.success]


def run_pre_stop_hooks(vm_config: ResolvedVMConfig, ssh: SSHAdapter) -> LifecycleResult:
    """Run pre-stop commands before shutting down the VM."""
    commands = vm_config.pre_stop_commands
    if not commands:
        return LifecycleResult(all_success=True, results=[])

    logger.info(f"Running {len(commands)} pre-stop hooks for {vm_config.name}")
    return _run_hooks(commands, ssh, vm_config.name, "pre-stop")


def run_post_start_hooks(vm_config: ResolvedVMConfig, ssh: SSHAdapter) -> LifecycleResult:
    """Run post-start commands after VM is up and reachable."""
    results = []

    # Disable auto-upgrades if configured
    if vm_config.disable_auto_upgrades:
        logger.info(f"Disabling auto-upgrades on {vm_config.name}")
        upgrade_result = _run_hooks(
            DISABLE_AUTO_UPGRADES_COMMANDS, ssh, vm_config.name, "disable-upgrades"
        )
        results.extend(upgrade_result.results)

    # Custom post-start commands
    commands = vm_config.post_start_commands
    if commands:
        logger.info(f"Running {len(commands)} post-start hooks for {vm_config.name}")
        hook_result = _run_hooks(commands, ssh, vm_config.name, "post-start")
        results.extend(hook_result.results)

    all_success = all(r.success for r in results) if results else True
    return LifecycleResult(all_success=all_success, results=results)


def _run_hooks(
    commands: list[str],
    ssh: SSHAdapter,
    vm_name: str,
    phase: str,
) -> LifecycleResult:
    """Execute a list of commands via SSH. Best-effort: failures don't stop subsequent commands."""
    results = []

    for cmd in commands:
        try:
            stdout, stderr, exit_code = ssh.run_command(cmd, timeout=60)
            success = exit_code == 0
            if not success:
                logger.warning(
                    f"[{vm_name}] {phase} hook failed (exit={exit_code}): {cmd}\n"
                    f"stderr: {stderr[:200]}"
                )
            results.append(HookResult(
                success=success,
                command=cmd,
                stdout=stdout[:500],
                stderr=stderr[:500],
                exit_code=exit_code,
            ))
        except Exception as e:
            logger.error(f"[{vm_name}] {phase} hook exception: {cmd} -> {e}")
            results.append(HookResult(
                success=False,
                command=cmd,
                stderr=str(e),
                exit_code=-1,
            ))

    all_success = all(r.success for r in results)
    return LifecycleResult(all_success=all_success, results=results)
