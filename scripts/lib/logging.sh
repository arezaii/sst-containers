#!/bin/bash
# Unified logging functions for local and CI environments
# Provides consistent logging with GitHub Actions integration

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/github-actions.sh"

# Colors for local output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Log level for filtering
LOG_LEVEL="${LOG_LEVEL:-INFO}"  # DEBUG, INFO, WARN, ERROR

# Convert log level to numeric value for comparison
log_level_value() {
    case "$1" in
        DEBUG) echo 0 ;;
        INFO)  echo 1 ;;
        WARN)  echo 2 ;;
        ERROR) echo 3 ;;
        *)     echo 1 ;;
    esac
}

# Check if message should be logged based on level
should_log() {
    local level="$1"
    local current_level_val
    local msg_level_val

    current_level_val=$(log_level_value "$LOG_LEVEL")
    msg_level_val=$(log_level_value "$level")

    [[ $msg_level_val -ge $current_level_val ]]
}

# Debug logging
log_debug() {
    local message="$1"

    if should_log "DEBUG"; then
        if is_github_actions; then
            echo "::debug::$message"
        else
            echo -e "${PURPLE}[DEBUG]${NC} $message" >&2
        fi
    fi
}

# Info logging
log_info() {
    local message="$1"

    if should_log "INFO"; then
        if is_github_actions; then
            annotate_step "notice" "$message"
        else
            echo -e "${BLUE}[INFO]${NC} $message"
        fi
    fi
}

# Success logging (special case of info)
log_success() {
    local message="$1"

    if should_log "INFO"; then
        if is_github_actions; then
            annotate_step "notice" "[SUCCESS] $message"
        else
            echo -e "${GREEN}[SUCCESS]${NC} $message"
        fi
    fi
}

# Warning logging
log_warning() {
    local message="$1"

    if should_log "WARN"; then
        if is_github_actions; then
            annotate_step "warning" "$message"
        else
            echo -e "${YELLOW}[WARNING]${NC} $message" >&2
        fi
    fi
}

# Error logging
log_error() {
    local message="$1"

    if should_log "ERROR"; then
        if is_github_actions; then
            annotate_step "error" "$message"
        else
            echo -e "${RED}[ERROR]${NC} $message" >&2
        fi
    fi
}

# Fatal error (logs and exits)
log_fatal() {
    local message="$1"
    local exit_code="${2:-1}"

    log_error "$message"
    exit "$exit_code"
}

# Start a logical group of operations
log_group_start() {
    local group_name="$1"

    start_group "$group_name"

    if ! is_github_actions; then
        echo -e "${CYAN}=== $group_name ===${NC}"
    fi
}

# End a logical group
log_group_end() {
    end_group

    if ! is_github_actions; then
        echo ""  # Add spacing for readability
    fi
}

# Log command execution with timing
log_exec() {
    local description="$1"
    shift
    local command=("$@")

    log_info "Executing: $description"
    log_debug "Command: ${command[*]}"

    local start_time
    start_time=$(date +%s)

    if should_log "DEBUG"; then
        # Show command output in debug mode
        "${command[@]}"
    else
        # Hide output unless there's an error
        local temp_log
        temp_log=$(mktemp)
        if ! "${command[@]}" > "$temp_log" 2>&1; then
            log_error "Command failed: ${command[*]}"
            log_error "Output:"
            cat "$temp_log" >&2
            rm -f "$temp_log"
            return 1
        fi
        rm -f "$temp_log"
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_debug "Completed in ${duration}s"
    return 0
}

# Progress indicator for long operations
log_progress() {
    local current="$1"
    local total="$2"
    local message="$3"

    if is_github_actions; then
        log_info "[$current/$total] $message"
    else
        local percentage=$((current * 100 / total))
        echo -e "${CYAN}[${percentage}%]${NC} $message"
    fi
}
