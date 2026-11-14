#!/bin/sh
# Build and start X-TOOLS (also after updates: git pull && sudo sh deploy/setup.sh).
set -eu
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created deploy/.env from .env.example – adjust it if needed."
fi

# Group of the Docker socket, so the collector may use it (once, in .env).
if ! grep -q '^DOCKER_GID=' .env; then
  [ -n "$(tail -c1 .env)" ] && echo >> .env
  echo "DOCKER_GID=$(stat -c %g /var/run/docker.sock)" >> .env
fi

docker compose up -d --build --remove-orphans

PORT=$(sed -n 's/^XT_PORT=//p' .env | tail -n1)
PORT=${PORT:-8080}
i=0
until curl -fs -o /dev/null "http://127.0.0.1:${PORT}/api/health"; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    echo "X-TOOLS does not answer. Logs: sudo docker logs --tail 50 x-tools" >&2
    exit 1
  fi
  sleep 1
done
echo "X-TOOLS is running on http://127.0.0.1:${PORT}"
echo "Collector log: sudo docker logs --tail 20 x-tools-collector"
