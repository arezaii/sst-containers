#!/bin/bash
# Simplified argument parsing framework
# Compatible with older bash versions, focused on reducing duplication

set -euo pipefail

# Simple variables to track parsed arguments
SST_VERSION=""
MPICH_VERSION=""
SST_CORE_REPO=""
SST_CORE_PATH=""
SST_CORE_REF=""
SST_ELEMENTS_REPO=""
SST_ELEMENTS_REF=""
SST_ELEMENTS_VERSION=""
EXPERIMENT_NAME=""
BASE_IMAGE=""
ENABLE_PERF_TRACKING="false"
NO_CACHE="false"
CLEANUP="false"
VALIDATE_ONLY="false"
REGISTRY=""
TAG_SUFFIX=""
TAG_SUFFIX_SET="false"
HELP_REQUESTED="false"

# Build-specific variables
BUILD_NCPUS=""
CONTAINER_ENGINE=""
TARGET_PLATFORM=""
GITHUB_ACTIONS_MODE="false"

# Experiment-specific variables
BUILD_PLATFORMS=""
VALIDATION_MODE=""
declare -a BUILD_ARGS=()

# Remaining positional arguments
declare -a REMAINING_ARGS=()

# Track parsed options for profile enforcement
declare -a PARSED_CANONICAL_OPTIONS=()
declare -a UNKNOWN_OPTIONS=()

# Initialize with defaults from config
init_argument_defaults() {
    SST_VERSION="${DEFAULT_SST_VERSION:-15.1.2}"
    MPICH_VERSION="${DEFAULT_MPICH_VERSION:-4.0.2}"
    SST_CORE_REPO="${DEFAULT_SST_CORE_REPO:-https://github.com/sstsimulator/sst-core.git}"
    SST_CORE_PATH=""
    SST_ELEMENTS_REPO=""
    SST_ELEMENTS_REF=""
    SST_ELEMENTS_VERSION=""
    REGISTRY="${DEFAULT_REGISTRY:-localhost:5000}"
    BUILD_NCPUS="${DEFAULT_BUILD_NCPUS:-4}"
    CONTAINER_ENGINE=""
    TARGET_PLATFORM=""
    GITHUB_ACTIONS_MODE="false"
    ENABLE_PERF_TRACKING="false"
    NO_CACHE="false"
    CLEANUP="false"
    VALIDATE_ONLY="false"
    HELP_REQUESTED="false"
    TAG_SUFFIX_SET="false"
    BUILD_ARGS=()
    REMAINING_ARGS=()
    PARSED_CANONICAL_OPTIONS=()
    UNKNOWN_OPTIONS=()

    # Experiment-specific defaults
    EXPERIMENT_NAME=""
    BASE_IMAGE="sst-core:latest"
    TAG_SUFFIX="latest"
    if declare -F detect_platform >/dev/null; then
        BUILD_PLATFORMS="$(detect_platform)"
    else
        BUILD_PLATFORMS="linux/amd64"
    fi
    VALIDATION_MODE=""
}

record_parsed_option() {
    local canonical_option="$1"
    local existing_option

    if [[ ${#PARSED_CANONICAL_OPTIONS[@]} -gt 0 ]]; then
        for existing_option in "${PARSED_CANONICAL_OPTIONS[@]}"; do
            if [[ "$existing_option" == "$canonical_option" ]]; then
                return 0
            fi
        done
    fi

    PARSED_CANONICAL_OPTIONS+=("$canonical_option")
}

canonicalize_container_engine() {
    local raw_engine="$1"

    case "$raw_engine" in
        docker|podman)
            echo "$raw_engine"
            ;;
        *)
            return 1
            ;;
    esac
}

normalize_container_engine_argument() {
    local explicit_engine="${CONTAINER_ENGINE:-}"

    if [[ -n "$explicit_engine" ]]; then
        if ! explicit_engine=$(canonicalize_container_engine "$explicit_engine"); then
            log_error "Invalid container engine: $CONTAINER_ENGINE"
            log_error "Valid engines: docker, podman"
            return 1
        fi
        CONTAINER_ENGINE="$explicit_engine"
    fi

    return 0
}

canonicalize_validation_mode() {
    local raw_mode="$1"

    case "$raw_mode" in
        full|quick|metadata|none)
            echo "$raw_mode"
            ;;
        *)
            return 1
            ;;
    esac
}

normalize_validation_mode() {
    local default_mode="${1:-none}"
    local explicit_mode="${VALIDATION_MODE:-}"

    if [[ -n "$explicit_mode" ]]; then
        if ! explicit_mode=$(canonicalize_validation_mode "$explicit_mode"); then
            log_error "Invalid validation mode: $VALIDATION_MODE"
            log_error "Valid modes: full, quick, metadata, none"
            return 1
        fi
    fi

    VALIDATION_MODE="${explicit_mode:-$default_mode}"

    return 0
}

