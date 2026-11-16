# Beta testing checklist

Thank you for testing X-TOOLS! Pick the sections that fit your setup – nobody needs to do everything.

**Three ways to tick the boxes:**

- Open [`beta-checklist.html`](beta-checklist.html) in your browser (download it and open the file): tick items, mark problems with a note, your progress is kept; at the end copy or download the report.
- Create an issue from the template **Beta test** (GitLab: *New issue → Description → Beta test*) and tick the boxes in the issue.
- Print this page.

**Please test on a non-critical machine or with test containers** – start/stop and Proxmox changes work on real systems.

## Your setup

- X-TOOLS version (sidebar bottom) and date of `git pull`
- Where it runs: VPS / LXC / VM / bare metal, distribution, Docker version
- How you reach it: Caddy / nginx / Traefik / Cloudflare Tunnel / LAN / SSH tunnel
- Agents: Proxmox host? Docker hosts? (how many)
- Browser and devices (desktop, phone), light or dark mode

## 1. Installation and first login

- [ ] `sudo sh deploy/setup.sh` finishes with "X-TOOLS is running" and prints a setup code
- [ ] `sudo docker ps` shows `x-tools` and `x-tools-collector`
- [ ] The setup page rejects a wrong setup code
- [ ] With the right code the admin account is created and you are logged in
- [ ] Log out and in again works; a wrong password is rejected, many wrong attempts are slowed down

## 2. Reachability

