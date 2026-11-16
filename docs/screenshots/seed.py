#!/usr/bin/env python3
"""Fills a fresh X-TOOLS instance with demo data for screenshots (not for production!).

Usage (development only):
  XT_DATA_DIR=/tmp/demo/data XT_EXCHANGE_DIR=/tmp/demo/exchange XT_MONITOR=false XT_PORT=18200 x-tools serve &
  python3 docs/screenshots/seed.py <setup code> /tmp/demo
"""

import http.cookiejar
import json
import math
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "http://127.0.0.1:18200"
CODE, DEMO = sys.argv[1], Path(sys.argv[2])
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
random.seed(7)


def call(path, body=None, method=None, headers=None):
    csrf = next((c.value for c in cj if c.name == "xt_csrf"), "")
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", "X-CSRF-Token": csrf, **(headers or {})})
    with opener.open(req) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


GB = 1024 ** 3
NOW = time.time()

# --- listeners so that port checks are green ---------------------------------------------
pids = []
for port in (18301, 18302, 18303, 18304, 18305):
    pids.append(subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd="/tmp").pid)
(DEMO / "listeners.pids").write_text("\n".join(map(str, pids)))

call("/api/setup", {"username": "admin", "password": "correct horse battery", "code": CODE})
call("/api/features", {"customers": True}, method="PUT")

# --- services and customers ---------------------------------------------------------------
def service(name, ports, domains=(), folder="", typ="Docker Compose"):
    return call("/api/services", {"name": name, "ports": [{"port": p, "label": l} for p, l in ports],
                                  "domains": list(domains), "folder": folder, "type": typ})["id"]

shop = service("ACME web shop", [(18301, "Web")], ["shop.acme-example.com"], "/home/marc/sites/acme-shop")
blog = service("ACME blog", [(18302, "Web")], ["blog.acme-example.com"], "/home/marc/sites/acme-blog")
bakery = service("Bakery Smith website", [(18303, "Web")], ["smith-bakery.example"], "/home/marc/sites/smith-bakery")
cloud = service("Nextcloud", [(18304, "Web")], ["cloud.example.com"], "/home/marc/apps/nextcloud")
git = service("Gitea", [(18305, "Web")], ["git.example.com"], "/home/marc/apps/gitea")
mail = service("Mail relay", [(18399, "SMTP")], [], "/home/marc/apps/mail", "Docker Compose")
call("/api/services", {"name": "Grafana", "ports": [{"port": 18305, "label": "Web"}], "domains": ["grafana.example.com"]})
cat_a = call("/api/customer-categories", {"name": "A-customer"})["id"]
cat_b = call("/api/customer-categories", {"name": "B-customer"})["id"]
import datetime as _dt
_today = _dt.date.today()
acme = call("/api/customers", {
    "name": "ACME Shop GmbH", "agreements": "Hosting incl. updates, 99.5 % availability, monthly invoice",
    "category_id": cat_a, "service_ids": [shop, blog], "tags": ["Hosting", "Shop"],
    "links": [{"title": "Contract (PDF)", "url": "https://files.example.org/acme/contract.pdf"},
              {"title": "Documentation", "url": "https://wiki.example.org/acme"}],
    "contacts": [{"name": "Anna Meyer", "role": "Technical", "email": "anna@acme-example.com", "phone": "+49 30 1234567"},
                 {"name": "Jonas Weber", "role": "Billing", "email": "billing@acme-example.com", "phone": ""}],
    "contract": {"contract_end": (_today + _dt.timedelta(days=75)).isoformat(), "notice_days": 30,
                 "support_hours": "Mon-Fri 9-17", "response_time": "4 hours"}})
_t1 = call(f"/api/customers/{acme['id']}/tickets", {"title": "Renew the shop certificate", "priority": "high", "status": "progress",
                                                   "due": (_today + _dt.timedelta(days=5)).isoformat(), "description": "Certificate of shop.acme-example.com expires soon."})
call(f"/api/tickets/{_t1['id']}/comments", {"text": "Checked with the customer: renewal via Cloudflare is fine."})
call(f"/api/customers/{acme['id']}/tickets", {"title": "Agree on a maintenance window", "priority": "normal"})
call(f"/api/customers/{acme['id']}/tickets", {"title": "Staging site returns 502", "priority": "urgent"})
call(f"/api/customers/{acme['id']}/journal", {"text": "Phone call with Anna: shop moves to the new server in January."})
call("/api/customers", {"name": "Bakery Smith", "category_id": cat_b, "service_ids": [bakery],
                        "contacts": [{"name": "Tom Smith", "role": "", "email": "tom@smith-bakery.example", "phone": ""}]})

