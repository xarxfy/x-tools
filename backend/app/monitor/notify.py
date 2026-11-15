"""Notification settings and delivery through Telegram and ntfy."""

import json
import re

from cryptography.fernet import InvalidToken

from app.collector.httpjson import post_json
from app.core.config import get_settings
from app.core.security import decrypt_json, encrypt_json
from app.monitor import state

KEY = "notifications"
EVENT_KINDS = ("port", "container", "docker", "system", "site", "agent", "cloudflare", "job")
TELEGRAM_TOKEN = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,60}$")
TELEGRAM_CHAT = re.compile(r"^(-?\d{1,20}|@[A-Za-z0-9_]{5,32})$")
NTFY_TOPIC = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NTFY_SERVER = re.compile(r"^https?://[^\s/]+$")


def defaults() -> dict:
    return {
        "enabled": False,
        "telegram": {"enabled": False, "chat_id": "", "token": ""},
        "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token": ""},
        "events": {k: True for k in EVENT_KINDS},
        "delay": 2,
        "recovery": True,
    }


def load() -> dict:
    """Settings with defaults filled in; tokens stay encrypted."""
    data = defaults()
    for key, value in (state.load(KEY, {}) or {}).items():
        if isinstance(data.get(key), dict) and isinstance(value, dict):
            data[key].update(value)
        elif key in data:
            data[key] = value
    return data


def public(settings: dict) -> dict:
    """For the UI: never the tokens, only whether one is stored."""
    out = json.loads(json.dumps(settings))
    for channel in ("telegram", "ntfy"):
        out[channel]["has_token"] = bool(out[channel].pop("token", ""))
    return out


def secret(token_enc: str) -> str:
    if not token_enc:
        return ""
    try:
        return decrypt_json(token_enc)
    except InvalidToken:
        raise ValueError("Token cannot be decrypted – was the secret key changed?") from None


def save(body: dict) -> dict:
    """Validate and store. An empty token field keeps the stored token."""
    old, new = load(), defaults()
    new["enabled"] = bool(body.get("enabled"))
    new["recovery"] = bool(body.get("recovery"))
    events = body.get("events") or {}
    new["events"] = {k: bool(events.get(k)) for k in EVENT_KINDS}
    try:
        new["delay"] = max(0, min(120, int(body.get("delay", 2))))
    except (TypeError, ValueError):
        raise ValueError("Delay must be a number") from None

    tg_in, tg = body.get("telegram") or {}, new["telegram"]
    tg["enabled"] = bool(tg_in.get("enabled"))
    tg["chat_id"] = str(tg_in.get("chat_id") or "").strip()
    if tg["chat_id"] and not TELEGRAM_CHAT.match(tg["chat_id"]):
        raise ValueError("Chat ID: a number (e.g. 123456789 or -100…) or @channelname")
    token = str(tg_in.get("token") or "").strip()
    if token and not TELEGRAM_TOKEN.match(token):
        raise ValueError("The bot token does not look right (123456:ABC…)")
    tg["token"] = "" if tg_in.get("clear_token") else (encrypt_json(token) if token else old["telegram"]["token"])
    if tg["enabled"] and not (tg["token"] and tg["chat_id"]):
        raise ValueError("Telegram needs a bot token and a chat ID")

    nt_in, nt = body.get("ntfy") or {}, new["ntfy"]
    nt["enabled"] = bool(nt_in.get("enabled"))
    nt["server"] = str(nt_in.get("server") or "").strip().rstrip("/") or "https://ntfy.sh"
    if not NTFY_SERVER.match(nt["server"]):
        raise ValueError("ntfy server: only the address, e.g. https://ntfy.sh")
    nt["topic"] = str(nt_in.get("topic") or "").strip()
    if nt["topic"] and not NTFY_TOPIC.match(nt["topic"]):
        raise ValueError("ntfy topic: letters, digits, - and _ only")
    token = str(nt_in.get("token") or "").strip()
    if len(token) > 200:
        raise ValueError("ntfy token is too long")
    nt["token"] = "" if nt_in.get("clear_token") else (encrypt_json(token) if token else old["ntfy"]["token"])
    if nt["enabled"] and not nt["topic"]:
        raise ValueError("ntfy needs a topic")

    state.save(KEY, new)
    return new


def active_channels(settings: dict) -> list[str]:
    return [c for c in ("telegram", "ntfy") if settings["enabled"] and settings[c]["enabled"]]


def send_telegram(cfg: dict, title: str, body: str, link: str) -> None:
    message = f"{title}\n\n{body}" + (f"\n\n{link}" if link else "")
    api = get_settings().telegram_api.rstrip("/")
    post_json(f"{api}/bot{secret(cfg['token'])}/sendMessage",
              {"chat_id": cfg["chat_id"], "text": message[:4000], "disable_web_page_preview": True})


def send_ntfy(cfg: dict, title: str, body: str, link: str, level: str) -> None:
    payload = {"topic": cfg["topic"], "title": title, "message": body[:4000],
               "priority": 4 if level == "down" else 3,
               "tags": ["warning"] if level == "down" else ["white_check_mark"] if level == "up"
               else ["information_source"]}
    if link:
        payload["click"] = link
    token = secret(cfg["token"])
    post_json(cfg["server"] + "/", payload, {"Authorization": f"Bearer {token}"} if token else None)


def notify(settings: dict, title: str, body: str, level: str, only: list[str] | None = None) -> dict:
    """Send to all active channels; returns {channel: error or None}."""
    link = get_settings().base_url
    results: dict = {}
    for channel in only or active_channels(settings):
        try:
            if channel == "telegram":
                send_telegram(settings["telegram"], title, body, link)
            else:
                send_ntfy(settings["ntfy"], title, body, link, level)
            results[channel] = None
        except (OSError, ValueError, KeyError) as error:
            results[channel] = str(error)
            print(f"Notification via {channel} failed: {error}", flush=True)
    return results
