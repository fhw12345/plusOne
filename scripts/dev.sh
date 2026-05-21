#!/usr/bin/env bash
# One-shot local dev: backend (8001) + frontend (3000), fixture mode, console email.
# Run from repo root: ./scripts/dev.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/.dev-logs"
mkdir -p "$LOG_DIR"

# Kill anything still bound to the dev ports (best-effort, Windows-friendly)
for port in 18001 3000; do
  pid=$(netstat -ano 2>/dev/null | awk -v p=":$port" '$2 ~ p && /LISTENING/ {print $5; exit}')
  if [ -n "$pid" ]; then
    echo "Killing PID $pid on port $port"
    taskkill //PID "$pid" //F >/dev/null 2>&1 || true
  fi
done

echo "Starting backend on http://localhost:18001 ..."
( cd "$ROOT/backend" && uv run uvicorn plus_one.main:app --host 127.0.0.1 --port 18001 --reload \
    >"$LOG_DIR/backend.log" 2>&1 & echo $! >"$LOG_DIR/backend.pid" )

echo "Starting frontend on http://localhost:3000 ..."
( cd "$ROOT/frontend" && pnpm dev >"$LOG_DIR/frontend.log" 2>&1 & echo $! >"$LOG_DIR/frontend.pid" )

cat <<EOF

Dev stack starting. Logs:
  backend : $LOG_DIR/backend.log
  frontend: $LOG_DIR/frontend.log

Open http://localhost:3000

Magic-link sign-in (dev mode, console email):
  1. Enter any email on /signin
  2. Look at backend log for the link, OR:
     curl "http://localhost:18001/api/auth/dev/last-link?email=YOUR@EMAIL" | jq
  3. Open the printed URL — you'll be logged in.

Stop everything:
  ./scripts/dev-stop.sh
EOF
