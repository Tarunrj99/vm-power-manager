#!/usr/bin/env bash
# =============================================================================
# GPU Reservation Setup Helper
#
# Creates a GCP Compute Engine reservation to guarantee GPU availability for
# your VM — even when the VM is stopped.
#
# Usage:
#   ./scripts/gpu-reservation-setup.sh \
#     --project MY_PROJECT \
#     --zone us-central1-a \
#     --machine-type n1-standard-8 \
#     --gpu-type nvidia-tesla-t4 \
#     --gpu-count 1 \
#     --name my-vm-gpu-reserve
#
# See docs/GPU_AVAILABILITY.md for full context on why this is needed.
# =============================================================================

set -euo pipefail

# --- Defaults ---------------------------------------------------------------
PROJECT=""
ZONE=""
MACHINE_TYPE=""
GPU_TYPE=""
GPU_COUNT="1"
RESERVATION_NAME=""
VM_COUNT="1"
DRY_RUN="false"
DELETE="false"
LIST="false"

# --- Color helpers ----------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }

# --- Usage ------------------------------------------------------------------
usage() {
  cat <<EOF
GPU Reservation Setup Helper

Creates (or deletes) a GCP Compute Engine reservation to guarantee GPU capacity.

USAGE:
  $(basename "$0") [OPTIONS]

OPTIONS:
  --project       GCP project ID (required)
  --zone          Zone for the reservation (required)
  --machine-type  Machine type, e.g. n1-standard-8 (required for create)
  --gpu-type      GPU accelerator type, e.g. nvidia-tesla-t4 (required for create)
  --gpu-count     Number of GPUs per VM (default: 1)
  --vm-count      Number of VMs to reserve (default: 1)
  --name          Reservation name (default: <vm-name>-gpu-reserve)
  --dry-run       Print the command without executing
  --delete        Delete an existing reservation
  --list          List all reservations in the zone

EXAMPLES:
  # Create a reservation for 1 T4 GPU
  $(basename "$0") --project my-project --zone us-central1-a \\
    --machine-type n1-standard-8 --gpu-type nvidia-tesla-t4 --name my-vm-reserve

  # List existing reservations
  $(basename "$0") --project my-project --zone us-central1-a --list

  # Delete a reservation
  $(basename "$0") --project my-project --zone us-central1-a \\
    --name my-vm-reserve --delete

  # Dry run (show command only)
  $(basename "$0") --project my-project --zone us-central1-a \\
    --machine-type n1-standard-8 --gpu-type nvidia-tesla-t4 --name test --dry-run

SUPPORTED GPU TYPES:
  nvidia-tesla-t4          (T4, budget-friendly)
  nvidia-tesla-a100        (A100 40GB)
  nvidia-a100-80gb         (A100 80GB)
  nvidia-l4                (L4, inference-optimized)
  nvidia-tesla-v100        (V100)
  nvidia-tesla-p100        (P100)
  nvidia-h100-80gb         (H100)

COST NOTE:
  Reservations charge the GPU rate even when the VM is stopped.
  However, this is typically cheaper than keeping the entire VM running
  (no CPU/memory charges while stopped).

EOF
  exit 1
}

# --- Parse arguments --------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)       PROJECT="$2"; shift 2;;
    --zone)          ZONE="$2"; shift 2;;
    --machine-type)  MACHINE_TYPE="$2"; shift 2;;
    --gpu-type)      GPU_TYPE="$2"; shift 2;;
    --gpu-count)     GPU_COUNT="$2"; shift 2;;
    --vm-count)      VM_COUNT="$2"; shift 2;;
    --name)          RESERVATION_NAME="$2"; shift 2;;
    --dry-run)       DRY_RUN="true"; shift;;
    --delete)        DELETE="true"; shift;;
    --list)          LIST="true"; shift;;
    -h|--help)       usage;;
    *)               error "Unknown option: $1"; usage;;
  esac
done

# --- Validation -------------------------------------------------------------
if [[ -z "$PROJECT" ]]; then
  error "--project is required"
  exit 1
fi

if [[ -z "$ZONE" ]]; then
  error "--zone is required"
  exit 1
fi

# --- List reservations ------------------------------------------------------
if [[ "$LIST" == "true" ]]; then
  info "Listing reservations in $ZONE (project: $PROJECT)..."
  echo ""
  gcloud compute reservations list \
    --filter="zone:$ZONE" \
    --project="$PROJECT" \
    --format="table(name, specificReservation.count, specificReservation.instanceProperties.machineType, status)"
  exit 0
fi

# --- Delete reservation -----------------------------------------------------
if [[ "$DELETE" == "true" ]]; then
  if [[ -z "$RESERVATION_NAME" ]]; then
    error "--name is required for deletion"
    exit 1
  fi

  warn "Deleting reservation: $RESERVATION_NAME"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY RUN] gcloud compute reservations delete $RESERVATION_NAME --zone=$ZONE --project=$PROJECT --quiet"
  else
    gcloud compute reservations delete "$RESERVATION_NAME" \
      --zone="$ZONE" \
      --project="$PROJECT" \
      --quiet
    ok "Reservation deleted: $RESERVATION_NAME"
  fi
  exit 0
fi

# --- Create reservation -----------------------------------------------------
if [[ -z "$MACHINE_TYPE" ]]; then
  error "--machine-type is required for creation"
  exit 1
fi

if [[ -z "$GPU_TYPE" ]]; then
  error "--gpu-type is required for creation"
  exit 1
fi

if [[ -z "$RESERVATION_NAME" ]]; then
  RESERVATION_NAME="${GPU_TYPE}-reserve-$(date +%s)"
  warn "No --name provided; using: $RESERVATION_NAME"
fi

info "Creating GPU reservation..."
echo ""
echo "  Project:      $PROJECT"
echo "  Zone:         $ZONE"
echo "  Machine type: $MACHINE_TYPE"
echo "  GPU type:     $GPU_TYPE"
echo "  GPU count:    $GPU_COUNT"
echo "  VM count:     $VM_COUNT"
echo "  Name:         $RESERVATION_NAME"
echo ""

CMD="gcloud compute reservations create $RESERVATION_NAME \
  --vm-count=$VM_COUNT \
  --machine-type=$MACHINE_TYPE \
  --accelerator=count=$GPU_COUNT,type=$GPU_TYPE \
  --zone=$ZONE \
  --project=$PROJECT"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [DRY RUN] $CMD"
  exit 0
fi

eval "$CMD"

echo ""
ok "Reservation created successfully!"
echo ""
info "To verify:"
echo "  gcloud compute reservations describe $RESERVATION_NAME --zone=$ZONE --project=$PROJECT"
echo ""
info "To delete later:"
echo "  $(basename "$0") --project $PROJECT --zone $ZONE --name $RESERVATION_NAME --delete"
echo ""
warn "Note: You will be charged for the reserved GPU even when the VM is stopped."
warn "This guarantees GPU availability on restart."
