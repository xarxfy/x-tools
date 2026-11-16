"""Administration of a Linux server through the agent: installing updates, local users with SSH keys, ufw firewall.

Everything here runs as root on the managed server, so every input is validated twice: by X-TOOLS before the
command is queued (``validate``) and again by the agent before it is executed. Only a fixed set of actions exists;
arguments never reach a shell. The agent keeps itself reachable: it never locks out the last administrator and never
removes the firewall rule that lets SSH in.
"""

import base64
import errno
import hashlib
import ipaddress
import os
import pwd
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.collector.linux import run

USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
             "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
COMMENT_RE = re.compile(r"^[\w@. +-]{0,60}$")
PORT_RE = re.compile(r"^(\d{1,5})(:(\d{1,5}))?$")
USER_ACTIONS = ("user.lock", "user.unlock", "user.sudo", "user.nosudo", "user.key_add", "user.key_remove",
                "user.create", "user.delete")
UFW_ACTIONS = ("ufw.enable", "ufw.disable", "ufw.add", "ufw.delete")
ACTIONS = USER_ACTIONS + UFW_ACTIONS + ("system.update",)
NO_LOGIN = ("nologin", "false", "sync", "shutdown", "halt")
MAX_USERS = 60


class AdminError(ValueError):
    """A refused or failed administration action; the text is shown to the user."""


# --- validation (X-TOOLS and agent) ---------------------------------------------------


def parse_key(line: str) -> tuple[str, str, str]:
    """(type, base64 blob, comment) of an authorized_keys line without options; ValueError otherwise."""
    line = line.strip()
    if not line or "\n" in line or "\r" in line or len(line) > 4000:
        raise AdminError("Enter exactly one public key")
    parts = line.split(None, 2)
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise AdminError("Not a public SSH key (expected ssh-ed25519, ssh-rsa, ecdsa-…)")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise AdminError("The key is not valid base64") from None
    if not blob.startswith(len(parts[0]).to_bytes(4, "big") + parts[0].encode()):
        raise AdminError("The key type does not match the key")
    comment = parts[2].strip() if len(parts) > 2 else ""
    if not COMMENT_RE.match(comment):
        raise AdminError("The key comment contains unusual characters")
    return parts[0], parts[1], comment


