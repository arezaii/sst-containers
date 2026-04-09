#!/bin/bash
# Local source checkout helpers

set -euo pipefail

if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
source "${SCRIPT_LIB_DIR}/logging.sh"
source "${SCRIPT_LIB_DIR}/validation.sh"

LOCAL_SOURCE_STAGE_ROOT_REL=".build-contexts"
LOCAL_SST_CORE_STAGE_REL="${LOCAL_SOURCE_STAGE_ROOT_REL}/sst-core-input"
LOCAL_CORE_STAGE_ACTIVE="false"

run_local_sources_python() {
    local operation="$1"
    shift || true
    local python_bin="${PYTHON_BIN:-python3}"
    local project_root="${PROJECT_ROOT:-$(cd "${SCRIPT_LIB_DIR}/../.." && pwd)}"

    PYTHONPATH="${project_root}${PYTHONPATH:+:${PYTHONPATH}}" \
        "$python_bin" - "$operation" "$@" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

from sst_container_factory.orchestration import (
    reset_local_source_stage_dir,
    stage_local_sst_core_checkout,
    validate_local_sst_core_checkout,
)


def _optional_path(raw_value: str | None) -> Path | None:
    if not raw_value:
        return None
    return Path(raw_value)


def main() -> int:
    operation = sys.argv[1]
    try:
        if operation == "reset":
            reset_local_source_stage_dir(_optional_path(sys.argv[2] if len(sys.argv) > 2 else None))
            return 0
        if operation == "validate":
            validate_local_sst_core_checkout(sys.argv[2])
            return 0
        if operation == "stage":
            stage_local_sst_core_checkout(
                sys.argv[2],
                _optional_path(sys.argv[3] if len(sys.argv) > 3 else None),
            )
            return 0
        print(f"Unsupported local-sources operation: {operation}", file=sys.stderr)
        return 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


raise SystemExit(main())
PY
}

cleanup_local_source_stage() {
    if [[ "${LOCAL_CORE_STAGE_ACTIVE:-false}" == "true" ]]; then
        reset_local_source_stage_dir >/dev/null 2>&1 || true
        LOCAL_CORE_STAGE_ACTIVE="false"
    fi
}

get_local_sst_core_stage_dir() {
    local project_root="${1:-${PROJECT_ROOT:-}}"

    if [[ -z "$project_root" ]]; then
        log_error "PROJECT_ROOT is required to resolve the local SST-core staging directory"
        return 1
    fi

    echo "${project_root}/${LOCAL_SST_CORE_STAGE_REL}"
}

reset_local_source_stage_dir() {
    local stage_dir="${1:-}"

    if [[ -z "$stage_dir" ]]; then
        stage_dir="$(get_local_sst_core_stage_dir)"
    fi

    run_local_sources_python reset "$stage_dir"
}

validate_local_sst_core_checkout() {
    local source_dir="$1"

    run_local_sources_python validate "$source_dir"
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

    if [[ -z "$stage_dir" ]]; then
        stage_dir="$(get_local_sst_core_stage_dir)"
    fi

    run_local_sources_python stage "$source_dir" "$stage_dir"
    LOCAL_CORE_STAGE_ACTIVE="true"
}
