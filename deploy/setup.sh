#!/bin/sh
# Build and start X-TOOLS (also after updates: git pull && sudo sh deploy/setup.sh).
set -eu
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created deploy/.env from .env.example – adjust it if needed."
fi

docker compose up -d --build

PORT=$(docker compose port x-tools 8080 2>/dev/null | sed 's/.*://')
i=0
until curl -fs -o /dev/null "http://127.0.0.1:${PORT:-8080}/api/health"; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    echo "X-TOOLS does not answer. Logs: sudo docker logs --tail 50 x-tools" >&2
    exit 1
  fi
  sleep 1
done
echo "X-TOOLS is running on http://127.0.0.1:${PORT:-8080}"