def fingerprint(blob_b64: str) -> str:
    digest = hashlib.sha256(base64.b64decode(blob_b64)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def check_port(value: str) -> str:
    m = PORT_RE.match(str(value or ""))
    if not m:
        raise AdminError("Port must be a number (1-65535) or a range like 8000:8100")
    low, high = int(m.group(1)), int(m.group(3) or m.group(1))
    if not (1 <= low <= 65535 and 1 <= high <= 65535 and low <= high):
        raise AdminError("Port out of range")
    return m.group(0)


def validate(action: str, target: str, args: dict) -> dict:
    """Checks the arguments of an administration action and returns the cleaned ones."""
    if action not in ACTIONS:
        raise AdminError("Unknown action")
    args = args or {}
    if action in USER_ACTIONS:
        if not USER_RE.match(target or ""):
            raise AdminError("Invalid user name (lower-case letters, digits, - and _)")
    elif target != "host":
        raise AdminError("Unknown target")
    if action == "user.key_add":
        return {"key": _clean_key(args.get("key", ""))}
    if action == "user.key_remove":
        fp = str(args.get("fingerprint", ""))
        if not FINGERPRINT_RE.match(fp):
            raise AdminError("Invalid key fingerprint")
        return {"fingerprint": fp}
    if action == "user.create":
        key = str(args.get("key", "")).strip()
        return {"sudo": bool(args.get("sudo")), "key": _clean_key(key) if key else ""}
    if action == "user.delete":
        return {"remove_home": bool(args.get("remove_home"))}
    if action == "ufw.add":
        rule = str(args.get("rule", ""))
        proto = str(args.get("proto", "tcp"))
        if rule not in ("allow", "deny", "reject", "limit"):
            raise AdminError("Rule must be allow, deny, reject or limit")
        if proto not in ("tcp", "udp", "any"):
            raise AdminError("Protocol must be tcp, udp or any")
        source = str(args.get("source", "")).strip()
        if source:
            try:
                source = str(ipaddress.ip_network(source, strict=False))
            except ValueError:
                raise AdminError("Source must be an IP address or network like 10.0.0.0/24") from None
        if rule == "limit" and proto == "udp":
            raise AdminError("limit works for tcp only")
        comment = str(args.get("comment", "")).strip()
        if not COMMENT_RE.match(comment):
            raise AdminError("The comment contains unusual characters")
        return {"rule": rule, "port": check_port(args.get("port", "")), "proto": proto, "source": source,
                "comment": comment}
    if action == "ufw.delete":
        number = args.get("number")
        if not isinstance(number, int) or not 1 <= number <= 500:
            raise AdminError("Invalid rule number")
        return {"number": number, "to": str(args.get("to", ""))[:80], "action": str(args.get("action", ""))[:20],
                "from": str(args.get("from", ""))[:80]}
    return {}


def _clean_key(value) -> str:
    kind, blob, comment = parse_key(str(value))
    return f"{kind} {blob}" + (f" {comment}" if comment else "")


# --- users -------------------------------------------------------------------------------


def _admin_group() -> str:
    for name in ("sudo", "wheel"):
        try:
            import grp
            grp.getgrnam(name)
            return name
        except KeyError:
            continue
    return "sudo"


def _group_members(name: str) -> set[str]:
    import grp
    try:
        g = grp.getgrnam(name)
    except KeyError:
        return set()
    members = set(g.gr_mem)
    members |= {p.pw_name for p in pwd.getpwall() if p.pw_gid == g.gr_gid}
    return members


def _shadow() -> dict[str, tuple[str, str]]:
    out = {}
    try:
        for line in Path("/etc/shadow").read_text().splitlines():
            f = line.split(":")
            if len(f) >= 8:
                out[f[0]] = (f[1], f[7])
    except OSError:
        pass
    return out


def _expired(expire: str) -> bool:
    return expire.isdigit() and int(expire) <= int(time.time() // 86400)


def _ssh_dir(p: pwd.struct_passwd, create: bool = False) -> Path | None:
    """~/.ssh of the user, only when it is a real directory (never follow symlinks while running as root)."""
    home = Path(p.pw_dir)
    ssh = home / ".ssh"
    try:
        if home.is_symlink() or not home.is_dir():
            return None
        if not ssh.is_symlink() and ssh.is_dir():
            return ssh
        if ssh.exists() or ssh.is_symlink() or not create:
            return None
        ssh.mkdir(mode=0o700)
        os.chown(ssh, p.pw_uid, p.pw_gid)
        return ssh
    except OSError:
        return None


def read_keys(p: pwd.struct_passwd) -> list[dict]:
    ssh = _ssh_dir(p)
    path = ssh / "authorized_keys" if ssh else None
    if not path or path.is_symlink() or not path.is_file():
        return []
    keys = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    for line in lines[:200]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # options may precede the key type; find it
        for i, part in enumerate(parts[:6]):
            if part in KEY_TYPES and i + 1 < len(parts):
                try:
                    keys.append({"type": part, "fingerprint": fingerprint(parts[i + 1]),
                                 "comment": " ".join(parts[i + 2:])[:80], "options": i > 0})
                except ValueError:
                    pass
                break
    return keys


def last_login(name: str) -> float | None:
    try:
        out = run(["lastlog", "-u", name], timeout=5).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    if len(out) < 2 or "Never" in out[-1]:
        return None
    m = re.search(r"([A-Z][a-z]{2}) ([A-Z][a-z]{2}) +(\d+) (\d\d:\d\d:\d\d) .*?(\d{4})\s*$", out[-1])
    if not m:
        return None
    try:
        return time.mktime(time.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)} {m.group(5)}", "%b %d %H:%M:%S %Y"))
    except ValueError:
        return None


def users() -> list[dict]:
    """Login-capable accounts (root and normal users) with sudo, lock state, last login and SSH keys."""
    admins = _group_members(_admin_group())
    shadow = _shadow()
    out = []
    for p in sorted(pwd.getpwall(), key=lambda u: u.pw_uid):
        if not (p.pw_uid == 0 or 1000 <= p.pw_uid < 60000):
            continue
        shell = p.pw_shell.rsplit("/", 1)[-1]
        has_login = shell not in NO_LOGIN and bool(shell)
        pw, expire = shadow.get(p.pw_name, ("", ""))
        out.append({"name": p.pw_name, "uid": p.pw_uid, "home": p.pw_dir, "shell": p.pw_shell,
                    "login": has_login, "sudo": p.pw_name in admins or p.pw_uid == 0,
                    "locked": _expired(expire), "password": bool(pw) and pw[0] not in "!*",
                    "last_login": last_login(p.pw_name), "keys": read_keys(p)})
        if len(out) >= MAX_USERS:
            break
    return out


def _user(name: str) -> pwd.struct_passwd:
    try:
        return pwd.getpwnam(name)
    except KeyError:
        raise AdminError(f"User {name} does not exist") from None


def _would_orphan(name: str) -> bool:
    """True when `name` is the only unlocked sudo user (an administrator must stay reachable)."""
    shadow = _shadow()
    others = [n for n in _group_members(_admin_group()) if n != name and n != "root"
              and not _expired(shadow.get(n, ("", ""))[1])]
    return not others


READ_ONLY_HINT = ("The agent may not write to the system (its service is read-only: installed before version 7 or "
                  "without control). Create a new install command with “Allow control” and run it on this server.")


def _cmd(args: list[str]) -> None:
    out = run(args, timeout=60)
    if out.returncode != 0:
        text = (out.stderr or out.stdout or f"{args[0]} failed").strip()
        if "read-only file system" in text.lower() or "cannot lock" in text.lower():
            text = f"{text[:150]} – {READ_ONLY_HINT}"
        raise AdminError(text[:400])


def _write_keys(p: pwd.struct_passwd, lines: list[str]) -> None:
    ssh = _ssh_dir(p, create=True)
    if ssh is None:
        raise AdminError("The .ssh folder of this user is missing or not a regular folder")
    path = ssh / "authorized_keys"
    if path.is_symlink():
        raise AdminError("authorized_keys is a symbolic link – refusing to write")
    tmp = ssh / f".authorized_keys.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join(line + "\n" for line in lines))
    try:
        os.chown(tmp, p.pw_uid, p.pw_gid)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)  # only left over when something failed


