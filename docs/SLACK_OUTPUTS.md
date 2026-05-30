# Slack Output Examples

Below are examples of all Slack messages the system generates. These use sample/placeholder data — your actual output will reflect your VM names, metrics, and configuration.

---

## `/vm status` — Real-Time Status Overview

```
┌─────────────────────────────────────────────────────────┐
│  VM Status Overview                                     │
├─────────────────────────────────────────────────────────┤
│  ⚡ GPU VMs                                             │
│                                                         │
│  🟢 ml-training-gpu-01                                  │
│                                                         │
│  Status: Running                                        │
│  Running Since: May 29, 2026 10:30 AM (1d 14h)         │
│                                                         │
│  GPU Model: nvidia-tesla-t4                             │
│  GPU Util: 72.3%                                        │
│  GPU Memory: 9.8/15.0 GB                                │
│                                                         │
│  CPU: 34.2% (4 cores)                                   │
│  RAM: 48.9% (79.5/162.8 GB)                             │
│  Disk: 77.0% (155/200 GB)                               │
│  Processes: 3 active                                    │
│  IP: 34.123.45.67                                       │
│─────────────────────────────────────────────────────────│
│  🔴 inference-gpu-02                                    │
│                                                         │
│  Status: Stopped                                        │
│                                                         │
│  GPU Model: nvidia-tesla-a100                           │
│  GPU Util: —                                            │
│  GPU Memory: —                                          │
│                                                         │
│  CPU: —                                                 │
│  RAM: —                                                 │
│  Disk: —                                                │
│  Processes: 0 active                                    │
│  IP: —                                                  │
│─────────────────────────────────────────────────────────│
│  🖥️ Standard VMs                                        │
│                                                         │
│  🟢 staging-api-server                                  │
│                                                         │
│  Status: Running                                        │
│  Running Since: May 28, 2026 9:00 AM (2d 15h)          │
│                                                         │
│  CPU: 12.1% (2 cores)                                   │
│  RAM: 31.4% (2.5/8.0 GB)                               │
│  Disk: 45.0% (18/40 GB)                                │
│  Processes: 5 active                                    │
│  IP: 35.200.10.22                                       │
│─────────────────────────────────────────────────────────│
│  🕐 Updated at May 30, 2026 11:45 PM                   │
└─────────────────────────────────────────────────────────┘
```

---

## Daily VM Report (9 AM)

```
┌─────────────────────────────────────────────────────────┐
│  📊 Daily VM Report                                     │
├─────────────────────────────────────────────────────────┤
│  💬 Daily overview of all managed VMs. If you're using  │
│  a VM listed here, please review and stop it if not     │
│  actively in use — to save costs.                       │
│─────────────────────────────────────────────────────────│
│  ⚡ GPU VMs                                             │
│                                                         │
│  🟢 ml-training-gpu-01                                  │
│                                                         │
│  Status: Running                                        │
│  Running Since: May 29, 2026 10:30 AM (23h 15m)        │
│                                                         │
│  GPU Model: nvidia-tesla-t4                             │
│  GPU Util: 0.5%                                         │
│  GPU Memory: 0.4/15.0 GB                                │
│                                                         │
│  CPU: 2.1% (4 cores)                                    │
│  RAM: 12.3% (20.0/162.8 GB)                             │
│  Disk: 77.0% (155/200 GB)                               │
│  Processes: 0 active                                    │
│  IP: 34.123.45.67                                       │
│                                                         │
│  🛑 To stop this VM: /vm stop ml-training-gpu-01        │
│  cc: @alice @bob                                        │
│─────────────────────────────────────────────────────────│
│  🖥️ Standard VMs                                        │
│                                                         │
│  🟢 staging-api-server                                  │
│                                                         │
│  Status: Running                                        │
│  Uptime: 3d 2h                                          │
│                                                         │
│  CPU: 8.4% (2 cores)                                    │
│  RAM: 29.1% (2.3/8.0 GB)                               │
│  Disk: 45.0% (18/40 GB)                                │
│  Processes: 4 active                                    │
│  IP: 35.200.10.22                                       │
│                                                         │
│  🛑 To stop this VM: /vm stop staging-api-server        │
│  cc: @charlie                                           │
│─────────────────────────────────────────────────────────│
│  📅 May 30, 2026 9:00 AM                                │
│  💡 /vm status for real-time metrics                    │
└─────────────────────────────────────────────────────────┘
```

---

## GPU Status Report (9 PM)

