#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== Building Vloop Harness ==="
cd "$REPO_ROOT/harness-ui" && npm run build
cd "$REPO_ROOT/harness-core" && cargo tauri build
echo "=== Build complete. Bundles in harness-core/target/release/bundle/ ==="