normalize_simple_arguments() {
    local default_validation_mode="${1:-none}"

    normalize_container_engine_argument || return 1
    normalize_validation_mode "$default_validation_mode" || return 1

    return 0
}

has_unknown_options() {
    [[ ${#UNKNOWN_OPTIONS[@]} -gt 0 ]]
}

validate_known_options() {
    local unknown_option

    if ! has_unknown_options; then
        return 0
    fi

    for unknown_option in "${UNKNOWN_OPTIONS[@]}"; do
        log_error "Unknown option: $unknown_option"
    done

    return 1
}

is_option_supported_for_profile() {
    local profile="$1"
    local option="$2"

    case "$profile:$option" in
        custom-build:--help|custom-build:--core-repo|custom-build:--core-path|custom-build:--core-ref|custom-build:--elements-repo|custom-build:--elements-ref|custom-build:--mpich-version|custom-build:--engine|custom-build:--platform|custom-build:--build-ncpus|custom-build:--registry|custom-build:--tag-suffix|custom-build:--enable-perf-tracking|custom-build:--no-cache|custom-build:--validation)
            return 0
            ;;
        experiment-build:--help|experiment-build:--base-image|experiment-build:--engine|experiment-build:--registry|experiment-build:--tag-suffix|experiment-build:--platforms|experiment-build:--no-cache|experiment-build:--build-arg|experiment-build:--validation)
            return 0
            ;;
        local-build:--help|local-build:--sst-version|local-build:--mpich-version|local-build:--core-repo|local-build:--core-path|local-build:--core-ref|local-build:--elements-repo|local-build:--elements-ref|local-build:--elements-version|local-build:--experiment-name|local-build:--base-image|local-build:--engine|local-build:--platform|local-build:--build-ncpus|local-build:--registry|local-build:--tag-suffix|local-build:--enable-perf-tracking|local-build:--no-cache|local-build:--validation|local-build:--validate-only|local-build:--cleanup)
            return 0
            ;;
    esac

    return 1
}

validate_argument_profile() {
    local profile="$1"
    local option

    [[ ${#PARSED_CANONICAL_OPTIONS[@]} -eq 0 ]] && return 0

    for option in "${PARSED_CANONICAL_OPTIONS[@]}"; do
        if ! is_option_supported_for_profile "$profile" "$option"; then
            log_error "Unsupported option for $profile: $option"
            return 1
        fi
    done

    return 0
}

print_profile_option_help() {
    local option="$1"

    case "$option" in
        --base-image)
            printf '    --base-image IMAGE             Base image for experiment builds\n'
            ;;
        --build-arg)
            printf '    --build-arg KEY=VALUE          Additional build argument (repeatable)\n'
            ;;
        --build-ncpus)
            printf '    --build-ncpus NUMBER           Number of CPU cores for build (default: %s)\n' "$BUILD_NCPUS"
            ;;
        --core-ref)
            printf '    --core-ref REF                 SST-core branch, tag, or commit SHA\n'
            ;;
        --core-repo)
            printf '    --core-repo URL                SST-core repository URL\n'
            ;;
        --core-path)
            printf '    --core-path PATH               Local SST-core checkout to copy into the build context\n'
            ;;
        --elements-ref)
            printf '    --elements-ref REF             SST-elements branch, tag, or commit SHA\n'
            ;;
        --elements-repo)
            printf '    --elements-repo URL            SST-elements repository URL\n'
            ;;
        --elements-version)
            printf '    --elements-version VERSION     SST-elements version override for full builds\n'
            ;;
        --enable-perf-tracking)
            printf '    --enable-perf-tracking         Enable SST performance tracking\n'
            ;;
        --engine)
            printf '    --engine ENGINE                Container engine to use (docker/podman)\n'
            ;;
        --experiment-name)
            printf '    --experiment-name NAME         Experiment name for experiment container builds\n'
            ;;
        --help)
            printf '    --help, -h                     Show this help message\n'
            ;;
        --mpich-version)
            printf '    --mpich-version VERSION        MPICH version to use (default: %s)\n' "$MPICH_VERSION"
            ;;
        --no-cache)
            printf '    --no-cache                     Disable build cache\n'
            ;;
        --platform)
            printf '    --platform PLATFORM            Target platform (host platform only; default: auto-detected)\n'
            ;;
        --platforms)
            printf '    --platforms PLATFORMS          Build platform (single host platform only; default: %s)\n' "$BUILD_PLATFORMS"
            ;;
        --registry)
            printf '    --registry REGISTRY            Registry for image tags (default: %s)\n' "$REGISTRY"
            ;;
        --sst-version)
            printf '    --sst-version VERSION          SST version to use (default: %s)\n' "$SST_VERSION"
            ;;
        --tag-suffix)
            printf '    --tag-suffix SUFFIX            Tag suffix for generated image tags (default: %s)\n' "$TAG_SUFFIX"
            ;;
        --cleanup)
            printf '    --cleanup                      Remove built images and temporary state after success\n'
            ;;
        --validate-only)
            printf '    --validate-only                Skip the build and validate the last built image\n'
            ;;
        --validation)
            printf '    --validation MODE              Validation mode: full, quick, metadata, or none (default: %s)\n' "$VALIDATION_MODE"
            ;;
    esac
}

