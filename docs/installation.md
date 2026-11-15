# Installation

- [Requirements](#requirements)
- [Install](#install)
- [First login: the setup code](#first-login-the-setup-code)
- [Making it reachable](#making-it-reachable) – Caddy · nginx/Traefik · Cloudflare Tunnel · VPN/SSH
- [Homelab only](#homelab-only-no-vps-nothing-public)
- [Updating](#updating) · [Backup](#backup) · [Uninstall](#uninstall) · [Import from Server-Info](#import-from-server-info)

## Requirements

A Linux server (VPS, LXC or VM) with Docker and the compose plugin. About 200 MB RAM.
Docker Desktop (macOS/Windows) is not supported: X-TOOLS uses the host network for port checks.

## Install

### One command (recommended)

```sh
curl -fsSL https://raw.githubusercontent.com/xarxfy/x-tools/main/install.sh | sudo bash
```

For a private repository add a token for this run: `curl … | sudo XT_GIT_TOKEN=<token> bash` (it is never stored).

The installer:

1. installs `git`/`curl` if missing and checks **Docker** – if it is missing it offers to install it (get.docker.com),
2. clones X-TOOLS to `/opt/x-tools`,
3. asks **how you reach X-TOOLS**: *domain* (Caddy in a container fetches the HTTPS certificate; ports 80/443 must be
   free), *proxy* (your own reverse proxy or Cloudflare Tunnel; X-TOOLS listens on 127.0.0.1) or *lan* (open
   `http://<server-ip>:8080`, no proxy), plus port, time zone and whether to enable the
   [website deployer](#deploying-customer-websites-optional),
4. writes `deploy/.env`, builds and starts the containers and prints the **setup code**.

Press Enter to take the suggested answer. For unattended installs use `--yes` and variables, e.g.
`XT_MODE=lan XT_TIMEZONE=Europe/Berlin XT_DEPLOYER=no bash install.sh --yes` (all variables are listed at the top of
`install.sh`).

It also installs the helper **`x-tools-ctl`**:

| Command | What it does |
|---|---|
| `sudo x-tools-ctl update` | fetches the newest version, rebuilds and restarts (settings and data stay) |
| `sudo x-tools-ctl status` | containers, health, version |
| `sudo x-tools-ctl logs` | follows the log of the web container |
| `sudo x-tools-ctl setup-code` | shows the one-time code for the first login again |
| `sudo x-tools-ctl uninstall` | removes X-TOOLS; asks separately whether to delete the data (make a backup first) |

Running the installer again on a server that has X-TOOLS is the same as `update`. Updating a private repository needs
`XT_GIT_TOKEN` again (`sudo XT_GIT_TOKEN=… x-tools-ctl update`).

### Manual install

```sh
git clone https://github.com/xarxfy/x-tools.git
cd x-tools/deploy
cp .env.example .env      # at least XT_BASE_URL and XT_TIMEZONE – see configuration.md
sudo sh setup.sh          # builds the image, starts both containers, waits until X-TOOLS answers
```

X-TOOLS now runs on `http://127.0.0.1:8080`, reachable from the server itself only. Two containers are running:

| Container | Role | Access |
|---|---|---|
| `x-tools` | web UI + API, port/site checks, notifications | host network, listens on `127.0.0.1:8080` |
| `x-tools-collector` | reads Docker and compose files, runs start/stop/restart/logs | no network, folders read-only |

## First login: the setup code

As long as no account exists, X-TOOLS prints a one-time **setup code** to its log (`setup.sh` shows it too):

```sh
sudo docker logs x-tools
#   Setup code: ABCD-EFGH
```

The setup page asks for this code, so nobody who stumbles upon a fresh installation can claim it.

## Making it reachable

Pick one. X-TOOLS itself always stays on `127.0.0.1:8080`.

| Option | Needs | HTTPS | Open ports |
|---|---|---|---|
| [A) Caddy](#a-caddy) | own domain | automatic | 80, 443 |
| [B) nginx / Traefik](#b-nginx-or-traefik) | own domain | certbot / Traefik | 80, 443 |
| [C) Cloudflare Tunnel](#c-cloudflare-tunnel) | domain at Cloudflare | Cloudflare | none |
| [D) VPN or SSH](#d-private-only-vpn-or-ssh) | – | – (private connection) | none |

### A) Caddy

Point a DNS record (e.g. `tools.example.com`) to your server, install Caddy, add to `/etc/caddy/Caddyfile`:

```
tools.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

`sudo systemctl reload caddy`, set `XT_BASE_URL=https://tools.example.com` in `deploy/.env`, run `sudo sh setup.sh`.

### B) nginx or Traefik

Terminate HTTPS and proxy to `http://127.0.0.1:8080`, passing `X-Forwarded-For` and `X-Forwarded-Proto`:

```nginx
server {
    listen 443 ssl;
    server_name tools.example.com;
    # ssl_certificate …; ssl_certificate_key …;   (e.g. sudo certbot --nginx -d tools.example.com)
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### C) Cloudflare Tunnel

Zero Trust → Networks → Tunnels → your tunnel → *Public hostname*: `tools.example.com` → `HTTP` → `localhost:8080`.
Recommended: a Cloudflare Access application in front of it as a second login. Agents then need a service token –
see [agents.md](agents.md#behind-cloudflare-access).

### D) Private only (VPN or SSH)

Reach it through WireGuard/Tailscale, or with an SSH tunnel from your computer:

```sh
ssh -L 8080:127.0.0.1:8080 you@your-server   # then open http://localhost:8080
```

## Homelab only (no VPS, nothing public)

```
  Laptop / phone (LAN or VPN)
          │  http://192.168.1.10:8080
          ▼
  LXC/VM "tools" (Docker)            Proxmox host                 LXCs/VMs with Docker
  ├─ x-tools          ◀── reports ── x-tools-agent (Proxmox) ◀─API  x-tools-agent (Docker host)
  └─ x-tools-collector
```

1. Small Debian LXC/VM with Docker, install X-TOOLS as above.
2. In `deploy/.env`:

   ```sh
   XT_HOST=0.0.0.0                       # listen on the LAN, not only on 127.0.0.1
   XT_BASE_URL=http://192.168.1.10:8080  # the address you open; also used in agent install commands
   XT_TRUST_PROXY=false                  # no reverse proxy in front
   ```

   `sudo sh setup.sh` again, open `http://192.168.1.10:8080`, enter the setup code.
3. *Settings → Agents → Add server* for the Proxmox host and every LXC/VM with Docker ([agents.md](agents.md)).
4. Services on other machines: enter their IP under *Host*, so their ports are checked there.

From outside, use a VPN instead of opening a port. HTTPS inside the LAN: Caddy with `tls internal`. Without HTTPS the
session cookie travels unencrypted inside your network – fine for a home LAN you trust, not for shared networks.

## Deploying customer websites (optional)

With *Customers* switched on you can roll out a customer's website from a git repository: *Customers → customer →
Websites → Add website*. This needs a third container, the **deployer**. It has network access and the Docker
socket – the one place where X-TOOLS may start containers – so it is off by default.

```sh
# deploy/.env
COMPOSE_PROFILES=deploy
XT_SITES_DIR=/srv/x-tools-sites     # optional, this is the default
```

Then run `sudo sh setup.sh` again. It creates the folder and starts `x-tools-deployer`.

What happens on *Deploy*: the repository is cloned (later: updated) into `XT_SITES_DIR/<name>`, the variables you
entered are written to `.env`, and `docker compose up -d --build` starts it. Which compose file is used:

1. the one you entered, else `compose.yaml`/`compose.yml`/`docker-compose.yaml`/`docker-compose.yml` in the repository,
2. else, if you entered a **port**: a static website – a folder `public`, `dist`, `build`, `html` or `_site` with an
   `index.html` (or the repository root) is served by nginx on `127.0.0.1:<port>`.

Put your reverse proxy or Cloudflare Tunnel in front of that port (or of the port your compose file publishes) and add
the domain to the website's service – it was created automatically and is linked to the customer, so port and
website checks work as usual.

- **Private repositories:** enter an access token (a read-only deploy token is enough). It is stored encrypted and
  passed to git per job, never written into `.git/config`.
- **Variables** (`.env`) are stored encrypted and are never shown again.
- Only `https://`/`http://` repository addresses without user name are accepted.
- Deleting a website forgets it; tick *also remove containers and files* to remove those too. The service
  (with its credentials) stays.
- Operators can deploy; everything is written to the audit log. The deploy log is visible to operators only.

## Updating

```sh
cd x-tools && git pull && sudo sh deploy/setup.sh
```

Database migrations run automatically.

## Backup

**In the UI:** *Settings → Backup* downloads database and secret key as one file, encrypted with a passphrase you
choose, and restores such a file.

**On the command line:** everything lives in the volume `<project>_x-tools-data` (default project name: `deploy`):

```sh
sudo docker run --rm -v deploy_x-tools-data:/data -v "$PWD":/backup busybox tar czf /backup/x-tools-data.tgz -C /data .
```

Without the secret key stored credentials and tokens cannot be decrypted.

## Uninstall

```sh
cd x-tools/deploy
sudo docker compose down          # add -v to delete the data volumes as well
```

Agents: see [agents.md](agents.md#remove-an-agent).

## Import from Server-Info

```sh
sudo docker run --rm -v deploy_x-tools-data:/data -v /path/to/server-info:/si:ro x-tools:local \
  python /app/migrate/import_server_info.py --source /si/data --old-env /si/.env
```

Services, customers, credentials (re-encrypted), notification settings and agents are taken over; running it twice
does not duplicate anything.
