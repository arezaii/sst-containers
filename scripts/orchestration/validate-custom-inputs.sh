#!/bin/bash
# Validate inputs for the build-custom workflow
# Determines build type (core vs full) and tag suffix, then sets GITHUB_OUTPUT variables
#
# Required environment variables:
#   CORE_REF     - SST-core branch, tag, or commit SHA
#
# Optional environment variables:
#   ELEMENTS_REPO - SST-elements repository URL (triggers full build when set)
#   ELEMENTS_REF  - SST-elements reference (required when ELEMENTS_REPO is set)
#   IMAGE_TAG     - explicit image tag to use as tag_suffix (default: sanitized CORE_REF)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

CORE_REF="${CORE_REF:-}"
ELEMENTS_REPO="${ELEMENTS_REPO:-}"
ELEMENTS_REF="${ELEMENTS_REF:-}"
IMAGE_TAG="${IMAGE_TAG:-}"

# CORE_REF is always required
if [[ -z "$CORE_REF" ]]; then
    log_error "CORE_REF (sst_core_ref input) is required"
    exit 1
fi

log_group_start "Validate Custom Build Inputs"

# Determine build type
if [[ -n "$ELEMENTS_REPO" ]]; then
    if [[ -z "$ELEMENTS_REF" ]]; then
        log_error "SST-elements ref (ELEMENTS_REF) is required when elements_repo is provided"
        exit 1
    fi
    BUILD_TYPE="full"
    log_info "Build type: full (core + elements)"
else
    BUILD_TYPE="core"
    log_info "Build type: core only"
fi

# Determine image tag suffix
if [[ -n "$IMAGE_TAG" ]]; then
    TAG_SUFFIX="$IMAGE_TAG"
    log_info "Tag suffix: ${TAG_SUFFIX} (explicit)"
else
    # Sanitize core ref: replace / with -, truncate to 50 chars
    TAG_SUFFIX=$(echo "$CORE_REF" | sed 's/\//-/g' | cut -c1-50)
    log_info "Tag suffix: ${TAG_SUFFIX} (derived from core ref)"
fi

log_group_end

set_output "build_type"  "$BUILD_TYPE"
set_output "tag_suffix"  "$TAG_SUFFIX"

log_success "Input validation complete: build_type=${BUILD_TYPE}, tag_suffix=${TAG_SUFFIX}"
