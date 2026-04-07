#!/bin/bash
# Cleanup and resource management functions
# Provides consistent cleanup patterns across test modules

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/logging.sh"

init_cleanup_tracking() {
    if [[ -n "${CLEANUP_CONTAINERS_INITIALIZED:-}" ]]; then
        return 0
    fi

    CLEANUP_CONTAINERS=()
    CLEANUP_IMAGES=()
    CLEANUP_VOLUMES=()
    CLEANUP_FILES=()
    CLEANUP_DIRECTORIES=()
    export CLEANUP_CONTAINERS_INITIALIZED=true
}

# Track resources for cleanup (defensive initialization)
init_cleanup_tracking

# Signal handler for cleanup on exit
cleanup_on_exit() {
    local exit_code=$?
    log_info "Starting cleanup process..."

    init_cleanup_tracking

    # Clean up containers
    if declare -p CLEANUP_CONTAINERS &>/dev/null && [ ${#CLEANUP_CONTAINERS[@]} -gt 0 ]; then
        log_debug "Cleaning up containers: ${CLEANUP_CONTAINERS[*]}"
        cleanup_containers "${CLEANUP_CONTAINERS[@]}"
    fi

    # Clean up images
    if declare -p CLEANUP_IMAGES &>/dev/null && [ ${#CLEANUP_IMAGES[@]} -gt 0 ]; then
        log_debug "Cleaning up images: ${CLEANUP_IMAGES[*]}"
        cleanup_images "${CLEANUP_IMAGES[@]}"
    fi

    # Clean up volumes
    if declare -p CLEANUP_VOLUMES &>/dev/null && [ ${#CLEANUP_VOLUMES[@]} -gt 0 ]; then
        log_debug "Cleaning up volumes: ${CLEANUP_VOLUMES[*]}"
        cleanup_volumes "${CLEANUP_VOLUMES[@]}"
    fi

    # Clean up temporary files
    if declare -p CLEANUP_FILES &>/dev/null && [ ${#CLEANUP_FILES[@]} -gt 0 ]; then
        log_debug "Cleaning up files: ${CLEANUP_FILES[*]}"
        cleanup_files "${CLEANUP_FILES[@]}"
    fi

    # Clean up directories
    if declare -p CLEANUP_DIRECTORIES &>/dev/null && [ ${#CLEANUP_DIRECTORIES[@]} -gt 0 ]; then
        log_debug "Cleaning up directories: ${CLEANUP_DIRECTORIES[*]}"
        cleanup_directories "${CLEANUP_DIRECTORIES[@]}"
    fi

    log_info "Cleanup process completed"
    exit $exit_code
}

# Clean up containers
cleanup_containers() {
    local engine container_name

    for entry in "$@"; do
        engine="${entry%%:*}"
        container_name="${entry#*:}"

        if "$engine" container inspect "$container_name" &>/dev/null; then
            log_debug "Stopping and removing container: $container_name"
            "$engine" container stop "$container_name" 2>/dev/null || true
            "$engine" container rm "$container_name" 2>/dev/null || true
        fi
    done
}

# Clean up images
cleanup_images() {
    local engine image_tag

    for entry in "$@"; do
        engine="${entry%%:*}"
        image_tag="${entry#*:}"

        if "$engine" image inspect "$image_tag" &>/dev/null; then
            log_debug "Removing image: $image_tag"
            "$engine" image rm "$image_tag" 2>/dev/null || true
        fi
    done
}

# Clean up volumes
cleanup_volumes() {
    local engine volume_name

    for entry in "$@"; do
        engine="${entry%%:*}"
        volume_name="${entry#*:}"

        if "$engine" volume inspect "$volume_name" &>/dev/null; then
            log_debug "Removing volume: $volume_name"
            "$engine" volume rm "$volume_name" 2>/dev/null || true
        fi
    done
}

# Clean up files
cleanup_files() {
    for file_path in "$@"; do
        if [ -f "$file_path" ]; then
            log_debug "Removing file: $file_path"
            rm -f "$file_path" 2>/dev/null || true
        fi
    done
}

# Clean up directories
cleanup_directories() {
    for dir_path in "$@"; do
        if [ -d "$dir_path" ]; then
            log_debug "Removing directory: $dir_path"
            rm -rf "$dir_path" 2>/dev/null || true
        fi
    done
}



# Register cleanup handler
register_cleanup_handler() {
    trap cleanup_on_exit EXIT INT TERM
}

# Clean up specific resource type immediately
# cleanup_resource_type() {
#     local resource_type="$1"

#     case "$resource_type" in
#         "containers")
#             if [ ${#CLEANUP_CONTAINERS[@]:-0} -gt 0 ]; then
#                 cleanup_containers "${CLEANUP_CONTAINERS[@]}"
#                 CLEANUP_CONTAINERS=()
#             fi
#             ;;
#         "images")
#             if [ ${#CLEANUP_IMAGES[@]:-0} -gt 0 ]; then
#                 cleanup_images "${CLEANUP_IMAGES[@]}"
#                 CLEANUP_IMAGES=()
#             fi
#             ;;
#         "volumes")
#             if [ ${#CLEANUP_VOLUMES[@]:-0} -gt 0 ]; then
#                 cleanup_volumes "${CLEANUP_VOLUMES[@]}"
#                 CLEANUP_VOLUMES=()
#             fi
#             ;;
#         "files")
#             if [ ${#CLEANUP_FILES[@]:-0} -gt 0 ]; then
#                 cleanup_files "${CLEANUP_FILES[@]}"
#                 CLEANUP_FILES=()
#             fi
#             ;;
#         "directories")
#             if [ ${#CLEANUP_DIRECTORIES[@]} -gt 0 ]; then
#                 cleanup_directories "${CLEANUP_DIRECTORIES[@]}"
#                 CLEANUP_DIRECTORIES=()
#             fi
#             ;;
#         *)
#             log_error "Unknown resource type: $resource_type"
#             return 1
#             ;;
#     esac
# }
