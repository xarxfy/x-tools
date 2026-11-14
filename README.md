# X-TOOLS

Self-hosted overview of your servers, services, Docker containers and the websites you host for others – with
alerts when something breaks.

> **Status: early development (0.1).** X-TOOLS is the successor of a private tool. All areas are in place; expect
> rough edges until 1.0.

## What it does

- **Overview** – everything that needs attention on one page: ports not answering, stopped containers, unreachable
  websites, silent servers, full disks.
- **Services** – what runs where: host, ports (checked every minute), domains, folders.
- **Servers & Docker** – containers grouped by compose project, start/stop/restart, logs, compose files and
  Dockerfiles (secrets masked), git status of the project folder.
- **Agents** – connect more servers (e.g. a Proxmox host at home). Agents only report outbound over HTTPS; no open
  ports, no VPN, nothing can be triggered on them. Proxmox nodes, storage, LXCs and VMs via a read-only API token.
- **Customers** (optional, switch on in *Settings → General*) – contacts and agreements for the sites you host for
  others, with external checks (DNS, HTTPS, certificate).
- **Credentials** – logins per service, encrypted at rest.
- **Notifications** – Telegram and ntfy.
- **History** – what went wrong when (with duration), uptime per service, load/memory/disk curves for 30 days.
- **Account** – change password, two-factor login (TOTP) with recovery codes, encrypted backups from the UI.
- **Users & roles** – viewer (read only), operator (maintain services, control containers), admin; audit log of
  who did what.

## How it is built

```
                 HTTPS                    HTTP (localhost)
  Browser  ───────────────▶  Reverse proxy  ───────────────▶  x-tools            ── SQLite + secret key
                             (Caddy, nginx,                   web UI + API          (volume "data")
                              Traefik, Cloudflare             port checks,
                              Tunnel …)                       site checks, alerts
                                                                  │
                                                                  │ files only (volume "exchange")
                                                                  ▼
                                                              x-tools-collector  ── Docker socket,
                                                              no network            compose folders (read-only)

  Other server:  x-tools-agent  ── HTTPS POST /api/agent/report ──▶  x-tools
```

- **One image, three roles:** `x-tools serve` (web UI + API), `x-tools collect` (Docker collector) and
  `x-tools agent` (reports another server).
- **The web container never touches Docker.** Container actions are written as small command files into the shared
  `exchange` volume; the collector validates them (known container, not protected, only start/stop/restart/logs)
  and executes them. The collector has no network and never sees the database or the secret key.
- The web container uses the **host network** so it can check whether the ports of your services answer. It listens
  on `127.0.0.1:8080` only – put a reverse proxy in front of it. (Linux only; Docker Desktop has no host network.)
- Backend: Python, FastAPI, SQLAlchemy, SQLite (migrations run automatically). Frontend: React, TypeScript, Vite.

## Installation

Requirements: a Linux server with Docker and the compose plugin.

```sh
git clone <repository> x-tools
cd x-tools/deploy
cp .env.example .env      # set XT_BASE_URL, XT_TIMEZONE, XT_COMPOSE_ROOTS …
sudo sh setup.sh          # builds the image, starts both containers, waits until X-TOOLS answers
```

X-TOOLS now runs on `http://127.0.0.1:8080` – reachable from the server itself only. Make it reachable in one of the
ways below, then open it and create the administrator account.

### First login: the setup code

As long as no account exists, X-TOOLS prints a one-time **setup code** to its log:

```sh
sudo docker logs x-tools
#   X-TOOLS is not set up yet.
#   Setup code: ABCD-EFGH
```

The setup page asks for this code, so nobody who stumbles upon a fresh installation can claim it. After the account
is created the setup page is gone. (A restart before the setup generates a new code.)

### Making it reachable

Pick one. In every case X-TOOLS itself stays on `127.0.0.1:8080`.

**A) Caddy (own domain, automatic HTTPS) – no Cloudflare needed.**
Point a DNS record (e.g. `tools.example.com`) to your server, open ports 80 and 443, install Caddy and add to
`/etc/caddy/Caddyfile`:

