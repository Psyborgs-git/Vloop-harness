#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# VLoop — Linux Docker install helper
#
# Usage:
#   chmod +x packaging/linux/install-docker.sh
#   sudo ./packaging/linux/install-docker.sh
#
# Installs Docker Engine via the official get.docker.com convenience
# script and adds the current user to the `docker` group so they can
# talk to the daemon without `sudo`.
# ---------------------------------------------------------------------------
set -euo pipefail

echo "VLoop — Docker Engine installer for Linux"
echo "=========================================="
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
    echo "  ⚠  Docker daemon is not running or the current user lacks"
    echo "     permission.  Try:"
    echo ""
    echo "       sudo systemctl enable --now docker"
    echo "       sudo usermod -aG docker $USER"
    echo ""
    echo "     Then log out and back in."
    exit 1
fi

# ------------------------------------------------------------------
# 2. Check for root or sudo
# ------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "  This script requires superuser privileges to install Docker."
    echo "  Please re-run with:  sudo $0"
    exit 1
fi

# ------------------------------------------------------------------
# 3. Install via get.docker.com
# ------------------------------------------------------------------
echo "  → Downloading and running the official Docker install script …"
if curl -fsSL https://get.docker.com | sh; then
    echo ""
    echo "  ✓ Docker Engine installed successfully."
else
    echo ""
    echo "  ✗ The install script reported an error."
    echo "    Install Docker manually: https://docs.docker.com/engine/install/"
    exit 1
fi

# ------------------------------------------------------------------
# 4. Enable and start the service
# ------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
    echo "  → Enabling and starting Docker via systemd …"
    systemctl enable docker 2>/dev/null || true
    systemctl start docker 2>/dev/null || true
elif command -v service &>/dev/null; then
    echo "  → Starting Docker via service …"
    service docker start 2>/dev/null || true
fi

# ------------------------------------------------------------------
# 5. Add the invoking user to docker group
# ------------------------------------------------------------------
INVOKING_USER="${SUDO_USER:-$USER}"
if [ -n "$INVOKING_USER" ] && [ "$INVOKING_USER" != "root" ]; then
    echo "  → Adding user '$INVOKING_USER' to the docker group …"
    usermod -aG docker "$INVOKING_USER" 2>/dev/null || true
    echo ""
    echo "  ┌────────────────────────────────────────────────────────┐"
    echo "  │  ⚠  You must log out and back in (or run               │"
    echo "  │     'newgrp docker') for group changes to take effect. │"
    echo "  └────────────────────────────────────────────────────────┘"
fi

# ------------------------------------------------------------------
# 6. Done
# ------------------------------------------------------------------
echo ""
echo "  ✓ Docker Engine is installed and the service has been started."
echo ""
echo "  After logging out and back in, VLoop will detect Docker"
echo "  automatically.  Refresh the Setup view to verify."
