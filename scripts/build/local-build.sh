#!/bin/bash
# Local Container Build Script

# Use standardized initialization
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

# Change to repository root so relative paths work correctly
cd "${PROJECT_ROOT}"

# Load simple argument parsing
source "${SCRIPT_DIR}/../lib/simple-args.sh"

# Configuration
REGISTRY=$(get_config_value "REGISTRY" "$DEFAULT_REGISTRY")
BUILD_NCPUS=$(get_config_value "BUILD_NCPUS" "$DEFAULT_BUILD_NCPUS")
PLATFORM=$(uname -m)

# Use centralized configuration values
DEFAULT_SST_VERSION=$(get_config_value "SST_VERSION" "$DEFAULT_SST_VERSION")
DEFAULT_MPICH_VERSION=$(get_config_value "MPICH_VERSION" "$DEFAULT_MPICH_VERSION")

# Parse and normalize arguments using the shared CLI framework.
if ! parse_script_arguments "local-build" "full" "$@"; then
    trap - EXIT ERR
    exit 1
fi

# Handle help with cleanup trap disabled
if [[ "$HELP_REQUESTED" == "true" ]]; then
    trap - EXIT ERR
    show_argument_profile_help "local-build"
    exit 0
fi

# Extract container type from remaining arguments
CONTAINER_TYPE=""
while IFS= read -r arg; do
    case "$arg" in
        core|full|dev|custom|experiment)
            if [[ -z "$CONTAINER_TYPE" ]]; then
                CONTAINER_TYPE="$arg"
                break
            fi
            ;;
    esac
done < <(get_remaining_args)

# Validate required arguments
if ! validate_required_args "CONTAINER_TYPE" "$CONTAINER_TYPE" "Container type"; then
    log_error "Usage: $(basename "$0") [OPTIONS] CONTAINER_TYPE"
    log_error "Use --help for more information"
    exit 1
fi

if ! validate_container_type "$CONTAINER_TYPE"; then
    log_error "Valid types: ${VALID_CONTAINER_TYPES[*]}"
    exit 1
fi

if [[ "$VALIDATE_ONLY" != "true" ]] && [[ -n "$SST_CORE_PATH" ]] && [[ "$CONTAINER_TYPE" != "custom" ]]; then
    log_error "--core-path is only supported with CONTAINER_TYPE=custom"
    exit 1
fi

# Validate SST version for release builds
if [[ "$CONTAINER_TYPE" =~ ^(core|full)$ ]]; then
    if ! validate_sst_version "$SST_VERSION"; then
        log_warning "SST version ${SST_VERSION} may not be valid."
        log_warning "Known valid versions: ${VALID_SST_VERSIONS[*]}"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Set up remaining configuration
REGISTRY="${REGISTRY:-$DEFAULT_REGISTRY}"
BUILD_NCPUS="${BUILD_NCPUS:-$DEFAULT_BUILD_NCPUS}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-$(detect_container_engine)}"

if [[ "$VALIDATE_ONLY" == "true" ]] && [[ "$VALIDATION_MODE" == "none" ]]; then
    log_error "--validate-only requires a validation mode other than none"
    trap - EXIT ERR
    exit 1
fi

PLATFORM="${TARGET_PLATFORM:-${PLATFORM:-$(uname -m)}}"

# Detect platform architecture
case "$PLATFORM" in
    x86_64|amd64|linux/amd64)
        DOCKER_PLATFORM="linux/amd64"
        ARCH="amd64"
        ;;
    aarch64|arm64|linux/arm64)
        DOCKER_PLATFORM="linux/arm64"
        ARCH="arm64"
        ;;
    *)
        log_error "Unsupported platform: $PLATFORM"
        log_error "Supported platforms: x86_64, arm64, linux/amd64, linux/arm64"
        exit 1
        ;;
esac

if ! require_host_platform "$DOCKER_PLATFORM" "Target platform (--platform)"; then
    exit 1
fi

# Validate container engine
if ! validate_container_engine "$CONTAINER_ENGINE"; then
    log_error "Container engine validation failed"
    exit 1
fi

