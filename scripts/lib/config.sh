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
    "busybox" "scratch" "node" "python" "golang" "openjdk" "nginx" "httpd"
    "redis" "postgres" "mysql" "mariadb" "mongo" "memcached" "rabbitmq"
    "elasticsearch" "kibana" "grafana" "prometheus" "consul" "vault" "traefik"
    "caddy" "haproxy" "envoy"
)

# Get configuration value with fallback
get_config_value() {
    local var_name="$1"
    local default_value="$2"
    echo "${!var_name:-$default_value}"
}

get_registry_value() {
    get_config_value "REGISTRY" "$DEFAULT_REGISTRY"
}

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
            echo "sst-experiment/${experiment_name}"
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
        *"sst-experiment/"*)
            echo "experiment"
            ;;
        *"sst-custom:"*|*"sst-perf-track-custom:"*)
            echo "custom"
            ;;
        *"sst-dev:"*)
            echo "dev"
            ;;
        *"sst-full:"*|*"sst-perf-track-full:"*)
            echo "full"
            ;;
        *)
            echo "core"
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

# Generate image tag
generate_image_tag() {
    local registry="$1"
    local container_type="$2"
    local sst_version="$3"
    local arch="${4:-}"

    if [[ -n "$arch" ]]; then
        echo "${registry}/sst-${container_type}:${sst_version}-${arch}"
    else
        echo "${registry}/sst-${container_type}:${sst_version}"
    fi
}

# Generate architecture-specific image tag (matches workflow pattern)
generate_arch_image_tag() {
    local registry="$1"
    local container_type="$2"
    local sst_version="$3"
    local arch="$4"

    echo "${registry}/sst-${container_type}:${sst_version}-${arch}"
}

# Generate base image tag for fat manifest (matches workflow pattern)
generate_base_image_tag() {
    local registry="$1"
    local container_type="$2"
    local sst_version="$3"

    echo "${registry}/sst-${container_type}:${sst_version}"
}
