# Changelog

All notable changes to this project will be documented in this file.

## [1.5.0] — 2026-05-31

### Added

- **Fully configurable reports**: New `reports` config section replaces `schedule`
  - `reports.daily.title` / `reports.gpu.title` — custom report names
  - `reports.daily.message` / `reports.gpu.message` — custom header messages
  - `reports.daily.display` / `reports.gpu.display` — toggle each metric on/off
  - `reports.daily.schedules` / `reports.gpu.schedules` — multiple cron expressions
  - `reports.daily.enabled` / `reports.gpu.enabled` — disable reports entirely
- **Metric display toggles**: `show_gpu_model`, `show_gpu_utilization`, `show_gpu_memory`, `show_cpu`, `show_ram`, `show_disk`, `show_processes`, `show_uptime`, `show_ip`
- Users can build fully custom report templates from config alone — no code changes

### Changed

- Replaced `schedule` config section with `reports` (backward-compatible defaults)
- `daily_summary()` and `gpu_status_report()` accept `ReportConfig` parameter
- Deploy scripts read schedules from `reports.daily.schedules` / `reports.gpu.schedules`

## [1.4.0] — 2026-05-31

### Added

- **Consolidated GPU Status Report**: New `send_gpu_status_report()` — sends one consolidated message for all running GPU VMs instead of individual per-VM alerts
- **Redesigned Daily Digest**: Beautiful multi-line format with each metric on its own labeled line, "Running Since" with date + duration, cost-awareness note
- **12-hour schedule**: Daily full report at 9 AM, GPU-only status at 9 PM (configurable)
- **Cost reminder messages**: Both reports include a friendly note about stopping idle VMs
- **Smart duration format**: Shows `25d 20h` for long-running VMs, `2h 15m` for shorter, `10m` for recent
- `gpu_status` Cloud Function entry point for the 9 PM report

### Changed

- GPU alerts are now consolidated (1 message for all VMs) instead of individual per-VM messages
- Disabled per-VM GPU running alerts (replaced by consolidated report)
- Templates completely redesigned: spacious, each metric on its own line, clear section labels
- Alert interval changed from 1 hour to 12 hours

### Removed

- Hourly per-VM GPU running alerts (replaced by 12h consolidated report)

## [1.3.0] — 2026-05-30

### Added

- **Exact metric values**: All metrics now report absolute values alongside percentages — RAM (used/total GB), Disk (used/total GB), GPU VRAM (used/total GB), CPU core count
- **New fields in `MetricSnapshot`**: `gpu_memory_used_mb`, `gpu_memory_total_mb`, `cpu_cores`, `memory_used_mb`, `memory_total_mb`, `disk_used_gb`, `disk_total_gb`
- **Enhanced SSH collector**: `get_gpu_memory()`, `get_cpu_cores()`, `get_memory_info()`, `get_disk_info()` — return exact values alongside percentages
- **Rich Slack displays**: Status, daily digest, and GPU alerts now show e.g. "RAM: 14.1% (22.9/162.8 GB)" and "Disk: 18% (259/1454 GB)"

### Changed

- Updated VM configurations and metric collection improvements
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