log_info "=== Local Container Build ==="
log_info "Container Type: $CONTAINER_TYPE"
log_info "Platform: $DOCKER_PLATFORM"
log_info "Container Engine: $CONTAINER_ENGINE"
log_info "Registry: $REGISTRY"
log_info "SST Version: $SST_VERSION"
if [[ -n "$SST_ELEMENTS_VERSION" ]]; then
    log_info "SST Elements Version: $SST_ELEMENTS_VERSION"
fi
log_info "MPICH Version: $MPICH_VERSION"

# Function to download source tarballs
download_sources() {
    log_info "Downloading source files..."

    # Delegate to canonical download script for consistency
    local download_script="${PROJECT_ROOT}/scripts/build/download_tarballs.sh"

    if [[ ! -x "$download_script" ]]; then
        log_error "Download script not found: $download_script"
        exit 1
    fi

    cd "${PROJECT_ROOT}/Containerfiles"
    case "$CONTAINER_TYPE" in
        "core")
            "$download_script" --force --sst-version "$SST_VERSION" --mpich-version "$MPICH_VERSION"
            ;;
        "full")
            if [[ -n "$SST_ELEMENTS_VERSION" ]]; then
                "$download_script" --force --sst-version "$SST_VERSION" --sst-elements-version "$SST_ELEMENTS_VERSION" --mpich-version "$MPICH_VERSION"
            else
                "$download_script" --force --sst-version "$SST_VERSION" --sst-elements-version "$SST_VERSION" --mpich-version "$MPICH_VERSION"
            fi
            ;;
        "dev")
            # Development container only needs MPICH, no SST sources
            "$download_script" --force --mpich-version "$MPICH_VERSION"
            ;;
        "custom")
            # Custom builds get SST from git repos, only need MPICH
            "$download_script" --force --mpich-version "$MPICH_VERSION"
            ;;
        "experiment")
            # Experiment containers build on existing SST images, only need MPICH if at all
            "$download_script" --force --mpich-version "$MPICH_VERSION"
            ;;
        *)
            log_error "Unknown container type: $CONTAINER_TYPE"
            exit 1
            ;;
    esac
    cd "${PROJECT_ROOT}"

    log_success "Source files ready"
}

