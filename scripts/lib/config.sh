#!/bin/bash
# Centralized configuration for test environments
# Provides default values and environment variable handling

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Container and build configuration
DEFAULT_REGISTRY="${REGISTRY:-localhost:5000}"
DEFAULT_MPICH_VERSION="${MPICH_VERSION:-4.0.2}"
DEFAULT_BUILD_NCPUS="${BUILD_NCPUS:-4}"
DEFAULT_SST_VERSION="15.1.2"

# Container size limits (MB)
DEFAULT_MAX_SIZE_CORE=2048
DEFAULT_MAX_SIZE_FULL=4096
DEFAULT_MAX_SIZE_DEV=4096
DEFAULT_MAX_SIZE_EXPERIMENT=8192

# SST repository defaults
DEFAULT_SST_CORE_REPO="https://github.com/sstsimulator/sst-core.git"
DEFAULT_SST_ELEMENTS_REPO="https://github.com/sstsimulator/sst-elements.git"

# Supported build types and versions
VALID_CONTAINER_TYPES=("core" "full" "dev" "custom" "experiment")
VALID_SST_VERSIONS=("14.0.0" "14.1.0" "15.0.0" "15.1.0" "15.1.1" "15.1.2")

# Standard images that should resolve from Docker Hub without a custom registry prefix.
DOCKER_LIBRARY_IMAGES=(
    "ubuntu" "alpine" "debian" "centos" "fedora" "rocky" "almalinux" "amazonlinux"
)

# Get configuration value with fallback
get_config_value() {
    local var_name="$1"
    local default_value="$2"
    echo "${!var_name:-$default_value}"
}

# get_registry_value() {
#     get_config_value "REGISTRY" "$DEFAULT_REGISTRY"
# }

# Validate container type
validate_container_type() {
    local container_type="$1"
    for valid_type in "${VALID_CONTAINER_TYPES[@]}"; do
        if [[ "$container_type" == "$valid_type" ]]; then
            return 0
        fi
    done
    return 1
}

# Validate SST version
validate_sst_version() {
    local sst_version="$1"
    for valid_version in "${VALID_SST_VERSIONS[@]}"; do
        if [[ "$sst_version" == "$valid_version" ]]; then
            return 0
        fi
    done
    return 1
}

# Get default image size limit based on container type
get_default_size_limit() {
    local container_type="$1"
    case "$container_type" in
        "core")
            echo "$DEFAULT_MAX_SIZE_CORE"
            ;;
        "full")
            echo "$DEFAULT_MAX_SIZE_FULL"
            ;;
        "dev"|"custom")
            echo "$DEFAULT_MAX_SIZE_DEV"
            ;;
        "experiment")
            echo "$DEFAULT_MAX_SIZE_EXPERIMENT"
            ;;
        *)
            echo "$DEFAULT_MAX_SIZE_FULL"  # fallback
            ;;
    esac
}

get_container_image_name() {
    local container_type="$1"
    local enable_perf_tracking="${2:-false}"
    local experiment_name="${3:-}"

    case "$container_type" in
        core|full|dev|custom)
            if [[ "$enable_perf_tracking" == "true" ]] && [[ "$container_type" != "dev" ]]; then
                echo "sst-perf-track-${container_type}"
            else
                echo "sst-${container_type}"
            fi
            ;;
        experiment)
            if [[ -z "$experiment_name" ]]; then
                return 1
            fi
            echo "${experiment_name}"
            ;;
        *)
            return 1
            ;;
    esac
}

generate_container_image_tag() {
    local registry="$1"
    local container_type="$2"
    local version_or_tag="$3"
    local arch="${4:-}"
    local enable_perf_tracking="${5:-false}"
    local experiment_name="${6:-}"
    local image_name=""

    image_name=$(get_container_image_name "$container_type" "$enable_perf_tracking" "$experiment_name") || return 1

    if [[ -n "$arch" ]]; then
        echo "${registry}/${image_name}:${version_or_tag}-${arch}"
    else
        echo "${registry}/${image_name}:${version_or_tag}"
    fi
}

detect_container_type_from_image_tag() {
    local image_tag="$1"

    case "$image_tag" in
        *"/sst-experiment/"*)
            echo "experiment"
            ;;
        *"sst-perf-track-custom:"*|*"/sst-perf-track-custom:"*|*"sst-custom:"*|*"/sst-custom:"*)
            echo "custom"
            ;;
        *"sst-perf-track-core:"*|*"/sst-perf-track-core:"*|*"sst-core:"*|*"/sst-core:"*)
            echo "core"
            ;;
        *"sst-dev:"*|*"/sst-dev:"*)
            echo "dev"
            ;;
        *"sst-perf-track-full:"*|*"/sst-perf-track-full:"*|*"sst-full:"*|*"/sst-full:"*)
            echo "full"
            ;;
        *)
            # Experiment images are published directly under the experiment package
            # name (for example ghcr.io/org/phold-example:latest) rather than under
            # an sst-experiment/ namespace.
            echo "experiment"
            ;;
    esac
}