from app.core.db import session_scope  # noqa: E402  (after the server wrote the database)
from app.models import Agent, Customer, Event, Heartbeat, Metric  # noqa: E402
from app.monitor import sites, state  # noqa: E402

state.save(sites.KEY, {
    "shop.acme-example.com": {"level": "up", "label": "OK", "ms": 142, "ips": ["104.21.4.7"], "cloudflare": True,
                              "cert_expires": NOW + 61 * 86400, "checked_at": NOW - 120},
    "blog.acme-example.com": {"level": "warn", "label": "Certificate expires in 9 days", "ms": 311, "ips": ["203.0.113.10"],
                              "cert_expires": NOW + 9 * 86400, "checked_at": NOW - 120},
    "smith-bakery.example": {"level": "up", "label": "OK", "ms": 88, "ips": ["104.21.9.2"], "cloudflare": True,
                             "cert_expires": NOW + 77 * 86400, "checked_at": NOW - 120},
})

# --- local Docker (the collector's snapshot) -------------------------------------------------
def ct(name, image, state_="running", service="", ports=(), status="Up 3 days", health=""):
    return {"name": name, "image": image, "state": state_, "health": health, "status": status, "service": service,
            "ports": [{"public": p, "private": p, "proto": "tcp", "ip": "127.0.0.1"} for p in ports], "created": NOW - 86400 * 9}

def project(name, folder, containers, compose):
    return {"name": name, "working_dir": folder, "folder": folder, "containers": containers,
            "compose": [{"path": f"{folder}/docker-compose.yml", "content": compose, "error": None}], "dockerfiles": [],
            "git": {"commit": "a41f9c2", "subject": "Bump image versions", "author": "marc", "time": NOW - 86400 * 2,
                    "branch": "main", "remote": "https://git.example.com/ops/" + name + ".git", "dirty": 0},
            "service": None}

compose_nc = "services:\n  app:\n    image: nextcloud:29\n    ports: [\"127.0.0.1:18304:80\"]\n    environment:\n      MYSQL_PASSWORD: ********\n  db:\n    image: mariadb:11\n  redis:\n    image: redis:7\n"
compose_gt = "services:\n  gitea:\n    image: gitea/gitea:1.22\n    ports: [\"127.0.0.1:18305:3000\"]\n"
compose_mon = "services:\n  grafana:\n    image: grafana/grafana:11\n  prometheus:\n    image: prom/prometheus:v2.54\n"
snapshot = {"collected_at": NOW, "error": None, "docker": "27.3.1",
            "system": {"cpus": 4, "uptime": 86400 * 10.7, "load": [0.62, 0.48, 0.41], "mem_total": 16 * GB,
                       "mem_used": 6.2 * GB, "disk_total": 220 * GB, "disk_used": 96 * GB, "hostname": "tools"},
            "projects": [
                project("nextcloud", "/home/marc/apps/nextcloud", [ct("nextcloud-app-1", "nextcloud:29", ports=[18304], health="healthy"),
                        ct("nextcloud-db-1", "mariadb:11"), ct("nextcloud-redis-1", "redis:7")], compose_nc),
                project("gitea", "/home/marc/apps/gitea", [ct("gitea", "gitea/gitea:1.22", ports=[18305])], compose_gt),
                project("monitoring", "/home/marc/apps/monitoring", [ct("grafana", "grafana/grafana:11"),
                        ct("prometheus", "prom/prometheus:v2.54", state_="exited", status="Exited (1) 2 hours ago")], compose_mon)],
            "containers": [ct("x-tools", "x-tools:local"), ct("x-tools-collector", "x-tools:local", health="healthy")]}
(DEMO / "exchange").mkdir(exist_ok=True)
(DEMO / "exchange" / "snapshot.json").write_text(json.dumps(snapshot))

# --- agents ----------------------------------------------------------------------------------
def agent(name, kind, report):
    extra = ({"proxmox_url": "https://127.0.0.1:8006", "proxmox_token_id": "root@pam!xtools", "proxmox_token_secret": "demo"}
             if kind == "proxmox" else {})
    r = call("/api/agents", {"name": name, "kind": kind, "control": True, **extra})
    opener.open(urllib.request.Request(BASE + "/api/agent/report", data=json.dumps(report).encode(), method="POST",
                headers={"X-Agent-Key": r["key"], "Content-Type": "application/json"}))
    return r["id"]

def svc(name, desc, active="active", sub="running"):
    return {"name": name + ".service", "active": active, "sub": sub, "enabled": "enabled", "description": desc}

