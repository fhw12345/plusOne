#!/usr/bin/env bash
# Stop the dev stack started by dev.sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/.dev-logs"

for name in backend frontend; do
  pidfile="$LOG_DIR/$name.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    echo "Stopping $name (pid $pid)"
    taskkill //PID "$pid" //F //T >/dev/null 2>&1 || kill -9 "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done

# Belt-and-braces: anything still on the dev ports
for port in 18001 3000; do
  pid=$(netstat -ano 2>/dev/null | awk -v p=":$port" '$2 ~ p && /LISTENING/ {print $5; exit}')
  if [ -n "$pid" ]; then
    echo "Killing stray PID $pid on port $port"
    taskkill //PID "$pid" //F >/dev/null 2>&1 || true
  fi
done

echo "Dev stack stopped."
