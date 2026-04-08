#!/bin/bash
# Local source checkout helpers

set -euo pipefail

if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/logging.sh"
source "${SCRIPT_LIB_DIR}/validation.sh"

LOCAL_SOURCE_STAGE_ROOT_REL=".local-sources"
LOCAL_SST_CORE_STAGE_REL="${LOCAL_SOURCE_STAGE_ROOT_REL}/sst-core"
LOCAL_CORE_STAGE_ACTIVE="false"

cleanup_local_source_stage() {
    if [[ "${LOCAL_CORE_STAGE_ACTIVE:-false}" == "true" ]]; then
        reset_local_source_stage_dir >/dev/null 2>&1 || true
        LOCAL_CORE_STAGE_ACTIVE="false"
    fi
}

is_git_work_tree() {
    local source_dir="$1"

    git -C "$source_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

stage_git_work_tree() {
    local source_dir="$1"
    local stage_dir="$2"
    local temp_index
    local status=0

    temp_index="$(mktemp "${TMPDIR:-/tmp}/sst-core-stage-index.XXXXXX")"

    if ! GIT_INDEX_FILE="$temp_index" git -C "$source_dir" read-tree HEAD; then
        status=$?
    elif ! GIT_INDEX_FILE="$temp_index" git -C "$source_dir" add -A .; then
        status=$?
    elif ! GIT_INDEX_FILE="$temp_index" git -C "$source_dir" checkout-index --all --force --prefix="$stage_dir/"; then
        status=$?
    fi

    rm -f "$temp_index"
    return "$status"
}

get_local_sst_core_stage_dir() {
    local project_root="${1:-${PROJECT_ROOT:-}}"

    if [[ -z "$project_root" ]]; then
        log_error "PROJECT_ROOT is required to resolve the local SST-core staging directory"
        return 1
    fi

    echo "${project_root}/Containerfiles/${LOCAL_SST_CORE_STAGE_REL}"
}

reset_local_source_stage_dir() {
    local stage_dir="${1:-}"

    if [[ -z "$stage_dir" ]]; then
        stage_dir="$(get_local_sst_core_stage_dir)"
    fi

    rm -rf "$stage_dir"
    mkdir -p "$stage_dir"
    : > "$stage_dir/.gitkeep"
}

validate_local_sst_core_checkout() {
    local source_dir="$1"
    local source_description="${2:-Local SST-core checkout (--core-path)}"
    local resolved_source_dir

    if ! validate_directory_exists "$source_dir" "$source_description"; then
        return 1
    fi

    resolved_source_dir="$(cd "$source_dir" && pwd)"

    if [[ ! -f "$resolved_source_dir/autogen.sh" ]]; then
        log_error "$source_description is missing autogen.sh: $resolved_source_dir"
        return 1
    fi

    if [[ ! -f "$resolved_source_dir/configure.ac" && ! -f "$resolved_source_dir/configure.ac.in" ]]; then
        log_error "$source_description does not look like an SST-core source tree: $resolved_source_dir"
        return 1
    fi

    return 0
}

validate_custom_core_source_selection() {
    local core_path="$1"
    local core_ref="$2"
    local core_repo="$3"

    if [[ -n "$core_path" ]]; then
        if [[ -n "$core_ref" ]]; then
            log_error "--core-ref cannot be combined with --core-path"
            return 1
        fi

        validate_local_sst_core_checkout "$core_path" "Local SST-core checkout (--core-path)" || return 1
        return 0
    fi

    validate_required_args "SST_CORE_REF" "$core_ref" "SST-core reference (--core-ref)" || return 1
    validate_git_ref "$core_ref" "SST-core reference" || return 1
    validate_url "$core_repo" "SST-core repository URL" || return 1

    return 0
}

stage_local_sst_core_checkout() {
    local source_dir="$1"
    local stage_dir="${2:-}"
    local resolved_source_dir

    validate_local_sst_core_checkout "$source_dir" "Local SST-core checkout (--core-path)" || return 1
    resolved_source_dir="$(cd "$source_dir" && pwd)"

    if [[ -z "$stage_dir" ]]; then
        stage_dir="$(get_local_sst_core_stage_dir)"
    fi

    reset_local_source_stage_dir "$stage_dir"

    if is_git_work_tree "$resolved_source_dir" && git -C "$resolved_source_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
        stage_git_work_tree "$resolved_source_dir" "$stage_dir"
    else
        tar --exclude='.git' -cf - -C "$resolved_source_dir" . | tar -xf - -C "$stage_dir"
    fi

    if [[ ! -f "$stage_dir/autogen.sh" ]]; then
        log_error "Failed to stage local SST-core checkout into build context: $stage_dir"
        return 1
    fi

    LOCAL_CORE_STAGE_ACTIVE="true"
    log_info "Staged local SST-core checkout: $resolved_source_dir"
}
