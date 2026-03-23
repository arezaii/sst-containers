#!/bin/bash
# GitHub Actions wrapper for custom builds
# Maintains compatibility with existing workflow while using modular build scripts

set -euo pipefail

# Use standardized initialization
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

show_usage() {
    cat << EOF
GitHub Actions Custom Build Wrapper

This script maintains compatibility with existing GitHub Actions workflows
while using the new modular build system.

Usage: $0 [OPTIONS]

Input Options (from GitHub Actions):
  --core-repo URL             SST-core repository URL
  --core-ref REF              SST-core branch, tag, or commit SHA
  --elements-repo URL         SST-elements repository URL (optional)
  --elements-ref REF          SST-elements branch, tag, or commit SHA
  --image-prefix PREFIX       Image name prefix (e.g., "sst-devel")
  --tag-suffix SUFFIX         Tag suffix for image
  --mpich-version VERSION     MPICH version to use
  --build-platforms LIST      Comma-separated platform list
  --force-rebuild BOOL        Force rebuild even if image exists
  --ignore-cache BOOL         Ignore build cache
  --enable-perf-tracking      Enable SST performance tracking

Output:
  Sets GitHub Actions outputs for downstream jobs

EOF
}

# Default values (matching GitHub Actions workflow)
CORE_REPO=""
CORE_REF=""
ELEMENTS_REPO=""
ELEMENTS_REF=""
IMAGE_PREFIX=""
TAG_SUFFIX=""
MPICH_VERSION="4.0.2"
BUILD_PLATFORMS="linux/amd64,linux/arm64"
FORCE_REBUILD=false
IGNORE_CACHE=false
ENABLE_PERF_TRACKING=false

# Parse GitHub Actions-style inputs
while [[ $# -gt 0 ]]; do
    case $1 in
        --core-repo)
            CORE_REPO="$2"
            shift 2
            ;;
        --core-ref)
            CORE_REF="$2"
            shift 2
            ;;
        --elements-repo)
            ELEMENTS_REPO="$2"
            shift 2
            ;;
        --elements-ref)
            ELEMENTS_REF="$2"
            shift 2
            ;;
        --image-prefix)
            IMAGE_PREFIX="$2"
            shift 2
            ;;
        --tag-suffix)
            TAG_SUFFIX="$2"
            shift 2
            ;;
        --mpich-version)
            MPICH_VERSION="$2"
            shift 2
            ;;
        --build-platforms)
            BUILD_PLATFORMS="$2"
            shift 2
            ;;
        --force-rebuild)
            FORCE_REBUILD="$2"
            shift 2
            ;;
        --ignore-cache)
            IGNORE_CACHE="$2"
            shift 2
            ;;
        --enable-perf-tracking)
            # Support both forms:
            #   --enable-perf-tracking
            #   --enable-perf-tracking true|false
            if [[ $# -gt 1 ]] && [[ "${2:-}" != --* ]]; then
                ENABLE_PERF_TRACKING="$2"
                shift 2
            else
                ENABLE_PERF_TRACKING="true"
                shift
            fi
            ;;
        --help)
            show_usage
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            exit 1
            ;;
        *)
            log_error "Unexpected argument: $1"
            exit 1
            ;;
    esac
done

# Normalize boolean-like values for perf tracking (bash-3 compatible)
perf_tracking_normalized="$(printf '%s' "$ENABLE_PERF_TRACKING" | tr '[:upper:]' '[:lower:]')"
case "$perf_tracking_normalized" in
    true|1|yes)
        ENABLE_PERF_TRACKING=true
        ;;
    false|0|no)
        ENABLE_PERF_TRACKING=false
        ;;
    *)
        log_error "Invalid value for --enable-perf-tracking: $ENABLE_PERF_TRACKING"
        log_error "Expected true/false (or use bare --enable-perf-tracking)"
        exit 1
        ;;
esac

# Validate required inputs
if [[ -z "$CORE_REF" ]]; then
    log_error "SST-core reference is required (--core-ref)"
    exit 1
fi

if [[ -z "$IMAGE_PREFIX" ]]; then
    log_error "Image prefix is required (--image-prefix)"
    exit 1
fi

if [[ -z "$TAG_SUFFIX" ]]; then
    log_error "Tag suffix is required (--tag-suffix)"
    exit 1
fi

# GitHub Actions environment setup
if ! is_github_actions; then
    log_error "This wrapper is designed for GitHub Actions environment"
    exit 1
fi

# Determine current platform for this runner
CURRENT_PLATFORM=$(detect_platform)
log_info "Running on platform: $CURRENT_PLATFORM"

# Check if this platform is in the build list
IFS=',' read -ra PLATFORMS <<< "$BUILD_PLATFORMS"
SHOULD_BUILD=false

for platform in "${PLATFORMS[@]}"; do
    if [[ "$platform" == "$CURRENT_PLATFORM" ]]; then
        SHOULD_BUILD=true
        break
    fi
done

