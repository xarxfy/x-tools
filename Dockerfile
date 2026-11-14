# X-TOOLS – one image for the web UI/API and the Docker collector.

# --- 1. Build the React frontend ------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python runtime -------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XT_DATA_DIR=/data \
    XT_FRONTEND_DIR=/app/frontend
# git: read commit info of compose projects; tzdata: XT_TIMEZONE
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend && rm -rf ./backend
COPY --from=frontend /src/dist /app/frontend
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin xtools \
    && mkdir -p /data /exchange && chown xtools:xtools /data /exchange
USER xtools
VOLUME /data
EXPOSE 8080
# Web process; the collector overrides this in docker-compose.yml (it has no network).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('XT_PORT', '8080'), timeout=4)" || exit 1
CMD ["x-tools", "serve"]
