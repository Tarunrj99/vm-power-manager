# Setup Guide

Complete step-by-step guide to deploy VM Power Manager on GCP Cloud Functions with Slack integration.

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| GCP project with **Compute Engine API** enabled | VM start/stop operations |
| **Ops Agent** installed on managed VMs | Cloud Monitoring metrics (GPU, CPU, memory, disk) |
| SSH key pair (optional) | Fallback metrics + process monitoring. See [METRICS_SETUP.md](METRICS_SETUP.md) |
| Python 3.11+ | Local testing only |
| `gcloud` CLI authenticated | Deployment |
| Slack workspace (admin access recommended) | Bot creation |

---

## Step 1: Create Slack App

1. Go to **https://api.slack.com/apps** → **Create New App** → **From scratch**
2. **App Name**: `VM Power Manager`
3. **Workspace**: select your workspace

### Configure OAuth & Permissions

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages and notifications |
| `commands` | Handle `/vm` slash command |
| `channels:read` | Verify channel membership |

### Install to Workspace

1. Click **Install to Workspace** → **Allow**
2. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### Get Signing Secret

1. Go to **Basic Information**
2. Under **App Credentials**, copy the **Signing Secret**

### Create Slash Command (placeholder URL for now)

1. Go to **Slash Commands** → **Create New Command**
2. Fill in:
   - **Command**: `/vm`
   - **Request URL**: `https://example.com` (updated in Step 5)
   - **Short Description**: `Manage VMs — start, stop, status, extend`
   - **Usage Hint**: `[status|start|stop|extend|help] [vm-name]`

### Enable Interactivity (placeholder URL for now)

1. Go to **Interactivity & Shortcuts**
2. Toggle **Interactivity** → **On**
3. **Request URL**: `https://example.com` (updated in Step 5)
4. Click **Save Changes**

---

## Step 2: Create Private Deployment Directory

The public repo contains only generic examples. Your real config (with project IDs,
VM names, secrets) lives in a **separate private directory** that is never committed.

```bash
# Create deployment dir next to the cloned repo
mkdir ~/vm-power-manager-deploy
cd ~/vm-power-manager-deploy

# Copy example config and customize
cp ../vm-power-manager/config.example.yaml ./config.yaml
# Edit config.yaml with your real project IDs, VM names, channels, users

# Create .env for secrets
cat > .env << 'EOF'
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
EOF
```

---

## Step 3: Edit Configuration

Edit `config.yaml` in your deployment directory:

- Set `state.project` and `state.bucket` to your GCP project and bucket name
- Add your VMs under `vms:` with name, project, zone, GPU type, and notify_users
- Set `slack.default_channel` to your alerts channel
- Adjust `idle_timeout_minutes` and metric thresholds as needed

See [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) for all available options.

---

## Step 4: Deploy to GCP

From your private deployment directory:

```bash
cd ~/vm-power-manager-deploy

# Set environment
export $(grep -v '^#' .env | xargs)
export PROJECT_ID=your-gcp-project-id
export REPO_ROOT=~/vm-power-manager   # path to the cloned public repo

# Run deployment
bash deploy.sh
```

> **Alternatively**, you can use the example script from the repo directly:
> ```bash
> cd ~/vm-power-manager/examples/gcp-cloud-function/
> export PROJECT_ID=your-gcp-project
> export SLACK_BOT_TOKEN=xoxb-...
> export SLACK_SIGNING_SECRET=...
> bash deploy.sh
> ```

The script will:
1. Bundle the library source code
2. Create a GCS bucket for state persistence
3. Create a Pub/Sub topic for scheduled triggers
4. Deploy the **monitor** Cloud Function (Pub/Sub triggered, runs every 10 min)
5. Deploy the **Slack handler** Cloud Function (HTTP triggered, always-on CPU)
6. Create a Cloud Scheduler job

At the end, it prints the **Slack URL**:

```
Slack URL: https://vm-power-slack-XXXXXXX-uc.a.run.app
```

---

## Step 5: Update Slack App with Deployed URL

Go back to **https://api.slack.com/apps** → select your app:

### Update Slash Command

1. **Slash Commands** → click `/vm` → **Edit**
2. Set **Request URL** to the Slack URL printed by `deploy.sh`
3. **Save**

