#!/bin/bash
# Validate experiment inputs for the build-experiment workflow
# Checks that the experiment directory exists, detects whether it has a custom Containerfile,
# resolves and verifies the base image reference, and counts files in the directory
# Sets GITHUB_OUTPUT variables for downstream jobs
#
# Required environment variables:
#   EXPERIMENT_NAME - name of the experiment directory (relative to project root)
#
# Optional environment variables:
#   BASE_IMAGE  - base image to use when no custom Containerfile exists
#                 (default: sst-core:latest; short names are resolved via ghcr.io/REPO_OWNER/)
#   REPO_OWNER  - GitHub repository owner for resolving short image names
#                 (default: current user via whoami)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

EXPERIMENT_NAME="${EXPERIMENT_NAME:-}"
BASE_IMAGE="${BASE_IMAGE:-sst-core:latest}"
REPO_OWNER="${REPO_OWNER:-$(whoami)}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-$(detect_container_engine)}"

if [[ -z "$EXPERIMENT_NAME" ]]; then
    log_error "EXPERIMENT_NAME is required"
    exit 1
fi

if ! validate_container_engine "$CONTAINER_ENGINE"; then
    log_error "Container engine validation failed"
    exit 1
fi

log_group_start "Validate Experiment Inputs"
log_info "Experiment name: ${EXPERIMENT_NAME}"

# Check if experiment directory exists (non-lethal: sets output and exits cleanly)
if [[ ! -d "$EXPERIMENT_NAME" ]]; then
    log_error "Experiment directory '${EXPERIMENT_NAME}' does not exist"
    set_output "experiment_exists" "false"
    log_group_end
    exit 0
fi

set_output "experiment_exists" "true"
log_info "Experiment directory found: ${EXPERIMENT_NAME}"

# Detect whether the experiment provides its own Containerfile
if [[ -f "${EXPERIMENT_NAME}/Containerfile" ]]; then
    log_info "Custom Containerfile found in experiment directory"
    set_output "has_containerfile" "true"
    set_output "resolved_base_image" ""
else
    log_info "No custom Containerfile - using template Containerfile.experiment"
    set_output "has_containerfile" "false"

    # Resolve the base image reference: short names become ghcr.io/OWNER/NAME
    RESOLVED_IMAGE=$(resolve_base_image_reference "$BASE_IMAGE" "$REPO_OWNER")
    log_info "Resolved base image: ${RESOLVED_IMAGE}"
    set_output "resolved_base_image" "$RESOLVED_IMAGE"

    # Verify the base image is accessible in the registry
    if inspect_remote_manifest "$CONTAINER_ENGINE" "$RESOLVED_IMAGE" >/dev/null 2>&1; then
        log_success "Base image is accessible: ${RESOLVED_IMAGE}"
    else
        log_error "Base image not found or not accessible: ${RESOLVED_IMAGE}"
        log_error "For images in this repository, use format: sst-core:latest"
        log_error "For external images, use a full path: ghcr.io/username/image:tag"
        log_group_end
        exit 1
    fi
fi

# Count files in the experiment directory
FILES_COUNT=$(find "$EXPERIMENT_NAME" -type f | wc -l | tr -d ' ')
log_info "Files in experiment directory: ${FILES_COUNT}"
set_output "files_count" "$FILES_COUNT"

log_group_end
log_success "Experiment validation complete: ${EXPERIMENT_NAME}"
