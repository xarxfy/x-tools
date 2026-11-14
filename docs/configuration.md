# Configuration

All settings are environment variables prefixed with `XT_` in `deploy/.env` (template: `deploy/.env.example`).
After changes: `sudo sh deploy/setup.sh`. Everything else (notifications, agents, users, Cloudflare, features) is
set in the UI under *Settings*.

| Variable | Default | Meaning |
|---|---|---|
| `XT_BASE_URL` | – | Address you open X-TOOLS with; used in notification links and agent install commands. `https://` marks cookies Secure |
| `XT_TIMEZONE` | `UTC` | Time zone for displayed times and logs |
| `XT_HOST` / `XT_PORT` | `127.0.0.1` / `8080` | Address of the web UI. `0.0.0.0` only without a reverse proxy (homelab) |
| `XT_TRUST_PROXY` | `true` | Trust `X-Forwarded-*` headers. Set `false` when X-TOOLS is reached directly |
| `XT_COMPOSE_ROOTS` | `/opt,/srv,/home` | Folders that may contain compose projects |
| `XT_HOME_DIR` | – | Home folder shown as `~` in paths |
| `XT_CHECK_HOST` | `127.0.0.1` | Host on which service ports are checked when a service has no host |
| `XT_PROTECTED_CONTAINERS` | `x-tools,x-tools-collector` | Containers that cannot be stopped from the UI |
| `XT_COLLECT_INTERVAL` | `60` | Seconds between Docker snapshots |
| `XT_SITE_INTERVAL` | `300` | Seconds between website checks of customer domains |
| `XT_SECRET_KEY` | generated | Fernet key for encrypted data (default: `secret.key` in the data volume) |
| `XT_DATA_DIR` | `/data` | Database and secret key |
| `XT_API_DOCS` | `false` | Interactive API docs at `/api/docs` |

**Compose projects outside `/home`, `/opt` and `/srv`:** add the folder to `XT_COMPOSE_ROOTS` **and** as a
read-only volume of the collector in `deploy/docker-compose.yml`.

## Agents

The agent (`x-tools agent`) reads its own variables – the install command writes them to
`/etc/x-tools-agent/agent.env`:

| Variable | Meaning |
|---|---|
| `XT_AGENT_URL`, `XT_AGENT_KEY` | where to report and the agent key |
| `XT_AGENT_DOCKER` | `0` = do not read Docker (Proxmox hosts) |
| `XT_COMPOSE_ROOTS` | folders with compose projects on that server |
| `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access service token (optional) |
| `PROXMOX_URL`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET`, `PROXMOX_VERIFY_TLS` | Proxmox API (Proxmox hosts) |
