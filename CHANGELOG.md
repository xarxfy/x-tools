# Changelog

All notable changes to X-TOOLS. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow
[Semantic Versioning](https://semver.org/). Entries for the next version go under *Unreleased*.

## [Unreleased]

### Added
- **One-command installer** `install.sh` and helper `x-tools-ctl` (update, status, logs, setup-code, uninstall):
  checks/installs Docker, asks how X-TOOLS is reached (domain with Caddy and automatic HTTPS, own proxy, LAN),
  optional website deployer, unattended mode with `--yes`.

### Added
- **Linux servers** as a third agent kind (*Settings → Agents → Linux server*, new sidebar entry *Servers*): load,
  memory, disks, systemd services (failed ones raise an alert), listening ports with process, OS/kernel, pending
  updates (apt/dnf cache), reboot flag. With control: start/stop/restart services, journal, reboot. Optionally
  reports Docker too. Agent protocol version: **6** (existing agents show an update hint).
- **Deploy customer websites from git** (Customers → Websites): repository, branch, optional access token and
  `.env` variables (encrypted); compose projects or static sites (nginx). Per website: deploy, redeploy, stop, log.
  A service linked to the customer is created automatically.
- Optional third container `x-tools-deployer` (`COMPOSE_PROFILES=deploy` in `deploy/.env`), separate Docker image
  target, `XT_SITES_DIR`. The web container still has no Docker access.

## [0.1.0] – 2026-11-15 – first beta

X-TOOLS is the successor of the private tool *Server-Info*, rebuilt with a FastAPI backend and a React frontend.
Agent protocol version: **5**.

### Added

**Basics**
- Web UI (React, light and dark mode, phone layout) and JSON API (FastAPI, SQLite, automatic migrations).
- Docker deployment with two containers from one image: `x-tools` (web UI + API, host network) and
  `x-tools-collector` (Docker access, no network). `deploy/setup.sh` builds, starts and prints the setup code.
- One-time setup code for the first account, printed to the server log.
- Import of Server-Info data (services, customers, credentials re-encrypted, notifications, agents).
- Help page with all areas as an expandable tree and search; documentation in `docs/`.

**Overview and history**
- Overview of everything that needs attention, tiles, metrics of this server, recent events.
- History: problems with start and end, uptime per service (7 days), load/memory/disk charts for 30 days.

**Services**
- Services with host, ports (checked every minute, also on other machines), domains, folder, type, customer.
- Credentials per service, encrypted at rest, revealed and copied on demand.
- Assistant for new services: templates (web app, Node.js, static site, WordPress, PostgreSQL, proxy only), free port
  suggestion with conflict check, generated `docker-compose.yml`, `.env` with random passwords, Dockerfile, proxy
  and tunnel configuration (Cloudflare Tunnel, Caddy, nginx, Traefik) and a setup checklist per service.
- *Configs* for existing services (reverse proxy / tunnel snippets).
- Domains page grouped by root domain.

**Docker**
- Containers per compose project with state and health, start/stop/restart, logs (secrets masked), compose files and
  Dockerfiles (secrets masked, `.env` never read), git status, "Add as service".
- One Docker page for this server and all Docker hosts with metrics and charts.

**Agents**
- Agent kinds *Proxmox host* and *Docker host*; one-line install command (works once, one hour) that installs a
  hardened systemd service (single Python file, standard library only); Docker variant in `deploy/agent`.
- Install options are remembered (secrets stored encrypted, never sent back to the browser).
- Rename, disable, delete with uninstall command; update hint when an agent is outdated.
- Optional control (opt-in on the agent): commands by long polling, still no open ports.

**Proxmox**
- Nodes, storage, guests with filters and search; host network, Proxmox version, kernel and available updates.
- Detail page per LXC/VM: resources and disks, network cards with current IP addresses, snapshots, backups, options,
  tags and the `.conf` file (read from `/etc/pve` on the host, secrets masked).
- With control: start, shut down, stop, reboot; change cores, memory, swap, start at boot and tags; grow disks.

**Cloudflare**
- Read-only view of zones, DNS records, tunnels with routes and Access applications, checked against services
  (missing DNS records, tunnels without route, routes to the wrong port, DNS not pointing to the tunnel).
- Optional changes (admin switch): DNS records and tunnel routes, "Create route" quick fix.

**Customers** (optional area)
- Contacts, agreements, assigned services, external website checks (DNS, HTTPS, certificate) every 5 minutes.

**Notifications**
- Telegram and ntfy with delay, "back to normal" messages, event switches, test messages and a status display.

**Users and security**
- Roles viewer, operator, admin – enforced by the API; user management for admins.
- Audit log of logins, viewed credentials, container and Proxmox actions, Cloudflare changes and all settings.
- Change password, two-factor login (TOTP) with recovery codes, encrypted backups and restore in the UI.
- Argon2 password hashes, hashed session tokens, CSRF protection, login throttling.

### Fixed during the beta preparation
- Containers stopped through X-TOOLS stayed muted after being started and stopped outside of X-TOOLS.
- Inline secrets such as `ENV API_TOKEN=…` in Dockerfiles were not masked.
- Memory field of the Proxmox edit dialog blocked values that were not multiples of 256 MB.
- Cloudflare changes failed right after an update because of an outdated cached snapshot.

[Unreleased]: https://git.xcloudy.dev/mguettler/x-tools/-/compare/v0.1.0...main
[0.1.0]: https://git.xcloudy.dev/mguettler/x-tools/-/tags/v0.1.0
