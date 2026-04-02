#!/bin/bash
# Custom SST container build script
# Builds SST containers from any Git repository and branch/tag/commit

# Use standardized initialization
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

# Load simple argument parsing
source "${SCRIPT_DIR}/../lib/simple-args.sh"

# Parse and normalize arguments using the shared CLI framework.
if ! parse_script_arguments "custom-build" "none" "$@"; then
    trap - EXIT ERR
    exit 1
fi

# Handle help with cleanup trap disabled
if [[ "$HELP_REQUESTED" == "true" ]]; then
    trap - EXIT ERR
    show_argument_profile_help "custom-build"
    exit 0
fi

# Validate required arguments
if ! validate_required_args "SST_CORE_REF" "$SST_CORE_REF" "SST-core reference (--core-ref)"; then
    exit 1
fi

if ! validate_git_ref "$SST_CORE_REF" "SST-core reference"; then
    exit 1
fi

if ! validate_url "$SST_CORE_REPO" "SST-core repository URL"; then
    exit 1
fi

if [[ -n "$SST_ELEMENTS_REF" ]] && [[ -z "$SST_ELEMENTS_REPO" ]]; then
    SST_ELEMENTS_REPO="$DEFAULT_SST_ELEMENTS_REPO"
fi

# If elements repo is specified, elements ref is also required
if [[ -n "$SST_ELEMENTS_REPO" ]] && ! validate_required_args "SST_ELEMENTS_REF" "$SST_ELEMENTS_REF" "SST-elements reference (--elements-ref) when elements repo is specified"; then
    exit 1
fi

if [[ -n "$SST_ELEMENTS_REPO" ]] && ! validate_url "$SST_ELEMENTS_REPO" "SST-elements repository URL"; then
    exit 1
fi

if [[ -n "$SST_ELEMENTS_REF" ]] && ! validate_git_ref "$SST_ELEMENTS_REF" "SST-elements reference"; then
    exit 1
fi

# Detect container engine if not specified
if [[ -z "$CONTAINER_ENGINE" ]]; then
    CONTAINER_ENGINE=$(detect_container_engine)
fi

# Validate container engine
if ! validate_container_engine "$CONTAINER_ENGINE"; then
    exit 1
fi

# Detect target platform if not specified
if [[ -z "$TARGET_PLATFORM" ]]; then
    TARGET_PLATFORM=$(detect_platform)
fi

# Validate target platform
if ! validate_platform "$TARGET_PLATFORM"; then
    exit 1
fi

# Check if we can build for target platform locally
if ! can_build_platform "$TARGET_PLATFORM"; then
    log_warning "Cross-platform build detected"
fi

# Determine build type and generate tag
BUILD_TYPE="core-build"
if [[ -n "$SST_ELEMENTS_REPO" ]]; then
    BUILD_TYPE="full-build"
fi

# Generate tag suffix if not explicitly provided
if [[ "${TAG_SUFFIX_SET:-false}" != "true" ]]; then
    TAG_SUFFIX="$SST_CORE_REF"
    if [[ -n "$SST_ELEMENTS_REPO" ]]; then
        TAG_SUFFIX="${TAG_SUFFIX}-full"
    fi
fi

# Generate final image tag
ARCH=$(get_arch)
IMAGE_TAG=$(generate_container_image_tag "$REGISTRY" "custom" "$TAG_SUFFIX" "$ARCH" "$ENABLE_PERF_TRACKING")

log_group_start "Custom SST Container Build"
log_info "Build Configuration:"
log_info "  SST Core Repository: $SST_CORE_REPO"
log_info "  SST Core Reference: $SST_CORE_REF"
if [[ -n "$SST_ELEMENTS_REPO" ]]; then
    log_info "  SST Elements Repository: $SST_ELEMENTS_REPO"
    log_info "  SST Elements Reference: $SST_ELEMENTS_REF"
