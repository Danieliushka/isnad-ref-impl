#!/bin/bash
# isnad Platform — production start
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting isnad backend..."
cd "$DIR"
python -m uvicorn src.isnad.api_v1:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo "Starting isnad frontend..."
cd "$DIR/web"
npm run build && npm start -- -p 3000 &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID, Frontend PID: $FRONTEND_PID"
wait
