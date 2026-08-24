#!/bin/zsh
set -euo pipefail

APP_ROOT="${0:A:h}"
LEGACY_STATE_DIR="$APP_ROOT/.cs-board-codex"
STATE_DIR="$APP_ROOT/.videosketchit"
PYTHON="$APP_ROOT/.venv/bin/python"
BACKEND_URL="http://127.0.0.1:18775"
FRONTEND_URL="http://127.0.0.1:13010"
if [[ -d "$LEGACY_STATE_DIR" && ! -e "$STATE_DIR" ]]; then
  mv "$LEGACY_STATE_DIR" "$STATE_DIR"
fi
mkdir -p "$STATE_DIR"

if [[ ! -x "$PYTHON" || ! -d "$APP_ROOT/web/node_modules" ]]; then
  echo "This independent edition is not installed yet. Run the Pinokio Install action first." >&2
  exit 1
fi

if ! curl --silent --fail --max-time 2 "$BACKEND_URL/api/health" >/dev/null 2>&1; then
  cd "$APP_ROOT"
  nohup "$PYTHON" -m uvicorn webapp.server:app --host 127.0.0.1 --port 18775 \
    >"$STATE_DIR/backend-output.log" 2>"$STATE_DIR/backend-error.log" &
fi

if ! curl --silent --fail --max-time 2 "$FRONTEND_URL" >/dev/null 2>&1; then
  cd "$APP_ROOT/web"
  nohup npm run start >"$STATE_DIR/frontend-output.log" 2>"$STATE_DIR/frontend-error.log" &
fi

for attempt in {1..90}; do
  if curl --silent --fail --max-time 2 "$BACKEND_URL/api/health" >/dev/null 2>&1 && \
     curl --silent --fail --max-time 2 "$FRONTEND_URL" >/dev/null 2>&1; then
    echo "VideoSketchIt is ready: $FRONTEND_URL"
    open "$FRONTEND_URL"
    exit 0
  fi
  sleep 1
done

echo "Startup failed. Check $STATE_DIR for logs." >&2
exit 1
