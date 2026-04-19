#!/usr/bin/env bash
set -euo pipefail

echo "=== Vloop Harness Setup ==="

if ! command -v cargo &>/dev/null; then echo "ERROR: Rust/Cargo not found." && exit 1; fi
echo "✓ Rust $(rustc --version)"
if ! command -v node &>/dev/null; then echo "ERROR: Node.js not found." && exit 1; fi
echo "✓ Node $(node --version)"
if ! command -v python3 &>/dev/null; then echo "ERROR: Python 3.11+ not found." && exit 1; fi
echo "✓ Python $(python3 --version)"
command -v ollama &>/dev/null && echo "✓ Ollama found" || echo "⚠ Ollama not found — install from https://ollama.ai"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "--- Installing harness-ui npm dependencies ---"
cd "$REPO_ROOT/harness-ui" && npm install

echo "--- Setting up inference-backend Python environment ---"
cd "$REPO_ROOT/inference-backend"
[ ! -d ".venv" ] && python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip && pip install -q -e ".[dev]"

echo "=== Setup complete! Run ./scripts/dev.sh to start all services ==="
