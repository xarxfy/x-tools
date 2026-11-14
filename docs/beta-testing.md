# Beta testing checklist

Thank you for testing X-TOOLS! Work through the sections that fit your setup – nobody needs to do everything.
Tick a box when it works; for anything else, write a short report (template at the end).

**Please test on a non-critical machine or with test containers.** Start/stop works on real containers.

## 0. Your setup (please note in every report)

- X-TOOLS version (sidebar bottom, e.g. `v0.1.0`) and date of `git pull`
- Where it runs: VPS / LXC / VM / bare metal, distribution, Docker version
- How you reach it: Caddy / nginx / Traefik / Cloudflare Tunnel / LAN only / SSH tunnel
- Browser and device (desktop, phone), light or dark mode

## 1. Installation and first login

- [ ] `sudo sh deploy/setup.sh` finishes with "X-TOOLS is running" and prints a setup code
- [ ] Both containers run: `sudo docker ps` shows `x-tools` and `x-tools-collector`
- [ ] The setup page rejects a wrong setup code
- [ ] With the right code the admin account is created and you are logged in
- [ ] Log out and in again works; a wrong password is rejected, many wrong attempts are slowed down

## 2. Reachability

- [ ] X-TOOLS is reachable the way you chose ([installation.md](installation.md#making-it-reachable))
- [ ] With HTTPS: the browser shows a valid certificate, you stay logged in after a reload
- [ ] Without login, `https://<your-address>/api/services` answers `401`

## 3. Overview

- [ ] "Needs attention" lists real problems (or "All good"); every entry links to the right page
- [ ] Tiles (servers, containers, services) show plausible numbers
- [ ] "Recent events" fills up over time

## 4. Services

- [ ] Add, edit and delete a service; search finds it
- [ ] Ports of running services are green, a wrong port turns red within a minute
- [ ] *Host* set to another machine (e.g. an LXC IP): its ports are checked there
- [ ] After a day: the uptime badge (e.g. "100 %") appears

## 5. Assistant (Services → Assistant)

- [ ] Every template can be chosen; a port already in use shows a warning
- [ ] A domain that another service uses shows a warning
- [ ] Generated files can be copied and downloaded (file names make sense)
- [ ] **Deploy one generated service for real** (e.g. static website or WordPress) – does it start? Does the
      generated Caddy/nginx/tunnel config work?
- [ ] The created service has a checklist; ticking steps updates "x/y setup steps"
- [ ] *Configs* in an existing service generates proxy configs for its domain and port

## 6. Credentials

- [ ] Add logins to a service; password hidden until the eye is clicked; copy works
- [ ] Edit and delete logins
- [ ] The *Credentials* page lists services with and without logins

## 7. Servers and Docker (this server)

- [ ] *Servers → This server* shows load, memory, disk; the chart fills after some hours
- [ ] *Docker*: containers grouped by compose project, correct state
- [ ] Stop and start a **test** container; the state updates within seconds
- [ ] Logs open, time zone correct, secrets in logs masked
- [ ] Compose files and Dockerfiles open; passwords/tokens are masked (••••••); `.env` contents never appear
- [ ] `x-tools` itself is marked "protected" and cannot be stopped
- [ ] "Add as service" creates a service with folder and ports

## 8. Agents

- [ ] *Settings → Agents → Add server → Docker host*: the install command runs on an LXC/VM/server
- [ ] The server appears within a minute; *Docker* in the sidebar shows its containers (read-only)
- [ ] *Add server → Proxmox host* with an API token (role PVEAuditor): nodes, storage and all LXCs/VMs appear;
      *Proxmox* appears in the sidebar
- [ ] Running the same install command twice is rejected ("already used")
- [ ] *Install command* on an existing agent: the old installation stops reporting until the new command runs
- [ ] Disable an agent → no more data; enable again
- [ ] Delete an agent → the uninstall command is shown and removes the agent on the server
- [ ] Optional: behind Cloudflare Access with a service token ([agents.md](agents.md#behind-cloudflare-access))
- [ ] With **Allow control**: as operator restart a test container on a Docker host and read its logs
- [ ] With **Allow control** on a Proxmox host (token with PVEVMUser): start/shut down a **test** LXC; without the
      privilege a clear error is shown
- [ ] As viewer: no control buttons; an agent without control shows no buttons for anyone

## 9. Cloudflare (if you use it)

- [ ] *Settings → Cloudflare*: a token with read permissions is accepted, a wrong token is rejected
- [ ] *Cloudflare* appears in the sidebar; zones, DNS records, tunnels and Access apps are correct
- [ ] Hostnames show the right chain (DNS → tunnel → route → Access) and the matching service
- [ ] Deliberately set a service port different from the tunnel route → a problem is shown (and on the overview)
- [ ] *Allow changes* (token with DNS Edit + Tunnel Edit): add a tunnel route for a test hostname – route and DNS
      record appear in Cloudflare; delete it again
- [ ] *Create route* on a hostname with a problem fixes it
- [ ] Add, edit, delete a test DNS record; all changes are in the audit log
- [ ] Removing the token hides the sidebar entry

## 10. Customers (optional area)

- [ ] *Settings → General*: switching on shows *Customers* in the sidebar, switching off hides it again
- [ ] Add a customer, assign services; the customer page shows contact, sites and agreements
- [ ] Website checks show DNS/HTTPS/certificate; "Check now" updates them

## 11. Notifications

- [ ] Telegram and/or ntfy: "Send test" arrives
- [ ] Stop a test container **outside** of X-TOOLS (`docker stop …`): a message arrives after the delay
- [ ] Start it again: a "back to normal" message arrives
- [ ] A container stopped **through X-TOOLS** is not reported

## 12. Account and security

- [ ] Change your password; other sessions are logged out
- [ ] Turn on two-factor login (QR code with your authenticator app); login asks for the code
- [ ] A recovery code works once; then it is used up
- [ ] Turn two-factor login off again

## 13. Users, roles, audit log

- [ ] Create a **viewer**: sees services, servers, Docker; no credentials, no start/stop, no logs, only *Account* in
      the settings
- [ ] Create an **operator**: can edit services and credentials, start/stop containers; no users, agents, backups
- [ ] Disable a user → they are logged out and cannot log in; reset their password → new password works
- [ ] The audit log shows logins (also failed ones), viewed credentials, container actions and changes – with user
      and IP; filters work

## 14. Backup and update

- [ ] *Settings → Backup*: download a backup with a passphrase
- [ ] Restore it (ideally on a second test installation): data and credentials are back, everyone is logged out
- [ ] `git pull && sudo sh deploy/setup.sh`: data, users and settings are kept

## 15. Look and feel

- [ ] Phone: menu works, no horizontal scrolling, dialogs fit on the screen
- [ ] Dark mode looks right
- [ ] Anything confusing, missing or in the way? Every opinion helps.

---

## Reporting a problem

Please send (issue in the repository or message to the maintainer):

```
What I did:        (steps)
What I expected:
What happened:     (error message, screenshot)
Section:           (e.g. 8. Agents)
Setup:             (see section 0)
Logs (if useful):  sudo docker logs --tail 50 x-tools
                   sudo docker logs --tail 50 x-tools-collector
                   journalctl -u x-tools-agent -n 50
```

**Never post passwords, tokens, agent keys or setup codes** – remove them from logs and screenshots.
