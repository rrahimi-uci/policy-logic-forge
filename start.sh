#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/ui/.runtime"
PID_FILE="$RUNTIME_DIR/ui.pid"
LOG_FILE="$RUNTIME_DIR/ui.log"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
HOST="${C2C_UI_HOST:-127.0.0.1}"
PORT="${C2C_UI_PORT:-8787}"
PIPELINE_ROOT="${C2C_PIPELINE_ROOT:-$ROOT_DIR/pipeline-output}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -f "$PID_FILE" ]]; then
  pid="$(<"$PID_FILE")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    echo "C2C UI is already running (PID $pid) at http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -d "$ROOT_DIR/ui/frontend/dist" ]]; then
  echo "Building the frontend..."
  npm --prefix "$ROOT_DIR/ui/frontend" run build
fi

if curl --silent --fail "http://$HOST:$PORT/" >/dev/null 2>&1; then
  echo "Cannot start C2C UI: http://$HOST:$PORT is already responding." >&2
  echo "Set C2C_UI_PORT to another port or stop the existing service first." >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
cd "$ROOT_DIR"
nohup "$PYTHON_BIN" -m ui.backend.api \
  --pipeline-root "$PIPELINE_ROOT" \
  --host "$HOST" \
  --port "$PORT" \
  >"$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

for _ in {1..20}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "C2C UI failed to start. See $LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
  if curl --silent --fail "http://$HOST:$PORT/" >/dev/null 2>&1; then
    echo "C2C UI started at http://$HOST:$PORT (PID $pid)"
    echo "Log: $LOG_FILE"
    exit 0
  fi
  sleep 0.25
done

echo "C2C UI process started (PID $pid), but the health check did not respond yet." >&2
echo "Log: $LOG_FILE" >&2