```
tools.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

`sudo systemctl reload caddy` – Caddy gets a Let's Encrypt certificate by itself. Set
`XT_BASE_URL=https://tools.example.com` in `deploy/.env` and run `sudo sh setup.sh` again.

**B) nginx or Traefik** – same idea: terminate HTTPS and proxy to `http://127.0.0.1:8080`, passing
`X-Forwarded-For` and `X-Forwarded-Proto`. Example for nginx (certificate e.g. via certbot):

```nginx
server {
    listen 443 ssl;
    server_name tools.example.com;
    # ssl_certificate …; ssl_certificate_key …;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**C) Cloudflare Tunnel (no open ports at all).**
Zero Trust → Networks → Tunnels → your tunnel → *Public hostname*: `tools.example.com` → `HTTP` → `localhost:8080`.
Recommended: put a Cloudflare Access application in front of it as a second login.

**D) Private only (VPN or SSH).**
Keep it off the internet entirely: reach it through WireGuard/Tailscale (proxy to the VPN address), or simply with an
SSH tunnel from your computer:

```sh
ssh -L 8080:127.0.0.1:8080 you@your-server   # then open http://localhost:8080
```

Leave `XT_BASE_URL` empty or set it to the address you use. Without `https://` cookies are not marked Secure – only
do that on a private connection.

### Homelab only (no VPS, nothing public)

X-TOOLS does not need a VPS or a public address. A typical setup at home:

```
  Your laptop / phone (LAN or VPN)
          │  http://192.168.1.10:8080
          ▼
  LXC or VM "tools" (Docker)          Proxmox host            Other LXCs/VMs
  ├─ x-tools          ◀── reports ──  x-tools-agent  ◀─ API   x-tools-agent (Docker)
  └─ x-tools-collector                (nodes, LXCs, VMs)
```

1. Create a small Debian LXC/VM with Docker and install X-TOOLS as above.
2. Make it reachable in your LAN – in `deploy/.env`:

   ```sh
   XT_HOST=0.0.0.0                      # listen on all interfaces, not only 127.0.0.1
   XT_PORT=8080
   XT_BASE_URL=http://192.168.1.10:8080 # the address you open; also used in agent install commands
   XT_TRUST_PROXY=false                 # no reverse proxy in front
   ```

   `sudo sh setup.sh` again, then open `http://192.168.1.10:8080` and enter the setup code.
3. Add your servers: *Settings → Agents → Add server*. For the Proxmox host switch on *Proxmox* and enter an API
   token (role `PVEAuditor`). Run the shown command as root on that machine – the agent reports over your LAN.
4. Services on other machines: enter their IP under *Host* in the service, so their ports are checked there.

From outside, use a VPN (WireGuard, Tailscale, the VPN of your router) instead of opening a port. Want HTTPS inside
the LAN? Put Caddy in front with `tls internal` (own certificate authority) and keep `XT_HOST=127.0.0.1`.

Without HTTPS the session cookie is sent unencrypted inside your network – fine for a home LAN you trust, not for
shared networks.

### Updating

```sh
cd x-tools && git pull && sudo sh deploy/setup.sh
```

### Backup

*Settings → Backup* downloads database and secret key as one file, encrypted with a passphrase you choose, and
restores such a file. On the command line:

Everything lives in the Docker volume `<project>_x-tools-data` (database and `secret.key`). **Back up the whole
volume.** Without the secret key stored credentials and notification tokens cannot be decrypted. Example:

```sh
sudo docker run --rm -v deploy_x-tools-data:/data -v "$PWD":/backup busybox tar czf /backup/x-tools-data.tgz -C /data .
```

(The volume name starts with the compose project name – by default the folder name `deploy`.)

## More servers (agents)

There are two kinds of agents – install one on the Proxmox host and one on every LXC/VM that runs Docker:

- **Proxmox host** – host metrics plus nodes, storage and all LXCs/VMs through the Proxmox API (read-only token).
- **Docker host** – a server, LXC or VM with Docker: containers, compose files, git status.

