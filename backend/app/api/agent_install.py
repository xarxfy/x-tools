"""One-line agent installation.

Creating an agent (or "new install command") returns a command like

    curl -fsSL https://tools.example.com/api/agent/install/<token> | sh

The token is random, valid for one hour and works once. The install script it
returns contains the agent key and the optional Proxmox/Cloudflare values, so
those are kept only encrypted and only until the script is fetched – X-TOOLS
itself never stores the Proxmox token permanently.
"""

import hashlib
import re
import secrets
import time

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from app.collector.bundle import agent_bundle
from app.core.config import get_settings
from app.core.security import decrypt_json, encrypt_json
from app.monitor import state

KEY = "agent_installs"
VALID_SECONDS = 3600

PATTERNS = {
    "proxmox_url": r"^https?://[A-Za-z0-9.\-\[\]:]+(:\d{1,5})?/?$",
    "proxmox_token_id": r"^[A-Za-z0-9._@!\-]{1,100}$",
    # Secrets: anything except whitespace, quotes, backslash, $ and backtick (they end up in a shell script).
    "proxmox_token_secret": r"^[A-Za-z0-9._~+/=:@!%^&*(),;?\-]{1,200}$",
    "cf_client_id": r"^[A-Za-z0-9._\-]{1,200}$",
    "cf_client_secret": r"^[A-Za-z0-9._~+/=:@!%^&*(),;?\-]{1,256}$",
    "compose_roots": r"^[A-Za-z0-9_/.,\-]{0,300}$",
}


class InstallOptions(BaseModel):
    kind: str = Field(default="docker", pattern="^(proxmox|docker)$")
    proxmox_url: str = ""
    proxmox_token_id: str = ""
    proxmox_token_secret: str = ""
    proxmox_verify_tls: bool = False
    control: bool = False  # agent accepts commands from X-TOOLS (operators)
    cf_client_id: str = ""
    cf_client_secret: str = ""
    compose_roots: str = Field(default="/opt,/srv,/home,/root")

    @field_validator(*PATTERNS, mode="before")
    @classmethod
    def check(cls, value, info):
        value = str(value or "").strip()
        # Accept values pasted together with their name, e.g. "CF-Access-Client-Secret: abc" or "PROXMOX_TOKEN_ID=…"
        value = re.sub(r"^(CF[-_]ACCESS[-_]CLIENT[-_](ID|SECRET)|PROXMOX[-_]TOKEN[-_](ID|SECRET)|PROXMOX[-_]URL)\s*[:=]\s*",
                       "", value, flags=re.I).strip().strip("\"'")
        if value and not re.match(PATTERNS[info.field_name], value):
            raise ValueError("contains characters that are not allowed (spaces, quotes, $, ` and \\ are not "
                             "possible) – paste only the value")
        return value

    @model_validator(mode="after")
    def complete(self):
        proxmox = [self.proxmox_url, self.proxmox_token_id, self.proxmox_token_secret]
        if self.kind == "proxmox" and not all(proxmox):
            raise ValueError("A Proxmox host needs URL, API token ID and token secret")
        if self.kind == "docker":  # Docker hosts never get Proxmox credentials
            self.proxmox_url = self.proxmox_token_id = self.proxmox_token_secret = ""
        if bool(self.cf_client_id) != bool(self.cf_client_secret):
            raise ValueError("Cloudflare Access needs client ID and client secret")
        return self


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_base(request: Request) -> str:
    base = get_settings().base_url
    if base:
        return base
    proto = request.headers.get("x-forwarded-proto", request.url.scheme) if get_settings().trust_proxy \
        else request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto.split(',')[0].strip()}://{host}"


def create_install(request: Request, agent_id: str, key: str, opts: InstallOptions) -> dict:
    token = secrets.token_urlsafe(24)
    now = time.time()
    payload = encrypt_json({"key": key, **opts.model_dump()})

    def add(data):
        data = {h: v for h, v in data.items() if v.get("expires", 0) > now and v.get("agent_id") != agent_id}
        data[_hash(token)] = {"agent_id": agent_id, "expires": now + VALID_SECONDS, "payload": payload}
        return data
    state.update(KEY, add)
    base = public_base(request)
    headers = ""
    if opts.cf_client_id:
        headers = f"-H 'CF-Access-Client-Id: {opts.cf_client_id}' -H 'CF-Access-Client-Secret: {opts.cf_client_secret}' "
    return {"command": f"curl -fsSL {headers}'{base}/api/agent/install/{token}' | sh",
            "expires_at": now + VALID_SECONDS, "base_url": base}


def take_install(token: str) -> dict | None:
    found: dict = {}

    def pop(data):
        entry = data.pop(_hash(token), None)
        if entry and entry.get("expires", 0) > time.time():
            found.update(entry)
        return data
    state.update(KEY, pop)
    if not found:
        return None
    return {"agent_id": found["agent_id"], **decrypt_json(found["payload"])}


