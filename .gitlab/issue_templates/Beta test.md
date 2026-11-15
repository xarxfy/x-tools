<!-- Beta test of X-TOOLS 0.1.0. Tick what works; for problems add a comment below the item or a separate issue. The full instructions: docs/beta-testing.md -->

## Your setup

- X-TOOLS version (sidebar bottom) and date of `git pull`: 
- Where it runs: VPS / LXC / VM / bare metal, distribution, Docker version: 
- How you reach it: Caddy / nginx / Traefik / Cloudflare Tunnel / LAN / SSH tunnel: 
- Agents: Proxmox host? Docker hosts? (how many): 
- Browser and devices (desktop, phone), light or dark mode: 

## 1. Installation and first login

- [ ] `sudo sh deploy/setup.sh` finishes with "X-TOOLS is running" and prints a setup code
- [ ] `sudo docker ps` shows `x-tools` and `x-tools-collector`
- [ ] The setup page rejects a wrong setup code
- [ ] With the right code the admin account is created and you are logged in
- [ ] Log out and in again works; a wrong password is rejected, many wrong attempts are slowed down

## 2. Reachability

- [ ] X-TOOLS is reachable the way you chose (docs/installation.md)
- [ ] With HTTPS: valid certificate, you stay logged in after a reload
- [ ] Without login, `/api/services` answers `401`

## 3. Overview

- [ ] *Needs attention* lists real problems (or *All good*); every entry leads to the right place
- [ ] Tiles (LXCs/VMs, containers, services, customers) show plausible numbers
- [ ] *Recent events* fills up over time

## 4. Services

- [ ] Add, edit and delete a service; search finds it
- [ ] Ports of running services are green, a wrong port turns red within a minute
- [ ] *Host* set to another machine: its ports are checked there
- [ ] After a day the uptime badge (e.g. "100 %") appears

## 5. Assistant (Services → Assistant)

- [ ] Every template can be chosen; a port already in use and a domain already in use show warnings
- [ ] Generated files can be copied and downloaded (file names make sense)
- [ ] **Deploy one generated service for real** – it starts, the Caddy/nginx/tunnel config works
- [ ] The created service has a checklist; ticking steps updates "x/y setup steps"
- [ ] *Configs* in an existing service generates proxy configs for its domain and port

## 6. Credentials

- [ ] Add logins to a service; password hidden until revealed; copy works
- [ ] Edit and delete logins; the *Credentials* page lists services with and without logins

## 7. Docker (this server)

- [ ] Without the collector having reported, *Docker* shows a hint instead of an empty page
- [ ] *This server* shows load, memory, disk; *Chart* fills after some hours
- [ ] Containers grouped by compose project with the correct state
- [ ] Stop and start a **test** container; the state updates within seconds
- [ ] Logs open, time zone correct, secrets in logs masked
- [ ] Compose files and Dockerfiles open with passwords/tokens masked (••••••); `.env` contents never appear
- [ ] `x-tools` itself is marked *protected* and cannot be stopped
- [ ] *Add as service* creates a service with folder and ports

## 8. Agents – Docker hosts

- [ ] *Settings → Agents → Add server → Docker host*: the install command runs on an LXC/VM/server
- [ ] Until the first report the server is listed as *waiting for the first report*
- [ ] The host appears on *Docker* within a minute with metrics and containers
- [ ] Running the same install command twice is rejected ("already used")
- [ ] *Install command* on an existing agent is prefilled; the old installation stops until the new command runs
- [ ] Rename, disable and enable an agent
- [ ] Delete an agent → the uninstall command is shown and removes the agent on the server
- [ ] Optional: behind Cloudflare Access with a service token (docs/agents.md)

## 9. Agents – Proxmox host

- [ ] Without a Proxmox agent, *Proxmox* shows a hint to set one up
- [ ] *Add server → Proxmox host* with an API token (role PVEAuditor): nodes, storage and all LXCs/VMs appear
- [ ] Node card: Proxmox version, kernel and updates are right; *Host network* lists the bridges
- [ ] Click a guest: resources, disks, network with current IPs, snapshots, backups and options are right
- [ ] The `.conf` file on the detail page matches `/etc/pve/lxc/<id>.conf` on the host (password lines masked)

## 10. Control (operator, agent with *Allow control*)

- [ ] Docker host: restart a test container and read its logs
- [ ] Proxmox (token with the XTools role from docs/agents.md): start/shut down a **test** LXC
- [ ] Change memory and cores of a **test** LXC, grow its disk by 1 GB, change tags – new values appear shortly after
- [ ] Without the privilege a clear error is shown
- [ ] As viewer: no control buttons; an agent without control shows no buttons for anyone

## 11. Cloudflare (if you use it)

- [ ] *Settings → Cloudflare*: a token with read permissions is accepted, a wrong one rejected
- [ ] *Cloudflare* appears in the sidebar; zones, DNS records, tunnels and Access apps are correct
- [ ] *Hostnames* show the right chain (DNS → tunnel → route → Access) and the matching service
- [ ] A service port different from the tunnel route is shown as a problem (also on the overview)
- [ ] *Allow changes* (token with DNS Edit + Tunnel Edit): add a route for a test hostname, then delete it
- [ ] *Create route* on a hostname with a problem fixes it; add, edit, delete a test DNS record
- [ ] Removing the token hides the sidebar entry

