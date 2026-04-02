#!/bin/bash
# Validate a container image pulled from the registry
# Checks image size against a configurable limit and verifies the container can be instantiated
#
# Required environment variables:
#   IMAGE_TAG   - fully qualified image tag to validate
#   PLATFORM    - target platform (e.g., linux/amd64)
#
# Optional environment variables:
#   MAX_SIZE_MB       - maximum allowed image size in MB (default: 2048)
#   CONTAINER_ENGINE  - docker or podman (default: auto-detect)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

IMAGE_TAG="${IMAGE_TAG:-}"
PLATFORM="${PLATFORM:-}"
MAX_SIZE_MB="${MAX_SIZE_MB:-2048}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-$(detect_container_engine)}"

if [[ -z "$IMAGE_TAG" ]]; then
    log_error "IMAGE_TAG is required"
    exit 1
fi

if [[ -z "$PLATFORM" ]]; then
    log_error "PLATFORM is required"
    exit 1
fi

if ! validate_container_engine "$CONTAINER_ENGINE"; then
    log_error "Container engine validation failed"
    exit 1
fi

log_group_start "Validate Container"
log_info "Image:    ${IMAGE_TAG}"
log_info "Platform: ${PLATFORM}"
log_info "Max size: ${MAX_SIZE_MB} MB"
log_info "Engine:   ${CONTAINER_ENGINE}"

# Pull the image for the target platform
log_info "Pulling image..."
"$CONTAINER_ENGINE" pull "$IMAGE_TAG"

# Inspect image size
IMAGE_SIZE=$("$CONTAINER_ENGINE" image inspect "$IMAGE_TAG" --format='{{.Size}}')
IMAGE_SIZE_MB=$((IMAGE_SIZE / 1024 / 1024))
log_info "Image size: ${IMAGE_SIZE_MB} MB"

if [[ $IMAGE_SIZE_MB -gt $MAX_SIZE_MB ]]; then
    log_error "Image size (${IMAGE_SIZE_MB} MB) exceeds maximum allowed size (${MAX_SIZE_MB} MB)"
    log_group_end
    exit 1
fi

# Verify the container can be instantiated (create + immediately remove)
CONTAINER_ID=$("$CONTAINER_ENGINE" create --platform "$PLATFORM" "$IMAGE_TAG" /bin/true)
if [[ -n "$CONTAINER_ID" ]]; then
    "$CONTAINER_ENGINE" rm "$CONTAINER_ID" >/dev/null 2>&1
    log_success "Container validation passed: ${IMAGE_SIZE_MB} MB, ${PLATFORM}"
else
    log_error "Failed to instantiate container"
    log_group_end
    exit 1
fi

log_group_end
