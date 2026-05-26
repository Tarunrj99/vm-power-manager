# vm-power-manager

**A cloud-agnostic VM lifecycle automation system.**  
Auto-stops idle VMs based on configurable metrics, sends Slack warnings before shutdown, and lets users control VMs directly from Slack — driven by a single YAML config.

_One library. Any cloud. One config file per deployment._

![python](https://img.shields.io/badge/python-3.11+-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![platform](https://img.shields.io/badge/platform-GCP%20%7C%20AWS%20%7C%20Azure%20%7C%20SSH-lightgrey) ![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

[Quick start](#quick-start--5-minutes) · [Config](#configuration-model) · [Features](#feature-catalog) · [Architecture](#architecture-at-a-glance) · [Deployment](#deployment-recipes) · [Local dev](#local-development) · [Docs](#docs-index)

---

## Why this project exists

GPU VMs are expensive. They get left running overnight, over weekends, during vacations — burning hundreds of dollars while sitting idle at 0% utilization. The usual "solutions" are:

* Manual reminders that nobody follows
* Per-cloud scripts that hardcode thresholds and break when you add a VM
* Cron jobs that don't warn users and kill active work

This repo is the opposite:

* **One library** (`vm_power_manager`) contains all the monitoring, idle detection, process analysis, lifecycle hooks, Slack messaging, access control, and state management.
* **One config file** per deployment defines your VMs, thresholds, users, and channels — no code changes needed.
* **Any runtime** (Cloud Function, Lambda, Cloud Run, or a local FastAPI server) is a ~10-line wrapper that imports the library.
* **Users stay in control** — Slack warnings before shutdown, one-click cancel, manual start/stop, per-VM access control.

Adding a new VM = one entry in `config.yaml`. Changing thresholds = one line edit. No rewriting code.

---

## Table of contents

1. [Requirements](#requirements)
2. [Architecture at a glance](#architecture-at-a-glance)
3. [Repository layout](#repository-layout)
4. [Quick start — 5 minutes](#quick-start--5-minutes)
5. [Configuration model](#configuration-model)
6. [Feature catalog](#feature-catalog)
7. [Deployment recipes](#deployment-recipes)
8. [Local development](#local-development)
9. [Debugging](#debugging)
10. [Extending](#extending)
11. [Docs index](#docs-index)
12. [Contributing](#contributing)
13. [Security](#security)
14. [License](#license)

---

## Requirements

### On your workstation

| Tool | Version | Purpose |
|------|---------|---------|
| Python | **3.11+** | Library runtime |
| pip | any recent | Installs the library from GitHub |
| git | any recent | Cloning and publishing |
| gcloud CLI | latest | Only if deploying on GCP |

### Cloud accounts & permissions

| Cloud | You need |
|-------|----------|
| **GCP** | Project with Compute Engine API, Cloud Monitoring API, Cloud Storage. IAM roles: `roles/compute.instanceAdmin.v1`, `roles/monitoring.viewer`, `roles/storage.objectAdmin`. |
| **AWS** | EC2 + CloudWatch permissions, S3 for state (future). |
| **Any** | Any VM reachable via SSH works with the generic SSH adapter. |

### External services

* **Slack App** with Bot Token — create at [api.slack.com/apps](https://api.slack.com/apps). Scopes: `chat:write`, `commands`, `channels:read`.
* (Optional) GCS bucket for state persistence in production.

### Python dependencies

Declared in `pyproject.toml`:
* Runtime: `pydantic >= 2.0`, `pyyaml >= 6.0`, `google-cloud-compute`, `google-cloud-monitoring`, `google-cloud-storage`, `slack-sdk`, `paramiko`.
* Local dev (`[dev]` extra): `fastapi`, `uvicorn`, `pytest`, `ruff`.

---

## Architecture at a glance

```
┌─────────────────────────┐
│  Trigger                │  Cloud Scheduler · EventBridge · Cron
│  (every 10 min)         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐       ┌──────────────────────────────────┐
│  Runtime wrapper        │──────▶│        vm_power_manager           │
│  (Cloud Function,       │       │                                    │
│   Lambda, FastAPI)      │       │  metrics → idle detect → notify → │
│  ~10 lines of code      │       │  stop/start → lifecycle hooks      │
└─────────────────────────┘       └──────────────┬───────────────────┘
                                                  │
            ┌─────────────────────────────────────┼───────────────┐
            │                                     │               │
            ▼                                     ▼               ▼
┌───────────────────┐            ┌──────────────────┐  ┌─────────────────┐
│  Cloud APIs       │            │  Slack           │  │  State Backend  │
│  (Compute, Mon.)  │            │  (#vm-alerts)    │  │  (GCS/Redis/    │
│  + SSH for procs  │            │                  │  │   File/etc.)    │
└───────────────────┘            └──────────────────┘  └─────────────────┘
```

The wrapper is platform-specific. Everything downstream is cloud-agnostic.

---

## Repository layout

```
vm-power-manager/
├── README.md                        ← you are here
├── LICENSE                          ← MIT
├── pyproject.toml                   ← installable as `vm-power-manager`
├── config.example.yaml              ← the one file users copy & edit
├── Makefile                         ← common dev tasks
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── .env.example
├── .gitignore
│
├── src/vm_power_manager/            ← the library
│   ├── __init__.py                  ← public API: check_idle(), handle_slack()
│   ├── api.py                       ← entry points called by wrappers
│   ├── config.py                    ← YAML loader + 3-layer merge
│   ├── bundled_defaults.yaml        ← ships with package (safe defaults)
│   ├── models.py                    ← Pydantic models (VMConfig, VMState, etc.)
│   ├── monitor.py                   ← idle detection engine
│   ├── process_detector.py          ← smart process detection (watch/exclude)
│   ├── lifecycle.py                 ← pre-stop/post-start hooks
│   ├── adapters/                    ← cloud-specific implementations
│   │   ├── base.py                  ← abstract interfaces
│   │   ├── gcp.py                   ← GCP Compute Engine
│   │   └── ssh.py                   ← generic SSH (any VM)
│   ├── metrics/                     ← metric collection
│   │   ├── monitoring_api.py        ← GCP Cloud Monitoring API
│   │   └── ssh_metrics.py           ← SSH-based (nvidia-smi, ps, free)
│   ├── state/                       ← state persistence
│   │   ├── base.py                  ← abstract interface
│   │   ├── gcs_bucket.py            ← GCP Cloud Storage
│   │   ├── firestore.py             ← GCP Firestore
│   │   ├── redis_state.py           ← Redis
│   │   └── file_state.py            ← local files (dev/testing)
│   └── slack/                       ← Slack integration
│       ├── messages.py              ← Block Kit builders (all message types)
│       ├── commands.py              ← /vm start|stop|status|extend|pause
│       ├── interactions.py          ← button click handler
│       └── access_control.py        ← permission checks
│
├── examples/                        ← deployment-ready starters
│   ├── gcp-cloud-function/          ← GCP Cloud Function (prod)
│   └── local-dev/                   ← FastAPI dev server
│
├── scripts/                         ← helper scripts
│   └── gpu-reservation-setup.sh    ← create GCP GPU reservations
│
├── docs/                            ← deeper docs
│   ├── CONFIG_REFERENCE.md
│   ├── SETUP_GUIDE.md
│   └── GPU_AVAILABILITY.md         ← GPU unavailability guide
│
└── tests/
```

---

## Quick start — 5 minutes

> Goal: get a GCP Cloud Function monitoring your GPU VMs and posting Slack notifications with start/stop buttons.

### 1. Clone this repo

```bash
git clone git@github.com:Tarunrj99/vm-power-manager.git
cd vm-power-manager
```

### 2. Copy the deployment example

```bash
cp -r examples/gcp-cloud-function/ ~/my-vm-manager/
cd ~/my-vm-manager/
```

### 3. Edit `config.yaml`

Update the VMs list, Slack channel, notify_users, and state bucket. Only override what's different from defaults — everything else is inherited.

### 4. Set secrets

```bash
export SLACK_BOT_TOKEN=xoxb-your-bot-token
export SLACK_SIGNING_SECRET=your-signing-secret
```

### 5. Deploy

```bash
export PROJECT_ID=your-gcp-project
./deploy.sh
```

### 6. Wire Slack

Copy the deployed function URL and set it as the Request URL for your `/vm` slash command and Interactivity in the Slack App settings.

Full step-by-step: [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md).

---

## Configuration model

There are **two** YAML files in the whole system, and you only ever edit one:

| File | Lives in | Purpose | Edited by |
|------|----------|---------|-----------|
| `src/vm_power_manager/bundled_defaults.yaml` | Inside the package | Safe defaults — auto-stop off, sane thresholds | Library maintainers |
| `config.yaml` | Next to your function | Your overrides | You |

The library deep-merges them at startup: `defaults ← your config`. Any key you don't set is inherited from defaults, so `config.yaml` stays small and focused.

Top-level sections (all documented in [config.example.yaml](config.example.yaml)):

```yaml
app:        # environment, debug mode, dry run
slack:      # bot token env var, default channel, access control mode
defaults:   # idle thresholds, process monitoring, lifecycle hooks, notifications
state:      # backend choice: gcs_bucket | firestore | redis | file
vms:        # list of managed VMs with per-VM overrides
```

Full reference: [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md).

---

## Feature catalog

| Feature | What it does | Status |
|---------|-------------|--------|
| Idle detection | Monitors GPU/CPU/memory/processes, triggers warnings | stable |
| Smart process detection | Distinguishes app processes from system services | stable |
| Slack warnings | 5-min countdown with Keep Running / Stop Now buttons | stable |
| Manual start/stop | `/vm start <name>`, `/vm stop <name>` from Slack | stable |
| Per-VM access control | Only authorized users can control each VM | stable |
| Lifecycle hooks | Pre-stop/post-start commands, auto-upgrade prevention | stable |
| Extend/Pause | `/vm extend <name> 30`, `/vm pause <name>` | stable |
| **GPU availability protection** | Pre-stop warning, multi-zone retry, auto-migrate on start | stable |
| Daily summary | Overview of all VMs posted at configured time | stable |
| Multiple state backends | GCS, Firestore, S3, DynamoDB, Redis, File | stable |

---

## Deployment recipes

| Cloud | Runtime | Trigger | State Backend | Folder |
|-------|---------|---------|---------------|--------|
| GCP | Cloud Function (Gen 2) | Cloud Scheduler → Pub/Sub | GCS Bucket | `examples/gcp-cloud-function/` |
| AWS | Lambda | EventBridge | S3 (future) | pattern identical |
| Local | FastAPI | HTTP POST | File | `examples/local-dev/` |

Every recipe has the same shape: wrapper + `requirements.txt` + `config.yaml` + `deploy.sh`. The wrapper is never more than ~10 lines.

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Run the debug server:

```bash
cd examples/local-dev/
pip install -r requirements.txt
export SLACK_BOT_TOKEN=xoxb-...
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
python app.py
```

Trigger a monitoring check:

```bash
curl -sX POST http://localhost:8080/monitor | python -m json.tool
```

---

## Debugging

* Set `app.debug_mode: true` — verbose logging of every metric collection and decision.
* Set `app.dry_run: true` — runs full monitoring but doesn't actually stop VMs or send Slack messages.
* Check state directly: `gsutil cat gs://your-bucket/state/vm-name.json` (or inspect `./state/` locally).
* Cloud Function logs: `gcloud functions logs read vm-power-monitor --project=YOUR_PROJECT`

---

## Extending

### Add a new VM

One entry in `config.yaml`:

```yaml
vms:
  - name: "my-new-vm"
    cloud: "gcp"
    gcp_name: "my-new-vm"
    project: "my-project"
    zone: "us-central1-a"
    notify_users: ["@myuser"]
```

### Add a new cloud adapter

1. Create `src/vm_power_manager/adapters/your_cloud.py` implementing `VMAdapter`.
2. Add a lazy import in `monitor.py` `_get_vm_adapter()`.
3. Copy an example folder and adjust the wrapper.

### Add a new state backend

1. Create `src/vm_power_manager/state/your_backend.py` implementing `StateBackend`.
2. Add a case in `state/__init__.py` `create_state_backend()`.

---

## Docs index

| Doc | Topic |
|-----|-------|
| [CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) | Every config key, with examples |
| [SETUP_GUIDE.md](docs/SETUP_GUIDE.md) | End-to-end: GCP + Slack setup |
| [GPU_AVAILABILITY.md](docs/GPU_AVAILABILITY.md) | GPU unavailability after stop: problem, prevention, fallback |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, PR checklist |
| [SECURITY.md](SECURITY.md) | Disclosure policy |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

---

## Contributing

PRs and issues are very welcome. The short version:

1. Fork the repo and create a feature branch.
2. `make venv && make test && make lint` — everything must be green.
3. Open a PR against `main` with a clear title.

Full checklist in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Security

No secrets ever live in `config.yaml`: Slack tokens and signing secrets are always read from environment variables that the config _names_. If you find a security issue, please do **not** open a public issue — follow the disclosure process in [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE). Use it freely inside your organisation or as the base for your own VM management layer.
