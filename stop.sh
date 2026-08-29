#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/ui/.runtime/ui.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "C2C UI is not running."
  exit 0
fi

pid="$(<"$PID_FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  echo "Invalid UI PID file; removing it."
  rm -f "$PID_FILE"
  exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "C2C UI was not running; removed stale PID file."
  exit 0
fi

kill "$pid"
for _ in {1..20}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "C2C UI stopped."
    exit 0
  fi
  sleep 0.25
done

echo "C2C UI did not stop gracefully; sending SIGKILL to PID $pid." >&2
kill -KILL "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "C2C UI stopped."