fi
log_info "  MPICH Version: $MPICH_VERSION"
log_info "  Performance Tracking: $ENABLE_PERF_TRACKING"
log_info "  Build Type: $BUILD_TYPE"
log_info "  Target Platform: $TARGET_PLATFORM"
log_info "  Container Engine: $CONTAINER_ENGINE"
log_info "  Image Tag: $IMAGE_TAG"
log_group_end

# Build arguments array
build_args=(
    "--file" "Containerfiles/Containerfile.tag"
    "--target" "$BUILD_TYPE"
    "--tag" "$IMAGE_TAG"
    "--build-arg" "SSTrepo=${SST_CORE_REPO}"
    "--build-arg" "tag=${SST_CORE_REF}"
    "--build-arg" "mpich=${MPICH_VERSION}"
    "--build-arg" "NCPUS=${BUILD_NCPUS}"
    "--platform" "$TARGET_PLATFORM"
)

# Add elements-specific build args if building full
if [[ "$BUILD_TYPE" == "full-build" ]]; then
    build_args+=(
        "--build-arg" "SSTElementsRepo=${SST_ELEMENTS_REPO}"
        "--build-arg" "elementsTag=${SST_ELEMENTS_REF}"
    )
fi

# Add perf tracking build argument if enabled
if [[ "$ENABLE_PERF_TRACKING" == "true" ]]; then
    build_args+=("--build-arg" "ENABLE_PERF_TRACKING=1")
fi

# Add cache control
if [[ "$NO_CACHE" == "true" ]]; then
    build_args+=("--no-cache")
fi

# Execute build
log_group_start "Building Container"
start_time=$(date +%s)

if log_exec "Container build" "$CONTAINER_ENGINE" build "${build_args[@]}" "Containerfiles"; then
    end_time=$(date +%s)
    build_time=$((end_time - start_time))
    log_success "Container build completed in ${build_time}s"
else
    log_error "Container build failed"
    exit 1
fi

log_group_end

# Get image size
IMAGE_SIZE_MB=$(get_image_size_mb "$CONTAINER_ENGINE" "$IMAGE_TAG")
log_info "Image size: ${IMAGE_SIZE_MB}MB"

# Report build metrics for GitHub Actions
if [[ "$GITHUB_ACTIONS_MODE" == "true" ]] || is_github_actions; then
    report_build_metrics "$IMAGE_TAG" "$build_time" "$IMAGE_SIZE_MB" "$TARGET_PLATFORM"
fi

# Validate container if requested
if [[ "$VALIDATION_MODE" != "none" ]]; then
    log_group_start "Validating Container"

    # Determine container type for validation
    VALIDATION_TYPE="custom"
    MAX_SIZE_MB=$(get_default_size_limit "custom")

    case "$VALIDATION_MODE" in
        quick)
            if quick_validate_image "$CONTAINER_ENGINE" "$IMAGE_TAG"; then
                log_success "Quick container validation passed"
            else
                log_error "Quick container validation failed"
                exit 1
            fi
            ;;
        metadata)
            if no_exec_validate_image "$CONTAINER_ENGINE" "$IMAGE_TAG" "$MAX_SIZE_MB"; then
                log_success "Metadata-only container validation passed"
            else
                log_error "Metadata-only container validation failed"
                exit 1
            fi
            ;;
        full)
            if validate_container "$CONTAINER_ENGINE" "$IMAGE_TAG" "$VALIDATION_TYPE" "$MAX_SIZE_MB"; then
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

    log_group_end
fi

# Cleanup if requested and validation passed
if [[ "$CLEANUP" == "true" ]]; then
    log_info "Cleaning up image: $IMAGE_TAG"
    if "$CONTAINER_ENGINE" rmi "$IMAGE_TAG" &> /dev/null; then
        log_success "Image cleaned up successfully"
    else
        log_warning "Failed to clean up image"
    fi
fi

log_success "Custom build completed successfully"
log_info "Image: $IMAGE_TAG"

# Output final result for consumption by other scripts
if [[ "$GITHUB_ACTIONS_MODE" == "true" ]] || is_github_actions; then
    set_output "image-tag" "$IMAGE_TAG"
    set_output "build-successful" "true"
fi

exit 0