get_default_size_limit_for_image_tag() {
    local image_tag="$1"
    local container_type=""

    container_type=$(detect_container_type_from_image_tag "$image_tag")
    get_default_size_limit "$container_type"
}

resolve_base_image_reference() {
    local base_image="$1"
    local default_owner="${2:-$(whoami)}"
    local library_image=""

    if [[ -z "$base_image" ]]; then
        return 1
    fi

    if [[ "$base_image" == *"/"* ]]; then
        echo "$base_image"
        return 0
    fi

    library_image="${base_image%%[:@]*}"
    for known_image in "${DOCKER_LIBRARY_IMAGES[@]}"; do
        if [[ "$library_image" == "$known_image" ]]; then
            echo "$base_image"
            return 0
        fi
    done

    echo "ghcr.io/${default_owner}/${base_image}"
}

inspect_manifest_ref() {
    local image_ref="$1"
    local inspect_bin="${2:-${MANIFEST_INSPECT_BIN:-docker}}"

    "$inspect_bin" manifest inspect "$image_ref" >/dev/null 2>&1
}

collect_verified_manifest_images() {
    local manifest_tag="$1"
    local platforms="$2"
    local inspect_bin="${3:-${MANIFEST_INSPECT_BIN:-docker}}"
    local verified_images="[]"

    if [[ -z "$manifest_tag" ]]; then
        echo "[]"
        return 0
    fi

    if [[ -z "$platforms" ]]; then
        echo "[]"
        return 0
    fi

    IFS=',' read -ra platform_array <<< "$platforms"

    for platform in "${platform_array[@]}"; do
        local arch="${platform#linux/}"
        local temp_tag="${manifest_tag}-${arch}"

        if inspect_manifest_ref "$temp_tag" "$inspect_bin"; then
            verified_images=$(echo "$verified_images" | jq -c --arg tag "$temp_tag" '. += [$tag]')
        else
            echo "WARNING: Skipping missing platform image ${temp_tag}" >&2
        fi
    done

    echo "$verified_images"
}

# Generate latest tagging information from built images JSON
# Returns JSON array with latest tag information for each unique image base
generate_latest_tagging_info() {
    local built_images_json="$1"

    if [[ -z "$built_images_json" ]] || [[ "$built_images_json" == "null" ]]; then
        echo "[]"
        return 0
    fi

    # Parse built images and group by base name (removing architecture suffix)
    local tagging_info="[]"
    local processed_bases=()

    # Process each image in the JSON array
    while IFS= read -r image; do
        if [[ -n "$image" ]] && [[ "$image" != "null" ]]; then
            # Extract base name by removing architecture suffix
            # Example: ghcr.io/owner/sst-core:15.1.2-amd64 -> ghcr.io/owner/sst-core
            if [[ "$image" =~ ^(.+):(.+)-(amd64|arm64|x86_64|aarch64)$ ]]; then
                local base_image="${BASH_REMATCH[1]}"
                local source_tag="${BASH_REMATCH[2]}"
                local base_name="${base_image}"
                local latest_tag

                # Determine latest tag based on source tag pattern
                if [[ "$source_tag" =~ ^master- ]]; then
                    # Master builds get master-latest tag
                    latest_tag="${base_name}:master-latest"
                else
                    # Release builds get plain latest tag
                    latest_tag="${base_name}:latest"
                fi

                # Check if we've already processed this base name
                local already_processed=false
                if [[ ${#processed_bases[@]} -gt 0 ]]; then
                    for processed in "${processed_bases[@]}"; do
                        if [[ "$processed" == "$base_name" ]]; then
                            already_processed=true
                            break
                        fi
                    done
                fi

                if [[ "$already_processed" == "false" ]]; then
                    processed_bases+=("$base_name")

                    # Find all platform images for this base name
                    local platform_images="[]"
                    while IFS= read -r check_image; do
                        if [[ -n "$check_image" ]] && [[ "$check_image" != "null" ]]; then
                            if [[ "$check_image" =~ ^${base_image}:${source_tag}-(amd64|arm64|x86_64|aarch64)$ ]]; then
                                platform_images=$(echo "$platform_images" | jq -c --arg img "$check_image" '. += [$img]')
                            fi
                        fi
                    done < <(echo "$built_images_json" | jq -r '.[]')

                    # Add to tagging info if we found platform images
                    if [[ "$(echo "$platform_images" | jq 'length')" -gt 0 ]]; then
                        local entry=$(jq -n \
                            --arg base "$base_name" \
                            --arg latest "$latest_tag" \
                            --argjson images "$platform_images" \
                            '{base_name: $base, latest_tag: $latest, platform_images: $images}')
                        tagging_info=$(echo "$tagging_info" | jq -c --argjson entry "$entry" '. += [$entry]')
                    fi
                fi
            fi
        fi
    done < <(echo "$built_images_json" | jq -r '.[]')

    echo "$tagging_info"
}
