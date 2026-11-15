"""Background loops: notify about new and solved issues, check customer websites."""

import threading
import time

from app.core.config import get_settings
from app.monitor import history, maintenance, notify, sites, state
from app.monitor.issues import ALERT_STATE, find_issues

START_DELAY = 30  # let everything come up after a (re)start before alerting


def check_alerts(now: float | None = None) -> dict | None:
    """One monitoring run. Returns the sent message (for tests) or None."""
    settings = notify.load()
    issues = find_issues()
    try:  # history must never stop notifications
        history.record_events(issues)
        history.record_metrics()
    except Exception as error:  # noqa: BLE001
        print(f"History: {error}", flush=True)
    current = {i["key"]: i for i in issues if settings["events"].get(i["kind"], True) and not i.get("manual")}
    now = now or time.time()
    paused = maintenance.silenced_keys(list(current.values()), now)
    active = bool(notify.active_channels(settings))
    new, solved = [], []

    def change(data):
        open_issues = data.setdefault("open", {})
        for key, issue in current.items():
            entry = open_issues.setdefault(key, {"since": now, "sent": False})
            entry.update(text=issue["text"], level=issue["level"], paused=key in paused)
            if key in paused:
                entry["since"] = now  # the delay starts again when the window is over
                continue
            if active and not entry["sent"] and now - entry["since"] >= settings["delay"] * 60:
                new.append(issue)
                entry["sent"] = True
        for key in list(open_issues):
            if key not in current:
                entry = open_issues.pop(key)
                if active and entry.get("sent") and settings["recovery"] and not entry.get("paused"):
                    solved.append(entry)
        return data
    state.update(ALERT_STATE, change)
    if not (new or solved):
        return None

    parts = []
    if new:
        parts.append("\n".join(f"• {i['text']}" for i in new))
    if solved:
        parts.append(("Back to normal:\n" if new else "") + "\n".join(f"• solved: {i['text']}" for i in solved))
    title = (f"⚠️ X-TOOLS: {len(new)} problem{'s' if len(new) != 1 else ''}" if new
             else "✅ X-TOOLS: back to normal")
    body = "\n\n".join(parts)
    results = notify.notify(settings, title, body, "down" if new else "up")

    def remember(data):
        data["last"] = {"time": now, "title": title, "results": results}
        return data
    state.update(ALERT_STATE, remember)
    return {"title": title, "body": body, "results": results}


def _loop(name: str, delay: int, interval_fn, fn) -> None:
    time.sleep(delay)
    while True:
        error_text = ""
        try:
            fn()
        except Exception as error:  # noqa: BLE001 – monitoring must never take the app down
            error_text = f"{type(error).__name__}: {error}"[:300]
            print(f"{name}: {error_text}", flush=True)
        if name == "Monitoring":
            try:
                def mark(data):
                    data["checked_at"] = time.time()
                    data["error"] = error_text
                    return data
                state.update(ALERT_STATE, mark)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(interval_fn())


def start_background() -> None:
    settings = get_settings()
    if not settings.monitor:
        return
    threading.Thread(target=_loop, name="alerts", daemon=True,
                     args=("Monitoring", START_DELAY, lambda: get_settings().alert_interval, check_alerts)).start()
    threading.Thread(target=_loop, name="sites", daemon=True,
                     args=("Website checks", 20, lambda: get_settings().site_interval, sites.run_checks)).start()
    from app.monitor import autobackup, updates
    threading.Thread(target=_loop, name="backup", daemon=True,
                     args=("Automatic backup", 60, lambda: 60, autobackup.run_if_due)).start()
    threading.Thread(target=_loop, name="updates", daemon=True,
                     args=("Update check", 120, lambda: 1800, updates.check_if_due)).start()
    from app.integrations import cloudflare
    threading.Thread(target=_loop, name="cloudflare", daemon=True,
                     args=("Cloudflare", 25, lambda: 60, cloudflare.refresh_if_due)).start()
