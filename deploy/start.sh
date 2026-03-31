#!/bin/bash
# isnad Platform — local production-like start
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:${API_PORT}/api/v1}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}

trap cleanup EXIT INT TERM

echo "Starting isnad backend..."
cd "$DIR"
PYTHONPATH="$DIR/src" python -m uvicorn isnad.api_v1:app --host "$API_HOST" --port "$API_PORT" --proxy-headers &
BACKEND_PID=$!

echo "Starting isnad frontend..."
cd "$DIR/web"
NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" npm run build
NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" npm start -- -p "$WEB_PORT" &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID, Frontend PID: $FRONTEND_PID"
wait