show_argument_profile_help() {
    local profile="$1"
    local script_name

    script_name="$(basename "$0")"

    case "$profile" in
        custom-build)
            cat << EOF
Custom SST Container Build Script

Build SST containers from arbitrary repositories and refs.

Usage: $script_name [OPTIONS]

Required options:
EOF
            print_profile_option_help --core-ref
            print_profile_option_help --core-path
            cat << EOF

Options:
EOF
            print_profile_option_help --core-repo
            print_profile_option_help --elements-repo
            print_profile_option_help --elements-ref
            print_profile_option_help --mpich-version
            print_profile_option_help --engine
            print_profile_option_help --platform
            print_profile_option_help --build-ncpus
            print_profile_option_help --registry
            print_profile_option_help --tag-suffix
            print_profile_option_help --enable-perf-tracking
            print_profile_option_help --no-cache
            print_profile_option_help --validation
            print_profile_option_help --help
            cat << EOF

Validation modes:
    full      Complete validation including runtime checks
    quick     Fast validation without full runtime coverage
    metadata  Validate image metadata without executing the container
    none      Skip validation

Examples:
  $script_name --core-ref main
  $script_name --core-path /path/to/sst-core --tag-suffix local-core
  $script_name --core-ref v15.1.0 --elements-repo https://github.com/custom/sst-elements.git --elements-ref develop
  $script_name --core-ref main --enable-perf-tracking --validation quick
EOF
            ;;
        experiment-build)
            cat << EOF
Usage: $script_name [OPTIONS] EXPERIMENT_NAME

Build experiment containers for SST with optional custom Containerfiles.

Positional arguments:
    EXPERIMENT_NAME                Experiment name (required) - must match existing directory

Options:
EOF
            print_profile_option_help --base-image
            print_profile_option_help --engine
            print_profile_option_help --registry
            print_profile_option_help --tag-suffix
            print_profile_option_help --platforms
            print_profile_option_help --no-cache
            print_profile_option_help --build-arg
            print_profile_option_help --validation
            print_profile_option_help --help
            cat << EOF

Validation modes:
    full      Complete validation including size check and functionality tests
    quick     Basic validation without execution tests
    metadata  Validate image metadata without executing the container
    none      Skip validation entirely

Performance tracking:
    Experiment containers inherit SST performance tracking from their base image.
    Use a performance-tracking-enabled base image when you need those capabilities.

Examples:
  $script_name phold-example
  $script_name --base-image sst-core:latest tcl-test-experiment
  $script_name --registry myregistry.io/user --no-cache ahp-graph

Notes:
    - Experiment directory must exist in project root
        - Local experiment builds support only a single host-matching platform
    - If the experiment contains Containerfile, it will be used directly
    - Otherwise, Containerfiles/Containerfile.experiment is used as a template
    - Base images are validated for accessibility when using the template flow
EOF
            ;;
        local-build)
            cat << EOF
    Local Container Build Script

Usage: $script_name [OPTIONS] CONTAINER_TYPE

    Build one container type locally using the same containerfiles and configuration model as the repository workflows.

Container types:
    core        Build SST-core only
    full        Build SST-core + SST-elements
    dev         Build the development image
    custom      Build from custom repositories and refs
    experiment  Build an experiment container

Common options:
EOF
            print_profile_option_help --engine
            print_profile_option_help --platform
            print_profile_option_help --registry
            print_profile_option_help --build-ncpus
            print_profile_option_help --no-cache
            print_profile_option_help --validation
            print_profile_option_help --validate-only
            print_profile_option_help --cleanup
            print_profile_option_help --help
            cat << EOF

Release and development build options:
EOF
            print_profile_option_help --sst-version
            print_profile_option_help --elements-version
            print_profile_option_help --mpich-version
            print_profile_option_help --enable-perf-tracking
            cat << EOF

Custom build options:
EOF
            print_profile_option_help --core-repo
            print_profile_option_help --core-path
            print_profile_option_help --core-ref
            print_profile_option_help --elements-repo
            print_profile_option_help --elements-ref
            cat << EOF

Experiment build options:
EOF
            print_profile_option_help --experiment-name
            print_profile_option_help --base-image
            print_profile_option_help --tag-suffix
            cat << EOF

