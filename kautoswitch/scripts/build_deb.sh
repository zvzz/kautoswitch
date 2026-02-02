#!/bin/bash
# Build kautoswitch .deb package.
#
# Usage:
#   Path A (host build):
#     sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools
#     ./scripts/build_deb.sh
#
#   Path B (container build):
#     ./scripts/build_deb.sh --container
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"

mkdir -p "$DIST_DIR"

if [ "${1:-}" = "--container" ]; then
    echo "=== Building in container ==="
    CONTAINER_CMD=""
    if command -v podman &>/dev/null; then
        CONTAINER_CMD="podman"
    elif command -v docker &>/dev/null; then
        CONTAINER_CMD="docker"
    else
        echo "ERROR: Neither docker nor podman found."
        exit 1
    fi

    $CONTAINER_CMD run --rm \
        -v "$PROJECT_DIR:/src:Z" \
        -v "$DIST_DIR:/dist:Z" \
        -w /build \
        ubuntu:24.04 \
        bash -c '
            set -e
            apt-get update -qq
            apt-get install -y -qq devscripts debhelper dh-python python3-all python3-setuptools >/dev/null 2>&1
            cp -a /src /build/kautoswitch
            cd /build/kautoswitch
            dpkg-buildpackage -us -uc -b
            cp /build/kautoswitch_*.deb /dist/
            echo "=== Build complete ==="
            ls -lh /dist/*.deb
        '
else
    echo "=== Building on host ==="
    # Verify build deps
    for pkg in devscripts debhelper dh-python python3-all; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            echo "Missing build dependency: $pkg"
            echo "Install with: sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools"
            exit 1
        fi
    done

    cd "$PROJECT_DIR"
    dpkg-buildpackage -us -uc -b

    # Move .deb to dist/
    mv ../kautoswitch_*.deb "$DIST_DIR/" 2>/dev/null || true
    mv ../kautoswitch_*.buildinfo "$DIST_DIR/" 2>/dev/null || true
    mv ../kautoswitch_*.changes "$DIST_DIR/" 2>/dev/null || true

    echo "=== Build complete ==="
    ls -lh "$DIST_DIR"/*.deb
fi

echo ""
echo "Install with:"
echo "  sudo apt install ./$DIST_DIR/kautoswitch_*.deb"