linux_report = {"version": "8", "hostname": "web-01", "control": True,
    "system": {"cpus": 2, "uptime": 86400 * 41.2, "load": [0.31, 0.25, 0.2], "mem_total": 4 * GB, "mem_used": 1.7 * GB,
               "disk_total": 40 * GB, "disk_used": 17 * GB, "hostname": "web-01"},
    "linux": {"os": "Debian GNU/Linux 13 (trixie)", "kernel": "6.12.115+deb13-amd64", "arch": "x86_64",
              "updates": ["libssl3", "openssl", "curl", "libcurl4", "linux-image-amd64"], "reboot_required": True,
              "services": [svc("nginx", "A high performance web server and reverse proxy"),
                           svc("php8.3-fpm", "The PHP 8.3 FastCGI Process Manager"),
                           svc("postgresql@16-main", "PostgreSQL Cluster 16-main"),
                           svc("fail2ban", "Fail2Ban Service"), svc("ssh", "OpenBSD Secure Shell server"),
                           svc("cron", "Regular background program processing daemon"),
                           svc("certbot", "Certbot renewal", "failed", "failed"),
                           svc("unattended-upgrades", "Unattended Upgrades Shutdown")],
              "ports": [{"port": 22, "proto": "tcp", "address": "0.0.0.0", "process": "sshd"},
                        {"port": 80, "proto": "tcp", "address": "0.0.0.0", "process": "nginx"},
                        {"port": 443, "proto": "tcp", "address": "0.0.0.0", "process": "nginx"},
                        {"port": 5432, "proto": "tcp", "address": "127.0.0.1", "process": "postgres"}],
              "disks": [{"mount": "/", "fstype": "ext4", "used": 17 * GB, "total": 40 * GB},
                        {"mount": "/var/backups", "fstype": "ext4", "used": 61 * GB, "total": 100 * GB}],
              "users": [
                  {"name": "root", "uid": 0, "home": "/root", "shell": "/bin/bash", "login": True, "sudo": True, "locked": False,
                   "password": False, "last_login": time.time() - 86400 * 30, "keys": []},
                  {"name": "marc", "uid": 1000, "home": "/home/marc", "shell": "/bin/bash", "login": True, "sudo": True,
                   "locked": False, "password": False, "last_login": time.time() - 3600 * 5,
                   "keys": [{"type": "ssh-ed25519", "fingerprint": "SHA256:" + "k3Yd9" * 8 + "abc", "comment": "marc@laptop", "options": False}]},
                  {"name": "deploy", "uid": 1001, "home": "/home/deploy", "shell": "/bin/bash", "login": True, "sudo": False,
                   "locked": False, "password": False, "last_login": time.time() - 86400 * 2, "keys": []},
                  {"name": "freelancer", "uid": 1002, "home": "/home/freelancer", "shell": "/bin/bash", "login": True, "sudo": False,
                   "locked": True, "password": False, "last_login": None, "keys": []}],
              "firewall": {"installed": True, "active": True, "default": "deny (incoming), allow (outgoing), disabled (routed)",
                           "ssh_ports": [22],
                           "rules": [{"number": 1, "to": "22/tcp", "action": "LIMIT", "direction": "IN", "from": "Anywhere", "comment": "ssh"},
                                     {"number": 2, "to": "80/tcp", "action": "ALLOW", "direction": "IN", "from": "Anywhere", "comment": "web"},
                                     {"number": 3, "to": "443/tcp", "action": "ALLOW", "direction": "IN", "from": "Anywhere", "comment": "web"},
                                     {"number": 4, "to": "5432/tcp", "action": "ALLOW", "direction": "IN", "from": "10.0.0.0/24", "comment": "database"}]},
              "update_job": {"state": "ok", "started": time.time() - 86400, "finished": time.time() - 86400 + 140, "manager": "apt",
                             "log": "$ apt-get update\nGet:1 http://deb.debian.org/debian trixie InRelease\nReading package lists...\n$ apt-get -y upgrade\n5 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"}},
    "docker": None, "proxmox": None}
def net(name, ip, prefix=24, virtual=False):
    return {"name": name, "mac": "bc:24:11:%02x:%02x:%02x" % (random.randrange(256), random.randrange(256), random.randrange(256)),
            "state": "up", "virtual": virtual, "addrs": [{"ip": ip, "prefix": prefix}]}