```
┌─────────────────────────────────────────────────────────┐
│  🔔 GPU VMs Status                                      │
├─────────────────────────────────────────────────────────┤
│  💬 This is a periodic reminder. GPU VMs are expensive  │
│  when idle. If you are not using this VM, please stop   │
│  it. Ignore if actively working.                        │
│─────────────────────────────────────────────────────────│
│  🟢 ml-training-gpu-01                                  │
│                                                         │
│  Status: Running                                        │
│  Running Since: May 29, 2026 10:30 AM (1d 11h)         │
│                                                         │
│  GPU Model: nvidia-tesla-t4                             │
│  GPU Util: 0.0%                                         │
│  GPU Memory: 0.4/15.0 GB                                │
│                                                         │
│  CPU: 1.8% (4 cores)                                    │
│  RAM: 12.0% (19.5/162.8 GB)                             │
│  Disk: 77.0% (155/200 GB)                               │
│  Processes: 0 active                                    │
│  IP: 34.123.45.67                                       │
│                                                         │
│  🛑 To stop this VM: /vm stop ml-training-gpu-01        │
│  cc: @alice @bob                                        │
│─────────────────────────────────────────────────────────│
│  📅 May 30, 2026 9:00 PM                                │
│  💡 /vm status for real-time metrics                    │
└─────────────────────────────────────────────────────────┘
```

---

## Idle Warning (Before Auto-Stop)

```
┌─────────────────────────────────────────────────────────┐
│  ⚠️ VM Shutting Down in 10 min                          │
├─────────────────────────────────────────────────────────┤
│  VM Name:          Cloud:                               │
│  ml-training-      GCP                                  │
│  gpu-01                                                 │
│                                                         │
│  Zone:             GPU Type:                            │
│  us-central1-a     nvidia-tesla-t4                      │
├─────────────────────────────────────────────────────────┤
│  Metrics (idle for 50 min):                             │
│    GPU: 0%  |  CPU: 1%  |  RAM: 12%                    │
│    Processes: 0  |  Sessions: 0                         │
│  No application processes detected.                     │
│                                                         │
│  cc: @alice @bob                                        │
│                                                         │
│  [ Keep Running ]  [ Stop Now ]                         │
└─────────────────────────────────────────────────────────┘
```

---

## VM Stopped Notification

```
┌─────────────────────────────────────────────────────────┐
│  🔴 VM Stopped: ml-training-gpu-01                      │
├─────────────────────────────────────────────────────────┤
│  Reason: Auto-stopped (idle timeout)                    │
│  Session uptime: 1h 35m                                 │
│                                                         │
│  cc: @alice @bob                                        │
│                                                         │
│  [ Start VM ]                                           │
└─────────────────────────────────────────────────────────┘
```

---

## VM Started Notification

```
┌─────────────────────────────────────────────────────────┐
│  🟢 VM Started: ml-training-gpu-01                      │
├─────────────────────────────────────────────────────────┤
│  Started by: @alice                                     │
│  GPU: nvidia-tesla-t4                                   │
│  External IP: 34.123.45.67                              │
│                                                         │
│  cc: @alice @bob                                        │
│                                                         │
│  [ Stop VM ]  [ Status ]                                │
└─────────────────────────────────────────────────────────┘
```

---

## GPU Availability Warning (Before Stop)

```
┌─────────────────────────────────────────────────────────┐
│  GPU Availability Warning                               │
├─────────────────────────────────────────────────────────┤
│  VM: ml-training-gpu-01                                 │
│  GPU: nvidia-tesla-t4                                   │
│  Zone: us-central1-a                                    │
│                                                         │
│  ⚠️ High risk — No GPU reservation found.               │
│  GPU type nvidia-tesla-t4 may not be available in       │
│  us-central1-a when you try to restart.                 │
│  You may need to migrate the VM to a different zone.    │
│                                                         │
│  Stopping this VM releases the GPU back to the shared   │
│  pool. If the zone runs out of GPU capacity, you won't  │
│  be able to restart without migrating to another zone.  │
│                                                         │
│  [ Stop Anyway ]  [ Keep Running ]                      │
│                                                         │
│  💡 Tip: Create a GPU reservation to guarantee          │
│  capacity: gcloud compute reservations create ...       │
│  — see docs/GPU_AVAILABILITY.md                         │
└─────────────────────────────────────────────────────────┘
```

---

## VM Started After Zone Migration

```
┌─────────────────────────────────────────────────────────┐
│  🟢 VM Started (Zone Changed)                           │
│                                                         │
│  VM: ml-training-gpu-01                                 │
│  Original zone: us-central1-a (GPU unavailable)         │
│  New zone: us-central1-b                                │
│  Attempts: 3                                            │
│                                                         │
│  ⚠️ The VM was migrated to us-central1-b because GPU    │
│  capacity was exhausted in us-central1-a.               │
└─────────────────────────────────────────────────────────┘
```

---

## Shutdown Cancelled

```
┌─────────────────────────────────────────────────────────┐
│  ✅ Shutdown Cancelled — ml-training-gpu-01             │
│  Cancelled by @alice. VM will keep running.             │
└─────────────────────────────────────────────────────────┘
```

---

## Slash Commands Reference

| Command | Description |
|---------|-------------|
| `/vm status` | Show real-time status of all VMs |
| `/vm start <name>` | Start a stopped VM |
| `/vm stop <name>` | Stop a running VM (with GPU warning if applicable) |
| `/vm extend <name> <minutes>` | Extend idle timeout |
| `/vm pause <name>` | Pause monitoring for a VM |

---

> **Note:** All notifications are interactive — buttons allow one-click actions directly from Slack. Actual rendering uses Slack Block Kit with rich formatting, emoji, and contextual timestamps.
