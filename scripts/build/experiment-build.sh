#!/bin/bash
# Experiment Build Script - SST Container Factory
# Builds experiment containers with optional custom Containerfiles

# Use standardized initialization
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/init.sh"

# Load simple argument parsing
source "${SCRIPT_DIR}/../lib/simple-args.sh"

# Default values using centralized config
EXPERIMENT_NAME=""
BASE_IMAGE="sst-core:latest"
TAG_SUFFIX="latest"
BUILD_PLATFORMS="linux/amd64"
NO_CACHE=false
REGISTRY=$(get_config_value "REGISTRY" "$DEFAULT_REGISTRY")
VALIDATION_MODE="full"

# Build args that will be passed to container engine
declare -a BUILD_ARGS

show_usage() {
    show_argument_profile_help "experiment-build"
}

detect_experiment_containerfile_type() {
    local experiment_name="$1"
    local base_image="$2"
    local container_engine="$3"

    log_info "Validating experiment configuration..."

    # Check if experiment directory exists
    if ! validate_directory_exists "$PROJECT_ROOT/$experiment_name" "Experiment directory '$experiment_name'"; then
        exit 1
    fi

    log_info "Experiment directory exists: $experiment_name"

    # Check if experiment has its own Containerfile
    if [ -f "$PROJECT_ROOT/$experiment_name/Containerfile" ]; then
        log_info "Using custom Containerfile from experiment directory"
        echo "custom"
        return 0
    else
        log_info "Using template Containerfile.experiment"

        # Validate base image if using template
        if [ -n "$base_image" ]; then
            validate_base_image "$base_image" "$container_engine"
        fi

        echo "template"
        return 0
    fi
}

validate_base_image() {
    local base_image="$1"
    local container_engine="${2:-${CONTAINER_ENGINE:-$(detect_container_engine)}}"
    local resolved_image

    log_info "Validating base image: $base_image"

    resolved_image=$(resolve_base_image_reference "$base_image")

    log_info "Resolved base image: $resolved_image"

    # Check base image accessibility
    if ! inspect_remote_manifest "$container_engine" "$resolved_image" >/dev/null 2>&1; then
        log_error "Base image not found: $resolved_image"
        log_error "For images in this repository, use format: sst-core:latest"
        log_error "For external images, use full path: ghcr.io/username/image:tag"
        exit 1
    fi

    log_info "Base image is accessible"
}