# Function to build container image
build_container() {
    local containerfile=""
    local build_target=""
    local context="${PROJECT_ROOT}/Containerfiles"
    local tag_name=""
    local build_args=()

    # Configure build parameters based on container type
    case "$CONTAINER_TYPE" in
        "core")
            containerfile="${PROJECT_ROOT}/Containerfiles/Containerfile"
            build_target="sst-core"
            local core_tag_suffix="$SST_VERSION"
            if [[ "${TAG_SUFFIX_SET:-false}" == "true" ]]; then
                core_tag_suffix="$TAG_SUFFIX"
            fi
            tag_name=$(generate_container_image_tag "$REGISTRY" "core" "$core_tag_suffix" "$ARCH" "$ENABLE_PERF_TRACKING")
            build_args+=(
                "--build-arg" "SSTver=${SST_VERSION}"
                "--build-arg" "mpich=${MPICH_VERSION}"
                "--build-arg" "NCPUS=${BUILD_NCPUS}"
            )
            ;;
        "full")
            containerfile="${PROJECT_ROOT}/Containerfiles/Containerfile"
            build_target="sst-full"
            local tag_base="$SST_VERSION"
            if [[ "${TAG_SUFFIX_SET:-false}" == "true" ]]; then
                tag_base="$TAG_SUFFIX"
            fi
            tag_name=$(generate_container_image_tag "$REGISTRY" "full" "$tag_base" "$ARCH" "$ENABLE_PERF_TRACKING")
            build_args+=(
                "--build-arg" "SSTver=${SST_VERSION}"
                "--build-arg" "mpich=${MPICH_VERSION}"
                "--build-arg" "NCPUS=${BUILD_NCPUS}"
            )
            if [[ -n "$SST_ELEMENTS_VERSION" ]]; then
                build_args+=(
                    "--build-arg" "SST_ELEMENTS_VERSION=${SST_ELEMENTS_VERSION}"
                )
            fi
            ;;
        "dev")
            containerfile="${PROJECT_ROOT}/Containerfiles/Containerfile.dev"
            local dev_tag_suffix="latest"
            if [[ "${TAG_SUFFIX_SET:-false}" == "true" ]]; then
                dev_tag_suffix="$TAG_SUFFIX"
            fi
            tag_name=$(generate_container_image_tag "$REGISTRY" "dev" "$dev_tag_suffix" "$ARCH")
            build_args+=(
                "--build-arg" "mpich=${MPICH_VERSION}"
                "--build-arg" "NCPUS=${BUILD_NCPUS}"
            )
            ;;
        "custom")
            local build_suffix=""
            local using_local_core_checkout="false"

            containerfile="${PROJECT_ROOT}/Containerfiles/Containerfile.tag"
            if ! validate_custom_core_source_selection "$SST_CORE_PATH" "$SST_CORE_REF" "$SST_CORE_REPO"; then
                exit 1
            fi

            if [[ -n "$SST_CORE_PATH" ]]; then
                using_local_core_checkout="true"
                if ! stage_local_sst_core_checkout "$SST_CORE_PATH"; then
                    exit 1
                fi
            fi

            if [[ -n "$SST_ELEMENTS_REF" ]] && [[ -z "$SST_ELEMENTS_REPO" ]]; then
                SST_ELEMENTS_REPO="$DEFAULT_SST_ELEMENTS_REPO"
            fi

            if [[ -n "$SST_ELEMENTS_REPO" || -n "$SST_ELEMENTS_REF" ]]; then
                build_target="full-build"
                if [[ "$using_local_core_checkout" == "true" ]]; then
                    build_suffix="local-full"
                else
                    build_suffix="${SST_CORE_REF}-full"
                fi
                build_args+=(
                    "--build-arg" "SSTElementsRepo=${SST_ELEMENTS_REPO}"
                    "--build-arg" "elementsTag=${SST_ELEMENTS_REF:-main}"
                )
            else
                build_target="core-build"
                if [[ "$using_local_core_checkout" == "true" ]]; then
                    build_suffix="local"
                else
                    build_suffix="${SST_CORE_REF}"
                fi
            fi

            if [[ "${TAG_SUFFIX_SET:-false}" == "true" ]]; then
                build_suffix="$TAG_SUFFIX"
            fi

            tag_name=$(generate_container_image_tag "$REGISTRY" "custom" "$build_suffix" "$ARCH" "$ENABLE_PERF_TRACKING")

            if [[ "$using_local_core_checkout" == "true" ]]; then
                build_args+=(
                    "--build-arg" "LOCAL_SST_CORE=1"
                    "--build-arg" "mpich=${MPICH_VERSION}"
                    "--build-arg" "NCPUS=${BUILD_NCPUS}"
                )
            else
                build_args+=(
                    "--build-arg" "LOCAL_SST_CORE=0"
                    "--build-arg" "SSTrepo=${SST_CORE_REPO}"
                    "--build-arg" "tag=${SST_CORE_REF}"
                    "--build-arg" "mpich=${MPICH_VERSION}"
                    "--build-arg" "NCPUS=${BUILD_NCPUS}"
                )
            fi
            ;;
        "experiment")
            if [[ -z "$EXPERIMENT_NAME" ]]; then
                log_error "Experiment builds require --experiment-name"
                exit 1
            fi
            # Delegate to experiment-build.sh so Containerfile detection and
            # build logic is exercised from the canonical implementation.
            local exp_build_script="${PROJECT_ROOT}/scripts/build/experiment-build.sh"
            local exp_args=(
                "$EXPERIMENT_NAME"
                "--registry" "$REGISTRY"
                "--tag-suffix" "$TAG_SUFFIX"
                "--platforms" "$DOCKER_PLATFORM"
                "--validation" "none"
            )
            [[ -n "$BASE_IMAGE" ]] && exp_args+=("--base-image" "$BASE_IMAGE")
            [[ "$NO_CACHE" == "true" ]] && exp_args+=("--no-cache")

            "$exp_build_script" "${exp_args[@]}"

            tag_name=$(generate_container_image_tag "$REGISTRY" "experiment" "$TAG_SUFFIX" "$ARCH" "false" "$EXPERIMENT_NAME")
            echo "$tag_name" > .last_built_image
            log_success "Build completed: $tag_name"
            return 0
            ;;
    esac

    # Add perf tracking build argument if enabled (only for core, full, custom)
    if [[ "$ENABLE_PERF_TRACKING" == "true" && "$CONTAINER_TYPE" =~ ^(core|full|custom)$ ]]; then
        build_args+=("--build-arg" "ENABLE_PERF_TRACKING=1")
    fi

    # Add no-cache flag if requested
    if [[ "$NO_CACHE" == "true" ]]; then
        build_args+=("--no-cache")
    fi

    # Add platform specification
    build_args+=("--platform" "$DOCKER_PLATFORM")

    log_info "Building container: $tag_name"
    log_info "Using containerfile: $containerfile"
    if [[ -n "$build_target" ]]; then
        log_info "Build target: $build_target"
        build_args+=("--target" "$build_target")
    fi

    # Execute build
    set -x
    "$CONTAINER_ENGINE" build \
        "${build_args[@]}" \
        --tag "$tag_name" \
        --file "$containerfile" \
        "$context"
    set +x

    echo "$tag_name" > .last_built_image
    log_success "Build completed: $tag_name"

    cleanup_local_source_stage
}

