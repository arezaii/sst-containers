#!/bin/bash
# Simplified argument parsing framework
# Compatible with older bash versions, focused on reducing duplication

set -euo pipefail

# Simple variables to track parsed arguments
SST_VERSION=""
MPICH_VERSION=""
SST_CORE_REPO=""
SST_CORE_REF=""
SST_ELEMENTS_REPO=""
SST_ELEMENTS_REF=""
SST_ELEMENTS_VERSION=""
EXPERIMENT_NAME=""
BASE_IMAGE=""
ENABLE_PERF_TRACKING="false"
NO_CACHE="false"
CLEANUP="false"
VALIDATE="false"
VALIDATE_ONLY="false"
VALIDATE_QUICK="false"
VALIDATE_NO_EXEC="false"
REGISTRY=""
TAG_SUFFIX=""
TAG_SUFFIX_SET="false"
HELP_REQUESTED="false"

# Build-specific variables
BUILD_NCPUS=""
CONTAINER_ENGINE=""
TARGET_PLATFORM=""
GITHUB_ACTIONS_MODE="false"

# Experiment-specific variables
IMAGE_PREFIX=""
BUILD_PLATFORMS=""
VALIDATION_MODE=""
declare -a BUILD_ARGS=()

# Container engine preferences
USE_DOCKER="false"
USE_PODMAN="false"

# Remaining positional arguments
declare -a REMAINING_ARGS=()

# Initialize with defaults from config
init_argument_defaults() {
    SST_VERSION="${DEFAULT_SST_VERSION:-15.1.2}"
    MPICH_VERSION="${DEFAULT_MPICH_VERSION:-4.0.2}"
    SST_CORE_REPO="${DEFAULT_SST_CORE_REPO:-https://github.com/sstsimulator/sst-core.git}"
    SST_ELEMENTS_REPO=""
    SST_ELEMENTS_REF=""
    SST_ELEMENTS_VERSION=""
    REGISTRY="${DEFAULT_REGISTRY:-localhost:5000}"
    BUILD_NCPUS="${DEFAULT_BUILD_NCPUS:-4}"
    CONTAINER_ENGINE=""
    TARGET_PLATFORM=""
    GITHUB_ACTIONS_MODE="false"
    ENABLE_PERF_TRACKING="false"
    NO_CACHE="false"
    CLEANUP="false"
    VALIDATE="false"
    VALIDATE_ONLY="false"
    VALIDATE_QUICK="false"
    VALIDATE_NO_EXEC="false"
    USE_DOCKER="false"
    USE_PODMAN="false"
    HELP_REQUESTED="false"
    TAG_SUFFIX_SET="false"
    BUILD_ARGS=()
    REMAINING_ARGS=()

    # Experiment-specific defaults
    EXPERIMENT_NAME=""
    BASE_IMAGE="sst-core:latest"
    IMAGE_PREFIX="ghcr.io/$(whoami)"
    TAG_SUFFIX="latest"
    BUILD_PLATFORMS="linux/amd64"
    VALIDATION_MODE="full"
}

# Parse command-line arguments using simple approach
parse_simple_arguments() {
    init_argument_defaults

    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h|help)
                HELP_REQUESTED="true"
                shift
                ;;
            --version|--sst-version)
                SST_VERSION="$2"
                shift 2
                ;;
            --mpich|--mpich-version)
                MPICH_VERSION="$2"
                shift 2
                ;;
            --repo|--sst-core-repo|--core-repo)
                SST_CORE_REPO="$2"
                shift 2
                ;;
            --ref|--sst-core-ref|--core-ref)
                SST_CORE_REF="$2"
                shift 2
                ;;
            --elements-repo|--sst-elements-repo)
                SST_ELEMENTS_REPO="$2"
                shift 2
                ;;
            --elements-ref|--sst-elements-ref)
                SST_ELEMENTS_REF="$2"
                shift 2
                ;;
            --elements-version|--sst-elements-version)
                SST_ELEMENTS_VERSION="$2"
                shift 2
                ;;
            --experiment-name)
                EXPERIMENT_NAME="$2"
                shift 2
                ;;
            --base-image)
                BASE_IMAGE="$2"
                shift 2
                ;;
            --registry)
                REGISTRY="$2"
                shift 2
                ;;
            --tag-suffix)
                TAG_SUFFIX="$2"
                TAG_SUFFIX_SET="true"
                shift 2
                ;;
            --enable-perf-tracking)
                ENABLE_PERF_TRACKING="true"
                shift
                ;;
            --no-cache)
                NO_CACHE="true"
                shift
                ;;
            --cleanup)
                CLEANUP="true"
                shift
                ;;
            --validate)
                VALIDATE="true"
                shift
                ;;
            --validate-only)
                VALIDATE_ONLY="true"
                shift
                ;;
            --validate-quick)
                VALIDATE_QUICK="true"
                shift
                ;;
            --validate-no-exec)
                VALIDATE_NO_EXEC="true"
                shift
                ;;
            --docker)
                USE_DOCKER="true"
                shift
                ;;
            --podman)
                USE_PODMAN="true"
                shift
                ;;
            --build-ncpus)
                BUILD_NCPUS="$2"
                shift 2
                ;;
            --engine)
                CONTAINER_ENGINE="$2"
                shift 2
                ;;
            --platform)
                TARGET_PLATFORM="$2"
                shift 2
                ;;
            --github-actions)
                GITHUB_ACTIONS_MODE="true"
                shift
                ;;
            --prefix)
                IMAGE_PREFIX="$2"
                shift 2
                ;;
            --platforms)
                BUILD_PLATFORMS="$2"
                shift 2
                ;;
            --validation)
                VALIDATION_MODE="$2"
                shift 2
                ;;
            --build-arg)
                BUILD_ARGS+=("$2")
                shift 2
                ;;
            *)
                # Store as remaining argument
                REMAINING_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

