#!/bin/bash
# Download script for SST container build sources
# Downloads MPICH, SST-core, and SST-elements source archives

set -euo pipefail

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/config.sh"
source "${SCRIPT_DIR}/../lib/logging.sh"

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] [SST_VERSION] [MPICH_VERSION]"
    echo ""
    echo "Downloads source archives for SST container builds"
    echo ""
    echo "Options:"
    echo "  --component COMP   Component(s) to download: all, mpich, sst-core, sst-full (default: all)"
    echo "  --sst-elements-version VER  SST-elements release version override for sst-full/all"
    echo "  --force, -f        Skip version validation warnings (for automation)"
    echo "  --help, -h         Show this help"
    echo ""
    echo "Arguments:"
    echo "  SST_VERSION        SST version to download (default: $DEFAULT_SST_VERSION)"
    echo "  MPICH_VERSION      MPICH version to download (default: $DEFAULT_MPICH_VERSION)"
    echo ""
    echo "Components:"
    echo "  all                Download MPICH + SST-core + SST-elements (default)"
    echo "  mpich              Download only MPICH (requires MPICH_VERSION)"
    echo "  sst-core           Download only SST-core tarball (requires SST_VERSION)"
    echo "  sst-full           Download SST-core + SST-elements (requires SST_VERSION)"
    echo ""
    echo "Examples:"
    echo "  $0                                 # Download all (SST $DEFAULT_SST_VERSION, MPICH $DEFAULT_MPICH_VERSION)"
    echo "  $0 15.0.0                          # Download all with SST 15.0.0, MPICH $DEFAULT_MPICH_VERSION"
    echo "  $0 15.0.0 4.1.1                    # Download all with SST 15.0.0, MPICH 4.1.1"
    echo "  $0 --component mpich $DEFAULT_MPICH_VERSION        # Download only MPICH $DEFAULT_MPICH_VERSION"
    echo "  $0 --component sst-core 15.0.0     # Download only SST-core 15.0.0"
    echo "  $0 --component sst-full 15.0.0     # Download SST-core + SST-elements 15.0.0"
    echo "  $0 --component sst-full --sst-elements-version 15.1.2 16.0.0"
    echo "                                     # Download SST-core 16.0.0 + SST-elements 15.1.2"
    echo "  $0 --force 15.1.2                  # Download all, SST 15.1.2, skip version warnings"
    echo "  $0 --help                          # Show this help"
}

# Parse command line arguments
FORCE_MODE=false
COMPONENT="all"
SST_VERSION=""
SST_ELEMENTS_VERSION=""
MPICH_VERSION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --component)
            COMPONENT="$2"
            shift 2
            ;;
        --sst-elements-version)
            SST_ELEMENTS_VERSION="$2"
            shift 2
            ;;
        --force|-f)
            FORCE_MODE=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        -*)
            echo "Error: Unknown option $1"
            show_usage
            exit 1
            ;;
        *)
            if [[ -z "$SST_VERSION" ]]; then
                SST_VERSION="$1"
            elif [[ -z "$MPICH_VERSION" ]]; then
                MPICH_VERSION="$1"
            else
                echo "Error: Too many arguments"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate component value
case "$COMPONENT" in
    all|mpich|sst-core|sst-full) ;;
    *)
        echo "Error: Unknown component '$COMPONENT'"
        echo "Valid components: all, mpich, sst-core, sst-full"
        exit 1
        ;;
esac

# Set defaults if not provided
SST_VERSION="${SST_VERSION:-$DEFAULT_SST_VERSION}"
MPICH_VERSION="${MPICH_VERSION:-$DEFAULT_MPICH_VERSION}"
SST_ELEMENTS_VERSION="${SST_ELEMENTS_VERSION:-$SST_VERSION}"

# Determine what to download based on component
DOWNLOAD_MPICH=false
DOWNLOAD_SST_CORE=false
DOWNLOAD_SST_ELEMENTS=false

case "$COMPONENT" in
    all)
        DOWNLOAD_MPICH=true
        DOWNLOAD_SST_CORE=true
        DOWNLOAD_SST_ELEMENTS=true
        ;;
    mpich)
        DOWNLOAD_MPICH=true
        ;;
    sst-core)
        DOWNLOAD_SST_CORE=true
        ;;
    sst-full)
        DOWNLOAD_SST_CORE=true
        DOWNLOAD_SST_ELEMENTS=true
        ;;
esac

# Validate SST version when downloading SST sources (unless force mode is enabled)
if [[ "$DOWNLOAD_SST_CORE" == "true" ]] && [[ "$FORCE_MODE" != "true" ]]; then
    if [[ ! " ${VALID_SST_VERSIONS[@]} " =~ " ${SST_VERSION} " ]]; then
        log_warning "SST version ${SST_VERSION} may not be valid."
        log_warning "Known valid versions: ${VALID_SST_VERSIONS[*]}"
        log_warning "Continuing anyway... (use --force to suppress this warning)"
    fi
