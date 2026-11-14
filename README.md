# X-TOOLS

Self-hosted overview of your servers, services and Docker containers – at home or on a VPS – with alerts when
something breaks.

> **Status: beta (0.1).** All areas are in place; expect rough edges until 1.0.
> Beta testers: see the [checklist](docs/beta-testing.md).

## Features

| Area | What you get |
|---|---|
| **Overview** | Everything that needs attention on one page, recent events, the state of this server |
| **Services** | What runs where: host, ports (checked every minute), domains, folder, uptime; credentials encrypted |
| **Assistant** | New services from templates – compose file, `.env`, proxy/tunnel config and a setup checklist |
| **Servers & Docker** | Containers per compose project, start/stop/restart, logs, compose files (secrets masked), charts |
| **Agents** | More servers: Proxmox hosts (nodes, LXCs, VMs) and Docker hosts – one install command, outbound only, optional control (start/stop) |
| **Cloudflare** | DNS, tunnels, routes and Access apps, checked against your services; optionally edit DNS records and tunnel routes |
| **Customers** | Optional: contacts, agreements and external website checks for sites you host for others |
| **Notifications** | Telegram and ntfy, with delay and "back to normal" |
| **Users** | Roles (viewer, operator, admin), two-factor login, audit log, encrypted backups |

## Quick start

Requirements: Linux with Docker and the compose plugin.

```sh
git clone <repository> x-tools
cd x-tools/deploy
cp .env.example .env      # set XT_BASE_URL and XT_TIMEZONE
sudo sh setup.sh          # builds and starts X-TOOLS, prints the setup code
```

X-TOOLS listens on `127.0.0.1:8080`. Make it reachable, open it and enter the setup code from the log
(`sudo docker logs x-tools`).

| Your situation | How |
|---|---|
| VPS with own domain | Caddy or nginx in front → [installation.md](docs/installation.md#making-it-reachable) |
| Domain at Cloudflare, no open ports | Cloudflare Tunnel → [installation.md](docs/installation.md#c-cloudflare-tunnel) |
| Only at home, nothing public | LAN mode, agents on Proxmox and LXCs → [installation.md](docs/installation.md#homelab-only-no-vps-nothing-public) |
| Just for me, no proxy | SSH tunnel or VPN → [installation.md](docs/installation.md#d-private-only-vpn-or-ssh) |

Update: `git pull && sudo sh deploy/setup.sh` · Backup: *Settings → Backup*

## Documentation

- [Installation](docs/installation.md) – install, reachability options, homelab, update, backup, uninstall
- [Agents](docs/agents.md) – Proxmox and Docker hosts, Proxmox token, Cloudflare Access, troubleshooting
- [Cloudflare](docs/cloudflare.md) – token permissions and what is checked
- [Configuration](docs/configuration.md) – all `XT_*` variables
- [Architecture & security](docs/architecture.md) – how the pieces fit and how data is protected
- [Development](docs/development.md)
- [Beta testing checklist](docs/beta-testing.md)

The *Help* page inside X-TOOLS explains every area as well.

## Security in short

- The web UI never accesses Docker; a separate collector without network does, and only start/stop/restart/logs.
- Credentials and tokens are encrypted; passwords in compose files and logs are masked; `.env` files are never read.
- Setup code for the first account, two-factor login, roles enforced by the API, audit log.
- Agents open no ports; controlling them is opt-in on the agent and limited to start/stop/restart/logs.

Details: [architecture.md](docs/architecture.md#security)

## License

[MIT](LICENSE)