build_experiment_container() {
    local container_type="$1"
    local containerfile_path="$2"
    local docker_context="$3"
    local tag_name="$4"
    local container_engine="$5"  # Pass container engine as parameter

    log_info "Building experiment container..."
    log_info "Container type: $container_type"
    log_info "Containerfile: $containerfile_path"
    log_info "Context: $docker_context"
    log_info "Tag: $tag_name"

    # Build the container arguments
    local build_cmd=("$container_engine" "build")

    # Add platform specification for multi-platform builds
    if [[ "$BUILD_PLATFORMS" == *","* ]]; then
        build_cmd+=("--platform" "$BUILD_PLATFORMS")
    else
        build_cmd+=("--platform" "$BUILD_PLATFORMS")
    fi

    # Add containerfile path
    build_cmd+=("-f" "$containerfile_path")

    # Add tag
    build_cmd+=("-t" "$tag_name")

    # Add no-cache flag if requested
    if [ "$NO_CACHE" = true ]; then
        build_cmd+=("--no-cache")
    fi

    # Add custom build args
    if [ ${#BUILD_ARGS[@]} -gt 0 ]; then
        for arg in "${BUILD_ARGS[@]}"; do
            build_cmd+=("--build-arg" "$arg")
        done
    fi

    # Add context (experiment directory)
    build_cmd+=("$docker_context")

    log_group_start "Container Build"
    log_exec "Building experiment container" "${build_cmd[@]}"
    log_group_end

    log_info "Container built successfully: $tag_name"

    # Set GitHub Actions outputs
    if is_github_actions; then
        set_output "container_tag" "$tag_name"
        set_output "container_type" "$container_type"
        set_output "success" "true"
    fi

    return 0
}

main() {
    # Parse and normalize command line arguments using the shared CLI framework.
    if ! parse_script_arguments "experiment-build" "full" "$@"; then
        trap - EXIT ERR
        exit 1
    fi

    # Handle help request
    if [ "$HELP_REQUESTED" = "true" ]; then
        trap - EXIT ERR
        show_usage
        exit 0
    fi

    log_info "Starting experiment container build..."

    # Get experiment name from remaining args (first positional argument)
    if [ ${#REMAINING_ARGS[@]} -gt 0 ]; then
        EXPERIMENT_NAME="${REMAINING_ARGS[0]}"
    fi

    # Validate required parameters
    if [ -z "$EXPERIMENT_NAME" ]; then
        log_error "Experiment name is required"
        log_error "Usage: $0 [OPTIONS] EXPERIMENT_NAME"
        log_error "Use --help for detailed options"
        exit 1
    fi

    # Detect and validate container engine
    local container_engine="${CONTAINER_ENGINE:-$(detect_container_engine)}"
    if ! validate_container_engine "$container_engine"; then
        log_error "Container engine validation failed"
        exit 1
    fi

    # Validate experiment and get containerfile type
    local containerfile_type
    containerfile_type=$(detect_experiment_containerfile_type "$EXPERIMENT_NAME" "$BASE_IMAGE" "$container_engine" | tail -1)

    # Determine containerfile path and context
    local containerfile_path
    local docker_context

    if [ "$containerfile_type" = "custom" ]; then
        containerfile_path="$PROJECT_ROOT/$EXPERIMENT_NAME/Containerfile"
        docker_context="$PROJECT_ROOT/$EXPERIMENT_NAME"
        # No base image build args needed for custom Containerfile
    else
        containerfile_path="$PROJECT_ROOT/Containerfiles/Containerfile.experiment"
        docker_context="$PROJECT_ROOT/$EXPERIMENT_NAME"

        # Add base image as build arg if specified
        if [ -n "$BASE_IMAGE" ]; then
            local resolved_base_image
            resolved_base_image=$(resolve_base_image_reference "$BASE_IMAGE")
            BUILD_ARGS+=("BASE_IMAGE=$resolved_base_image")
        fi
    fi

    # Build tag name
    local arch=$(get_arch)
    local tag_name
    tag_name=$(generate_container_image_tag "$REGISTRY" "experiment" "$TAG_SUFFIX" "$arch" "false" "$EXPERIMENT_NAME")

    log_info "Configuration:"
    log_info "  Experiment: $EXPERIMENT_NAME"
    log_info "  Container type: experiment"
    log_info "  Containerfile type: $containerfile_type"
    log_info "  Containerfile path: $containerfile_path"
    log_info "  Docker context: $docker_context"
    log_info "  Tag: $tag_name"
    log_info "  Platforms: $BUILD_PLATFORMS"
    log_info "  Validation: $VALIDATION_MODE"

    if [ ${#BUILD_ARGS[@]} -gt 0 ]; then
        log_info "  Build args:"
        for arg in "${BUILD_ARGS[@]}"; do
            log_info "    $arg"
        done
    fi

    # Build the container
    build_experiment_container "experiment" "$containerfile_path" "$docker_context" "$tag_name" "$container_engine"

    # Run validation when requested.
    case "$VALIDATION_MODE" in
        none)
            log_info "Skipping validation (validation mode: none)"
            ;;
        quick|metadata|full)
            log_info "Running container validation..."

            # Set appropriate size limit for experiments
            local max_size_mb=$(get_default_size_limit "experiment")

            case "$VALIDATION_MODE" in
                quick)
                    if quick_validate_image "$container_engine" "$tag_name"; then
                        log_success "Quick container validation passed"
                    else
                        log_error "Quick container validation failed"
                        exit 1
                    fi
                    ;;
                metadata)
                    if no_exec_validate_image "$container_engine" "$tag_name" "$max_size_mb"; then
                        log_success "Metadata-only container validation passed"
                    else
                        log_error "Metadata-only container validation failed"
                        exit 1
                    fi
                    ;;
                full)
                    if validate_container "$container_engine" "$tag_name" "experiment" "$max_size_mb"; then
                        log_success "Full container validation passed"
                    else
                        log_error "Full container validation failed"
                        exit 1
                    fi
                    ;;
            esac
            ;;
        *)
            log_error "Unsupported validation mode: $VALIDATION_MODE"
            exit 1
            ;;
    esac

    log_info "Experiment build completed successfully!"

    # Create job summary for GitHub Actions
    if is_github_actions; then
        create_job_summary "## [SUCCESS] Experiment Build Successful

**Container:** \`$tag_name\`
**Experiment:** \`$EXPERIMENT_NAME\`
**Containerfile Type:** \`$containerfile_type\`
**Validation:** \`$VALIDATION_MODE\`

Build completed successfully!"
    fi

    return 0
}

# Run main function
main "$@"
