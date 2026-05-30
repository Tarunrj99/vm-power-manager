# Configuration Reference

## Configuration Layering

| Layer | Location | Purpose |
|---|---|---|
| 1. Library Defaults | `src/vm_power_manager/bundled_defaults.yaml` | Every option with safe defaults. Never edit. |
| 2. Deployment Config | Your `config.yaml` | Only what changes per deployment. |
| 3. Slack Runtime | In-memory / state store | Temporary: extend, pause, cancel. |

## All Configuration Options

### app

| Key | Type | Default | Description |
|---|---|---|---|
| `name` | string | `vm-power-manager` | App name for logging |
| `environment` | string | `production` | Environment tag |
| `debug_mode` | bool | `false` | Verbose logging |
| `dry_run` | bool | `false` | Alerts but doesn't stop VMs |
| `deployment_id` | string | `null` | Unique ID for this deployment (optional) |

### app.manifest

Runtime version-compatibility check. The library periodically fetches a small JSON descriptor from upstream to verify the installed version is still supported. Disable for air-gapped environments or forks.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable/disable the check |
| `url` | string | _(GitHub API)_ | URL to fetch the manifest from |
| `refresh_interval_seconds` | int | `300` | Cache TTL between checks |
| `timeout_seconds` | int | `3` | HTTP fetch timeout |
| `tolerate_network_errors` | bool | `true` | Transient errors don't block operation |
| `tolerate_missing_manifest` | bool | `false` | If manifest is missing (404), block or allow |

### slack

| Key | Type | Default | Description |
|---|---|---|---|
| `bot_token_env` | string | `SLACK_BOT_TOKEN` | Env var for bot token |
| `signing_secret_env` | string | `SLACK_SIGNING_SECRET` | Env var for signing secret |
| `default_channel` | string | `#vm-alerts` | Default notification channel |
| `access_control` | string | `mentioned_only` | Global access control mode |

### defaults

| Key | Type | Default | Description |
|---|---|---|---|
| `idle_metric` | string | `gpu_utilization` | `gpu_utilization`, `cpu_utilization`, `memory_utilization`, `process_count`, `combined` |
| `idle_threshold_below` | float | `5` | Idle if metric below this % |
| `idle_duration_minutes` | int | `30` | How long idle before warning |
| `warning_minutes` | int | `5` | Warning time before stop |
| `check_interval_minutes` | int | `10` | Scheduler frequency |
| `auto_stop_enabled` | bool | `false` | Enable auto-stop (off by default) |
| `disable_auto_upgrades` | bool | `true` | Disable unattended-upgrades |
| `pre_stop_commands` | list | `[]` | Commands before stop |
| `post_start_commands` | list | `[]` | Commands after start |

### defaults.gpu_protection

Prevents GPU unavailability after VM stop. See [GPU_AVAILABILITY.md](GPU_AVAILABILITY.md) for full details.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable GPU protection features |
| `check_before_stop` | bool | `true` | Warn via Slack before stopping GPU VMs |
| `fallback_zones` | list | `[]` | Zones to try if original zone is exhausted |
| `max_start_retries` | int | `3` | Retries in original zone before fallback |
| `retry_delay_seconds` | int | `30` | Delay between retries |
| `auto_migrate` | bool | `false` | Auto-migrate VM to fallback zone on failure |
| `notify_on_zone_change` | bool | `true` | Slack alert when VM migrates to new zone |

### defaults.gpu_monitoring

Alerts when GPU VMs run continuously beyond a configurable threshold. Informational only — does not auto-stop.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable GPU running alerts |
| `alert_interval_minutes` | int | `60` | Alert every N minutes per running GPU VM |
| `alert_after_minutes` | int | `60` | Only start alerting after VM runs this long |
| `include_in_regular_check` | bool | `true` | Check during normal monitor cycle (every 10 min) |

Can be overridden per-VM to set different frequencies (e.g., A100 VMs every 30 min, T4 every 2 hours).

### defaults.metric_sources

If the primary source returns `None`, the system falls back to SSH automatically.

| Key | Type | Default | Description |
|---|---|---|---|
| `gpu_utilization` | string | `monitoring_api` | `monitoring_api` or `ssh` |
| `cpu_utilization` | string | `monitoring_api` | `monitoring_api` or `ssh` |
| `memory_utilization` | string | `monitoring_api` | `monitoring_api` or `ssh` |
| `disk_utilization` | string | `ssh` | `monitoring_api` or `ssh` |
| `process_count` | string | `ssh` | Always `ssh` |

### defaults.process_monitoring

