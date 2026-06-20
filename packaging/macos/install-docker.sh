#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# VLoop — macOS Docker install helper
#
# Usage:
#   chmod +x packaging/macos/install-docker.sh
#   ./packaging/macos/install-docker.sh
#
# This script downloads and installs Docker Desktop for macOS.
# After installation the user must *manually* launch Docker.app once
# so that the Docker daemon starts and the whale icon appears in the
# menu bar.  Once running, VLoop will detect Docker and workloads can
# be created from the UI.
# ---------------------------------------------------------------------------
set -euo pipefail

echo "VLoop — Docker Desktop installer for macOS"
echo "==========================================="
echo ""

# ------------------------------------------------------------------
# 1. Already installed?
# ------------------------------------------------------------------
if command -v docker &>/dev/null; then
    echo "  ✓ Docker CLI is already on PATH: $(docker --version 2>/dev/null || true)"
    if docker info &>/dev/null 2>&1; then
        echo "  ✓ Docker daemon is responding — everything looks good!"
        exit 0
    fi
    echo ""
    echo "  ⚠  Docker is installed but the daemon is not running."
    echo "     → Open Docker Desktop from /Applications and wait for the"
    echo "       whale icon to appear in the menu bar, then refresh the"
    echo "       VLoop Setup view."
    exit 1
fi

# ------------------------------------------------------------------
# 2. Determine architecture and download URL
# ------------------------------------------------------------------
ARCH=$(uname -m)
case "$ARCH" in
    arm64|aarch64)
        DMG_URL="https://desktop.docker.com/mac/main/arm64/Docker.dmg"
        ARCH_LABEL="Apple Silicon (arm64)"
        ;;
    x86_64|amd64)
        DMG_URL="https://desktop.docker.com/mac/main/amd64/Docker.dmg"
        ARCH_LABEL="Intel (x86_64)"
        ;;
    *)
        echo "  ✗ Unknown architecture: $ARCH — cannot auto-install Docker."
        echo "    Please install Docker Desktop manually: https://docs.docker.com/desktop/setup/install/mac-install/"
        exit 1
        ;;
esac

echo "  → Architecture: $ARCH_LABEL"
echo "  → Downloading Docker Desktop …"

# ------------------------------------------------------------------
# 3. Download
# ------------------------------------------------------------------
TMP_DMG="/tmp/vloop-docker-$$.dmg"
if ! curl -fsSL --progress-bar -o "$TMP_DMG" "$DMG_URL"; then
    echo "  ✗ Download failed."
    echo "    Install Docker Desktop manually: https://docs.docker.com/desktop/setup/install/mac-install/"
    rm -f "$TMP_DMG"
    exit 1
fi

echo "  → Mounting and installing to /Applications …"

# ------------------------------------------------------------------
# 4. Mount, copy, unmount
# ------------------------------------------------------------------
if ! hdiutil attach "$TMP_DMG" -nobrowse -quiet -mountpoint "/Volumes/Docker" 2>/dev/null; then
    echo "  ✗ Could not mount the disk image."
    rm -f "$TMP_DMG"
    exit 1
fi

cp -R "/Volumes/Docker/Docker.app" /Applications/ 2>/dev/null || true
hdiutil detach "/Volumes/Docker" -quiet -force 2>/dev/null || true
rm -f "$TMP_DMG"

# ------------------------------------------------------------------
# 5. Done
# ------------------------------------------------------------------
echo ""
echo "  ✓ Docker Desktop.app has been copied to /Applications."
echo ""
echo "  ┌────────────────────────────────────────────────────────┐"
echo "  │  Next step:  Open Docker.app and wait for the whale    │"
echo "  │  icon to appear in the menu bar.  The first launch     │"
echo "  │  may prompt for your admin password and a license      │"
echo "  │  agreement.  Once the daemon is running, VLoop will    │"
echo "  │  detect it automatically.                             │"
echo "  └────────────────────────────────────────────────────────┘"
echo ""
echo "  After Docker is running, refresh the VLoop Setup view or"
echo "  restart VLoop to pick up the new dependency status."
