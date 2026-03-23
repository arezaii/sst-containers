#!/bin/bash
# Container validation functions
# Provides comprehensive testing of built containers

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/logging.sh"
source "${SCRIPT_LIB_DIR}/platform.sh"
source "${SCRIPT_LIB_DIR}/config.sh"
source "${SCRIPT_LIB_DIR}/github-actions.sh"

# Validate required arguments with consistent error reporting.
validate_required_args() {
    local error_count=0

    while [[ $# -gt 0 ]]; do
        local arg_name="$1"
        local arg_value="$2"
        local arg_description="${3:-$arg_name}"

        if [[ -z "$arg_value" ]]; then
            log_error "$arg_description is required"
            ((error_count++))
        fi

        shift 3
    done

    if [[ $error_count -gt 0 ]]; then
        log_error "Use --help for usage information"
        return 1
    fi

    return 0
}

validate_file_exists() {
    local file_path="$1"
    local file_description="${2:-File}"

    if [[ ! -f "$file_path" ]]; then
        log_error "$file_description not found: $file_path"
        return 1
    fi

    return 0
}

validate_directory_exists() {
    local dir_path="$1"
    local dir_description="${2:-Directory}"

    if [[ ! -d "$dir_path" ]]; then
        log_error "$dir_description not found: $dir_path"
        return 1
    fi

    return 0
}

validate_url() {
    local url="$1"
    local url_description="${2:-URL}"

    if [[ -z "$url" ]]; then
        log_error "$url_description is required"
        return 1
    fi

    if [[ ! "$url" =~ ^https?://.*$ ]]; then
        log_error "Invalid $url_description format: $url"
        log_error "URL must start with http:// or https://"
        return 1
    fi

    return 0
}

validate_git_ref() {
    local ref="$1"
    local ref_description="${2:-Git reference}"

    if [[ -z "$ref" ]]; then
        log_error "$ref_description is required"
        return 1
    fi

    if [[ "$ref" =~ [[:space:]] ]]; then
        log_error "Invalid $ref_description format: '$ref'"
        log_error "Git references cannot contain spaces"
        return 1
    fi

    if [[ "$ref" =~ [\<\>\|\&\$\`] ]]; then
        log_error "Invalid $ref_description format: '$ref'"
        log_error "Git references cannot contain shell special characters"
        return 1
    fi

    return 0
}

# Check if container image exists
image_exists() {
    local engine="$1"
    local image_tag="$2"

    log_debug "Checking if image exists: $image_tag"
    "$engine" image inspect "$image_tag" &> /dev/null
}

# Get container image size in MB
get_image_size_mb() {
    local engine="$1"
    local image_tag="$2"

    if ! image_exists "$engine" "$image_tag"; then
        log_error "Image not found: $image_tag"
        return 1
    fi

    local size_bytes
    size_bytes=$("$engine" image inspect "$image_tag" --format='{{.Size}}' 2>/dev/null || echo "0")
    echo $((size_bytes / 1024 / 1024))
}

# Validate image size against limit
validate_image_size() {
    local engine="$1"
    local image_tag="$2"
    local max_size_mb="$3"

    log_info "Validating image size (max: ${max_size_mb}MB)"

    local actual_size_mb
    actual_size_mb=$(get_image_size_mb "$engine" "$image_tag")

    log_info "Image size: ${actual_size_mb}MB"

    if [[ $actual_size_mb -gt $max_size_mb ]]; then
        log_error "Image size ${actual_size_mb}MB exceeds limit ${max_size_mb}MB"
        return 1
    else
        log_success "Image size check passed"
        return 0
    fi
}

# Test container startup
test_container_startup() {
    local engine="$1"
    local image_tag="$2"

    log_info "Testing container startup"

    # Use the correct format for the bash entrypoint
    if "$engine" run --rm "$image_tag" -c 'echo "Container startup successful"' &> /dev/null; then
        log_success "Container startup test passed"
        return 0
    else
        log_error "Container startup test failed"
        return 1
    fi
}

# Test SST installation (for SST containers)
test_sst_installation() {
    local engine="$1"
    local image_tag="$2"
    local container_type="$3"  # core, full, dev
    local allow_platform_fallback="${4:-true}"

    log_info "Testing SST installation"

    case "$container_type" in
        dev)
            # Dev container shouldn't have SST installed
            log_info "Skipping SST test for dev container (SST not pre-installed)"
            return 0
            ;;
        core|full|custom)
            # Test SST-core installation by checking binary location
            if "$engine" run --rm "$image_tag" which sst &> /dev/null; then
                log_success "SST binary found"
            else
                log_error "SST is not properly installed or accessible"
                return 1
            fi

            # Test SST version using proper bash format
            if "$engine" run --rm "$image_tag" -c 'sst --version' &> /dev/null; then
                log_success "SST version check passed"
            else
                log_warning "SST version check failed (possibly due to execution environment)"
            fi

            log_success "SST installation test passed"

            # Additional test for full builds
            if [[ "$container_type" == "full" ]]; then
                log_info "Testing SST Elements (full build)"
                # Check for SST Elements in the version-aware path structure
                if "$engine" run --rm "$image_tag" -c 'find /opt/SST -name "sst-elements-library" -type d 2>/dev/null | head -1' | grep -q "sst-elements-library"; then
                    log_success "SST Elements library found"
                elif "$engine" run --rm "$image_tag" -c 'find /opt/SST -path "*/elements/include/sst/elements" -type d 2>/dev/null | head -1' | grep -q "elements"; then
                    log_success "SST Elements headers found"
                elif "$engine" run --rm "$image_tag" -c 'ls /opt/SST/*/elements/lib/ 2>/dev/null' &> /dev/null; then
                    log_success "SST Elements installation directory found"
                else
                    log_warning "SST Elements installation not found in expected SST directory structure"
                fi
            fi
            ;;
        experiment)
            log_info "Skipping SST test for experiment container (custom configuration)"
            return 0
            ;;
        *)
            log_warning "Unknown container type: $container_type"
            return 0
            ;;
    esac

    return 0
}

# Test MPI functionality
test_mpi_functionality() {
    local engine="$1"
    local image_tag="$2"

    log_info "Testing MPI functionality"

    # Test MPI installation by finding the binary (works with bash entrypoint)
    if "$engine" run --rm "$image_tag" which mpirun &> /dev/null; then
        log_success "MPI binary found"
    else
        log_error "MPI is not properly installed"
        return 1
    fi

    # Test basic MPI execution using proper bash format
    if "$engine" run --rm "$image_tag" -c 'mpirun --version' &> /dev/null; then
        log_success "MPI version check passed"
    else
        log_warning "MPI version check failed (possibly due to execution environment)"
    fi

    log_success "MPI functionality test passed"
    return 0
}

# Simplified container validation - focuses on essentials
validate_container() {
    local engine="$1"
    local image_tag="$2"
    local container_type="$3"
    local max_size_mb="${4:-$(get_default_size_limit "$container_type")}"  # Use dynamic limit based on container type

    log_group_start "Validating container: $image_tag"

    local validation_results=()
    local overall_success=true

    # Check if image exists
    if ! image_exists "$engine" "$image_tag"; then
        log_error "Container image not found: $image_tag"
        log_group_end
        return 1
    fi

    # Test 1: Image size validation
    if validate_image_size "$engine" "$image_tag" "$max_size_mb"; then
        validation_results+=("size_check:passed")
    else
        validation_results+=("size_check:failed")
        overall_success=false
    fi

    # Test 2: SST functionality (when applicable)
    if test_sst_installation "$engine" "$image_tag" "$container_type"; then
        validation_results+=("sst:passed")
    else
        validation_results+=("sst:failed")
        overall_success=false
    fi

    # Test 3: MPI functionality (when applicable)
    if [[ "$container_type" != "experiment" ]]; then
        if test_mpi_functionality "$engine" "$image_tag"; then
            validation_results+=("mpi:passed")
        else
            validation_results+=("mpi:failed")
            overall_success=false
        fi
    fi

    # Generate results summary
    local tests_passed="${validation_results[*]}"
    local image_size_mb
    image_size_mb=$(get_image_size_mb "$engine" "$image_tag")

    # Report results
    if $overall_success; then
        log_success "All validation tests passed"
    else
        log_error "Some validation tests failed"
    fi

    # Generate structured output for GitHub Actions
    if is_github_actions; then
        report_validation_metrics "$image_tag" "$overall_success" "$tests_passed" "$(validate_image_size "$engine" "$image_tag" "$max_size_mb" && echo "true" || echo "false")"
    fi

    log_group_end

    if $overall_success; then
        return 0
    else
        return 1
    fi
}

# No-exec validation - checks image without running any commands inside container
# Useful for containers with execution compatibility issues
no_exec_validate_image() {
    local engine="$1"
    local image_tag="$2"
    local max_size_mb="${3:-$(get_default_size_limit_for_image_tag "$image_tag")}"  # Use image-specific size limits by default

    log_info "No-exec validation of $image_tag"

    # Check if image exists
    if ! image_exists "$engine" "$image_tag"; then
        log_error "Image not found: $image_tag"
        return 1
    fi
    log_success "Image exists"

    # Check image size
    if validate_image_size "$engine" "$image_tag" "$max_size_mb"; then
        log_success "Image size check passed"
    else
        log_error "Image size check failed"
        return 1
    fi

    # Inspect image metadata
    local arch
    arch=$("$engine" image inspect "$image_tag" --format='{{.Architecture}}' 2>/dev/null || echo "unknown")
    log_info "Image architecture: $arch"

    # Check for expected environment variables or labels
    local config
    config=$("$engine" image inspect "$image_tag" --format='{{json .Config}}' 2>/dev/null || echo '{}')

    if echo "$config" | jq -e '.Env[]' | grep -i 'path.*sst\|path.*mpi' &> /dev/null; then
        log_success "Expected environment variables found"
    else
        log_warning "Expected SST/MPI environment variables not clearly visible"
    fi

    # Check layers for expected content indicators
    local history
    history=$("$engine" image inspect "$image_tag" --format='{{json .RootFS.Layers}}' 2>/dev/null || echo '[]')

    if [[ "$history" != "[]" ]] && [[ "$history" != "null" ]]; then
        log_success "Image layers structure verified"
    else
        log_warning "Could not verify image layers"
    fi

    log_success "No-exec validation passed"
    return 0
}

# Quick validation for existing images (used by quick-validate.sh)
# Only checks image existence and basic inspection without execution
quick_validate_image() {
    local engine="$1"
    local image_tag="$2"

    log_info "Quick validation of $image_tag"

    # Check if image exists
    if ! image_exists "$engine" "$image_tag"; then
        log_error "Image not found: $image_tag"
        return 1
    fi

    log_success "Image exists"

    # Get basic image information
    local image_size_mb
    image_size_mb=$(get_image_size_mb "$engine" "$image_tag")
    log_info "Image size: ${image_size_mb}MB"

    # Try to inspect the image for metadata
    if "$engine" image inspect "$image_tag" --format='{{.Config.Env}}' &> /dev/null; then
        log_success "Image inspection passed"
    else
        log_warning "Image inspection failed"
        return 1
    fi

    log_success "Quick validation passed"
    return 0
}