def _existing_lines(p: pwd.struct_passwd) -> list[str]:
    ssh = _ssh_dir(p)
    path = ssh / "authorized_keys" if ssh else None
    if not path or path.is_symlink() or not path.is_file():
        return []
    return path.read_text(errors="replace").splitlines()


def _line_fingerprint(line: str) -> str | None:
    parts = line.split()
    for i, part in enumerate(parts[:6]):
        if part in KEY_TYPES and i + 1 < len(parts):
            try:
                return fingerprint(parts[i + 1])
            except ValueError:
                return None
    return None


def user_action(action: str, name: str, args: dict) -> dict:
    args = validate(action, name, args)
    if action == "user.create":
        try:
            pwd.getpwnam(name)
            raise AdminError(f"User {name} already exists")
        except KeyError:
            pass
        _cmd(["useradd", "-m", "-s", "/bin/bash", name])
        p = _user(name)
        if args["sudo"]:
            _cmd(["usermod", "-aG", _admin_group(), name])
        if args["key"]:
            _write_keys(p, [args["key"]])
        return {"ok": True}
    p = _user(name)
    system = p.pw_uid == 0 or p.pw_uid < 1000
    if action in ("user.lock", "user.sudo", "user.nosudo", "user.delete") and system:
        raise AdminError("The root account and system accounts cannot be changed here")
    if action in ("user.lock", "user.nosudo", "user.delete") and name in _group_members(_admin_group()) \
            and _would_orphan(name):
        raise AdminError("This is the only administrator (sudo) account – the server would be left without one")
    if action == "user.lock":
        _cmd(["usermod", "-e", "1", name])
    elif action == "user.unlock":
        _cmd(["usermod", "-e", "", name])
    elif action == "user.sudo":
        _cmd(["usermod", "-aG", _admin_group(), name])
    elif action == "user.nosudo":
        _cmd(["gpasswd", "-d", name, _admin_group()])
    elif action == "user.delete":
        _cmd(["userdel"] + (["-r"] if args["remove_home"] else []) + [name])
    elif action == "user.key_add":
        fp = _line_fingerprint(args["key"])
        lines = _existing_lines(p)
        if fp in {_line_fingerprint(line) for line in lines}:
            raise AdminError("This key is already installed")
        _write_keys(p, lines + [args["key"]])
    elif action == "user.key_remove":
        lines = _existing_lines(p)
        kept = [line for line in lines if _line_fingerprint(line) != args["fingerprint"]]
        if len(kept) == len(lines):
            raise AdminError("Key not found")
        _write_keys(p, kept)
    return {"ok": True}


