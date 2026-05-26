"""Pydantic models for VM Power Manager configuration and state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IdleMetric(str, Enum):
    GPU_UTILIZATION = "gpu_utilization"
    CPU_UTILIZATION = "cpu_utilization"
    MEMORY_UTILIZATION = "memory_utilization"
    PROCESS_COUNT = "process_count"
    COMBINED = "combined"


class MetricSource(str, Enum):
    MONITORING_API = "monitoring_api"
    SSH = "ssh"


class AccessControlMode(str, Enum):
    MENTIONED_ONLY = "mentioned_only"
    CHANNEL_MEMBERS = "channel_members"
    SPECIFIC_USERS = "specific_users"


class StateBackendType(str, Enum):
    GCS_BUCKET = "gcs_bucket"
    FIRESTORE = "firestore"
    S3_BUCKET = "s3_bucket"
    DYNAMODB = "dynamodb"
    REDIS = "redis"
    FILE = "file"


class CloudProvider(str, Enum):
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    SSH = "ssh"


class ProcessMonitorStrategy(str, Enum):
    WATCH_LIST = "watch_list"
    EXCLUDE_LIST = "exclude_list"
    BOTH = "both"


class ProcessMonitoringConfig(BaseModel):
    strategy: ProcessMonitorStrategy = ProcessMonitorStrategy.WATCH_LIST
    watch_processes: list[str] = Field(default_factory=list)
    watch_commands: list[str] = Field(default_factory=list)
    exclude_processes: list[str] = Field(default_factory=list)
    check_active_sessions: bool = True


class MetricSources(BaseModel):
    gpu_utilization: MetricSource = MetricSource.MONITORING_API
    cpu_utilization: MetricSource = MetricSource.MONITORING_API
    memory_utilization: MetricSource = MetricSource.MONITORING_API
    process_count: MetricSource = MetricSource.SSH


class NotificationConfig(BaseModel):
    on_warning: bool = True
    on_stop: bool = True
    on_start: bool = True
    on_manual_stop: bool = True
    on_extend: bool = True
    on_cancel: bool = True
    daily_summary: bool = True
    daily_summary_time: str = "09:00"


class VMDefaults(BaseModel):
    idle_metric: IdleMetric = IdleMetric.GPU_UTILIZATION
    idle_threshold_below: float = 5.0
    idle_duration_minutes: int = 30
    warning_minutes: int = 5
    check_interval_minutes: int = 10
    auto_stop_enabled: bool = True
    metric_sources: MetricSources = Field(default_factory=MetricSources)
    process_monitoring: ProcessMonitoringConfig = Field(default_factory=ProcessMonitoringConfig)
    disable_auto_upgrades: bool = True
    pre_stop_commands: list[str] = Field(default_factory=list)
    post_start_commands: list[str] = Field(default_factory=list)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)


class VMConfig(BaseModel):
    """Configuration for a single managed VM."""

    name: str
    cloud: CloudProvider = CloudProvider.GCP

    # GCP-specific
    gcp_name: str | None = None
    project: str | None = None
    zone: str | None = None
    gpu_type: str | None = None

    # AWS-specific
    instance_id: str | None = None
    region: str | None = None

    # SSH-specific
    ssh_host: str | None = None
    ssh_user: str = "root"
    ssh_key_env: str | None = None
    ssh_port: int = 22

    # Slack
    channel: str | None = None
    notify_users: list[str] = Field(default_factory=list)
    access_control: AccessControlMode | None = None
    allowed_users: list[str] = Field(default_factory=list)

    # Per-VM overrides (None = use defaults)
    idle_metric: IdleMetric | None = None
    idle_threshold_below: float | None = None
    idle_duration_minutes: int | None = None
    warning_minutes: int | None = None
    auto_stop_enabled: bool | None = None
    metric_sources: MetricSources | None = None
    process_monitoring: ProcessMonitoringConfig | None = None
    disable_auto_upgrades: bool | None = None
    pre_stop_commands: list[str] | None = None
    post_start_commands: list[str] | None = None
    notifications: NotificationConfig | None = None

    def get_effective_config(self, defaults: VMDefaults) -> ResolvedVMConfig:
        """Merge this VM's overrides with defaults to produce final config."""
        return ResolvedVMConfig(
            name=self.name,
            cloud=self.cloud,
            gcp_name=self.gcp_name,
            project=self.project,
            zone=self.zone,
            gpu_type=self.gpu_type,
            instance_id=self.instance_id,
            region=self.region,
            ssh_host=self.ssh_host,
            ssh_user=self.ssh_user,
            ssh_key_env=self.ssh_key_env,
            ssh_port=self.ssh_port,
            channel=self.channel,
            notify_users=self.notify_users,
            access_control=self.access_control or AccessControlMode.MENTIONED_ONLY,
            allowed_users=self.allowed_users,
            idle_metric=self.idle_metric or defaults.idle_metric,
            idle_threshold_below=(
                self.idle_threshold_below
                if self.idle_threshold_below is not None
                else defaults.idle_threshold_below
            ),
            idle_duration_minutes=self.idle_duration_minutes or defaults.idle_duration_minutes,
            warning_minutes=self.warning_minutes or defaults.warning_minutes,
            auto_stop_enabled=(
                self.auto_stop_enabled
                if self.auto_stop_enabled is not None
                else defaults.auto_stop_enabled
            ),
            metric_sources=self.metric_sources or defaults.metric_sources,
            process_monitoring=self.process_monitoring or defaults.process_monitoring,
            disable_auto_upgrades=(
                self.disable_auto_upgrades
                if self.disable_auto_upgrades is not None
                else defaults.disable_auto_upgrades
            ),
            pre_stop_commands=(
                self.pre_stop_commands
                if self.pre_stop_commands is not None
                else defaults.pre_stop_commands
            ),
            post_start_commands=(
                self.post_start_commands
                if self.post_start_commands is not None
                else defaults.post_start_commands
            ),
            notifications=self.notifications or defaults.notifications,
        )