# Show standardized help for scripts
show_simple_help() {
    local script_name="$(basename "$0")"

    if [[ -n "${SCRIPT_DESCRIPTION:-}" ]]; then
        echo "$SCRIPT_DESCRIPTION"
    else
        echo "Usage: $script_name [OPTIONS]"
    fi

    echo
    echo "Common SST Container Options:"
    echo "  --sst-version VERSION     SST version to use (default: $SST_VERSION)"
    echo "  --mpich-version VERSION   MPICH version to use (default: $MPICH_VERSION)"
    echo "  --core-repo URL           SST-core repository URL"
    echo "  --core-ref REF            SST-core git reference (branch/tag/commit)"
    echo "  --elements-repo URL       SST-elements repository URL"
    echo "  --elements-ref REF        SST-elements git reference"
    echo "  --elements-version VER    SST-elements release version override (for full release builds)"
    echo "  --experiment-name NAME    Experiment name for testing"
    echo "  --base-image IMAGE        Base image for experiment builds"
    echo "  --registry URL            Container registry (default: $REGISTRY)"
    echo "  --tag-suffix SUFFIX       Custom tag suffix for images"
    echo "  --build-ncpus NUMBER      Number of CPU cores for build (default: $BUILD_NCPUS)"
    echo "  --engine ENGINE           Container engine to use (docker/podman)"
    echo "  --platform PLATFORM       Target platform (linux/amd64, linux/arm64)"
    echo "  --github-actions          Enable GitHub Actions output format"
    echo "  --enable-perf-tracking    Enable SST performance tracking"
    echo "  --no-cache               Build without using cache"
    echo "  --cleanup                Clean up after successful operation"
    echo "  --validate               Run validation after build"
    echo "  --validate-only          Only validate, don't build"
    echo "  --validate-quick         Quick validation (no execution tests)"
    echo "  --validate-no-exec       Validate without executing containers"
    echo "  --docker                 Use docker container engine"
    echo "  --podman                 Use podman container engine"
    echo "  --help, -h               Show this help message"

    if [[ -n "${SCRIPT_EXAMPLES:-}" ]]; then
        echo
        echo "Examples:"
        echo "$SCRIPT_EXAMPLES"
    fi
}

# Get container engine preference
get_container_engine_args() {
    if [[ "$USE_DOCKER" == "true" ]]; then
        echo "--docker"
    elif [[ "$USE_PODMAN" == "true" ]]; then
        echo "--podman"
    fi
}

# Build extra arguments for passing to other scripts
get_extra_args() {
    local args=()

    [[ "$NO_CACHE" == "true" ]] && args+=("--no-cache")
    [[ "$CLEANUP" == "true" ]] && args+=("--cleanup")
    [[ "$VALIDATE" == "true" ]] && args+=("--validate")
    [[ "$VALIDATE_ONLY" == "true" ]] && args+=("--validate-only")
    [[ "$VALIDATE_QUICK" == "true" ]] && args+=("--validate-quick")
    [[ "$VALIDATE_NO_EXEC" == "true" ]] && args+=("--validate-no-exec")
    [[ "$ENABLE_PERF_TRACKING" == "true" ]] && args+=("--enable-perf-tracking")

    # Add container engine
    local engine_args=$(get_container_engine_args)
    [[ -n "$engine_args" ]] && args+=("$engine_args")

    printf '%s\n' "${args[@]}"
}

# Get remaining positional arguments
get_remaining_args() {
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
        printf '%s\n' "${REMAINING_ARGS[@]}"
    fi
}
