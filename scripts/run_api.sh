#!/usr/bin/env bash
# Start Aether Assistant API using uv.
# Usage (from project root): ./scripts/run_api.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv not found. Install from https://github.com/astral-sh/uv"
  exit 1
fi

# Ensure venv + deps (idempotent)
if [[ ! -d .venv ]]; then
  echo "→ creating virtualenv with uv"
  uv venv
fi
echo "→ syncing dependencies"
uv sync

# Optional .env
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

echo "→ starting Aether Assistant on http://0.0.0.0:8000"
echo "   docs: http://localhost:8000/docs"
cd "$ROOT/backend"
exec uv run --project "$ROOT" uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