linux_report["network"] = [net("eth0", "10.0.0.21"), net("docker0", "172.17.0.1", 16, True)]
linux_report["linux"].update(os_id="debian", os_version="13")
linux_id = agent("web-01", "linux", linux_report)
db_report = json.loads(json.dumps(linux_report))
db_report["hostname"] = "db-01"
db_report["system"].update(hostname="db-01", load=[0.9, 0.7, 0.6], mem_used=3.1 * GB, disk_used=22 * GB)
db_report["linux"].update(updates=[], reboot_required=False, firewall={"installed": False}, update_job=None,
                          services=[svc("postgresql@16-main", "PostgreSQL Cluster 16-main"), svc("ssh", "OpenBSD Secure Shell server")])
db_report["network"] = [net("eth0", "10.0.0.22"), net("docker0", "172.17.0.1", 16, True)]
db_report["linux"].update(os_id="debian", os_version="11", os="Debian GNU/Linux 11 (bullseye)")
db_id = agent("db-01", "linux", db_report)
grp_prod = call("/api/server-groups", {"name": "Production"})["id"]
call("/api/server-groups", {"name": "Home network"})
call(f"/api/agents/{linux_id}/meta", {"group_id": grp_prod, "tags": ["debian", "web", "customer-acme"],
     "notes": "Web server for the ACME shop and blog.\nResponsible: Anna Meyer (anna@acme-example.com)\nRunbook: https://wiki.example.com/runbooks/web-01"}, method="PUT")
call(f"/api/agents/{db_id}/meta", {"group_id": grp_prod, "tags": ["debian", "database"]}, method="PUT")

def guest(vmid, name, typ, status, cpu, maxcpu, mem, maxmem, up):
    return {"vmid": vmid, "name": name, "type": typ, "status": status, "node": "pve", "cpu": cpu, "maxcpu": maxcpu,
            "mem": mem * GB, "maxmem": maxmem * GB, "uptime": up}
pve_report = {"version": "8", "hostname": "pve", "control": True,
    "system": {"cpus": 16, "uptime": 86400 * 63, "load": [1.9, 2.1, 1.8], "mem_total": 64 * GB, "mem_used": 38 * GB,
               "disk_total": 1800 * GB, "disk_used": 910 * GB, "hostname": "pve"},
    "docker": None, "linux": None,
    "proxmox": {"nodes": [{"name": "pve", "status": "online", "cpu": 0.12, "maxcpu": 16, "mem": 38 * GB, "maxmem": 64 * GB, "uptime": 86400 * 63}],
                "guests": [guest(100, "docker-host", "lxc", "running", 0.05, 4, 6.1, 8, 86400 * 30),
                           guest(101, "pihole", "lxc", "running", 0.01, 1, 0.2, 0.5, 86400 * 63),
                           guest(102, "homeassistant", "qemu", "running", 0.09, 2, 2.4, 4, 86400 * 12),
                           guest(103, "gitlab", "lxc", "running", 0.07, 4, 5.2, 8, 86400 * 20),
                           guest(104, "media", "lxc", "running", 0.02, 2, 1.1, 4, 86400 * 8),
                           guest(105, "win11-test", "qemu", "stopped", 0, 4, 0, 8, 0),
                           guest(106, "backup-server", "lxc", "running", 0.01, 2, 0.6, 2, 86400 * 63)],
                "storage": [{"storage": "local-zfs", "node": "pve", "disk": 520 * GB, "maxdisk": 1000 * GB},
                            {"storage": "backup", "node": "pve", "disk": 390 * GB, "maxdisk": 800 * GB}],
                "details": None}}
pve_report["network"] = [net("vmbr0", "10.0.0.2")]
pve_report["proxmox"]["details"] = {"fetched_at": time.time(), "backups": [], "nodes": {}, "guests": {
    "pve/100": {"fetched_at": time.time(), "ips": [{"interface": "eth0", "address": "10.0.0.30"}]},
    "pve/101": {"fetched_at": time.time(), "config": {"nets": [{"name": "eth0", "ip": "10.0.0.53/24", "mac": "bc:24:11:aa:00:01"}]}},
    "pve/102": {"fetched_at": time.time(), "ips": [{"interface": "enp0s18", "address": "10.0.0.60"}]},
    "pve/103": {"fetched_at": time.time(), "ips": [{"interface": "eth0", "address": "10.0.0.70"}]},
    "pve/104": {"fetched_at": time.time(), "ips": [{"interface": "eth0", "address": "10.0.0.80"}]},
    "pve/106": {"fetched_at": time.time(), "ips": [{"interface": "eth0", "address": "10.0.0.90"}]}}}
pve_id = agent("pve", "proxmox", pve_report)

