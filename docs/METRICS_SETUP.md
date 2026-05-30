# Metric Collection Guide

VM Power Manager collects VM metrics (GPU, CPU, memory, disk, processes) to determine idle state and display status. This guide covers all supported collection methods for any environment.

---

## Overview: How Metrics Are Collected

The system uses a **fallback chain**:

```
Cloud Monitoring API → SSH → None (shows "—")
```

- Primary source is tried first (configurable per metric)
- If primary fails, SSH fallback is attempted
- If both fail, the metric displays as "—" in Slack

| Metric | What It Measures | Command Used (SSH) | Cloud API Metric |
|--------|-----------------|-------------------|-----------------|
| GPU | GPU utilization % | `nvidia-smi` | `custom.googleapis.com/gpu/utilization` |
| CPU | CPU usage % | `top -bn1` | `compute.googleapis.com/instance/cpu/utilization` |
| Memory | RAM usage % | `free -m` | `agent.googleapis.com/memory/percent_used` |
| Disk | Root partition usage % | `df /` | `agent.googleapis.com/disk/percent_used` |
| Processes | Active user processes | `ps aux` | Not available (SSH only) |

---

## Choose Your Setup

| Your Environment | Recommended Method | Setup Time |
|-----------------|-------------------|-----------|
| **GCP VMs + Cloud Functions** | [Ops Agent](#method-1-gcp-ops-agent) | ~2 min per VM |
| **AWS EC2 + Lambda** | [SSH Keys](#method-2-ssh-keys-universal) | ~10 min |
| **Azure VMs** | [SSH Keys](#method-2-ssh-keys-universal) | ~10 min |
| **On-premise / Local VMs** | [SSH Keys](#method-2-ssh-keys-universal) | ~10 min |
| **Mixed environments** | [SSH Keys](#method-2-ssh-keys-universal) | ~10 min |
| **GCP VMs + need process monitoring** | Ops Agent + [SSH Keys](#method-2-ssh-keys-universal) | ~15 min |

---

## Method 1: GCP Ops Agent

### What Is It?

The **Google Cloud Ops Agent** is a lightweight background service that runs on your GCP VM. It automatically collects system metrics and sends them to Google Cloud Monitoring — a centralized API that our Cloud Function can query.

```
┌─────────────────────────┐       ┌──────────────────────┐       ┌─────────────────┐
│  Your GCP VM            │       │  Cloud Monitoring    │       │  Cloud Function │
│                         │       │  (Google managed)    │       │  (our code)     │
│  ┌───────────────────┐  │       │                      │       │                 │
│  │ Ops Agent         │──┼──────▶│  Stores metrics      │◀──────┼─ Queries API    │
│  │ (reads nvidia-smi,│  │ push  │  (GPU, CPU, MEM,     │ pull  │                 │
│  │  /proc, df, etc.) │  │       │   Disk every ~60s)   │       │                 │
│  └───────────────────┘  │       └──────────────────────┘       └─────────────────┘
└─────────────────────────┘
```

### Why It's Easy

- **One install command** — no SSH keys, no firewall changes, no network config
- **Automatic** — once installed, it pushes metrics every 60 seconds forever
- **Secure** — the VM pushes data OUT; nothing needs to connect IN
- **Zero maintenance** — auto-updates, survives reboots

### Limitations

- **GCP only** — won't work on AWS, Azure, or local machines
- **No process monitoring** — can't list running processes (SSH needed for that)
- **GPU needs extra config** — base install covers CPU/memory/disk; GPU needs NVML plugin

### Installation (Per VM)

```bash
# 1. SSH into the VM
gcloud compute ssh VM_NAME --zone=ZONE --project=PROJECT

# 2. Install the Ops Agent (one command)
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install

# 3. Enable GPU metrics (only needed for VMs with NVIDIA GPUs)
sudo tee /etc/google-cloud-ops-agent/config.yaml > /dev/null << 'EOF'
metrics:
  receivers:
    hostmetrics:
      type: hostmetrics
    gpu:
      type: nvml
  service:
    pipelines:
      default:
        receivers:
          - hostmetrics
      gpu:
        receivers:
          - gpu
EOF

# 4. Restart the agent
sudo systemctl restart google-cloud-ops-agent

# 5. Verify it's running
sudo systemctl status google-cloud-ops-agent
```

### Verify Metrics Are Flowing

After ~2 minutes, check in Cloud Console:
1. Go to **Monitoring → Metrics Explorer**
2. Search for `agent.googleapis.com/memory/percent_used`
3. Filter by your VM instance
4. You should see data points

Or via CLI:
```bash
gcloud monitoring time-series list \
  --project=YOUR_PROJECT \
  --filter='metric.type="agent.googleapis.com/memory/percent_used" AND resource.labels.instance_id="INSTANCE_ID"' \
  --limit=1
```

### What Each Metric Requires

| Metric | Ops Agent Base Install | GPU Plugin Needed | Notes |
|--------|----------------------|-------------------|-------|
| CPU | Built-in GCP (no agent needed) | No | `compute.googleapis.com/instance/cpu/utilization` is automatic |
| Memory | Yes | No | Reported as `agent.googleapis.com/memory/percent_used` |
| Disk | Yes | No | Reported as `agent.googleapis.com/disk/percent_used` |
| GPU | Yes | **Yes** (nvml receiver) | Needs NVIDIA drivers + NVML library on VM |
| Processes | **Not supported** | — | Requires SSH method |

### Uninstall (If Needed)

```bash
sudo apt-get remove google-cloud-ops-agent   # Debian/Ubuntu
sudo yum remove google-cloud-ops-agent       # RHEL/CentOS
```

---

## Method 2: SSH Keys (Universal)

### What Is It?

SSH-based metric collection connects directly to your VMs and runs commands (`nvidia-smi`, `free`, `df`, `ps`) to get real-time metrics. It works on **any VM** regardless of cloud provider.

```
┌─────────────────┐                    ┌─────────────────────────┐
│  Cloud Function │                    │  Your VM (any cloud)    │
│  (or local)     │                    │                         │
│                 │   SSH (port 22)    │  Runs: nvidia-smi       │
│  Has: private   │───────────────────▶│        free -m          │
│       key       │   authenticated    │        df /             │
│                 │◀───────────────────│        ps aux           │
└─────────────────┘   returns output   └─────────────────────────┘
```

### Why Use SSH?

- **Works everywhere** — GCP, AWS, Azure, DigitalOcean, on-premise, local VMs
- **Full metrics** — including process lists (the only way to get processes)
- **Real-time** — no delay, queries metrics on demand
- **No vendor lock-in** — standard SSH protocol

### Requirements

1. **SSH key pair** (private + public key)
2. **Public key deployed** on target VMs
3. **Network path** — port 22 reachable from where the code runs
4. **SSH user** with read permissions for system commands

### Setup

#### Step 1: Generate SSH Key Pair

```bash
# Generate a dedicated key (no passphrase for automation)
ssh-keygen -t rsa -b 4096 -f vm-power-manager-key -N "" -C "vm-power-manager"
```

Creates two files:
- `vm-power-manager-key` — **private key** (keep this secret, give to Cloud Function)
- `vm-power-manager-key.pub` — **public key** (deploy on every managed VM)

#### Step 2: Deploy Public Key to VMs

**On GCP** (project-wide — applies to all VMs):
```bash
gcloud compute project-info add-metadata \
  --metadata-from-file ssh-keys=<(
    echo "vm-power-manager:$(cat vm-power-manager-key.pub)"
  ) \
  --project=YOUR_PROJECT
```

**On GCP** (single VM):
```bash
gcloud compute instances add-metadata VM_NAME \
  --metadata-from-file ssh-keys=<(
    echo "vm-power-manager:$(cat vm-power-manager-key.pub)"
  ) \
  --zone=ZONE --project=YOUR_PROJECT
```

**On AWS EC2:**
```bash
# Append public key to authorized_keys on the instance
cat vm-power-manager-key.pub >> ~/.ssh/authorized_keys
```

**On any Linux VM:**
```bash
# Create user and add key
sudo useradd -m -s /bin/bash vm-power-manager
sudo mkdir -p /home/vm-power-manager/.ssh
sudo cp vm-power-manager-key.pub /home/vm-power-manager/.ssh/authorized_keys
sudo chown -R vm-power-manager:vm-power-manager /home/vm-power-manager/.ssh
sudo chmod 700 /home/vm-power-manager/.ssh
sudo chmod 600 /home/vm-power-manager/.ssh/authorized_keys
```

#### Step 3: Give Private Key to the Application

**For GCP Cloud Functions** (env var with key content):
```bash
gcloud functions deploy vm-power-monitor \
  --set-env-vars="VM_SSH_KEY=$(cat vm-power-manager-key)" \
  --region=us-central1 --project=YOUR_PROJECT
```

**For GCP Cloud Functions** (Secret Manager — recommended for production):
```bash
# Store key as a secret
gcloud secrets create vm-power-ssh-key \
  --data-file=vm-power-manager-key \
  --project=YOUR_PROJECT

# Deploy function with secret reference
gcloud functions deploy vm-power-monitor \
  --set-secrets="VM_SSH_KEY=vm-power-ssh-key:latest" \
  --region=us-central1 --project=YOUR_PROJECT
```

**For self-hosted / local deployment:**
```bash
# Just set the env var to the file path
export VM_SSH_KEY=/path/to/vm-power-manager-key
```

#### Step 4: Update config.yaml

```yaml
defaults:
  ssh_user: "vm-power-manager"    # username matching the public key
  ssh_key_env: "VM_SSH_KEY"       # env var name (holds path or key content)
  ssh_port: 22

  metric_sources:
    gpu_utilization: "monitoring_api"   # tries Cloud Monitoring first, SSH fallback
    cpu_utilization: "monitoring_api"
    memory_utilization: "monitoring_api"
    disk_utilization: "monitoring_api"
    process_count: "ssh"               # only available via SSH
```

Or if you want SSH as primary (for non-GCP environments):
```yaml
defaults:
  ssh_user: "ubuntu"
  ssh_key_env: "VM_SSH_KEY"

  metric_sources:
    gpu_utilization: "ssh"
    cpu_utilization: "ssh"
    memory_utilization: "ssh"
    disk_utilization: "ssh"
    process_count: "ssh"
```

#### Step 5: Verify SSH Works

```bash
# Test manually from your machine
ssh -i vm-power-manager-key vm-power-manager@VM_EXTERNAL_IP "echo OK"

# Test GPU metric
ssh -i vm-power-manager-key vm-power-manager@VM_EXTERNAL_IP \
  "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits"

# Test memory
ssh -i vm-power-manager-key vm-power-manager@VM_EXTERNAL_IP "free -m"

# Test disk
ssh -i vm-power-manager-key vm-power-manager@VM_EXTERNAL_IP "df / --output=pcent | tail -1"
```

---

## SSH Key Handling (How the Code Uses Keys)

The `ssh_key_env` config points to an environment variable. The system handles two formats automatically:

| Env Var Contains | How It's Used |
|-----------------|---------------|
| A file path (e.g., `/home/user/.ssh/key`) | Reads key from that file |
| Actual key content (starts with `-----BEGIN`) | Loads key directly from memory |

This means:
- **Local/self-hosted**: set `VM_SSH_KEY=/path/to/key` (file path)
- **Cloud Functions/Lambda**: set `VM_SSH_KEY=<actual key content>` (inline)

---

## GCP VMs: Automatic IP Resolution

When using the GCP cloud adapter, you don't need to set `ssh_host` for each VM. The SSH adapter automatically looks up the VM's external IP from the Compute API using the `project`, `zone`, and `name` from your config.

For non-GCP VMs, you must set `ssh_host` explicitly:

```yaml
vms:
  - name: my-aws-instance
    cloud: ssh
    ssh_host: "54.123.45.67"    # required for non-GCP
    ssh_user: "ubuntu"
```

---

## Network Requirements

### From Cloud Functions (Serverless)

| Requirement | How to Satisfy |
|------------|----------------|
| VM has external IP | Default for most VMs |
| Firewall allows port 22 | Add ingress rule for `0.0.0.0/0` on port 22 (or Cloud Function NAT IP range) |
| SSH key authorized | Deploy public key (Step 2 above) |

### From Self-Hosted (Same Network)

If running on the same VPC/network as your VMs, use internal IPs:
```yaml
vms:
  - name: my-vm
    ssh_host: "10.0.1.5"    # internal IP
```

No firewall changes needed if same VPC.

---

## Troubleshooting

### "—" for GPU metrics

If GPU metrics show "—" in Slack, the system cannot read GPU data. This requires `nvidia-smi` to be functional on the VM.

**Prerequisites for GPU metrics:**

1. **NVIDIA drivers must be installed** on the VM
2. **The nvidia kernel module must be loaded** (`lsmod | grep nvidia`)
3. **`nvidia-smi` must return data** when run by the SSH user

**Common issue: Driver installed but kernel module not loaded**

After a kernel update, the NVIDIA kernel module may fail to load. Symptoms:
- `nvidia-smi` says "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver"
- `lsmod | grep nvidia` returns nothing
- `lspci | grep -i nvidia` shows the GPU hardware exists

**Fix:**

```bash
# Load the module manually
sudo modprobe nvidia

# Verify it works
nvidia-smi

# Make it load on every boot
echo 'nvidia' | sudo tee /etc/modules-load.d/nvidia.conf
```

**If `modprobe nvidia` fails with "Module not found":**

```bash
# Install kernel headers for your current kernel
sudo apt-get install linux-headers-$(uname -r)

# Rebuild DKMS module
sudo dkms install nvidia/$(dkms status | grep nvidia | head -1 | awk -F',' '{print $1}' | awk -F'/' '{print $2}')

# Then load and persist
sudo modprobe nvidia
echo 'nvidia' | sudo tee /etc/modules-load.d/nvidia.conf
```

**If no NVIDIA packages are installed at all:**

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install nvidia-driver-535 nvidia-utils-535

# Then load and persist
sudo modprobe nvidia
echo 'nvidia' | sudo tee /etc/modules-load.d/nvidia.conf
```

**Verify everything works:**
```bash
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,name --format=csv,noheader
# Should output something like: 0 %, 2 MiB, 15360 MiB, Tesla T4
```

### "—" for Memory/Disk

1. **For Ops Agent**: Check `sudo systemctl status google-cloud-ops-agent`
2. **For SSH**: Verify connectivity with `ssh -i KEY USER@IP "free -m"`

### SSH "Temporary failure in name resolution"

The system can't resolve the VM hostname. Either:
- Set `ssh_host` to the VM's IP address explicitly, or
- For GCP VMs, ensure `project` and `zone` are set correctly in config

### SSH "Permission denied"

- Public key not deployed on VM
- Wrong `ssh_user` in config
- Key permissions too open (must be `chmod 600`)

### SSH "Connection timed out"

- Firewall blocking port 22
- VM doesn't have external IP
- Wrong IP address

---

## Quick Reference

```bash
# === Ops Agent (GCP) ===
# Install
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install

# Check status
sudo systemctl status google-cloud-ops-agent

# View agent logs
sudo journalctl -u google-cloud-ops-agent -f

# === SSH Verification ===
# Test connection
ssh -i KEY USER@IP "echo ok"

# Test all metrics at once
ssh -i KEY USER@IP "echo '=GPU='; nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo N/A; echo '=CPU='; top -bn1 | grep 'Cpu(s)' | awk '{print \$2}'; echo '=MEM='; free | awk '/Mem:/{printf \"%.1f\", \$3/\$2*100}'; echo; echo '=DISK='; df / --output=pcent | tail -1"

# === Cloud Monitoring (GCP) ===
# Check if metrics exist
gcloud monitoring time-series list --project=PROJECT \
  --filter='metric.type="agent.googleapis.com/memory/percent_used"' --limit=1
```
