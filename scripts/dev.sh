#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDS=()

cleanup() {
  echo "" && echo "Shutting down..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM EXIT

echo "=== Starting Vloop Harness dev environment ==="

cd "$REPO_ROOT/inference-backend"
[ -f ".venv/bin/activate" ] && source .venv/bin/activate
uvicorn inference_backend.main:app --reload --port 47201 --log-level info &
PIDS+=($!)

sleep 2

cd "$REPO_ROOT/harness-core"
cargo tauri dev &
PIDS+=($!)

echo "Services: inference-backend :47201 | Tauri/Vite :5173"
echo "Press Ctrl+C to stop."
wait
