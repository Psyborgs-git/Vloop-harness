#!/usr/bin/env bash
# VLoop Docker installer — checks for Docker and offers to install it.
# Docker is OPTIONAL for VLoop.  Only workloads that run containers need it.
# All other features (agents, providers, chat, AI workflows) work without Docker.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

banner() {
    printf "${CYAN}VLoop${NC}  %s\n" "$1"
}

warn() {
    printf "${YELLOW}⚠${NC}  %s\n" "$1"
}

ok() {
    printf "${GREEN}✓${NC}  %s\n" "$1"
}

err() {
    printf "${RED}✗${NC}  %s\n" "$1"
}

# ---------------------------------------------------------------------------
# Check if Docker is installed and running
# ---------------------------------------------------------------------------
check_docker() {
    if command -v docker &>/dev/null; then
        ok "Docker CLI found at $(command -v docker)"
        if docker info &>/dev/null 2>&1; then
            ok "Docker daemon is running"
            return 0
        else
            warn "Docker CLI is installed but the daemon is NOT running"
            return 2
        fi
    else
        warn "Docker is not installed"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Offer guided install
# ---------------------------------------------------------------------------
install_docker_macos() {
    banner "Docker is optional for VLoop — only container workloads need it."
    printf "\n"
    printf "Install options:\n"
    printf "  1) Docker Desktop (GUI, recommended)\n"
    printf "     → https://docs.docker.com/desktop/setup/install/mac-install/\n"
    printf "  2) Colima (lightweight, CLI-only)\n"
    printf "     → brew install colima docker\n"
    printf "     → colima start\n"
    printf "  3) Skip — VLoop works without Docker\n"
    printf "\n"
    read -r -p "Choose ([1]/2/3): " choice

    case "${choice:-1}" in
        1)
            if command -v brew &>/dev/null; then
                banner "Installing Docker Desktop via Homebrew..."
                brew install --cask docker
                ok "Docker Desktop installed.  Launch it from /Applications."
            else
                warn "Homebrew not found.  Please download Docker Desktop from:"
                warn "https://docs.docker.com/desktop/setup/install/mac-install/"
            fi
            ;;
        2)
            if command -v brew &>/dev/null; then
                banner "Installing Colima + Docker CLI..."
                brew install colima docker docker-completion
                colima start --cpu 2 --memory 4
                ok "Colima is running.  Docker commands should now work."
            else
                err "Homebrew is required for Colima.  Install Homebrew first:"
                err "https://brew.sh"
            fi
            ;;
        3|*)
            banner "Skipping Docker.  VLoop workloads that need containers will be unavailable."
            banner "All other features (agents, providers, chat) work without Docker."
            ;;
    esac
}

install_docker_linux() {
    banner "Docker is optional for VLoop — only container workloads need it."
    printf "\n"
    printf "Install options:\n"
    printf "  1) Docker Engine (recommended for servers)\n"
    printf "     → curl -fsSL https://get.docker.com | sh\n"
    printf "  2) Skip — VLoop works without Docker\n"
    printf "\n"
    read -r -p "Choose ([1]/2): " choice

    case "${choice:-1}" in
        1)
            banner "Installing Docker Engine..."
            curl -fsSL https://get.docker.com | sh
            if command -v systemctl &>/dev/null; then
                sudo systemctl enable docker
                sudo systemctl start docker
            fi
            sudo usermod -aG docker "$USER"
            ok "Docker installed.  You may need to log out and back in for group changes."
            ;;
        2|*)
            banner "Skipping Docker.  VLoop workloads that need containers will be unavailable."
            banner "All other features (agents, providers, chat) work without Docker."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
banner "Docker check"

STATUS=0
check_docker; STATUS=$? || true

case $STATUS in
    0)
        banner "Docker is ready.  VLoop workload features are fully available."
        exit 0
        ;;
    1)
        warn "Docker is not installed."
        case "$(uname -s)" in
            Darwin) install_docker_macos ;;
            Linux)  install_docker_linux ;;
            *)
                warn "Unsupported OS.  Please install Docker manually:"
                warn "https://docs.docker.com/engine/install/"
                ;;
        esac
        ;;
    2)
        warn "Docker daemon is not running."
        banner "Start Docker Desktop, or run 'colima start' if using Colima."
        ;;
esac

banner "Done.  VLoop agents, providers, and chat features work regardless of Docker status."