# Function to validate built container
validate_built_container() {
    local tag_name="${1:-}"
    local max_size_mb

    if [[ -z "$tag_name" ]] && [[ -f ".last_built_image" ]]; then
        tag_name=$(cat .last_built_image)
    fi

    if [[ -z "$tag_name" ]]; then
        log_error "No image tag specified for validation"
        exit 1
    fi

    log_info "Validating container: $tag_name"

    if [[ "$VALIDATION_MODE" == "none" ]]; then
        log_info "Skipping validation (validation mode: none)"
        return 0
    fi

    max_size_mb=$(get_default_size_limit "$CONTAINER_TYPE")

    case "$VALIDATION_MODE" in
        quick)
            if quick_validate_image "$CONTAINER_ENGINE" "$tag_name"; then
                log_success "Quick container validation passed"
            else
                log_error "Quick container validation failed"
                exit 1
            fi
            ;;
        metadata)
            if no_exec_validate_image "$CONTAINER_ENGINE" "$tag_name" "$max_size_mb"; then
                log_success "Metadata-only container validation passed"
            else
                log_error "Metadata-only container validation failed"
                exit 1
            fi
            ;;
        full)
            if validate_container "$CONTAINER_ENGINE" "$tag_name" "$CONTAINER_TYPE" "$max_size_mb"; then
                log_success "Container validation passed"
            else
                log_error "Container validation failed"
                exit 1
            fi
            ;;
        *)
            log_error "Unsupported validation mode: $VALIDATION_MODE"
            exit 1
            ;;
    esac
}

# Function to cleanup temporary files and images
cleanup() {
    log_info "Cleaning up..."

    cleanup_local_source_stage

    if [[ -f ".last_built_image" ]]; then
        local tag_name
        tag_name=$(cat .last_built_image)
        log_info "Removing image: $tag_name"
        "$CONTAINER_ENGINE" rmi "$tag_name" || log_warning "Failed to remove image"
        rm -f .last_built_image
    fi

    # Clean up build cache
    "$CONTAINER_ENGINE" builder prune -f || log_warning "Failed to prune build cache"

    log_success "Cleanup completed"
}

# Function for error cleanup (removes temporary files but not images)
error_cleanup() {
    log_info "Error cleanup..."
    cleanup_local_source_stage
    # Only clean up temporary files on error, preserve built images
    rm -f .last_built_image
}

# Function to run complete build sequence
run_build_sequence() {
    log_info "Starting local build sequence..."

    # Only download and build if not validate-only mode
    if [[ "$VALIDATE_ONLY" != "true" ]]; then
        # Pre-build checks
        if [[ ! -d "${PROJECT_ROOT}/Containerfiles" ]]; then
            log_error "Containerfiles directory not found. Please run from project root."
            exit 1
        fi

        # Download sources
        download_sources

        # Build container
        build_container
    fi

    # Validate container
    validate_built_container

    # Cleanup if requested
    if [[ "$CLEANUP" == "true" ]]; then
        cleanup
    else
        log_info "Image preserved. Use --cleanup to remove after the build."
        if [[ -f ".last_built_image" ]]; then
            local tag_name
            tag_name=$(cat .last_built_image)
            log_info "Built image: $tag_name"
        fi
    fi

    log_success "Build sequence completed successfully!"
}

# Trap for error cleanup (preserves images)
trap error_cleanup EXIT

# Run the build sequence
run_build_sequence

# Clear trap on successful completion
trap - EXIT