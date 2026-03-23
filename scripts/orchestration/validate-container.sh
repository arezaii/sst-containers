#!/bin/bash
# Validate a Docker container image pulled from the registry
# Checks image size against a configurable limit and verifies the container can be instantiated
#
# Required environment variables:
#   IMAGE_TAG   - fully qualified image tag to validate
#   PLATFORM    - target platform (e.g., linux/amd64)
#
# Optional environment variables:
#   MAX_SIZE_MB - maximum allowed image size in MB (default: 2048)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

IMAGE_TAG="${IMAGE_TAG:-}"
PLATFORM="${PLATFORM:-}"
MAX_SIZE_MB="${MAX_SIZE_MB:-2048}"

if [[ -z "$IMAGE_TAG" ]]; then
    log_error "IMAGE_TAG is required"
    exit 1
fi

if [[ -z "$PLATFORM" ]]; then
    log_error "PLATFORM is required"
    exit 1
fi

log_group_start "Validate Container"
log_info "Image:    ${IMAGE_TAG}"
log_info "Platform: ${PLATFORM}"
log_info "Max size: ${MAX_SIZE_MB} MB"

# Pull the image for the target platform
log_info "Pulling image..."
docker pull "$IMAGE_TAG"

# Inspect image size
IMAGE_SIZE=$(docker image inspect "$IMAGE_TAG" --format='{{.Size}}')
IMAGE_SIZE_MB=$((IMAGE_SIZE / 1024 / 1024))
log_info "Image size: ${IMAGE_SIZE_MB} MB"

if [[ $IMAGE_SIZE_MB -gt $MAX_SIZE_MB ]]; then
    log_error "Image size (${IMAGE_SIZE_MB} MB) exceeds maximum allowed size (${MAX_SIZE_MB} MB)"
    log_group_end
    exit 1
fi

# Verify the container can be instantiated (create + immediately remove)
CONTAINER_ID=$(docker create --platform "$PLATFORM" "$IMAGE_TAG" /bin/true)
if [[ -n "$CONTAINER_ID" ]]; then
    docker rm "$CONTAINER_ID" >/dev/null 2>&1
    log_success "Container validation passed: ${IMAGE_SIZE_MB} MB, ${PLATFORM}"
else
    log_error "Failed to instantiate container"
    log_group_end
    exit 1
fi

log_group_end