dk_report = {"version": "8", "hostname": "docker-host", "control": True,
    "system": {"cpus": 4, "uptime": 86400 * 30, "load": [0.4, 0.5, 0.5], "mem_total": 8 * GB, "mem_used": 3.8 * GB,
               "disk_total": 60 * GB, "disk_used": 24 * GB, "hostname": "docker-host"},
    "linux": None, "proxmox": None,
    "docker": {"collected_at": NOW, "error": None, "docker": "27.3.1",
               "projects": [project("paperless", "/opt/paperless", [ct("paperless-web", "paperless-ngx:2.13", ports=[8000]),
                            ct("paperless-broker", "redis:7")], "services:\n  web:\n    image: paperless-ngx:2.13\n")],
               "containers": []}}
dk_report["network"] = [net("eth0", "10.0.0.30"), net("br-3f2a", "172.18.0.1", 16, True)]
dk_id = agent("docker-host", "docker", dk_report)
for ip, name, notes in (("10.0.0.1", "Router", "Fritz!Box, ground floor"), ("10.0.0.40", "NAS", "Synology, backups"),
                        ("10.0.0.22", "Old printer", "to be removed")):
    call("/api/network/entries", {"ip": ip, "name": name, "notes": notes})

# --- history: metrics (7 days), events, jobs, sites -----------------------------------------
with session_scope() as db:
    now = datetime.now(timezone.utc)
    for source, base in (("local", (24, 39, 44)), (linux_id, (14, 42, 43)), (pve_id, (22, 59, 51)), (dk_id, (30, 47, 40))):
        for i in range(7 * 24 * 2):  # every 30 min
            ts = now - timedelta(minutes=30 * i)
            wave = math.sin(i / 7.0)
            db.add(Metric(source=source, ts=ts, load=max(1, base[0] + 12 * wave + random.uniform(-4, 4) + (25 if i % 97 < 3 else 0)),
                          mem=min(95, base[1] + 4 * math.sin(i / 40) + random.uniform(-1, 1)),
                          disk=base[2] + (7 * 24 * 2 - i) * 0.004))
    for key, kind, level, text, hours, dur in (
            ("port:x:18399", "port", "down", "Mail relay: port 18399 (SMTP) does not answer", 30, None),
            ("container:prometheus", "container", "down", "Container prometheus: stopped", 2, None),
            ("site:blog.acme-example.com", "site", "warn", "blog.acme-example.com (ACME Shop GmbH): certificate expires in 9 days", 20, None),
            ("agent:old", "agent", "down", "Server 'pve' does not report (last 9 min ago)", 70, 1.2),
            ("port:y:18304", "port", "down", "Nextcloud: port 18304 (Web) does not answer", 100, 0.1),
            ("container:grafana", "container", "warn", "Container grafana: unhealthy", 140, 3)):
        ev = Event(key=key, kind=kind, level=level, text=text, link="/", started_at=now - timedelta(hours=hours))
        if dur is not None:
            ev.ended_at = ev.started_at + timedelta(hours=dur)
        db.add(ev)
    for name, interval, ok_ago in (("Nightly backup", 1440, 6 * 60), ("Certificate renewal", 7 * 1440, 3 * 1440),
                                   ("Database dump", 1440, 3 * 1440 + 200)):
        db.add(Heartbeat(name=name, token=f"demo-{name.lower().replace(' ', '-')}-token-0000000000", interval_minutes=interval,
                         grace_minutes=60, last_ping_at=now - timedelta(minutes=ok_ago), last_ok_at=now - timedelta(minutes=ok_ago),
                         last_status="ok"))
    db.commit()

# customer website deployed by X-TOOLS
(DEMO / "exchange" / "deploy" / "status").mkdir(parents=True, exist_ok=True)
(DEMO / "exchange" / "deploy" / "alive").touch()
cust = {c["name"]: c["id"] for c in call("/api/customers")}
for name, cname, repo in (("ACME web shop (git)", "ACME Shop GmbH", "https://git.example.com/acme/shop"),
                          ("Bakery Smith (static)", "Bakery Smith", "https://git.example.com/smith/website")):
    s = call("/api/sites", {"name": name, "customer_id": cust[cname], "repo_url": repo, "branch": "main", "compose_file": "",
                            "port": 18301 if "static" in name else None, "env": []})
    (DEMO / "exchange" / "deploy" / "status" / f"{s['id']}.json").write_text(json.dumps(
        {"state": "ok", "action": "deploy", "started": NOW - 3600, "finished": NOW - 3540, "updated": NOW - 3540,
         "commit": "7c1e0ab", "subject": "Update opening hours", "log": "Done.\n"}))
print("demo data ready")
