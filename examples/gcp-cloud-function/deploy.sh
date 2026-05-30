#!/bin/bash
set -euo pipefail

# =============================================================================
# VM Power Manager — GCP Cloud Function Deployment Script
#
# Usage:
#   export SLACK_BOT_TOKEN=xoxb-...
#   export SLACK_SIGNING_SECRET=...
#   export PROJECT_ID=your-gcp-project
#   ./deploy.sh
#
# All schedule and interval settings are configurable via environment variables.
# =============================================================================

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID env var}"
REGION="${REGION:-us-central1}"
SLACK_BOT_TOKEN="${SLACK_BOT_TOKEN:?Set SLACK_BOT_TOKEN env var}"
SLACK_SIGNING_SECRET="${SLACK_SIGNING_SECRET:?Set SLACK_SIGNING_SECRET env var}"
STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-vm-power-state}"
SCHEDULER_INTERVAL="${SCHEDULER_INTERVAL:-10}"

# --- Schedule Configuration (configurable) ---
# Format: standard cron expressions
# Default: Daily report at 9 AM IST (3:30 UTC), GPU report at 9 PM IST (15:30 UTC)
DAILY_REPORT_CRON="${DAILY_REPORT_CRON:-30 3 * * *}"
DAILY_REPORT_TZ="${DAILY_REPORT_TZ:-UTC}"
GPU_REPORT_CRON="${GPU_REPORT_CRON:-30 15 * * *}"
GPU_REPORT_TZ="${GPU_REPORT_TZ:-UTC}"

# Optional: SSH key for metric collection (base64 encoded)
VM_SSH_KEY="${VM_SSH_KEY:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/.build"

echo "=== VM Power Manager Deployment ==="
echo "Project:       $PROJECT_ID"
echo "Region:        $REGION"
echo "Daily report:  $DAILY_REPORT_CRON ($DAILY_REPORT_TZ)"
echo "GPU report:    $GPU_REPORT_CRON ($GPU_REPORT_TZ)"
echo ""

# --- Build deployment package ---
echo "0. Packaging for deployment..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/config.yaml" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"
echo "   Done. (library installed from GitHub via requirements.txt)"
echo ""

# --- GCS State Bucket ---
echo "1. Creating state bucket (if not exists)..."
gsutil ls "gs://$STATE_BUCKET" 2>/dev/null || \
  gsutil mb -p "$PROJECT_ID" -l "$REGION" "gs://$STATE_BUCKET"

# --- Pub/Sub Topics ---
echo "2. Creating Pub/Sub topics (if not exists)..."
gcloud pubsub topics describe vm-power-monitor-trigger \
  --project="$PROJECT_ID" 2>/dev/null || \
  gcloud pubsub topics create vm-power-monitor-trigger --project="$PROJECT_ID"

gcloud pubsub topics describe vm-power-daily-digest-trigger \
  --project="$PROJECT_ID" 2>/dev/null || \
  gcloud pubsub topics create vm-power-daily-digest-trigger --project="$PROJECT_ID"

gcloud pubsub topics describe vm-power-gpu-status-trigger \
  --project="$PROJECT_ID" 2>/dev/null || \
  gcloud pubsub topics create vm-power-gpu-status-trigger --project="$PROJECT_ID"

# Build env vars string
ENV_VARS="SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET"
if [ -n "$VM_SSH_KEY" ]; then
  ENV_VARS="$ENV_VARS,VM_SSH_KEY=$VM_SSH_KEY"
fi

# --- Deploy Monitor Function ---
echo "3. Deploying monitor function..."
gcloud functions deploy vm-power-monitor \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-topic=vm-power-monitor-trigger \
  --entry-point=monitor \
  --source="$BUILD_DIR" \
  --set-env-vars="$ENV_VARS" \
  --memory=512MB \
  --timeout=120s \
  --gen2 \
  --quiet

