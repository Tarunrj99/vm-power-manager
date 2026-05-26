# GPU Availability After Stopping a VM

## The Problem

When you **stop** a GCP VM with a GPU attached, the GPU allocation is **released back to the shared pool** in that zone. When you try to restart the VM later, the zone may have run out of GPU capacity, resulting in:

```
ZONE_RESOURCE_POOL_EXHAUSTED: The zone does not have enough resources
available to fulfill the request. Try a different zone, or try again later.
```

This is a well-known GCP limitation that affects all GPU types — especially high-demand models like A100, L4, and H100.

### Why can't I just suspend the VM?

GCP **does not support suspending GPU instances**. Suspend preserves state and keeps the resource allocated, but it explicitly fails on any instance with GPUs attached. The only way to save costs on an idle GPU VM is to stop it — which releases the GPU.

### How common is this?

Very common. GPU capacity in popular zones (us-central1, us-east1, europe-west4) is frequently exhausted. Users have reported being unable to restart VMs for **days or weeks** during high-demand periods.

---

## How VM Power Manager Handles This

### 1. Pre-Stop GPU Warning

When you run `/vm stop <name>`, the system checks if the VM has a GPU and whether a reservation exists:

- **Reservation found** → Stop proceeds normally (GPU is guaranteed on restart)
- **No reservation** → A warning is shown with "Stop Anyway" and "Keep Running" buttons

This prevents accidental GPU loss from casual stop commands.

### 2. Smart Start with Retry + Fallback

When you run `/vm start <name>`:

1. **Retry in original zone** — Attempts to start N times with configurable delay (GPU capacity fluctuates)
2. **Fallback zones** — If configured, tries starting in alternative zones
3. **Auto-migrate** — If enabled, automatically migrates the VM to a zone with available GPUs
4. **Clear error reporting** — If all attempts fail, provides actionable next steps

### 3. Configuration

```yaml
defaults:
  gpu_protection:
    enabled: true
    check_before_stop: true        # Show warning before stopping GPU VMs
    fallback_zones: []             # Default fallback zones (override per-VM)
    max_start_retries: 3           # Retry in same zone before giving up
    retry_delay_seconds: 30        # Wait between retries
    auto_migrate: false            # Auto-migrate to fallback zone on failure
    notify_on_zone_change: true    # Alert when VM moves to a different zone

vms:
  - name: "my-gpu-vm"
    gpu_protection:
      fallback_zones: ["us-central1-b", "us-central1-c", "us-central1-f"]
      auto_migrate: true           # Allow automatic zone migration for this VM
```

---

## Prevention Strategies

### Option 1: GPU Reservation (Recommended for critical VMs)

A reservation **guarantees** GPU capacity in a specific zone. You pay for the reservation whether the VM is running or not, but you're guaranteed to be able to start.

```bash
# Create a reservation for 1 T4 GPU
gcloud compute reservations create my-vm-gpu-reserve \
  --vm-count=1 \
  --machine-type=n1-standard-8 \
  --accelerator=count=1,type=nvidia-tesla-t4 \
  --zone=us-central1-a \
  --project=YOUR_PROJECT

# Verify
gcloud compute reservations describe my-vm-gpu-reserve \
  --zone=us-central1-a --project=YOUR_PROJECT
```

**Cost**: You pay for the reserved GPU even when the VM is stopped. However, this is often cheaper than leaving the entire VM running idle (no CPU/memory charges).

### Option 2: Committed Use Discounts (CUDs)

If you plan to use GPUs long-term (1 or 3 years), CUDs provide:
- Guaranteed capacity
- 37%-57% discount on GPU pricing

```bash
gcloud compute commitments create my-gpu-commitment \
  --region=us-central1 \
  --resources=type=nvidia-tesla-a100,count=1 \
  --plan=12-month \
  --project=YOUR_PROJECT
```

### Option 3: Fallback Zones (Free, but not guaranteed)

Configure multiple zones so the system can try alternatives:

```yaml
vms:
  - name: "gpu-vm-01"
    zone: "us-central1-a"
    gpu_protection:
      fallback_zones:
        - "us-central1-b"
        - "us-central1-c"
        - "us-central1-f"
        - "us-west1-a"
        - "us-west1-b"
      auto_migrate: true
```

This is free but not guaranteed — all zones could be exhausted simultaneously.

### Option 4: Keep VM Running (Most Expensive)

For truly critical VMs, simply disable auto-stop:

```yaml
vms:
  - name: "critical-gpu-vm"
    auto_stop_enabled: false
```

---

## Cost Comparison

| Strategy | Monthly Cost (A100) | GPU Guaranteed? | Complexity |
|----------|-------------------|-----------------|------------|
| Keep running 24/7 | ~$2,500/month | Yes | None |
| Reservation (stopped) | ~$800/month | Yes | Low |
| CUD (1-year) | ~$1,100/month | Yes | Low |
| Fallback zones | $0 extra | No | Medium |
| No protection | $0 extra | No | High risk |

*Costs are approximate and vary by region/GPU type. Check [GCP pricing](https://cloud.google.com/compute/gpus-pricing) for current rates.*

---

## Troubleshooting

### VM won't start — GPU unavailable

1. **Check current availability**: 
   ```bash
   gcloud compute accelerator-types list --filter="zone:us-central1" --project=YOUR_PROJECT
   ```

2. **Try a different zone**:
   ```bash
   gcloud compute instances move MY_VM \
     --zone=us-central1-a \
     --destination-zone=us-central1-c \
     --project=YOUR_PROJECT
   ```

3. **Check if reservation exists**:
   ```bash
   gcloud compute reservations list --project=YOUR_PROJECT
   ```

4. **Create a reservation for the future**:
   ```bash
   # See scripts/gpu-reservation-setup.sh for a helper
   ```

### VM was auto-migrated to a different zone

If `auto_migrate: true` is configured and a fallback zone was used, the VM Power Manager will:
1. Notify via Slack with the new zone
2. Store the migration info in state
3. Future operations will use the new zone

To move back to the original zone when capacity returns:
```bash
gcloud compute instances move MY_VM \
  --zone=CURRENT_ZONE \
  --destination-zone=ORIGINAL_ZONE \
  --project=YOUR_PROJECT
```

---

## References

- [GCP: Troubleshooting resource availability](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability)
- [GCP: Reserving zonal resources](https://cloud.google.com/compute/docs/instances/reserving-zonal-resources)
- [GCP: Committed use discounts for GPUs](https://cloud.google.com/compute/docs/gpus#reserving_gpus_with_committed_use_discounts)
- [GCP: Moving instances across zones](https://cloud.google.com/compute/docs/instances/moving-instance-across-zones)
