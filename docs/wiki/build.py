#!/usr/bin/env python3
"""Builds the GitHub wiki from the files in docs/ (single source of truth – never edit the wiki by hand).

  python3 docs/wiki/build.py [output-folder]       default: build/wiki
  sh docs/wiki/publish.sh                          build + push to the wiki repository

Page names: see PAGES. Links between the documents are rewritten to wiki links, links to files in the repository
(README, CHANGELOG, LICENSE, …) to their GitHub address.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/xarxfy/x-tools"
BLOB = f"{REPO}/blob/main/"

# source file (relative to the repository) → wiki page name
PAGES = {
    "docs/guide.md": "How-it-works-and-Cloudflare",
    "docs/installation.md": "Installation",
    "docs/agents.md": "Agents",
    "docs/cloudflare.md": "Cloudflare-integration",
    "docs/configuration.md": "Configuration",
    "docs/architecture.md": "Architecture-and-security",
    "docs/development.md": "Development",
    "docs/beta-testing.md": "Beta-testing",
    "CHANGELOG.md": "Changelog",
}
NOTICE = ("> **X-TOOLS is entirely “vibe coded”** – written with an AI assistant, with tests but without an "
          "independent security audit. Keep backups and be careful what you give it control over.\n")
HOME = f"""# X-TOOLS

Self-hosted overview of your servers, services and Docker containers – at home or on a VPS – with alerts when
something breaks.

{NOTICE}
**Install in one command**

```sh
curl -fsSL https://raw.githubusercontent.com/xarxfy/x-tools/main/install.sh | sudo bash
```

then `sudo x-tools-ctl update | status | logs | setup-code | uninstall`.
Remove it again: `curl -fsSL https://raw.githubusercontent.com/xarxfy/x-tools/main/uninstall.sh | sudo bash`

## Where to start

| I want to … | Read |
|---|---|
| understand what the parts are and how they work together | [How it works and Cloudflare](How-it-works-and-Cloudflare) |
| install it (domain, own proxy, LAN, homelab) | [Installation](Installation) |
| use it behind **Cloudflare** (Tunnel, Access, WAF) | [How it works and Cloudflare](How-it-works-and-Cloudflare#behind-cloudflare) |
| connect more servers (Linux, Docker, Proxmox) | [Agents](Agents) |
| compare my domains with DNS and tunnels | [Cloudflare integration](Cloudflare-integration) |
| change settings (`XT_*` variables) | [Configuration](Configuration) |
| know how it is built and how data is protected | [Architecture and security](Architecture-and-security) |
| test the beta | [Beta testing](Beta-testing) |
| see what changed | [Changelog](Changelog) |
| hack on it | [Development](Development) |

## What you get

Overview with problems and history · Services, domains and encrypted credentials · Docker and Proxmox pages ·
Linux servers (services, ports, disks, updates) · Agents (outbound only, optional control) · Cloudflare check ·
Customers with website checks and deploy from git · Jobs (heartbeats) · Notifications (Telegram, ntfy) ·
Pause alerts · Users, roles, 2FA, audit log · Encrypted, automatic backups.

Source code, issues and license: [{REPO}]({REPO}) (MIT).

_This wiki is generated from the `docs/` folder of the repository. Please change the files there, not the wiki._
"""
SIDEBAR = """**[X-TOOLS](Home)**

- [How it works and Cloudflare](How-it-works-and-Cloudflare)
- [Installation](Installation)
- [Agents](Agents)
- [Cloudflare integration](Cloudflare-integration)
- [Configuration](Configuration)
- [Architecture and security](Architecture-and-security)
- [Beta testing](Beta-testing)
- [Changelog](Changelog)
- [Development](Development)

[Repository]({repo}) · [Issues]({repo}/issues)
""".replace("{repo}", REPO)

LINK = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)\s]+)\)")


def rewrite(text: str, source: str) -> str:
    base = Path(source).parent

    def fix(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if re.match(r"^(https?:|mailto:|#)", target):
            return match.group(0)
        path, _, anchor = target.partition("#")
        resolved = (ROOT / base / path).resolve()
        try:
            rel = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            return match.group(0)
        if rel in PAGES:
            return f"[{label}]({PAGES[rel]}{'#' + anchor if anchor else ''})"
        kind = "tree" if resolved.is_dir() else "blob"
        return f"[{label}]({REPO}/{kind}/main/{rel}{'#' + anchor if anchor else ''})"
    return LINK.sub(fix, text)


def build(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    (out / "Home.md").write_text(HOME, encoding="utf-8")
    (out / "_Sidebar.md").write_text(SIDEBAR, encoding="utf-8")
    (out / "_Footer.md").write_text(f"{NOTICE}", encoding="utf-8")
    for source, name in PAGES.items():
        text = (ROOT / source).read_text(encoding="utf-8")
        (out / f"{name}.md").write_text(rewrite(text, source), encoding="utf-8")
    return sorted(p.name for p in out.glob("*.md"))


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "wiki"
    print("\n".join(build(target)))