fi

echo "=================================================="
echo "SST Container Source Download Script"
echo "=================================================="
echo "Component:     $COMPONENT"
if [[ "$DOWNLOAD_SST_CORE" == "true" ]]; then
    echo "SST Version:   $SST_VERSION"
fi
if [[ "$DOWNLOAD_SST_ELEMENTS" == "true" ]]; then
    echo "Elements Ver:  $SST_ELEMENTS_VERSION"
fi
if [[ "$DOWNLOAD_MPICH" == "true" ]]; then
    echo "MPICH Version: $MPICH_VERSION"
fi
echo "=================================================="

# Download URLs
MPICH_URL="https://www.mpich.org/static/downloads/${MPICH_VERSION}/mpich-${MPICH_VERSION}.tar.gz"
SST_CORE_URL="https://github.com/sstsimulator/sst-core/releases/download/v${SST_VERSION}_Final/sstcore-${SST_VERSION}.tar.gz"
SST_ELEMENTS_URL="https://github.com/sstsimulator/sst-elements/releases/download/v${SST_ELEMENTS_VERSION}_Final/sstelements-${SST_ELEMENTS_VERSION}.tar.gz"

# Function to download with progress and error handling
download_file() {
    local url="$1"
    local filename="$2"
    local description="$3"

    echo ""
    echo "Downloading $description..."
    echo "URL: $url"
    echo "File: $filename"

    if [[ -f "$filename" ]]; then
        echo "File $filename already exists. Skipping download."
        echo "To re-download, delete the file first: rm $filename"
        return 0
    fi

    if wget --no-check-certificate --progress=bar:force "$url" -O "$filename"; then
        echo "[SUCCESS] Successfully downloaded $filename"
        # Show file size
        echo "  File size: $(ls -lh "$filename" | awk '{print $5}')"
    else
        echo "[ERROR] Failed to download $filename"
        echo "  URL: $url"
        rm -f "$filename"  # Remove partial download
        return 1
    fi
}

# Execute downloads based on component selection
if [[ "$DOWNLOAD_MPICH" == "true" ]]; then
    download_file "$MPICH_URL" "mpich-${MPICH_VERSION}.tar.gz" "MPICH ${MPICH_VERSION}"
fi

if [[ "$DOWNLOAD_SST_CORE" == "true" ]]; then
    download_file "$SST_CORE_URL" "sstcore-${SST_VERSION}.tar.gz" "SST-core ${SST_VERSION}"
fi

if [[ "$DOWNLOAD_SST_ELEMENTS" == "true" ]]; then
    # Save with elements version filename because Containerfile expects sstelements-${SST_ELEMENTS_VERSION}.tar.gz
    download_file "$SST_ELEMENTS_URL" "sstelements-${SST_ELEMENTS_VERSION}.tar.gz" "SST-elements ${SST_ELEMENTS_VERSION}"
fi

echo ""
echo "=================================================="
echo "Download Summary"
echo "=================================================="

# Build the list of expected files based on what was requested
files=()
if [[ "$DOWNLOAD_MPICH" == "true" ]]; then
    files+=("mpich-${MPICH_VERSION}.tar.gz")
fi
if [[ "$DOWNLOAD_SST_CORE" == "true" ]]; then
    files+=("sstcore-${SST_VERSION}.tar.gz")
fi
if [[ "$DOWNLOAD_SST_ELEMENTS" == "true" ]]; then
    files+=("sstelements-${SST_ELEMENTS_VERSION}.tar.gz")
fi

all_present=true
total_size=0

for file in "${files[@]}"; do
    if [[ -f "$file" ]]; then
        size_bytes=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
        size_mb=$((size_bytes / 1024 / 1024))
        total_size=$((total_size + size_mb))
        echo "[SUCCESS] $file (${size_mb} MB)"
    else
        echo "[ERROR] $file (MISSING)"
        all_present=false
    fi
done

echo "=================================================="
echo "Total download size: ${total_size} MB"

if $all_present; then
    echo "[SUCCESS] All requested files downloaded successfully!"
    echo ""
    echo "Files downloaded to current directory:"
    echo ""
    for file in "${files[@]}"; do
        echo "  $(pwd)/$file"
    done
    echo ""
    echo "Next steps:"
    echo "1. Files are ready in your current build directory"
    echo "2. Use the Containerfile to build an SST image"
else
    echo "[ERROR] Some downloads failed. Check network connection and try again."
    exit 1
fi