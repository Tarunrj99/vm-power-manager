# Changelog

All notable changes to this project will be documented in this file.

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
