# Architecture & security

```
                 HTTPS                    HTTP (localhost)
  Browser  ───────────────▶  Reverse proxy  ───────────────▶  x-tools            ── SQLite + secret key
                             (Caddy, nginx,                   web UI + API          (volume "data")
                              Traefik, Cloudflare             port/site checks,
                              Tunnel …)                       alerts, Cloudflare
                                                                  │
                                                                  │ files only (volume "exchange")
                                                                  ▼
                                                              x-tools-collector  ── Docker socket,
                                                              no network            compose folders (read-only)

  Other servers:  x-tools-agent  ── HTTPS: report every minute, poll for commands (if control is on) ──▶  x-tools
```

- **One image, three roles:** `x-tools serve` (web UI + API), `x-tools collect` (Docker collector) and
  `x-tools agent` (reports another server; installed as a single Python file).
- **The web container never touches Docker.** Container actions are small command files in the shared `exchange`
  volume; the collector validates them (known container, not protected, only start/stop/restart/logs) and runs them.
  The collector has no network and never sees the database or the secret key.
- The web container uses the **host network** so it can check whether the ports of your services answer.
- Backend: Python, FastAPI, SQLAlchemy, SQLite with Alembic migrations. Frontend: React, TypeScript, Vite.

## Security

- First account protected by a one-time setup code (server log). Argon2 password hashes, session tokens stored
  hashed, CSRF protection, login throttling, optional two-factor login (TOTP) with recovery codes.
- Roles (viewer, operator, admin) are enforced by the API, not only hidden in the UI. Logins, viewed and changed
  credentials, container actions and all changes land in the audit log (user, IP, one year).
- Credentials, notification tokens, the Cloudflare token and the Proxmox/Cloudflare tokens of agent install commands
  are encrypted with the instance's secret key; secrets are never sent back to the browser after saving. Backups
  from the UI are encrypted with a passphrase (scrypt + Fernet).
- Compose files, Dockerfiles and logs are shown with passwords, tokens and keys masked; `.env` files are never read.
- Agents authenticate with their own key (only a hash is stored) and open no ports. Control (start/stop) is opt-in on
  the agent itself; the agent fetches commands by long polling and only runs a fixed list of actions. Agent install
  commands work once and for one hour.
- Cloudflare is read-only unless an admin allows changes; changes are limited to DNS records and tunnel routes.
- Run X-TOOLS behind HTTPS or on a private connection. An additional login in front (Cloudflare Access, VPN) is
  recommended for anything with credentials in it.
