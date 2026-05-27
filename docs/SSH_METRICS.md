# SSH Metrics & Credentials

VM Power Manager collects metrics from two sources:
1. **GCP Cloud Monitoring API** (default) — requires Ops Agent on VMs
2. **SSH fallback** — connects directly to VMs for `nvidia-smi`, `free`, `df`, process lists

---

## How Metrics Are Collected

| Metric | Primary Source | Fallback | Requirement |
|--------|---------------|----------|-------------|
| CPU | Cloud Monitoring (`compute.googleapis.com/instance/cpu/utilization`) | SSH | Built-in (always works for running VMs) |
| GPU | Cloud Monitoring (`custom.googleapis.com/gpu/utilization`) | SSH (`nvidia-smi`) | Ops Agent with GPU plugin **or** SSH key |
| Memory | Cloud Monitoring (`agent.googleapis.com/memory/percent_used`) | SSH (`free -m`) | Ops Agent **or** SSH key |
| Disk | Cloud Monitoring (`agent.googleapis.com/disk/percent_used`) | SSH (`df /`) | Ops Agent **or** SSH key |
| Processes | SSH only | — | SSH key required |

**If a metric shows "—"**, it means both the Monitoring API and SSH fallback failed.

---

## Why Metrics Show "—"

Common reasons:

1. **Ops Agent not installed** — GPU, memory, and disk metrics need the Ops Agent running on the VM
2. **SSH keys not configured** — the fallback can't connect without credentials
3. **VM is stopped** — no metrics available for stopped instances
4. **Firewall rules** — SSH port (22) blocked from Cloud Function's network

---

## Option A: Install Ops Agent (Recommended for Cloud Functions)

The easiest way to get all metrics without SSH keys. Install on each managed VM:

```bash
# SSH into the VM
gcloud compute ssh VM_NAME --zone=ZONE --project=PROJECT

# Install Ops Agent
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install

# For GPU metrics, add nvidia-smi plugin
sudo tee /etc/google-cloud-ops-agent/config.yaml > /dev/null << 'EOF'
metrics:
  receivers:
    gpu:
      type: nvml
  service:
    pipelines:
      gpu:
        receivers:
          - gpu
EOF

sudo systemctl restart google-cloud-ops-agent
```

Verify metrics appear in Cloud Monitoring Explorer within ~2 minutes.

---

## Option B: Configure SSH Keys (For Full Metrics + Process Monitoring)

Required for process monitoring and as a fallback when Ops Agent isn't available.

### Step 1: Generate SSH Key Pair

```bash
ssh-keygen -t rsa -b 4096 -f vm-power-manager-key -N "" -C "vm-power-manager"
```

This creates:
- `vm-power-manager-key` — private key (keep secret)
- `vm-power-manager-key.pub` — public key (deploy to VMs)

### Step 2: Add Public Key to VMs

**Project-level** (applies to all VMs in the project):

```bash
gcloud compute project-info add-metadata \
  --metadata-from-file ssh-keys=<(
    echo "vm-power-manager:$(cat vm-power-manager-key.pub)"
  ) \
  --project=YOUR_PROJECT
```

**Per-VM** (more restrictive):

```bash
gcloud compute instances add-metadata VM_NAME \
  --metadata-from-file ssh-keys=<(
    echo "vm-power-manager:$(cat vm-power-manager-key.pub)"
  ) \
  --zone=ZONE --project=YOUR_PROJECT
```

### Step 3: Configure Cloud Function Environment

For Cloud Functions, store the private key as an environment variable:

```bash
# Set during deployment
gcloud functions deploy vm-power-monitor \
  --set-env-vars="VM_SSH_KEY=$(cat vm-power-manager-key)" \
  ...
```

Or use GCP Secret Manager (recommended for production):

```bash
# Create secret
gcloud secrets create vm-power-ssh-key \
  --data-file=vm-power-manager-key \
  --project=YOUR_PROJECT

# Reference in Cloud Function
gcloud functions deploy vm-power-monitor \
  --set-secrets="VM_SSH_KEY=vm-power-ssh-key:latest" \
  ...
```

### Step 4: Update config.yaml

```yaml
defaults:
  ssh_user: "vm-power-manager"
  ssh_key_env: "VM_SSH_KEY"    # env var name containing key path or key content
  ssh_port: 22

  metric_sources:
    gpu_utilization: "monitoring_api"   # tries API first, falls back to SSH
    cpu_utilization: "monitoring_api"
    memory_utilization: "monitoring_api"
    disk_utilization: "monitoring_api"
    process_count: "ssh"               # always requires SSH
```

---

## SSH Key Handling

The SSH adapter supports two modes for the key referenced by `ssh_key_env`:

| Value of env var | Behavior |
|-----------------|----------|
| File path (e.g., `/path/to/key`) | Uses the file directly |
| Key content (the actual private key text) | Loads key from memory (for serverless) |

This means in Cloud Functions, you can store the entire private key content in the environment variable — no filesystem needed.

---

## For GCP VMs: Automatic IP Resolution

When `ssh_host` is not set in a VM's config, the SSH adapter automatically resolves the VM's external IP from the GCP Compute API. You don't need to hardcode IPs.

---

## Network Requirements

For SSH to work from Cloud Functions:

1. **VMs must have external IPs** — or be reachable via VPC connector
2. **Firewall rule** allowing port 22 from Cloud Functions' egress IP range
3. **SSH key** must be authorized on the target VM

If using private IPs only, configure a [VPC connector](https://cloud.google.com/vpc/docs/configure-serverless-vpc-access) on the Cloud Function.

---

## Metric Source Priority

The system uses a **fallback chain**:

```
Monitoring API → SSH → None (shows "—")
```

- If Monitoring API returns data, SSH is never attempted
- SSH is only used when Monitoring API returns `None`
- If both fail, the metric displays as "—"

---

## Quick Diagnosis

```bash
# Check if Ops Agent is reporting metrics
gcloud monitoring metrics list --project=YOUR_PROJECT \
  --filter='metric.type = starts_with("agent.googleapis.com")'

# Check if VM has external IP
gcloud compute instances describe VM_NAME --zone=ZONE --project=PROJECT \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

# Test SSH connectivity manually
ssh -i vm-power-manager-key vm-power-manager@EXTERNAL_IP "echo ok"

# Check GPU metrics specifically
ssh -i vm-power-manager-key vm-power-manager@EXTERNAL_IP "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits"
```