(Docker containers can only be seen from the machine they run on; the Proxmox API can be read from anywhere.)

*Settings → Agents → Add server* creates a one-line install command:

```sh
curl -fsSL 'https://tools.example.com/api/agent/install/<one-time token>' | sh     # as root
```

It installs the systemd service `x-tools-agent` (a single Python file, standard library only – no Docker, no pip),
read-only and without open ports. The command works once and for one hour; *Install command* on the agent creates a
new one (with a new key), e.g. to add Proxmox later. The server shows up within a minute.

Prefer Docker? `deploy/agent` contains a compose file; put `XT_AGENT_URL` and `XT_AGENT_KEY` into its `.env`.

- **Proxmox:** Datacenter → Permissions → API Tokens → *Add*; then *Add → API Token Permission* with path `/` and
  role `PVEAuditor` (read-only). The token secret only goes into the install command and stays on the Proxmox host.
- **Behind Cloudflare Access:** create a service token and add a policy with action *Service Auth* for the path
  `/api/agent/` (install script, download and reports). Enter client ID and secret when creating the agent.
- Behind any other proxy or basic auth: make sure `/api/agent/report` is reachable for the agent; it authenticates
  with its own key (`X-Agent-Key`, only a hash is stored).

## Configuration

All settings are environment variables prefixed with `XT_` in `deploy/.env` (see `deploy/.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `XT_BASE_URL` | – | Public address, used in notification links; `https://` marks cookies Secure |
| `XT_TIMEZONE` | `UTC` | Time zone for displayed times and logs |
| `XT_COMPOSE_ROOTS` | `/opt,/srv,/home` | Folders that may contain compose projects (mounted into the collector) |
| `XT_HOME_DIR` | – | Home folder shown as `~` in paths |
| `XT_HOST` / `XT_PORT` | `127.0.0.1` / `8080` | Address of the web UI |
| `XT_CHECK_HOST` | `127.0.0.1` | Host on which service ports are checked when a service has no host |
| `XT_PROTECTED_CONTAINERS` | `x-tools,x-tools-collector` | Containers that cannot be stopped from the UI |
| `XT_TRUST_PROXY` | `true` | Trust `X-Forwarded-*` headers (keep X-TOOLS on 127.0.0.1 behind the proxy) |
| `XT_COLLECT_INTERVAL` | `60` | Seconds between Docker snapshots |
| `XT_SITE_INTERVAL` | `300` | Seconds between website checks |
| `XT_SECRET_KEY` | generated | Fernet key for encrypted data (default: `secret.key` in the data volume) |
| `XT_DATA_DIR` | `/data` | Database and secret key |
| `XT_API_DOCS` | `false` | Interactive API docs at `/api/docs` |

Compose projects outside `/home`, `/opt` and `/srv`: add the folder to `XT_COMPOSE_ROOTS` **and** as a read-only
volume of the collector in `deploy/docker-compose.yml`.

## Importing from Server-Info

```sh
sudo docker run --rm -v deploy_x-tools-data:/data -v /path/to/server-info:/si:ro x-tools:local \
  python /app/migrate/import_server_info.py --source /si/data --old-env /si/.env
```

Services, customers, credentials (re-encrypted), notification settings and agents are taken over; existing agents
keep working once their URL points to X-TOOLS. Running it twice does not duplicate anything.

## Security

- Admin account protected by a one-time setup code; Argon2 password hashes, session tokens stored hashed, CSRF
  protection, login throttling, optional two-factor login.
- Roles are enforced by the API (not only hidden in the UI); every relevant action lands in the audit log.
- The web process has no Docker access; the collector only allows start/stop/restart/logs of known, unprotected
  containers and has no network.
- Compose files, Dockerfiles and logs are shown with passwords, tokens and keys masked; `.env` files are never read.
- Credentials and notification tokens are encrypted with the instance's secret key.
- Always run X-TOOLS behind HTTPS or on a private connection; an additional login in front (Cloudflare Access,
  VPN) is recommended for anything with credentials in it.

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

## License

[MIT](LICENSE)
