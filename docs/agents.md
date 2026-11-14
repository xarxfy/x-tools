# Agents – more servers

An agent reports another machine to X-TOOLS every minute – **outbound HTTPS only**, no open ports. By default it
only reports; with **control** switched on, operators can also start/stop containers and Proxmox guests
([Control](#control)).

| Kind | Install it on | Reports |
|---|---|---|
| **Proxmox host** | the Proxmox host | host metrics, nodes, storage, all LXCs and VMs (Proxmox API, read-only token) |
| **Docker host** | every server, LXC or VM that runs Docker | containers, compose files, Dockerfiles, git status, host metrics |

Docker containers are only visible to an agent on the same machine; the Proxmox API can be read from anywhere.

## Add a server

1. *Settings → Agents → Add server*, choose the kind, for a Proxmox host enter the API token.
2. Run the shown command **as root** on that server (Proxmox: in the host shell; elsewhere `| sudo sh`):

   ```sh
   curl -fsSL 'https://tools.example.com/api/agent/install/<one-time token>' | sh
   ```

3. The server appears on the *Proxmox* or *Docker* page within a minute (until then it is listed there as
   "waiting for the first report").

The command works **once and for one hour**. It installs the systemd service `x-tools-agent`: one Python file
(standard library only, Python 3.10+), read-only file system access, no open ports. *Install command* on an existing
agent creates a new command with a new key – e.g. to reinstall, switch the kind or add Proxmox later.

**Prefer Docker?** `deploy/agent` contains a compose file; put `XT_AGENT_URL` and `XT_AGENT_KEY` into its `.env`.

## Control

Switch on **Allow control from X-TOOLS** when adding the server (or with a new *Install command*). Then users with the
role **operator** or **admin** can:

| Docker host | Proxmox host |
|---|---|
| start, stop, restart containers, read their logs | start, shut down, stop, reboot LXCs and VMs; change CPU cores, memory, swap, start at boot and tags; grow disks |

How it stays safe:

- The agent still opens no port: it asks X-TOOLS for commands (long polling over the same HTTPS connection it reports
  on) and sends the result back.
- It only accepts this fixed list of actions, only for containers/guests it reported itself, and only when control
  was switched on **on that server** (`XT_AGENT_CONTROL=1` in `/etc/x-tools-agent/agent.env`) – X-TOOLS alone cannot
  turn it on.
- Commands expire after a minute; every action is in the audit log with user and result.
- For Proxmox the API token needs `VM.PowerMgmt` (see below); without it the actions fail with a hint.

To switch control off again: *Install command* without the switch, or set `XT_AGENT_CONTROL=0` and
`systemctl restart x-tools-agent`.

## Proxmox details

Every 10 minutes (and right after a change) a Proxmox agent also reads, per LXC/VM: resources and disks, network
cards (bridge, VLAN, MAC, configured and **current** IP addresses – for VMs via the QEMU guest agent), snapshots,
backups on backup storages, OS, start at boot, features, tags and the guest's `.conf` file (read from `/etc/pve` when the agent runs on the host, otherwise rebuilt from the API; password and SSH key lines masked). Per node: Proxmox version, kernel, available
updates and the host network (bridges, bonds, VLANs). Click a guest on the *Proxmox* page to see its detail page.

Interval: `XT_PROXMOX_DETAILS_INTERVAL` (seconds, default 600, minimum 120) in `/etc/x-tools-agent/agent.env`.

## Proxmox API token

1. Datacenter → Permissions → API Tokens → *Add*: user e.g. `root@pam`, token ID `xtools`, *Privilege Separation* on.
2. Permissions → *Add → API Token Permission*: path `/`, token `root@pam!xtools`, role **PVEAuditor** (read-only).
   For [control](#control) create a role with exactly what X-TOOLS needs and give it to the token instead:

   ```sh
   pveum role add XTools -privs "VM.Audit VM.PowerMgmt VM.Config.CPU VM.Config.Memory VM.Config.Options VM.Config.Disk Datastore.Audit Datastore.AllocateSpace Sys.Audit"
   pveum acl modify / --tokens 'root@pam!xtools' --roles XTools
   ```

   | Privilege | Needed for |
   |---|---|
   | `VM.Audit`, `Datastore.Audit`, `Sys.Audit` | reading guests, snapshots, backups, node status and network |
   | `VM.PowerMgmt` | start, shut down, stop, reboot |
   | `VM.Config.CPU`, `VM.Config.Memory`, `VM.Config.Options` | cores, memory/swap, start at boot, tags |
   | `VM.Config.Disk`, `Datastore.AllocateSpace` | growing disks |

   Available updates are read through the API if the token may (`Sys.Modify`), otherwise – when the agent runs on
   the host itself – from the local apt lists.
3. Enter token ID (`root@pam!xtools`) and secret when adding the server. URL from the Proxmox host itself:
   `https://127.0.0.1:8006`.

Token and secret are stored encrypted with the instance key, so *Install command* on the same agent is filled in
(the secret is never shown again – leave the field empty to keep it, enter a new one to replace it).

## Behind Cloudflare Access

If X-TOOLS is protected by Cloudflare Access, the agent needs a **service token**:

1. Zero Trust → Access → Service Auth → *Create service token*.
2. Access → Applications → *Add* (self-hosted): hostname of X-TOOLS, **path `api/agent/`**, policy action
   **Service Auth**, include the service token.
3. Switch on *X-TOOLS is behind Cloudflare Access* when adding the server and enter client ID and secret.

A `403` or "answer was not JSON (login page?)" in the agent log means the token or the path rule does not match.

## Remove an agent

Delete it under *Settings → Agents* – X-TOOLS shows the uninstall command. Run it as root on that server:

```sh
systemctl disable --now x-tools-agent 2>/dev/null; rm -rf /opt/x-tools-agent /etc/x-tools-agent /etc/systemd/system/x-tools-agent.service; systemctl daemon-reload 2>/dev/null; docker rm -f x-tools-agent 2>/dev/null
```

## Troubleshooting

```sh
systemctl status x-tools-agent
journalctl -u x-tools-agent -n 50
```

| Message | Meaning |
|---|---|
| `HTTP 401 … Unknown agent key` | the agent was deleted or got a new key – run a new install command |
| `HTTP 403 … Agent is disabled` | enable it under *Settings → Agents* |
| `HTTP 403` / not JSON | Cloudflare Access (or another proxy) blocks `/api/agent/` |
| `Proxmox API: HTTP 401` | token ID/secret wrong or the token has no permission (role PVEAuditor on `/`) |
| `… needs the privilege …` | control is on, but the token lacks that privilege – use the XTools role above |
| `The agent did not answer` (in X-TOOLS) | agent not running, too old (needs v3) or control off on the server |