SCRIPT = r"""#!/bin/sh
# X-TOOLS agent installer – generated for one agent, works once.
# Installs /opt/x-tools-agent/agent.pyz (Python standard library only) as the
# systemd service x-tools-agent. Reports outbound over HTTPS, opens no ports.
set -eu

URL='__URL__'
KEY='__KEY__'

if [ "$(id -u)" != 0 ]; then
  echo "Please run as root (e.g. pipe into 'sudo sh' instead of 'sh')." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd not found – use the Docker variant instead (deploy/agent in the X-TOOLS repository)." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing python3 …"
    apt-get update -qq && apt-get install -y -qq python3 >/dev/null
  else
    echo "python3 (3.10 or newer) is required." >&2
    exit 1
  fi
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "python3 3.10 or newer is required." >&2; exit 1; }

mkdir -p /opt/x-tools-agent /etc/x-tools-agent
chmod 700 /etc/x-tools-agent
echo "Downloading agent …"
curl -fsSL __CURL_HEADERS__-H "X-Agent-Key: $KEY" "$URL/api/agent/bundle" -o /opt/x-tools-agent/agent.pyz.new
mv /opt/x-tools-agent/agent.pyz.new /opt/x-tools-agent/agent.pyz
chmod 644 /opt/x-tools-agent/agent.pyz

umask 077
cat > /etc/x-tools-agent/agent.env <<'ENV'
__ENV__
ENV

cat > /etc/systemd/system/x-tools-agent.service <<'UNIT'
[Unit]
Description=X-TOOLS agent (reports this server to X-TOOLS)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/env python3 -I /opt/x-tools-agent/agent.pyz
EnvironmentFile=/etc/x-tools-agent/agent.env
Restart=always
RestartSec=15
# Read-only everywhere; the agent only reads and sends.
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now x-tools-agent >/dev/null 2>&1 || systemctl enable --now x-tools-agent
systemctl restart x-tools-agent
sleep 3
if systemctl is-active --quiet x-tools-agent; then
  echo "X-TOOLS agent is running – this server shows up in X-TOOLS within a minute."
else
  echo "The agent did not start. Log: journalctl -u x-tools-agent -n 30" >&2
  exit 1
fi
echo "Log: journalctl -u x-tools-agent -f"
echo "Remove: systemctl disable --now x-tools-agent; rm -rf /opt/x-tools-agent /etc/x-tools-agent /etc/systemd/system/x-tools-agent.service; systemctl daemon-reload"
"""


def render_script(base: str, data: dict) -> str:
    env = [f"XT_AGENT_URL={base}", f"XT_AGENT_KEY={data['key']}", f"XT_TIMEZONE={get_settings().timezone}",
           f"XT_COMPOSE_ROOTS={data.get('compose_roots') or '/opt,/srv,/home,/root'}",
           f"XT_AGENT_DOCKER={'0' if data.get('kind') == 'proxmox' else '1'}",
           f"XT_AGENT_CONTROL={'1' if data.get('control') else '0'}"]
    curl_headers = ""
    if data.get("cf_client_id"):
        env += [f"CF_ACCESS_CLIENT_ID={data['cf_client_id']}", f"CF_ACCESS_CLIENT_SECRET={data['cf_client_secret']}"]
        curl_headers = (f"-H 'CF-Access-Client-Id: {data['cf_client_id']}' "
                        f"-H 'CF-Access-Client-Secret: {data['cf_client_secret']}' ")
    if data.get("proxmox_url"):
        env += [f"PROXMOX_URL={data['proxmox_url'].rstrip('/')}", f"PROXMOX_TOKEN_ID={data['proxmox_token_id']}",
                f"PROXMOX_TOKEN_SECRET={data['proxmox_token_secret']}",
                f"PROXMOX_VERIFY_TLS={'1' if data.get('proxmox_verify_tls') else '0'}"]
    return (SCRIPT.replace("__URL__", base).replace("__KEY__", data["key"])
            .replace("__CURL_HEADERS__", curl_headers).replace("__ENV__", "\n".join(env)))


def install_script(request: Request, token: str) -> PlainTextResponse:
    data = take_install(token) if re.match(r"^[A-Za-z0-9_\-]{20,64}$", token) else None
    if data is None:
        return PlainTextResponse("echo 'This install command is invalid, expired or was already used. "
                                 "Create a new one in X-TOOLS → Settings → Agents.' >&2; exit 1\n", status_code=404)
    return PlainTextResponse(render_script(public_base(request), data),
                             headers={"Cache-Control": "no-store", "Content-Type": "text/x-shellscript"})


def bundle_response() -> Response:
    return Response(agent_bundle(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=agent.pyz"})