- [ ] X-TOOLS is reachable the way you chose ([installation.md](installation.md#making-it-reachable))
- [ ] With HTTPS: valid certificate, you stay logged in after a reload
- [ ] Without login, `/api/services` answers `401`

## 3. Menu and navigation

- [ ] The sidebar has *Infrastructure* (Servers, Proxmox, Docker), *Manage* (Services, Domains, Customers), *Monitoring*; *Administration*, *Help* and your name at the bottom
- [ ] *Services* has a second tab *Credentials*; *Domains* has *DNS & tunnels* when the Cloudflare connection is on; *Monitoring* has Jobs, History, Maintenance
- [ ] Your name at the bottom opens *Account* (password, 2FA, language); the logout button next to it works
- [ ] On *Servers*, *Proxmox* and *Docker* an operator can add a host of that kind; on a host's page: rename, install command, disable, delete
- [ ] Old links (`/settings?tab=agents`, `/jobs`, `/credentials`, `/cloudflare`) lead to the new places

## 4. Search, notes, group actions

- [ ] `Ctrl/Cmd+K` (or `/`) opens the search; it finds a server, a service by port/domain/note, a customer, a container; Enter opens it
- [ ] A note on a server (with a `https://` link) can be saved, shows on its page and is found by the search
- [ ] *Servers → Group actions*: pick a group, review, run *Add a firewall rule* (or *Install updates*) on two test servers – each shows its own result
- [ ] *Servers → SSH keys* lists the keys with the servers and users; *Remove everywhere* works (test with a test key)
- [ ] A role without *Manage servers* sees neither *SSH keys* nor the admin actions in *Group actions*

## 5. Overview

- [ ] *Needs attention* lists real problems (or *All good*); every entry leads to the right place
- [ ] The banner shows the overall state; the counters (LXCs/VMs, containers, services, customers) are plausible
- [ ] *Servers* shows one row per server with load, memory, disk and pending updates; *Jobs · Backup* and *Websites* match the real state
- [ ] *Recent events* fills up over time

## 6. Services

- [ ] Add, edit and delete a service; search finds it
- [ ] Ports of running services are green, a wrong port turns red within a minute
- [ ] *Host* set to another machine: its ports are checked there
- [ ] After a day the uptime badge (e.g. "100 %") appears

## 7. Assistant (Services → Assistant)

- [ ] Every template can be chosen; a port already in use and a domain already in use show warnings
- [ ] Generated files can be copied and downloaded (file names make sense)
- [ ] **Deploy one generated service for real** – it starts, the Caddy/nginx/tunnel config works
- [ ] The created service has a checklist; ticking steps updates "x/y setup steps"
- [ ] *Configs* in an existing service generates proxy configs for its domain and port

## 8. Credentials

- [ ] Add logins to a service; password hidden until revealed; copy works
- [ ] Edit and delete logins; the *Credentials* page lists services with and without logins

## 9. Docker (this server)

- [ ] Without the collector having reported, *Docker* shows a hint instead of an empty page
- [ ] *This server* shows load, memory, disk; *Chart* fills after some hours
- [ ] Containers grouped by compose project with the correct state
- [ ] Stop and start a **test** container; the state updates within seconds
- [ ] Logs open, time zone correct, secrets in logs masked
- [ ] Compose files and Dockerfiles open with passwords/tokens masked (••••••); `.env` contents never appear
- [ ] `x-tools` itself is marked *protected* and cannot be stopped
- [ ] *Add as service* creates a service with folder and ports

## 10. Agents – Docker hosts

- [ ] the *Add Docker host* button on the *Docker* page: the install command runs on an LXC/VM/server
- [ ] Until the first report the server is listed as *waiting for the first report*
- [ ] The host appears on *Docker* within a minute with metrics and containers
- [ ] Running the same install command twice is rejected ("already used")
- [ ] *Install command* on an existing agent is prefilled; the old installation stops until the new command runs
- [ ] Rename, disable and enable an agent
- [ ] Delete an agent → the uninstall command is shown and removes the agent on the server
- [ ] Optional: behind Cloudflare Access with a service token ([agents.md](agents.md#behind-cloudflare-access))

## 11. Agents – Proxmox host

- [ ] Without a Proxmox agent, *Proxmox* shows a hint to set one up
- [ ] *Add server → Proxmox host* with an API token (role PVEAuditor): nodes, storage and all LXCs/VMs appear
- [ ] Node card: Proxmox version, kernel and updates are right; *Host network* lists the bridges
- [ ] Click a guest: resources, disks, network with current IPs, snapshots, backups and options are right
- [ ] The `.conf` file on the detail page matches `/etc/pve/lxc/<id>.conf` on the host (password lines masked)

## 12. Control (operator, agent with *Allow control*)

- [ ] Docker host: restart a test container and read its logs
- [ ] Proxmox (token with the XTools role from [agents.md](agents.md#proxmox-api-token)): start/shut down a **test** LXC
- [ ] Change memory and cores of a **test** LXC, grow its disk by 1 GB, change tags – new values appear shortly after
- [ ] Without the privilege a clear error is shown
- [ ] As viewer: no control buttons; an agent without control shows no buttons for anyone

## 13. Cloudflare (if you use it)

- [ ] *Administration → Cloudflare*: a token with read permissions is accepted, a wrong one rejected
- [ ] *Cloudflare* appears in the sidebar; zones, DNS records, tunnels and Access apps are correct
- [ ] *Hostnames* show the right chain (DNS → tunnel → route → Access) and the matching service
- [ ] A service port different from the tunnel route is shown as a problem (also on the overview)
- [ ] *Allow changes* (token with DNS Edit + Tunnel Edit): add a route for a test hostname, then delete it
- [ ] *Create route* on a hostname with a problem fixes it; add, edit, delete a test DNS record
- [ ] Removing the token hides the sidebar entry

## 14. One-command installer (on a fresh Debian/Ubuntu VM)

- [ ] `curl … | sudo bash` installs Docker if you agree, asks the questions and prints a setup code
- [ ] On a Proxmox host the installer refuses and says to use a separate VM/LXC
- [ ] Mode *lan*: `http://<server-ip>:8080` opens; mode *domain*: HTTPS works after DNS points to the server
- [ ] `sudo x-tools-ctl status`, `logs` and `setup-code` work
- [ ] `sudo x-tools-ctl update` keeps settings, account and data
- [ ] `sudo x-tools-ctl uninstall` asks before removing data; a reinstall afterwards still finds the data if you kept it
- [ ] `curl -fsSL …/uninstall.sh | sudo bash` does the same from outside; the second question is about the data

## 15. Customers (optional area)

- [ ] *Settings → General*: switching on shows *Customers*, switching off hides it again
- [ ] Add a customer, assign services; the customer page shows contact, sites and agreements
- [ ] Website checks show DNS/HTTPS/certificate; *Check now* updates them
- [ ] *Categories*: create A-customer/B-customer, reorder them, assign customers; filter and sorting in the list work; deleting a category keeps its customers

## 16. Linux servers (agent kind *Linux server*)

- [ ] *Add server → Linux server*: the install command works on a Debian/Ubuntu server; it appears under *Servers*
- [ ] Load, memory and disk meters, OS, kernel, pending updates and *Reboot required* are shown
- [ ] Services are listed; a deliberately failed service (`systemctl start` on a broken unit) raises a problem and a notification
- [ ] Listening ports show the process; disks show their fill level
- [ ] With *Allow control*: restart a harmless service and read its logs; `x-tools-agent` itself cannot be stopped
- [ ] Reboot (with confirmation) restarts the server and it reports again afterwards
- [ ] With *Also report Docker*, its containers appear on the Docker page
- [ ] The *Servers* page is a list; clicking a server opens its page with the tabs Overview, Services, Network, Users
- [ ] *Groups*: create, rename, reorder and delete groups; assign a server to one; the list is split into sections; deleting a group keeps the server
- [ ] *Group & tags*: add and remove free tags; clicking a tag filters the list; search finds name, group and tags
- [ ] *Pause alerts* for a group and for a tag silences the problems of its servers (they are marked as paused)
- [ ] *Install updates on N* in a group header starts the updates on its servers one after the other

## 17. Server administration (admin, agent *Allow control*, agent version 7 – use an unimportant test server)

- [ ] *Install updates* shows the log while it runs and ends with a clear result; afterwards the update count drops
- [ ] Users: the list matches `/etc/passwd`; add a test SSH key and log in with it, then remove the key again
- [ ] Create a test user, give and take *sudo*, lock the account (login stops working), unlock it, delete it
- [ ] The only sudo user cannot be locked, demoted or deleted (a clear message appears)
- [ ] Firewall: with ufw installed the rules match `ufw status numbered`; add and delete a rule for an unused port
- [ ] Turning the firewall on keeps your SSH session alive; a rule that would block SSH, or deleting the last SSH rule, is refused
- [ ] Every action appears in the audit log

## 18. Deploying customer websites (optional – needs `COMPOSE_PROFILES=deploy`)

- [ ] Without the deployer container, *Websites* shows a hint and *Deploy* says the deployer is not running
- [ ] With it: add a website with a public repository that has a compose file; *Deploy* runs, the log shows the steps
- [ ] The containers appear on the Docker page, the linked service shows the customer
- [ ] Push a change to the repository, *Redeploy*: the new commit is shown
- [ ] A repository without compose file but with `index.html` and a port is served on `127.0.0.1:<port>`
- [ ] Private repository with an access token works; the token and variables are never shown again
- [ ] *Stop* stops the containers; deleting with *also remove containers and files* removes them

## 19. Pause alerts, jobs, automatic backup, updates

- [ ] *Pause alerts* on the overview: pick a service for 30 min; its problem is marked *paused* and no message arrives
- [ ] *End now* removes the banner; a problem that is still there is reported after the delay
- [ ] *Jobs → Add job*: call the shown address with `curl`; the job is *on time*; stop calling and it turns *overdue* with a message
- [ ] `…/fail` marks the job failed and sends a message; the next successful call says *back to normal*
- [ ] *Administration → Backup → Automatic backup*: add a folder, set a passphrase, *Back up now* writes a file; an unwritable folder shows a problem
- [ ] A backup file from the folder can be restored with the passphrase (on a test instance)
- [ ] *Settings → About → Updates* shows the check result; *Check now* works

## 20. Notifications

- [ ] Telegram and/or ntfy: *Send test* arrives
- [ ] With the main switch off, a clear hint is shown and only tests are sent
- [ ] Stop a test container **outside** of X-TOOLS (`docker stop …`): a message arrives after the delay
- [ ] Start it again: a *back to normal* message arrives
- [ ] A container stopped **through X-TOOLS** is not reported; started and stopped outside again, it is
- [ ] *Monitoring checked … ago* is shown; open problems list whether they were notified

## 21. Account and security

- [ ] Change your password; other sessions are logged out
- [ ] Turn on two-factor login (QR code); login asks for the code
- [ ] A recovery code works once, then it is used up; turn two-factor login off again

## 22. Users, roles and permissions, audit log (area *Administration*, visible only with administration permissions)

- [ ] **Viewer** sees everything but changes nothing and sees no *Administration* in the sidebar; *Settings* shows only *Account*
- [ ] **Operator** edits services, customers, credentials and controls containers and servers; no users, agents, backups
- [ ] *Administration → Roles & permissions*: create a role (e.g. Support) with a few permissions, assign it to a user – exactly those things work for that user (try one allowed and one forbidden action)
- [ ] Changing a role's permissions takes effect for the user without logging in again; the built-in *Administrator* cannot be changed
- [ ] A role that is still assigned cannot be deleted; nobody can give a role or a user more permissions than their own
- [ ] The last user who can manage users cannot be disabled, deleted or demoted
- [ ] Disable a user → logged out, cannot log in; reset the password → new password works
- [ ] The audit log shows logins (also failed), viewed credentials, container/Proxmox actions, Cloudflare changes, role changes
- [ ] Old links like `/settings?tab=agents` lead to the new place under *Administration*

## 23. Backup and update

- [ ] *Administration → Backup*: download a backup with a passphrase
- [ ] Restore it (ideally on a test installation): data and credentials are back, everyone is logged out
- [ ] `git pull && sudo sh deploy/setup.sh` keeps data, users and settings

## 24. Look and feel

- [ ] Phone: menu works, no horizontal scrolling, dialogs fit on the screen
- [ ] Dark mode looks right
- [ ] Anything confusing, missing or in the way? (note it here)

---

## Reporting a problem

Open an issue (or message the maintainer) with:

```
What I did:        (steps)
What I expected:
What happened:     (error message, screenshot)
Section:           (e.g. Agents – Proxmox host)
Setup:             (see "Your setup")
Logs (if useful):  sudo docker logs --tail 50 x-tools
                   sudo docker logs --tail 50 x-tools-collector
                   journalctl -u x-tools-agent -n 50
```

**Never post passwords, tokens, agent keys or setup codes** – remove them from logs and screenshots.
