#!/bin/bash
# Platform detection and configuration functions
# Handles architecture detection and platform-specific settings

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/logging.sh"

# Detect the current platform architecture
detect_platform() {
    local platform
    platform=$(uname -m)

    case "$platform" in
        x86_64)
            echo "linux/amd64"
            ;;
        aarch64|arm64)
            echo "linux/arm64"
            ;;
        *)
            log_error "Unsupported platform: $platform"
            log_error "Supported platforms: x86_64 (amd64), aarch64/arm64"
            return 1
            ;;
    esac
}

# Get short architecture name
get_arch() {
    local platform
    platform=$(uname -m)

    case "$platform" in
        x86_64)
            echo "amd64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        *)
            log_error "Unsupported platform: $platform"
            return 1
            ;;
    esac
}


# Check if we can build for target platform locally
can_build_platform() {
    local target_platform="$1"
    local current_platform

    current_platform=$(detect_platform)

    if [[ "$target_platform" == "$current_platform" ]]; then
        return 0
    else
        log_warning "Cannot build $target_platform on $current_platform locally"
        log_info "Cross-platform builds require GitHub Actions or emulation"
        return 1
    fi
}

# Validate platform specification
validate_platform() {
    local platform="$1"

    case "$platform" in
        linux/amd64|linux/arm64)
            return 0
            ;;
        amd64)
            log_warning "Use 'linux/amd64' instead of 'amd64'"
            return 1
            ;;
        arm64)
            log_warning "Use 'linux/arm64' instead of 'arm64'"
            return 1
            ;;
        *)
            log_error "Invalid platform: $platform"
            log_error "Valid platforms: linux/amd64, linux/arm64"
            return 1
            ;;
    esac
}

# Get list of supported platforms for this project
# get_supported_platforms() {
#     echo "linux/amd64 linux/arm64"
# }

# Platform-specific container engine detection
detect_container_engine() {
    local preferred_engine="${CONTAINER_ENGINE:-}"

    # If engine is explicitly specified, validate it exists
    if [[ -n "$preferred_engine" ]]; then
        if command -v "$preferred_engine" &> /dev/null; then
            echo "$preferred_engine"
            return 0
        else
            log_warning "Specified container engine '$preferred_engine' not found"
        fi
    fi

    # Auto-detect available engines (prefer docker on macOS, podman on Linux)
    local platform
    platform=$(uname -s)

    if [[ "$platform" == "Darwin" ]]; then
        # macOS: prefer Docker
        if command -v docker &> /dev/null; then
            log_debug "Detected docker on macOS"
            echo "docker"
            return 0
        elif command -v podman &> /dev/null; then
            log_debug "Detected podman on macOS"
            echo "podman"
            return 0
        fi
    else
        # Linux: prefer Podman
        if command -v podman &> /dev/null; then
            log_debug "Detected podman on Linux"
            echo "podman"
            return 0
        elif command -v docker &> /dev/null; then
            log_debug "Detected docker on Linux"
            echo "docker"
            return 0
        fi
    fi

    # If no container engine found, show error
    log_error "No container engine found"
    log_error "Please install Docker or Podman:"
    log_error "  Docker: https://docs.docker.com/get-docker/"
    log_error "  Podman: https://podman.io/getting-started/installation"
    return 1
}

# Check container engine functionality
validate_container_engine() {
    local engine="$1"

    log_group_start "Validating container engine: $engine"

    # Check if command exists
    if ! command -v "$engine" &> /dev/null; then
        log_error "$engine command not found"
        log_group_end
        return 1
    fi

    # Test basic functionality
    if ! "$engine" version &> /dev/null; then
        log_error "$engine is not functioning properly"
        log_error "Try: sudo systemctl start docker"
        log_error "Or check: $engine system info"
        log_group_end
        return 1
    fi

    # Check for required features
    if [[ "$engine" == "docker" ]]; then
        # Check if Docker daemon is running
        if ! "$engine" info &> /dev/null; then
            log_error "Docker daemon is not running"
            log_error "Start with: sudo systemctl start docker"
            log_group_end
            return 1
        fi
    fi

    log_success "$engine is working correctly"

    # Log version information
    local version
    version=$($engine --version 2>/dev/null || echo "unknown")
    log_debug "$engine version: $version"

    log_group_end
    return 0
}

inspect_remote_manifest() {
    local engine="$1"
    local image_ref="$2"

    case "$engine" in
        podman)
            "$engine" manifest inspect "docker://${image_ref}"
            ;;
        *)
            "$engine" manifest inspect "$image_ref"
            ;;
    esac
}
