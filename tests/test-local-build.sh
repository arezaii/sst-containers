#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_SCRIPT="${REPO_ROOT}/scripts/build/local-build.sh"

show_usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] [CONTAINER_TYPE]

Quick local smoke test wrapper for scripts/build/local-build.sh.

Default smoke-test behavior:
    - container type defaults to dev
    - validation defaults to metadata
    - cleanup is enabled by default

Pass canonical build options through to scripts/build/local-build.sh.

Examples:
  $(basename "$0")
  $(basename "$0") core
  $(basename "$0") --validation quick core
  $(basename "$0") --sst-version 15.1.0 full
  $(basename "$0") --core-ref main custom

Use scripts/build/local-build.sh for the full local build interface.
EOF
}

main() {
    local has_validation="false"
    local has_cleanup="false"
    local container_type=""
    local current_arg
    declare -a delegated_args=()

    if [[ ! -x "$BUILD_SCRIPT" ]]; then
        echo >&2 "ERROR: Cannot execute build entry point: $BUILD_SCRIPT"
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        current_arg="$1"

        case "$current_arg" in
            --help|-h)
                show_usage
                exit 0
                ;;
            --validation)
                if [[ $# -lt 2 ]]; then
                    echo >&2 "ERROR: --validation requires a mode"
                    exit 1
                fi
                has_validation="true"
                delegated_args+=("$1" "$2")
                shift 2
                continue
                ;;
            --cleanup)
                has_cleanup="true"
                ;;
            core|full|dev|custom|experiment)
                if [[ -z "$container_type" ]]; then
                    container_type="$current_arg"
                fi
                ;;
        esac

        delegated_args+=("$current_arg")
        shift
    done

    if [[ -z "$container_type" ]]; then
        delegated_args+=("dev")
    fi

    if [[ "$has_validation" != "true" ]]; then
        delegated_args=("--validation" "metadata" "${delegated_args[@]}")
    fi

    if [[ "$has_cleanup" != "true" ]]; then
        delegated_args+=("--cleanup")
    fi

    exec "$BUILD_SCRIPT" "${delegated_args[@]}"
}

main "$@"