class ResolvedVMConfig(BaseModel):
    """Fully resolved VM config after merging defaults — no optional fields."""

    name: str
    cloud: CloudProvider

    gcp_name: str | None = None
    project: str | None = None
    zone: str | None = None
    gpu_type: str | None = None
    instance_id: str | None = None
    region: str | None = None
    ssh_host: str | None = None
    ssh_user: str = "root"
    ssh_key_env: str | None = None
    ssh_port: int = 22

    channel: str | None = None
    notify_users: list[str] = Field(default_factory=list)
    access_control: AccessControlMode = AccessControlMode.MENTIONED_ONLY
    allowed_users: list[str] = Field(default_factory=list)

    idle_metric: IdleMetric
    idle_threshold_below: float
    idle_duration_minutes: int
    warning_minutes: int
    auto_stop_enabled: bool
    metric_sources: MetricSources
    process_monitoring: ProcessMonitoringConfig
    disable_auto_upgrades: bool
    pre_stop_commands: list[str]
    post_start_commands: list[str]
    notifications: NotificationConfig


class SlackConfig(BaseModel):
    bot_token_env: str = "SLACK_BOT_TOKEN"
    signing_secret_env: str = "SLACK_SIGNING_SECRET"
    default_channel: str = "#vm-alerts"
    access_control: AccessControlMode = AccessControlMode.MENTIONED_ONLY


class StateConfig(BaseModel):
    backend: StateBackendType = StateBackendType.GCS_BUCKET
    project: str | None = None
    bucket: str | None = None
    prefix: str = "state/"
    collection: str | None = None
    table: str | None = None
    region: str | None = None
    url_env: str | None = None
    key_prefix: str = "vpm:"
    path: str = "./state/"


class AppConfig(BaseModel):
    name: str = "vm-power-manager"
    environment: str = "production"
    debug_mode: bool = False
    dry_run: bool = False


class Config(BaseModel):
    """Top-level configuration model."""

    app: AppConfig = Field(default_factory=AppConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    defaults: VMDefaults = Field(default_factory=VMDefaults)
    state: StateConfig = Field(default_factory=StateConfig)
    vms: list[VMConfig] = Field(default_factory=list)


# --- State Models ---


class VMState(BaseModel):
    """Per-VM runtime state stored in the state backend."""

    vm_name: str
    idle_since: datetime | None = None
    idle_minutes: int = 0
    warning_sent: bool = False
    warning_sent_at: datetime | None = None
    keep_running_until: datetime | None = None
    paused: bool = False
    paused_at: datetime | None = None
    last_checked: datetime | None = None
    session_started: datetime | None = None
    last_metrics: dict[str, Any] = Field(default_factory=dict)


class MetricSnapshot(BaseModel):
    """Point-in-time metrics for a VM."""

    gpu_utilization: float | None = None
    cpu_utilization: float | None = None
    memory_utilization: float | None = None
    active_process_count: int = 0
    active_processes: list[dict[str, str]] = Field(default_factory=list)
    active_sessions: int = 0
    session_users: list[str] = Field(default_factory=list)

    @property
    def is_idle(self) -> bool:
        """Quick check — actual idle logic is in monitor.py with thresholds."""
        return (
            self.active_process_count == 0
            and self.active_sessions == 0
            and (self.gpu_utilization or 0) < 5
        )


class ActiveProcess(BaseModel):
    user: str
    pid: int
    cmd: str
