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
# =============================================================================

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID env var}"
REGION="${REGION:-us-central1}"
SLACK_BOT_TOKEN="${SLACK_BOT_TOKEN:?Set SLACK_BOT_TOKEN env var}"
SLACK_SIGNING_SECRET="${SLACK_SIGNING_SECRET:?Set SLACK_SIGNING_SECRET env var}"
STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-vm-power-state}"
SCHEDULER_INTERVAL="${SCHEDULER_INTERVAL:-10}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/.build"

echo "=== VM Power Manager Deployment ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# --- Bundle source for Cloud Functions ---
echo "0. Bundling library source..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/config.yaml" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"
cp -r "$REPO_ROOT/src/vm_power_manager" "$BUILD_DIR/vm_power_manager"
find "$BUILD_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
echo "   Done."
echo ""

# --- GCS State Bucket ---
echo "1. Creating state bucket (if not exists)..."
gsutil ls "gs://$STATE_BUCKET" 2>/dev/null || \
  gsutil mb -p "$PROJECT_ID" -l "$REGION" "gs://$STATE_BUCKET"

# --- Pub/Sub Topic ---
echo "2. Creating Pub/Sub topic (if not exists)..."
gcloud pubsub topics describe vm-power-monitor-trigger \
  --project="$PROJECT_ID" 2>/dev/null || \
  gcloud pubsub topics create vm-power-monitor-trigger --project="$PROJECT_ID"

# --- Deploy Monitor Function ---
echo "3. Deploying monitor function..."
gcloud functions deploy vm-power-monitor \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-topic=vm-power-monitor-trigger \
  --entry-point=monitor \
  --source="$BUILD_DIR" \
  --set-env-vars="SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET" \
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
  --set-env-vars="SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET" \
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

# Get Slack function URL
SLACK_URL=$(gcloud functions describe vm-power-slack \
  --project="$PROJECT_ID" --region="$REGION" --gen2 \
  --format="value(serviceConfig.uri)")
echo ""
echo "   Slack URL: $SLACK_URL"

# --- Cloud Scheduler ---
echo "5. Creating Cloud Scheduler job (every $SCHEDULER_INTERVAL min)..."
gcloud scheduler jobs delete vm-power-monitor-job \
  --project="$PROJECT_ID" --location="$REGION" --quiet 2>/dev/null || true

gcloud scheduler jobs create pubsub vm-power-monitor-job \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --topic="vm-power-monitor-trigger" \
  --schedule="*/$SCHEDULER_INTERVAL * * * *" \
  --message-body='{"trigger": "scheduled"}' \
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
