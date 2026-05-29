# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] — 2026-05-30

### Added

- **Exact metric values**: All metrics now report absolute values alongside percentages — RAM (used/total GB), Disk (used/total GB), GPU VRAM (used/total GB), CPU core count
- **New fields in `MetricSnapshot`**: `gpu_memory_used_mb`, `gpu_memory_total_mb`, `cpu_cores`, `memory_used_mb`, `memory_total_mb`, `disk_used_gb`, `disk_total_gb`
- **Enhanced SSH collector**: `get_gpu_memory()`, `get_cpu_cores()`, `get_memory_info()`, `get_disk_info()` — return exact values alongside percentages
- **Rich Slack displays**: Status, daily digest, and GPU alerts now show e.g. "RAM: 14.1% (22.9/162.8 GB)" and "Disk: 18% (259/1454 GB)"

### Changed

- Replaced `featuresurface-ai-vm-01` with `featuresurface-ai-vm-02` (nvidia-a100-80gb, a2-ultragpu-1g)
- Status/daily templates redesigned: show VRAM, core count, total/used for memory and disk
- `_collect_metrics()` gathers exact values for all metric types when SSH is available
- GPU running alert and daily digest templates updated with exact values
- When SSH provides exact values, percentage is computed from SSH data (more reliable than Monitoring API for some metrics)
- Bumped to v1.3.1

## [1.2.0] — 2026-05-27

### Added

- **Disk metrics**: New `disk_utilization` field in `MetricSnapshot` — collected via SSH (`df`) or Monitoring API
- **GPU continuous-running alerts**: Configurable per-VM alerts when GPU VMs run beyond a threshold (e.g., every 30min/60min). Informational only — no auto-stop
- **Daily digest**: Comprehensive daily VM summary sent to Slack — shows uptime, GPU/CPU/memory/disk, active processes. GPU VMs highlighted separately
- **Metric fallback**: If Monitoring API returns `None` for a metric, SSH is attempted as fallback
- **Command attribution**: `/vm status|start|stop` now posts a visible message showing who ran the command (everyone in channel sees it)
- **GPU-first status display**: `/vm status` splits VMs into GPU VMs (full detail) and Standard VMs (compact)
- `GpuMonitoringConfig` model with `alert_interval_minutes`, `alert_after_minutes` per-VM overrides
- `send_daily_digest()` public API entry point
- Cloud Function `daily_digest` entry point + Cloud Scheduler job setup
- `last_gpu_alert_sent` field in `VMState` for alert tracking

### Changed

- Status template redesigned: GPU VMs show GPU type, utilization, disk, uptime; non-GPU VMs show compact CPU/MEM only
- `_collect_metrics()` now uses lazy SSH connection and fallback logic
- Bumped to v1.2.0

## [1.1.0] — 2026-05-27

### Added

- **GPU availability protection**: Pre-stop warning when GPU capacity is at risk, multi-zone start with retry + fallback zones, optional auto-migrate
- **Runtime version-compatibility check**: Periodic upstream manifest check (`.manifest.json`) ensures local installs are compatible; opt-out via `app.manifest.enabled: false`
- `GpuProtectionConfig` model with per-VM and default-level configuration
- `check_gpu_availability()` and `start_with_gpu_protection()` in GCP adapter
- Slack confirmation flow ("Stop Anyway" / "Keep Running") for GPU VMs without reservations
- `docs/GPU_AVAILABILITY.md` — guide on GPU unavailability and prevention strategies
- `scripts/gpu-reservation-setup.sh` — helper for creating GCP GPU reservations
- Deploy now uses pip install from pinned release tag (no more bundled source)

### Changed

- `config.example.yaml` updated with `gpu_protection` and `manifest` examples
- Version bumped to 1.1.0
- `examples/gcp-cloud-function/requirements.txt` now installs from GitHub tag

## [1.0.0] — 2026-05-26

### Added

- Initial release of VM Power Manager
- Idle detection engine with configurable metrics (GPU, CPU, memory, process count, combined)
- Smart process detection with watch_list/exclude_list/both strategies
- GCP Compute Engine adapter (start/stop/status via API)
- Generic SSH adapter (any VM reachable via SSH)
- GCP Cloud Monitoring API metric collector (Ops Agent metrics)
- SSH-based metric collector (nvidia-smi, ps, free, who)
- State backends: GCS Bucket, Firestore, Redis, local file
- Slack integration: Block Kit messages, slash commands, interactive buttons
- Per-VM access control (mentioned_only, channel_members, specific_users)
- Lifecycle hooks: pre-stop/post-start commands
- Auto-upgrade prevention (disables unattended-upgrades, holds NVIDIA drivers)
- 3-layer configuration: bundled defaults → deployment config → Slack runtime
- GCP Cloud Function deployment example with deploy.sh
- Local development server (FastAPI)
- Auto-stop disabled by default (manual start/stop via Slack)