Validation modes:
    full      Complete validation including runtime checks
    quick     Fast validation without full runtime coverage
    metadata  Validate image metadata without executing the container
        none      Skip validation after build

Examples:
  $script_name core
  $script_name --sst-version 15.1.0 full
  $script_name --sst-version 15.1.2 --elements-version 15.1.0 full
  $script_name --enable-perf-tracking core
  $script_name --core-repo https://github.com/sstsimulator/sst-core.git --core-ref main custom
  $script_name --core-path /path/to/sst-core --tag-suffix local-core custom
  $script_name --experiment-name phold-example experiment
    $script_name --validation quick core

For a quick smoke test wrapper, use:
    tests/test-local-build.sh
EOF
            ;;
        *)
            log_error "No CLI help profile is defined for: $profile"
            return 1
            ;;
    esac
}

parse_script_arguments() {
    local profile="$1"
    local default_validation_mode="${2:-none}"

    shift 2

    parse_simple_arguments "$@"
    normalize_simple_arguments "$default_validation_mode" || return 1

    if [[ "$HELP_REQUESTED" == "true" ]]; then
        return 0
    fi

    validate_known_options || return 1
    validate_argument_profile "$profile" || return 1

    return 0
}

# Parse command-line arguments using simple approach
parse_simple_arguments() {
    init_argument_defaults

    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                record_parsed_option "--help"
                HELP_REQUESTED="true"
                shift
                ;;
            --sst-version)
                record_parsed_option "--sst-version"
                SST_VERSION="$2"
                shift 2
                ;;
            --mpich-version)
                record_parsed_option "--mpich-version"
                MPICH_VERSION="$2"
                shift 2
                ;;
            --core-repo)
                record_parsed_option "--core-repo"
                SST_CORE_REPO="$2"
                shift 2
                ;;
            --core-path)
                record_parsed_option "--core-path"
                SST_CORE_PATH="$2"
                shift 2
                ;;
            --core-ref)
                record_parsed_option "--core-ref"
                SST_CORE_REF="$2"
                shift 2
                ;;
            --elements-repo)
                record_parsed_option "--elements-repo"
                SST_ELEMENTS_REPO="$2"
                shift 2
                ;;
            --elements-ref)
                record_parsed_option "--elements-ref"
                SST_ELEMENTS_REF="$2"
                shift 2
                ;;
            --elements-version)
                record_parsed_option "--elements-version"
                SST_ELEMENTS_VERSION="$2"
                shift 2
                ;;
            --experiment-name)
                record_parsed_option "--experiment-name"
                EXPERIMENT_NAME="$2"
                shift 2
                ;;
            --base-image)
                record_parsed_option "--base-image"
                BASE_IMAGE="$2"
                shift 2
                ;;
            --registry)
                record_parsed_option "--registry"
                REGISTRY="$2"
                shift 2
                ;;
            --tag-suffix)
                record_parsed_option "--tag-suffix"
                TAG_SUFFIX="$2"
                TAG_SUFFIX_SET="true"
                shift 2
                ;;
            --enable-perf-tracking)
                record_parsed_option "--enable-perf-tracking"
                ENABLE_PERF_TRACKING="true"
                shift
                ;;
            --no-cache)
                record_parsed_option "--no-cache"
                NO_CACHE="true"
                shift
                ;;
            --cleanup)
                record_parsed_option "--cleanup"
                CLEANUP="true"
                shift
                ;;
            --validate-only)
                record_parsed_option "--validate-only"
                VALIDATE_ONLY="true"
                shift
                ;;
            --build-ncpus)
                record_parsed_option "--build-ncpus"
                BUILD_NCPUS="$2"
                shift 2
                ;;
            --engine)
                record_parsed_option "--engine"
                CONTAINER_ENGINE="$2"
                shift 2
                ;;
            --platform)
                record_parsed_option "--platform"
                TARGET_PLATFORM="$2"
                shift 2
                ;;
            --github-actions)
                record_parsed_option "--github-actions"
                GITHUB_ACTIONS_MODE="true"
                shift
                ;;
            --platforms)
                record_parsed_option "--platforms"
                BUILD_PLATFORMS="$2"
                shift 2
                ;;
            --validation)
                record_parsed_option "--validation"
                VALIDATION_MODE="$2"
                shift 2
                ;;
            --build-arg)
                record_parsed_option "--build-arg"
                BUILD_ARGS+=("$2")
                shift 2
                ;;
            *)
                if [[ "$1" == --* ]]; then
                    UNKNOWN_OPTIONS+=("$1")
                else
                    REMAINING_ARGS+=("$1")
                fi
                shift
                ;;
        esac
    done
}

# Get remaining positional arguments
get_remaining_args() {
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
        printf '%s\n' "${REMAINING_ARGS[@]}"
    fi
}
