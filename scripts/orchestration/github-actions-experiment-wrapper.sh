#!/bin/bash
#
# GitHub Actions Wrapper for Experiment Builds
# Maintains compatibility with existing GitHub Actions workflow interface
#

set -euo pipefail

# Use standardized initialization
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

# GitHub Actions input mapping
EXPERIMENT_NAME="${INPUT_EXPERIMENT_NAME:-}"
BASE_IMAGE="${INPUT_BASE_IMAGE:-}"
IMAGE_PREFIX="${INPUT_IMAGE_PREFIX:-ghcr.io/$(whoami)}"
TAG_SUFFIX="${INPUT_TAG_SUFFIX:-latest}"
BUILD_PLATFORMS="${INPUT_BUILD_PLATFORMS:-linux/amd64}"
NO_CACHE="${INPUT_NO_CACHE:-false}"

# Internal parameters
VALIDATION_MODE="full"  # Default to full validation for GitHub Actions

# Parse command line arguments (primarily for error handling)
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            echo "GitHub Actions Experiment Build Wrapper"
            echo "This script is designed to be called by GitHub Actions."
            echo "It reads INPUT_* environment variables and invokes experiment-build.sh."
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            log_error "This script reads INPUT_* environment variables from GitHub Actions."
            exit 1
            ;;
        *)
            log_error "Unexpected argument: $1"
            log_error "This script does not accept positional arguments."
            exit 1
            ;;
    esac
done

main() {
    log_info "GitHub Actions Experiment Build Wrapper"

    # Validate required inputs
    if [ -z "$EXPERIMENT_NAME" ]; then
        log_error "experiment_name input is required"
        exit 1
    fi

    # Build arguments array
    local build_args=(
        "--experiment-name" "$EXPERIMENT_NAME"
        "--prefix" "$IMAGE_PREFIX"
        "--tag-suffix" "$TAG_SUFFIX"
        "--platforms" "$BUILD_PLATFORMS"
        "--validation" "$VALIDATION_MODE"
    )

    # Add base image if specified
    if [ -n "$BASE_IMAGE" ]; then
        build_args+=("--base-image" "$BASE_IMAGE")
    fi

    # Add no-cache flag if requested
    if [ "$NO_CACHE" = "true" ]; then
        build_args+=("--no-cache")
    fi

    log_info "Calling experiment build script with:"
    log_info "  Experiment: $EXPERIMENT_NAME"
    log_info "  Base Image: ${BASE_IMAGE:-<none>}"
    log_info "  Platforms: $BUILD_PLATFORMS"
    log_info "  Tag Suffix: $TAG_SUFFIX"
    log_info "  No Cache: $NO_CACHE"

    # Execute the experiment build script
    local build_script="${SCRIPT_LIB_DIR}/../build/experiment-build.sh"

    if [[ ! -x "$build_script" ]]; then
        log_error "Experiment build script not found or not executable: $build_script"
        exit 1
    fi

    log_group_start "Executing Experiment Build"
    if "$build_script" "${build_args[@]}"; then
        log_success "Experiment build completed successfully"
        log_group_end
        return 0
    else
        log_error "Experiment build failed"
        log_group_end
        return 1
    fi
}

# Run main function
main
