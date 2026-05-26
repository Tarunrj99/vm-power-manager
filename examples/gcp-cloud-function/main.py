"""GCP Cloud Functions entry points — thin wrappers around the library."""

import os

import functions_framework

from vm_power_manager import check_idle, handle_slack

CONFIG = os.path.join(os.path.dirname(__file__), "config.yaml")


@functions_framework.cloud_event
def monitor(cloud_event):
    """Cloud Scheduler triggers this every 10 min."""
    return check_idle(config=CONFIG)


@functions_framework.http
def slack(request):
    """Slack slash commands + button interactions."""
    return handle_slack(request, config=CONFIG)
