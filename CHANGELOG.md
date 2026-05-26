# Changelog

All notable changes to this project will be documented in this file.

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
