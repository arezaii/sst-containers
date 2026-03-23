#!/bin/bash
# Prepare image naming configuration for container builds
# Computes image tag patterns and sets GITHUB_OUTPUT variables
#
# Required environment variables:
#   CONTAINER_TYPE      - core, full, dev, custom, or experiment
#   IMAGE_PREFIX        - image name prefix (e.g., "owner/sst" or "owner/sst-dev")
#   TAG_SUFFIX          - tag suffix for images (e.g., "15.1.0" or "latest")
#   REGISTRY            - container registry (e.g., ghcr.io)
#
# Optional environment variables:
#   ENABLE_PERF_TRACKING - true/false (default: false); adds -perf-track to prefix for core/full/custom
#   EXPERIMENT_NAME      - experiment name (required when CONTAINER_TYPE=experiment)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

CONTAINER_TYPE="${CONTAINER_TYPE:-}"
IMAGE_PREFIX="${IMAGE_PREFIX:-}"
TAG_SUFFIX="${TAG_SUFFIX:-}"
REGISTRY="${REGISTRY:-ghcr.io}"
ENABLE_PERF_TRACKING="${ENABLE_PERF_TRACKING:-false}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-}"

# Validate required inputs
if [[ -z "$CONTAINER_TYPE" ]]; then
    log_error "CONTAINER_TYPE is required"
    exit 1
fi

if [[ -z "$IMAGE_PREFIX" ]]; then
    log_error "IMAGE_PREFIX is required"
    exit 1
fi

if [[ -z "$TAG_SUFFIX" ]]; then
    log_error "TAG_SUFFIX is required"
    exit 1
fi

log_group_start "Prepare Image Configuration"
log_info "Container type:      ${CONTAINER_TYPE}"
log_info "Image prefix:        ${IMAGE_PREFIX}"
log_info "Tag suffix:          ${TAG_SUFFIX}"
log_info "Registry:            ${REGISTRY}"
log_info "Perf tracking:       ${ENABLE_PERF_TRACKING}"

# Preserve the original prefix before any perf-track modification
ORIGINAL_IMAGE_PREFIX="$IMAGE_PREFIX"

# Apply perf-tracking suffix to image prefix for supported container types
if [[ "$ENABLE_PERF_TRACKING" == "true" ]] && [[ "$CONTAINER_TYPE" =~ ^(core|full|custom)$ ]]; then
    IMAGE_PREFIX="${IMAGE_PREFIX}-perf-track"
    log_info "Perf tracking enabled: image prefix modified to ${IMAGE_PREFIX}"
fi

# Compute tag patterns for each container type category
# core/full: prefix contains the base image name (e.g., owner/sst), type is appended
# dev/custom: prefix IS the full image name (e.g., owner/sst-dev or owner/sst-devel)
# experiment: prefix/experiment-name
CORE_FULL_PATTERN="${REGISTRY}/${IMAGE_PREFIX}-${CONTAINER_TYPE}:${TAG_SUFFIX}"
DEV_CUSTOM_PATTERN="${REGISTRY}/${IMAGE_PREFIX}:${TAG_SUFFIX}"
EXPERIMENT_PATTERN="${REGISTRY}/${ORIGINAL_IMAGE_PREFIX}/${EXPERIMENT_NAME}:${TAG_SUFFIX}"
DEFAULT_PATTERN="${REGISTRY}/${IMAGE_PREFIX}:${TAG_SUFFIX}"

log_info "Computed patterns:"
log_info "  core_full_pattern:   ${CORE_FULL_PATTERN}"
log_info "  dev_custom_pattern:  ${DEV_CUSTOM_PATTERN}"
log_info "  experiment_pattern:  ${EXPERIMENT_PATTERN}"
log_info "  default_pattern:     ${DEFAULT_PATTERN}"
log_group_end

# Emit GitHub Actions outputs
set_output "image_prefix"        "${IMAGE_PREFIX}"
set_output "core_full_pattern"   "${CORE_FULL_PATTERN}"
set_output "dev_custom_pattern"  "${DEV_CUSTOM_PATTERN}"
set_output "experiment_pattern"  "${EXPERIMENT_PATTERN}"
set_output "default_pattern"     "${DEFAULT_PATTERN}"

log_success "Image configuration complete"
