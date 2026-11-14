# Cloudflare (read-only)

X-TOOLS can read your Cloudflare account and compare it with your services. It **never changes anything** at
Cloudflare. The *Cloudflare* entry in the sidebar appears once a token is stored.

## What you see

- **Hostnames** – per hostname the chain DNS record → tunnel → route → Access application, plus the X-TOOLS service
  that uses the domain. Problems are marked:
  - domain of a service without DNS record
  - DNS points to a tunnel that has no route for the hostname (or to a tunnel that no longer exists)
  - tunnel route exists, but DNS does not point to the tunnel
  - the route goes to a different port than the service uses
- **DNS** – records per zone, proxied or DNS only.
- **Tunnels** – status, connections, routes (for tunnels managed in the dashboard; locally configured tunnels
  cannot be read through the API).
- **Access** – applications and their domains/paths.

Unhealthy tunnels and problems with service domains also appear on the overview and can be notified
(*Settings → Notifications → Cloudflare*).

## Token

Cloudflare dashboard → My Profile → API Tokens → *Create Token* → *Custom token*, with **read** permissions:

| Scope | Permission |
|---|---|
| Zone | Zone → Read |
| Zone | DNS → Read |
| Account | Cloudflare Tunnel → Read |
| Account | Access: Apps and Policies → Read |

Resources: the account(s) and zones X-TOOLS may see. Paste the token under *Settings → Cloudflare*; it is checked,
stored encrypted and data is fetched every 10 minutes (*Refresh* fetches immediately). Missing permissions are shown
per area – the rest still works.