if [[ "$SHOULD_BUILD" != "true" ]]; then
    log_info "Skipping build - platform $CURRENT_PLATFORM not in build list: $BUILD_PLATFORMS"
    set_output "image-tag" ""
    set_output "build-successful" "false"
    set_output "skipped" "true"
    exit 0
fi

# Set registry (GitHub Container Registry in Actions)
REGISTRY="${REGISTRY:-ghcr.io}"

log_group_start "GitHub Actions Custom Build Wrapper"
log_info "Configuration:"
log_info "  Core Repository: $CORE_REPO"
log_info "  Core Reference: $CORE_REF"
if [[ -n "$ELEMENTS_REPO" ]]; then
    log_info "  Elements Repository: $ELEMENTS_REPO"
    log_info "  Elements Reference: $ELEMENTS_REF"
fi
log_info "  Image Prefix: $IMAGE_PREFIX"
log_info "  Tag Suffix: $TAG_SUFFIX"
log_info "  MPICH Version: $MPICH_VERSION"
log_info "  Registry: $REGISTRY"
log_info "  Force Rebuild: $FORCE_REBUILD"
log_info "  Ignore Cache: $IGNORE_CACHE"
log_info "  Performance Tracking: $ENABLE_PERF_TRACKING"
log_group_end

# Build custom build script arguments
custom_build_args=(
    "--core-ref" "$CORE_REF"
    "--mpich-version" "$MPICH_VERSION"
    "--registry" "$REGISTRY"
    "--platform" "$CURRENT_PLATFORM"
    "--github-actions"
)

if [[ -n "$CORE_REPO" ]]; then
    custom_build_args+=("--core-repo" "$CORE_REPO")
fi

if [[ -n "$ELEMENTS_REPO" ]]; then
    custom_build_args+=("--elements-repo" "$ELEMENTS_REPO")
    custom_build_args+=("--elements-ref" "$ELEMENTS_REF")
fi

# Handle custom tag suffix (different from our script's tag generation)
if [[ "$TAG_SUFFIX" != "$CORE_REF" ]]; then
    custom_build_args+=("--tag-suffix" "$TAG_SUFFIX")
fi

if [[ "$IGNORE_CACHE" == "true" ]] || [[ "$FORCE_REBUILD" == "true" ]]; then
    custom_build_args+=("--no-cache")
fi

# Add perf tracking flag if enabled
if [[ "$ENABLE_PERF_TRACKING" == "true" ]]; then
    custom_build_args+=("--enable-perf-tracking")
fi

# Always validate in CI
custom_build_args+=("--validate")

# Call the custom build script
log_group_start "Executing Custom Build"

BUILD_SCRIPT="${SCRIPT_LIB_DIR}/../build/custom-build.sh"
if [[ ! -x "$BUILD_SCRIPT" ]]; then
    log_error "Custom build script not found or not executable: $BUILD_SCRIPT"
    exit 1
fi

if "$BUILD_SCRIPT" "${custom_build_args[@]}"; then
    log_success "Custom build completed successfully"
    BUILD_SUCCESS=true
else
    log_error "Custom build failed"
    BUILD_SUCCESS=false
fi

log_group_end

# Generate outputs for GitHub Actions matrix builds
if [[ "$BUILD_SUCCESS" == "true" ]]; then
    # The build script will have set outputs, but we need to generate the expected format

    # Read the image tag that was set by the build script
    IMAGE_TAG=""
    if [[ -n "${GITHUB_OUTPUT:-}" ]] && [[ -f "$GITHUB_OUTPUT" ]]; then
        # Extract image-tag from GitHub output file
        IMAGE_TAG=$(grep "^image-tag=" "$GITHUB_OUTPUT" | cut -d'=' -f2- | tail -1)
    fi

    if [[ -z "$IMAGE_TAG" ]]; then
        log_error "Failed to get image tag from build script"
        exit 1
    fi

    # Set additional outputs expected by the workflow
    set_output "build-successful" "true"
    set_output "platform" "$CURRENT_PLATFORM"

    # Create a JSON array with the single image for matrix collection
    BUILT_IMAGES_JSON=$(jq -n --arg tag "$IMAGE_TAG" '[$tag]')
    set_output "built-images" "$BUILT_IMAGES_JSON"

    create_job_summary "
## Custom Build Completed [SUCCESS]

| Property | Value |
|----------|-------|
| Image Tag | \`$IMAGE_TAG\` |
| Platform | $CURRENT_PLATFORM |
| Core Ref | $CORE_REF |
| MPICH Version | $MPICH_VERSION |
"

else
    set_output "build-successful" "false"
    set_output "built-images" "[]"

    create_job_summary "
## Custom Build Failed [FAILED]

| Property | Value |
|----------|-------|
| Platform | $CURRENT_PLATFORM |
| Core Ref | $CORE_REF |
| Error | Build execution failed |
"
    exit 1
fi

log_success "GitHub Actions wrapper completed successfully"
exit 0
