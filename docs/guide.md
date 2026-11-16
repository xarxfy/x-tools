# How X-TOOLS works – and what to do behind Cloudflare

A guide for people who install and run X-TOOLS. Technical details: [architecture.md](architecture.md).

- [The idea](#the-idea) · [The parts](#the-parts) · [First steps](#first-steps) · [Daily use](#daily-use)
- [Behind Cloudflare](#behind-cloudflare) · [When something does not work](#when-something-does-not-work)

## The idea

X-TOOLS is a self-hosted dashboard for the things you run: servers, Docker containers, Proxmox, websites, domains and
cron jobs. It does two things:

1. **Shows** what is where (which service on which server, which domain, which port) – the list you would otherwise
   keep in your head or in a spreadsheet.
2. **Watches** it and tells you when something breaks (Telegram or ntfy), and when it is fine again.

Optionally it also **acts**: start/stop containers, restart services, change Proxmox guests, roll out customer
websites. Everything that changes something needs the role *operator* and is written to the audit log.

## The parts

```
 your browser ──HTTPS──▶  reverse proxy / tunnel ──▶  x-tools (web UI + API, 127.0.0.1:8080)
                                                           │  shared "exchange" volume
                                                    x-tools-collector (Docker socket, no network)
 other servers:  x-tools-agent ──outbound HTTPS──▶ x-tools        (they only call out, no open ports)
 optional:       x-tools-deployer (git + docker compose, for customer websites)
```

| Part | What it does | Runs where |
|---|---|---|
| **Web UI + API** (`x-tools`) | The dashboard, database, checks, notifications | the server you installed it on |
| **Collector** (`x-tools-collector`) | Reads Docker and the compose files of *this* server; executes start/stop. No network access | same server |
| **Agent** (`x-tools-agent`) | One small service on every *other* server. Reports state, optionally takes commands. Three kinds: **Linux server** (services, ports, disks, updates), **Docker host**, **Proxmox host** (nodes, LXCs, VMs) | each other server |
| **Deployer** (`x-tools-deployer`, optional) | Clones a customer's git repository and starts it with docker compose | same server, off by default |
| **Helper** (`x-tools-ctl`) | `update`, `status`, `logs`, `setup-code`, `uninstall` | same server |

Why split like this: the web part, which people reach from the internet, never touches Docker. Only the small
collector/deployer have that power, and the collector has no network at all.

**Agents are outbound only.** An agent opens no port; it sends a report every minute and – only if you switched on
control – asks X-TOOLS for commands over the same connection. So servers behind NAT or in a home lab work without any
port forwarding, and X-TOOLS needs no access to them.

## First steps

1. **Install** ([installation.md](installation.md)): `curl -fsSL …/install.sh | sudo bash`. It prints a one-time
   **setup code**.
2. **Open X-TOOLS** and create the admin account with that code. Turn on two-factor login under *Settings → Account*.
3. **Add services** (*Services → Add*): name, ports, domains, folder. Ports are checked every minute. The
   *assistant* creates compose file, `.env` and proxy config for new services from templates.
4. **Connect more servers** (the *Add … server/host* button on the *Servers*, *Proxmox* or *Docker* page): choose the kind, copy the one-line install command and
   run it as root on that server. It is valid for one hour and works once.
5. **Turn on notifications** (*Administration → Notifications*): Telegram and/or ntfy, press *Send test*, then switch the
   main switch on. (Forgetting the main switch is the most common reason for “no message arrives”.)
6. Optional: **Customers** (*Settings → General*) for sites you host for others; **Cloudflare** (*Settings →
   Cloudflare*) to compare your domains with DNS, tunnels and Access; **Jobs** for cron jobs and backups;
   **automatic backup** (*Administration → Backup*).

## Daily use

- **Overview** – what needs attention right now, recent events, state of the server. *Pause alerts* before
  maintenance.
- **Services / Domains** – what runs where; credentials are stored encrypted (operators and admins).
- **Servers, Proxmox, Docker** – one page per kind of host, with metrics and charts of the last 30 days. Control
  buttons appear only if the agent was installed with *Allow control* and your role is operator or admin.
- **Jobs** – a cron job calls its secret address when it has run; no call, no peace.
- **Roles** – *viewer* reads, *operator* maintains and controls, *admin* manages users, agents, backups, settings.
- **Update** – `sudo x-tools-ctl update`. A hint appears in X-TOOLS when a new version exists. Back up before.

## Behind Cloudflare

Cloudflare can be in front of X-TOOLS in two ways, and they combine: a **Tunnel** (how the traffic reaches your
server) and **Access** (an extra login in front). A third use is the **API integration** (X-TOOLS reads your DNS and
tunnels).

### 1. Publish X-TOOLS with a Tunnel (no open ports)

1. Install `cloudflared` on the server (or use an existing tunnel) – Zero Trust → Networks → Tunnels.
2. *Public hostname* → `tools.example.com` → type **HTTP** → URL **`localhost:8080`**.
3. In `deploy/.env`: `XT_BASE_URL=https://tools.example.com` (cookies become *Secure*, links in notifications are
   right) and keep `XT_TRUST_PROXY=true` – then X-TOOLS reads the real visitor IP from Cloudflare's
   `CF-Connecting-IP` header for the audit log and the login throttle. Restart: `sudo sh deploy/setup.sh`.
4. SSL/TLS mode **Full** is fine; the tunnel itself is encrypted, X-TOOLS speaks plain HTTP to `cloudflared`.

With the installer choose the mode *proxy* and enter `https://tools.example.com`.

### 2. Put Cloudflare Access in front (recommended – but know what it blocks)

Access shows a login page to every request that is not logged in. That is wanted for people and **breaks every
machine** that talks to X-TOOLS. Machines have no browser: they get the HTML login page (or a 403) instead of JSON.
They must be let through:

| Who calls | Path | What to do |
|---|---|---|
| **Agents** (report, commands, install script, download) | `/api/agent/` | Access application on this **path** with action **Service Auth**, plus a *service token* (below) |
| **Cron jobs / backups** (heartbeats) | `/api/heartbeat/` | Access application on this path with action **Bypass** (the address is a secret) – or Service Auth and send the token headers with `curl` |
| **People** | everything else | normal Access policy (email, SSO …) |

Step by step for the agents:

1. Zero Trust → Access → **Service Auth** → *Create service token*. Copy **Client ID** and **Client Secret** (shown once).
2. Access → Applications → *Add an application* → *Self-hosted*: hostname `tools.example.com`, **path
   `api/agent/`**. Policy: action **Service Auth**, include the service token. (More specific paths win over the
   application for the whole hostname, so this one is evaluated first.)
3. In X-TOOLS, the *Add … server/host* button on the *Servers*, *Proxmox* or *Docker* page (or *Install command*): switch on **X-TOOLS is behind Cloudflare
   Access** and enter Client ID and Secret. The install command then carries the headers, and the agent sends them
   with every report. The secret is stored encrypted, so the next install command is pre-filled.

For heartbeats add a second application (path `api/heartbeat/`, action **Bypass**, include *Everyone*).

> The service token secret is a password. Never paste a full install command anywhere public – it contains it.
> If one leaks: Service Auth → delete/rotate the token and create a new install command.

### 3. Cloudflare settings that can get in the way

- **Bot Fight Mode / Super Bot Fight Mode / WAF rules** may challenge `curl` and Python agents (HTTP 403 or a
  JavaScript challenge). Add a *skip* rule in Security → WAF for the paths `/api/agent/` and `/api/heartbeat/`.
- **Long polling:** agents with control switched on keep a request open for up to 25 s. That is within Cloudflare's
  limits (100 s); no setting needed.
- **Caching:** nothing under `/api/` should be cached. The default (no caching of dynamic responses) is right.
- **Rate limiting rules:** an agent reports every minute and polls for commands every 25 s – do not rate-limit
  `/api/agent/` below that.

### 4. The Cloudflare integration (optional, read-only by default)

*Administration → Cloudflare*: an API token with **read** permissions (Zone, DNS, Tunnel, Access) lets the *Cloudflare* page
compare your service domains with DNS records, tunnel routes and Access applications and report mismatches
(“DNS points to a tunnel without a route”, “tunnel down”, 502/530 explained). An admin can allow changes to DNS
records and tunnel routes. Details and the exact permissions: [cloudflare.md](cloudflare.md).

### 5. Customer websites behind a Tunnel

A website deployed by X-TOOLS listens on `127.0.0.1:<port>`. Add a *Public hostname* in the same tunnel
(`customer.example.com` → `http://localhost:<port>`), put the domain into the website's service in X-TOOLS, and the
website check watches it from outside – the way visitors see it. Do **not** put Access in front of a public customer
website unless you want it private; the check would then see the login page.

## When something does not work

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent install command: `404` | Command expired (1 h), already used, or replaced by a newer one | Create a new *Install command* and run it right away |
| Install/agent gets an **HTML page** (`<!DOCTYPE html>`), `403`, or “answer was not JSON” in the agent log | Cloudflare Access (or a WAF rule) blocks `/api/agent/` | Section 2 and 3 above; check with `curl -i -H 'CF-Access-Client-Id: …' -H 'CF-Access-Client-Secret: …' https://tools.example.com/api/agent/commands` |
| Agent log: `Report failed … 403` | Service token wrong, expired, or the Access policy does not include it | New token, new install command |
| Server shows “does not report” | Agent stopped, wrong URL, or firewall blocks outbound HTTPS | On that server: `journalctl -u x-tools-agent -n 30` |
| Job turns *overdue* although it runs | The job's call is blocked (Access/WAF) or uses an old address | `curl -i <address>` from the job's machine must answer `{"ok":true,…}` |
| Login works but the audit log shows Cloudflare IPs | `XT_TRUST_PROXY=false` | Set `true` when X-TOOLS is behind Cloudflare/a proxy |
| Lost the admin password or the phone with the 2FA codes (and the recovery codes) | – | On the server: `sudo x-tools-ctl reset-admin` (several admins: add the name; `--generate` prints a random password). Another admin can also reset you under *Administration → Users* |
| Notification links point to the wrong address | `XT_BASE_URL` not set | Set it to the public `https://…` address |
| Cloudflare page: “530” / tunnel down | `cloudflared` not running or wrong service URL | `systemctl status cloudflared`, check the route points to `localhost:8080` |
| No message although a problem is shown | Main notification switch off, problem paused, or the event type switched off | *Administration → Notifications*; overview shows *paused* badges |

More: [agents.md](agents.md#troubleshooting) · [installation.md](installation.md) · the *Help* page inside X-TOOLS.