# --- ufw firewall ----------------------------------------------------------------------------

RULE_RE = re.compile(r"^\[\s*(\d+)\]\s+(.+?)\s{2,}(ALLOW|DENY|REJECT|LIMIT)(?: (IN|OUT|FWD))?\s{2,}(.+?)\s*(?:#\s*(.*))?$")


def ssh_ports() -> list[int]:
    """Ports sshd listens on (so that no firewall change cuts them off); 22 if unknown."""
    from app.collector.linux import ports
    found = sorted({p["port"] for p in ports() if p["proto"] == "tcp" and p["process"] == "sshd"})
    return found or [22]


def ufw_status() -> dict:
    if not shutil.which("ufw"):
        return {"installed": False}
    try:
        verbose = run(["ufw", "status", "verbose"], timeout=15)
        numbered = run(["ufw", "status", "numbered"], timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        return {"installed": True, "error": str(error)[:200]}
    if verbose.returncode != 0:
        return {"installed": True, "error": (verbose.stderr or verbose.stdout).strip()[:200]}
    active = bool(re.search(r"^Status: active", verbose.stdout, re.M))
    default = ""
    for line in verbose.stdout.splitlines():
        if line.startswith("Default:"):
            default = line.split(":", 1)[1].strip()
    rules = []
    for line in numbered.stdout.splitlines():
        m = RULE_RE.match(line)
        if m:
            rules.append({"number": int(m.group(1)), "to": m.group(2).strip(), "action": m.group(3),
                          "direction": m.group(4) or "IN", "from": m.group(5).strip(), "comment": m.group(6) or ""})
    return {"installed": True, "active": active, "default": default, "rules": rules[:200],
            "ssh_ports": ssh_ports()}


def _covers_ssh(rule: dict) -> bool:
    return rule["action"] in ("ALLOW", "LIMIT") and any(
        re.match(rf"^{p}(/tcp)?( \(v6\))?$", rule["to"]) for p in ssh_ports())


def ufw_action(action: str, args: dict) -> dict:
    args = validate(action, "host", args)
    if not shutil.which("ufw"):
        raise AdminError("ufw is not installed on this server")
    if action == "ufw.enable":
        for port in ssh_ports():
            _cmd(["ufw", "allow", f"{port}/tcp"])  # first let SSH in, then switch on
        _cmd(["ufw", "--force", "enable"])
    elif action == "ufw.disable":
        _cmd(["ufw", "disable"])
    elif action == "ufw.add":
        status = ufw_status()
        port, proto = args["port"], args["proto"]
        if status.get("active") and args["rule"] in ("deny", "reject") and not args["source"]:
            low, _, high = port.partition(":")
            if any(int(low) <= s <= int(high or low) for s in status.get("ssh_ports", [])) and proto != "udp":
                raise AdminError("This rule would block SSH, the way X-TOOLS administrators reach the server")
        cmd = ["ufw", args["rule"]]
        if args["source"]:
            cmd += ["from", args["source"], "to", "any", "port", port] + ([] if proto == "any" else ["proto", proto])
        else:
            cmd += [port if proto == "any" else f"{port}/{proto}"]
        if args["comment"]:
            cmd += ["comment", args["comment"]]
        _cmd(cmd)
    elif action == "ufw.delete":
        status = ufw_status()
        rules = {r["number"]: r for r in status.get("rules", [])}
        rule = rules.get(args["number"])
        if not rule or (rule["to"], rule["action"], rule["from"]) != (args["to"], args["action"], args["from"]):
            raise AdminError("The rules have changed – reload and try again")
        if status.get("active") and _covers_ssh(rule) and not any(
                r["number"] != rule["number"] and _covers_ssh(r) and r["to"].endswith("(v6)") == rule["to"].endswith("(v6)")
                for r in rules.values()):
            raise AdminError("This rule lets SSH in – deleting it would lock you out. Add another SSH rule first.")
        _cmd(["ufw", "--force", "delete", str(args["number"])])
    return {"ok": True}


# --- installing updates ----------------------------------------------------------------------------

_job: dict = {"state": "idle", "log": "", "started": None, "finished": None, "manager": ""}
_lock = threading.Lock()
LOG_MAX = 60_000


def update_job() -> dict | None:
    with _lock:
        return None if _job["state"] == "idle" else dict(_job)


def _append(text: str) -> None:
    with _lock:
        _job["log"] = (_job["log"] + text)[-LOG_MAX:]


def _steps() -> tuple[str, list[list[str]]]:
    env_apt = ["-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold",
               "-o", "DPkg::Lock::Timeout=120"]
    if shutil.which("apt-get"):
        return "apt", [["apt-get", "update", "-o", "DPkg::Lock::Timeout=120"],
                       ["apt-get", "-y", *env_apt, "upgrade"]]
    exe = shutil.which("dnf") or shutil.which("yum")
    if exe:
        return "dnf", [[exe, "-y", "upgrade"]]
    raise AdminError("No supported package manager found (apt, dnf or yum)")


def _run_update(steps: list[list[str]]) -> None:
    env = {**os.environ, "LANG": "C", "DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"}
    ok = True
    try:
        for step in steps:
            _append(f"$ {' '.join(step)}\n")
            proc = subprocess.Popen(step, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                    stdin=subprocess.DEVNULL)
            deadline = time.time() + 3600
            for line in proc.stdout:
                _append(line)
                if time.time() > deadline:
                    proc.kill()
                    _append("\nTimed out after one hour\n")
                    break
            if proc.wait() != 0:
                _append(f"\nExit code {proc.returncode}\n")
                ok = False
                break
    except OSError as error:
        _append(f"\n{error}\n")
        ok = False
    with _lock:
        _job.update(state="ok" if ok else "failed", finished=time.time())


def start_update() -> dict:
    """Starts the update in the background (it can take minutes); progress is reported with the next reports."""
    manager, steps = _steps()
    with _lock:
        if _job["state"] == "running":
            raise AdminError("An update is already running")
        _job.update(state="running", log="", started=time.time(), finished=None, manager=manager)
    threading.Thread(target=_run_update, args=(steps,), daemon=True).start()
    return {"ok": True}


def admin_action(action: str, target: str, args: dict) -> dict:
    """Entry point for the agent."""
    try:
        return _admin_action(action, target, args)
    except OSError as error:
        if error.errno == errno.EROFS:
            raise AdminError(READ_ONLY_HINT) from None
        raise


def _admin_action(action: str, target: str, args: dict) -> dict:
    args = validate(action, target, args)
    if action == "system.update":
        return start_update()
    if action in UFW_ACTIONS:
        return ufw_action(action, args)
    return user_action(action, target, args)