# --- Deploy Slack Function ---
echo "4. Deploying Slack handler function..."
gcloud functions deploy vm-power-slack \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point=slack \
  --source="$BUILD_DIR" \
  --set-env-vars="$ENV_VARS" \
  --memory=1Gi \
  --cpu=1 \
  --timeout=60s \
  --min-instances=1 \
  --gen2 \
  --quiet

# Enable always-on CPU for async Slack responses
echo "   Enabling always-on CPU..."
gcloud run services update vm-power-slack \
  --no-cpu-throttling \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --quiet

# --- Deploy Daily Digest Function ---
echo "5. Deploying daily digest function..."
gcloud functions deploy vm-power-daily-digest \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-topic=vm-power-daily-digest-trigger \
  --entry-point=daily_digest \
  --source="$BUILD_DIR" \
  --set-env-vars="$ENV_VARS" \
  --memory=512MB \
  --timeout=120s \
  --gen2 \
  --quiet

# --- Deploy GPU Status Function ---
echo "6. Deploying GPU status report function..."
gcloud functions deploy vm-power-gpu-status \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-topic=vm-power-gpu-status-trigger \
  --entry-point=gpu_status \
  --source="$BUILD_DIR" \
  --set-env-vars="$ENV_VARS" \
  --memory=512MB \
  --timeout=120s \
  --gen2 \
  --quiet

# Get Slack function URL
SLACK_URL=$(gcloud functions describe vm-power-slack \
  --project="$PROJECT_ID" --region="$REGION" --gen2 \
  --format="value(serviceConfig.uri)")
echo ""
echo "   Slack URL: $SLACK_URL"

# --- Cloud Scheduler ---
echo "7. Setting up Cloud Scheduler jobs..."

# Monitor job (every N min)
gcloud scheduler jobs delete vm-power-monitor-job \
  --project="$PROJECT_ID" --location="$REGION" --quiet 2>/dev/null || true
gcloud scheduler jobs create pubsub vm-power-monitor-job \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --topic="vm-power-monitor-trigger" \
  --schedule="*/$SCHEDULER_INTERVAL * * * *" \
  --message-body='{"trigger": "scheduled"}' \
  --quiet

# Daily report (configurable)
echo "   Daily report: $DAILY_REPORT_CRON ($DAILY_REPORT_TZ)"
gcloud scheduler jobs delete vm-power-daily-digest \
  --project="$PROJECT_ID" --location="$REGION" --quiet 2>/dev/null || true
gcloud scheduler jobs create pubsub vm-power-daily-digest \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --topic="vm-power-daily-digest-trigger" \
  --schedule="$DAILY_REPORT_CRON" \
  --message-body='{"trigger": "daily_digest"}' \
  --time-zone="$DAILY_REPORT_TZ" \
  --quiet

# GPU status report (configurable)
echo "   GPU report:   $GPU_REPORT_CRON ($GPU_REPORT_TZ)"
gcloud scheduler jobs delete vm-power-gpu-status \
  --project="$PROJECT_ID" --location="$REGION" --quiet 2>/dev/null || true
gcloud scheduler jobs create pubsub vm-power-gpu-status \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --topic="vm-power-gpu-status-trigger" \
  --schedule="$GPU_REPORT_CRON" \
  --message-body='{"trigger": "gpu_status"}' \
  --time-zone="$GPU_REPORT_TZ" \
  --quiet

# Cleanup
rm -rf "$BUILD_DIR"

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Slack function URL: $SLACK_URL"
echo ""
echo "Configure in your Slack App:"
echo "  1. Slash Command (/vm) Request URL → $SLACK_URL"
echo "  2. Interactivity Request URL       → $SLACK_URL"
echo "  3. Invite bot: /invite @VM Power Manager"
echo ""
echo "Schedule summary:"
echo "  Monitor:      every $SCHEDULER_INTERVAL min"
echo "  Daily report: $DAILY_REPORT_CRON ($DAILY_REPORT_TZ)"
echo "  GPU report:   $GPU_REPORT_CRON ($GPU_REPORT_TZ)"
echo ""