### Update Interactivity

1. **Interactivity & Shortcuts**
2. Set **Request URL** to the same Slack URL
3. **Save Changes**

---

## Step 6: Invite Bot to Channel

In your Slack workspace:

1. Go to the `#vm-alerts` channel (or create it)
2. Type: `/invite @VM Power Manager`

---

## Step 7: Test

Run these commands in Slack to verify:

```
/vm help              — Show available commands
/vm status            — Show all VMs status
/vm status gpu-vm-01     — Show specific VM status
/vm start gpu-vm-01      — Start a VM
/vm stop gpu-vm-01       — Stop a VM
```

---

## Deployed Resources Summary

| Resource | Name | Purpose |
|----------|------|---------|
| Cloud Function (Gen 2) | `vm-power-monitor` | Periodic idle check (every 10 min) |
| Cloud Function (Gen 2) | `vm-power-slack` | Handles Slack commands + button clicks |
| Cloud Scheduler | `vm-power-monitor-job` | Triggers monitor every 10 min |
| Pub/Sub Topic | `vm-power-monitor-trigger` | Connects Scheduler → Monitor |
| GCS Bucket | `${PROJECT_ID}-vm-power-state` | Persists VM state between runs |

---

## Troubleshooting

### "Permission Denied" on `/vm start`

Your Slack username is not in the `notify_users` list for that VM. Update `config.yaml` and redeploy.

### No Slack notifications arriving

1. Check function logs:
   ```bash
   gcloud functions logs read vm-power-monitor --project=YOUR_PROJECT --region=us-central1 --limit=20
   ```
2. Verify the bot is invited to the channel
3. Check that `SLACK_BOT_TOKEN` env var is set correctly on the function

### Metrics showing "—"

| Metric | Fix |
|--------|-----|
| CPU | Always works for running VMs (built-in GCP metric) |
| GPU | Install Ops Agent with GPU plugin **or** configure SSH keys |
| Memory | Install Ops Agent **or** configure SSH keys |
| Disk | Install Ops Agent **or** configure SSH keys |

**Quick fixes:**
1. Install the **Ops Agent** on each VM (see [METRICS_SETUP.md](METRICS_SETUP.md#method-1-gcp-ops-agent))
2. Or configure **SSH keys** for the Cloud Function (see [METRICS_SETUP.md](METRICS_SETUP.md#method-2-ssh-keys-universal))
3. Verify the function's service account has `monitoring.timeSeries.list` permission
4. Metrics populate after the monitor function runs (every 10 min)

### Button clicks not responding

- Verify **Interactivity Request URL** matches the deployed Slack function URL exactly
- Check the `vm-power-slack` function logs for errors

### Cloud Scheduler not triggering

```bash
# Manual trigger to test
gcloud scheduler jobs run vm-power-monitor-job \
  --project=YOUR_PROJECT --location=us-central1
```

### Redeployment

After config changes, redeploy from your private deployment directory:

```bash
cd ~/vm-power-manager-deploy
export $(grep -v '^#' .env | xargs)
bash deploy.sh
```

---

## Deployment Directory Pattern

The recommended setup separates **public code** from **private config**:

```
~/projects/
├── vm-power-manager/            ← Public repo (GitHub)
│   ├── src/vm_power_manager/    ← Library source
│   ├── examples/                ← Generic examples with placeholders
│   ├── docs/                    ← Documentation
│   └── config.example.yaml      ← Template to copy
│
└── vm-power-manager-deploy/     ← Private (never committed)
    ├── .env                     ← SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
    ├── config.yaml              ← Real project IDs, VM names, users
    └── deploy.sh                ← Deploys using public repo source
```

This ensures:
- No org-specific information (project IDs, VM names, usernames) in the public repo
- Secrets never touch git history
- Updating the library = `git pull` + redeploy

---

## Security Notes

- **Never** commit `.env` or credentials to git
- Keep org-specific config (project IDs, VM names) in the private deployment directory
- The Slack Signing Secret is used to verify incoming requests are from Slack
- Cloud Function env vars are encrypted at rest by GCP
- Consider restricting the `vm-power-slack` function to only accept traffic from Slack IPs in production
