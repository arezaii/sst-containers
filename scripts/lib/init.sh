#!/bin/bash
# Standardized script initialization
# Provides common setup boilerplate for all scripts

# Prevent double-initialization
if [[ "${SST_SCRIPT_INIT_DONE:-}" == "true" ]]; then
    return 0
fi

set -euo pipefail

# Calculate script directories (works from any depth in the project)
if [[ -z "${SCRIPT_DIR:-}" ]]; then
    SOURCE_PATH="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
    SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
fi

# Find the project root by looking for characteristic files
find_project_root() {
    local dir="$1"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/README.md" && -d "$dir/scripts" && -f "$dir/DEVCONTAINER_SETUP.md" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$1"  # fallback to original directory
}

PROJECT_ROOT="$(find_project_root "$SCRIPT_DIR")"
readonly PROJECT_ROOT

# Calculate lib directory path
SCRIPT_LIB_DIR="$PROJECT_ROOT/scripts/lib"
readonly SCRIPT_LIB_DIR

# Source all required libraries in correct order
source_libraries() {
    local lib_dir="$1"

    # Core configuration (must be first)
    source "$lib_dir/config.sh"

    # Logging (used by other libraries)
    source "$lib_dir/logging.sh"

    # Platform detection
    source "$lib_dir/platform.sh"

    # Validation utilities
    source "$lib_dir/validation.sh"

    # GitHub Actions integration
    source "$lib_dir/github-actions.sh"

    # Cleanup handlers (must be last)
    source "$lib_dir/cleanup.sh"
}

# Initialize all libraries
init_script_environment() {
    if [[ ! -d "$SCRIPT_LIB_DIR" ]]; then
        echo >&2 "ERROR: Cannot find script libraries at $SCRIPT_LIB_DIR"
        echo >&2 "Make sure you're running from within the SST container project"
        exit 1
    fi

    # Source all libraries
    source_libraries "$SCRIPT_LIB_DIR"

    # Register cleanup handler
    register_cleanup_handler

    # Mark initialization as complete
    SST_SCRIPT_INIT_DONE="true"

    log_debug "Script environment initialized (PROJECT_ROOT=$PROJECT_ROOT)"
}

# Initialize if called directly or sourced
init_script_environment

# Export commonly used variables and functions for scripts
export PROJECT_ROOT SCRIPT_DIR SCRIPT_LIB_DIR
export -f log_info log_error log_warning log_success log_debug
export -f log_group_start log_group_end