## 12. One-command installer (on a fresh Debian/Ubuntu VM)

- [ ] `curl … | sudo bash` installs Docker if you agree, asks the questions and prints a setup code
- [ ] Mode *lan*: `http://<server-ip>:8080` opens; mode *domain*: HTTPS works after DNS points to the server
- [ ] `sudo x-tools-ctl status`, `logs` and `setup-code` work
- [ ] `sudo x-tools-ctl update` keeps settings, account and data
- [ ] `sudo x-tools-ctl uninstall` asks before removing data; a reinstall afterwards still finds the data if you kept it
- [ ] `curl -fsSL …/uninstall.sh | sudo bash` does the same from outside; the second question is about the data

## 13. Customers (optional area)

- [ ] *Settings → General*: switching on shows *Customers*, switching off hides it again
- [ ] Add a customer, assign services; the customer page shows contact, sites and agreements
- [ ] Website checks show DNS/HTTPS/certificate; *Check now* updates them

## 14. Linux servers (agent kind *Linux server*)

- [ ] *Add server → Linux server*: the install command works on a Debian/Ubuntu server; it appears under *Servers*
- [ ] Load, memory and disk meters, OS, kernel, pending updates and *Reboot required* are shown
- [ ] Services are listed; a deliberately failed service (`systemctl start` on a broken unit) raises a problem and a notification
- [ ] Listening ports show the process; disks show their fill level
- [ ] With *Allow control*: restart a harmless service and read its logs; `x-tools-agent` itself cannot be stopped
- [ ] Reboot (with confirmation) restarts the server and it reports again afterwards
- [ ] With *Also report Docker*, its containers appear on the Docker page

## 15. Deploying customer websites (optional – needs `COMPOSE_PROFILES=deploy`)

- [ ] Without the deployer container, *Websites* shows a hint and *Deploy* says the deployer is not running
- [ ] With it: add a website with a public repository that has a compose file; *Deploy* runs, the log shows the steps
- [ ] The containers appear on the Docker page, the linked service shows the customer
- [ ] Push a change to the repository, *Redeploy*: the new commit is shown
- [ ] A repository without compose file but with `index.html` and a port is served on `127.0.0.1:<port>`
- [ ] Private repository with an access token works; the token and variables are never shown again
- [ ] *Stop* stops the containers; deleting with *also remove containers and files* removes them

## 16. Pause alerts, jobs, automatic backup, updates

- [ ] *Pause alerts* on the overview: pick a service for 30 min; its problem is marked *paused* and no message arrives
- [ ] *End now* removes the banner; a problem that is still there is reported after the delay
- [ ] *Jobs → Add job*: call the shown address with `curl`; the job is *on time*; stop calling and it turns *overdue* with a message
- [ ] `…/fail` marks the job failed and sends a message; the next successful call says *back to normal*
- [ ] *Settings → Backup → Automatic backup*: add a folder, set a passphrase, *Back up now* writes a file; an unwritable folder shows a problem
- [ ] A backup file from the folder can be restored with the passphrase (on a test instance)
- [ ] *Settings → About → Updates* shows the check result; *Check now* works

## 17. Notifications

- [ ] Telegram and/or ntfy: *Send test* arrives
- [ ] With the main switch off, a clear hint is shown and only tests are sent
- [ ] Stop a test container **outside** of X-TOOLS (`docker stop …`): a message arrives after the delay
- [ ] Start it again: a *back to normal* message arrives
- [ ] A container stopped **through X-TOOLS** is not reported; started and stopped outside again, it is
- [ ] *Monitoring checked … ago* is shown; open problems list whether they were notified

## 18. Account and security

- [ ] Change your password; other sessions are logged out
- [ ] Turn on two-factor login (QR code); login asks for the code
- [ ] A recovery code works once, then it is used up; turn two-factor login off again

## 19. Users, roles, audit log

- [ ] **Viewer**: sees everything, no credentials, no container/Proxmox actions, no logs, only *Account* in settings
- [ ] **Operator**: edits services and credentials, controls containers and guests; no users, agents, backups
- [ ] Disable a user → logged out, cannot log in; reset the password → new password works
- [ ] The audit log shows logins (also failed), viewed credentials, container/Proxmox actions, Cloudflare changes

## 20. Backup and update

- [ ] *Settings → Backup*: download a backup with a passphrase
- [ ] Restore it (ideally on a test installation): data and credentials are back, everyone is logged out
- [ ] `git pull && sudo sh deploy/setup.sh` keeps data, users and settings

## 21. Look and feel

- [ ] Phone: menu works, no horizontal scrolling, dialogs fit on the screen
- [ ] Dark mode looks right
- [ ] Anything confusing, missing or in the way? (note it here)

## Notes

(anything else – confusing, missing, in the way)

/label ~beta
