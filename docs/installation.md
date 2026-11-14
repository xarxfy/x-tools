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

```sh
git clone <repository> x-tools
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
