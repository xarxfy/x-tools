# X-TOOLS

Self-hosted overview of your servers, services, Docker containers and the websites you host for others – with
alerts when something breaks.

> **Status: early development (0.1).** X-TOOLS is the successor of a private tool and is being rebuilt step by step.
> Not ready for production use yet.

## What it will do

- **Overview** – everything that needs attention on one page: ports not answering, stopped containers, unreachable
  websites, silent servers, full disks.
- **Services** – what runs where: ports, domains, folders.
- **Servers & Docker** – containers grouped by compose project, start/stop/restart, logs, compose files and
  Dockerfiles (secrets masked).
- **Agents** – connect more servers (e.g. a Proxmox host at home). Agents only report outbound over HTTPS; no open
  ports, no VPN, nothing can be triggered on them.
- **Customers** – contacts and agreements for the sites you host, with external checks (DNS, HTTPS, certificate),
  last commit and last deploy.
- **Credentials** – logins per service, encrypted at rest.
- **Notifications** – Telegram and ntfy.

## Quick start (Docker)

```sh
git clone <repository> x-tools
cd x-tools/deploy
cp .env.example .env      # adjust XT_BASE_URL, XT_TIMEZONE …
docker compose up -d --build
```

Open the UI (port 8080 on localhost; put a reverse proxy or tunnel in front for HTTPS) and create the administrator
account. X-TOOLS generates a secret key in its data volume on first start – **back up the data volume**, stored
credentials can only be decrypted with that key.

## Configuration

All settings are environment variables prefixed with `XT_` (see `deploy/.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `XT_BASE_URL` | – | Public address, used in notification links; `https://` marks cookies Secure |
| `XT_TIMEZONE` | `UTC` | Time zone for displayed times |
| `XT_COMPOSE_ROOTS` | `/opt,/srv,/home` | Folders that may contain compose projects |
| `XT_PROTECTED_CONTAINERS` | `x-tools,x-tools-collector` | Containers that cannot be stopped from the UI |
| `XT_TRUST_PROXY` | `true` | Trust `X-Forwarded-*` headers from a reverse proxy |
| `XT_SECRET_KEY` | generated | Fernet key for encrypted data |
| `XT_DATA_DIR` | `/data` | Database and secret key |
| `XT_API_DOCS` | `false` | Interactive API docs at `/api/docs` |

## Development

```sh
# Backend (http://127.0.0.1:8080)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
XT_DATA_DIR=./dev-data XT_API_DOCS=true x-tools serve
pytest

# Frontend (http://127.0.0.1:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Database changes: edit `backend/app/models`, then
`XT_DATA_DIR=./dev-data alembic revision --autogenerate -m "describe change"`. Migrations run automatically on start.

## Security

- Session login (Argon2 password hashes, session tokens stored hashed, CSRF protection, login throttling).
- The web process has no Docker access; container actions go through the separate collector (coming in 0.2).
- Credentials and notification tokens are encrypted with the instance's secret key.
- Run X-TOOLS behind HTTPS.

## License

[MIT](LICENSE)
