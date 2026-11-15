# Security policy

X-TOOLS manages credentials and can control Docker, Proxmox and servers, so security reports are welcome.

**Note:** X-TOOLS is entirely “vibe coded” (written with an AI assistant) and has had **no independent security
audit**. Treat it accordingly: keep backups, put it behind HTTPS and an additional login (VPN, Cloudflare Access), and
give agents and the website deployer control only over systems you can afford to lose.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
*Security → Report a vulnerability* in the repository ([github.com/xarxfy/x-tools/security/advisories/new](https://github.com/xarxfy/x-tools/security/advisories/new)).

Helpful in a report: affected version (`Settings → About`), what you can do with it, steps to reproduce.
This is a one-person hobby project: expect an answer within a few days, not hours.

## Supported versions

Only the latest release gets fixes (currently the 0.1 beta line).

## What is in scope

Authentication and sessions, roles (a viewer or operator doing more than allowed), the agent protocol, the
install-command flow, encrypted storage (credentials, backups), the collector/deployer separation, the installer.

Out of scope: problems that need root on the server already, missing HTTPS when you chose to run without it,
Cloudflare/proxy misconfiguration, denial of service by someone who already has an account.

How the protection is built: [docs/architecture.md](docs/architecture.md#security).