| Key | Type | Default | Description |
|---|---|---|---|
| `strategy` | string | `watch_list` | `watch_list`, `exclude_list`, `both` |
| `watch_processes` | list | `[python, node, ...]` | Binaries indicating real work |
| `watch_commands` | list | `[]` | Keywords in command line |
| `exclude_processes` | list | `[nginx, sshd, ...]` | System services to ignore |
| `check_active_sessions` | bool | `true` | SSH/RDP sessions = active |

### defaults.notifications

| Key | Type | Default | Description |
|---|---|---|---|
| `on_warning` | bool | `true` | Notify before stop |
| `on_stop` | bool | `true` | Notify on stop |
| `on_start` | bool | `true` | Notify on start |
| `on_manual_stop` | bool | `true` | Notify on manual stop |
| `on_extend` | bool | `true` | Notify on extend |
| `on_cancel` | bool | `true` | Notify on cancel |
| `daily_summary` | bool | `true` | Daily summary |
| `daily_summary_time` | string | `09:00` | Summary time (24h) |

### state

| Key | Type | Default | Description |
|---|---|---|---|
| `backend` | string | `gcs_bucket` | Backend type |
| `project` | string | - | GCP project (for gcs_bucket/firestore) |
| `bucket` | string | - | Bucket name (gcs_bucket/s3_bucket) |
| `prefix` | string | `state/` | Object prefix |
| `collection` | string | - | Firestore collection |
| `table` | string | - | DynamoDB table |
| `region` | string | - | AWS region |
| `url_env` | string | `REDIS_URL` | Redis URL env var |
| `key_prefix` | string | `vpm:` | Redis key prefix |
| `path` | string | `./state/` | File backend directory |

### vms[] (per VM)

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | string | YES | Display name |
| `cloud` | string | YES | `gcp`, `aws`, `azure`, `ssh` |
| `gcp_name` | string | GCP | Instance name |
| `project` | string | GCP | GCP project |
| `zone` | string | GCP | GCP zone |
| `gpu_type` | string | No | GPU model name |
| `instance_id` | string | AWS | EC2 instance ID |
| `region` | string | AWS | AWS region |
| `ssh_host` | string | SSH | Hostname/IP |
| `ssh_user` | string | No | SSH username (default: root) |
| `ssh_key_env` | string | No | Env var for SSH key path |
| `ssh_port` | int | No | SSH port (default: 22) |
| `channel` | string | No | Override Slack channel |
| `notify_users` | list | No | Users to @mention |
| `access_control` | string | No | Override access mode |
| `allowed_users` | list | No | For `specific_users` mode |

Plus all `defaults.*` keys can be overridden per VM.

### schedule

Controls when automated reports are sent. Each report type accepts a **list** of cron expressions — one Cloud Scheduler job is created per expression.

| Key | Type | Default | Description |
|---|---|---|---|
| `daily_report_schedules` | list[string] | `["30 3 * * *"]` | Cron expressions for daily full report |
| `daily_report_timezone` | string | `UTC` | IANA timezone for daily report |
| `gpu_report_schedules` | list[string] | `["30 15 * * *"]` | Cron expressions for GPU status report |
| `gpu_report_timezone` | string | `UTC` | IANA timezone for GPU report |
| `gpu_report_enabled` | bool | `true` | Set `false` to disable GPU reports entirely |

#### Schedule Examples

```yaml
# Once daily at 9 AM IST (3:30 UTC)
schedule:
  daily_report_schedules:
    - "30 3 * * *"
  gpu_report_schedules:
    - "30 15 * * *"

# GPU report every 2 hours
schedule:
  gpu_report_schedules:
    - "0 */2 * * *"

# GPU report every 6 hours
schedule:
  gpu_report_schedules:
    - "0 */6 * * *"

# GPU report at specific times (10:00, 14:30, 21:14 UTC)
schedule:
  gpu_report_schedules:
    - "0 10 * * *"
    - "30 14 * * *"
    - "14 21 * * *"

# GPU report 3 times daily at 9 AM, 3 PM, 9 PM (IST timezone)
schedule:
  gpu_report_schedules:
    - "0 9 * * *"
    - "0 15 * * *"
    - "0 21 * * *"
  gpu_report_timezone: "Asia/Kolkata"

# Weekdays only
schedule:
  daily_report_schedules:
    - "0 9 * * 1-5"
  gpu_report_schedules:
    - "0 18 * * 1-5"

# Every 30 minutes (aggressive monitoring)
schedule:
  gpu_report_schedules:
    - "*/30 * * * *"
```
