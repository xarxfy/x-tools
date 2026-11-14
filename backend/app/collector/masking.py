"""Hide secrets in compose files, Dockerfiles, logs and git remotes."""

import re

ASSIGNMENT = re.compile(r"""^(\s*-?\s*["']?)([\w.\-\[\]'"]+?)(["']?\s*[:=]\s*)(.+)$""")
URL_CREDENTIALS = re.compile(r"(://[^:/\s@]+:)([^@\s]+)(@)")
INLINE_SECRET = re.compile(
    r"""(\b[\w.-]*(?:pass|secret|token|key|private|credential|salt|cookie)[\w.-]*["']?\s*[:=]\s*)"""
    r"""("[^"]*"|'[^']*'|[^\s,;&"']+)""", re.I)
SECRET_WORDS = {"pass", "password", "passwd", "pwd", "secret", "token", "key", "apikey", "privatekey", "private",
                "credential", "credentials", "salt", "cookie", "auth", "sessionkey", "secretkey", "accesskey"}
MASK = "••••••"


def secret_key_name(name: str) -> bool:
    """DB_PASSWORD, api_key, apiKey, accessToken → True; monkey, tokenizer, keys → False."""
    for part in re.split(r"[^a-z0-9]+", name.lower()):
        if part in SECRET_WORDS or part.endswith(("password", "passwd", "secret", "token")):
            return True
    return False


def mask_url(text: str) -> str:
    return URL_CREDENTIALS.sub(rf"\1{MASK}\3", text)


def mask_secrets(text: str) -> str:
    """Mask values of keys like PASSWORD, TOKEN, *_KEY line by line.
    References like ${VAR}, paths and block markers (| >) stay visible."""
    lines = []
    for line in text.split("\n"):
        line = mask_url(line)
        m = ASSIGNMENT.match(line)
        if m and secret_key_name(m.group(2)):
            value = m.group(4).strip().strip("\"'")
            keep = (not value or value.startswith(("$", "|", ">", "/", "./", "~", "{", "[", "#", "ENV["))
                    or value.lower().startswith("http") or value.lower() in ("true", "false", "null"))
            if not keep:
                line = m.group(1) + m.group(2) + m.group(3) + MASK
        # KEY=value later in the line, e.g. Dockerfile "ENV API_TOKEN=abc" or "--password=abc"
        lines.append(mask_inline(line))
    return "\n".join(lines)


def mask_inline(text: str) -> str:
    """For logs: also mask key=value in the middle of a line (DB_PASSWORD=…, "token": "…")."""
    def repl(m):
        key = re.match(r"[\w.-]+", m.group(1)).group(0)
        if not secret_key_name(key):
            return m.group(0)
        value = m.group(2).strip("\"'")
        if not value or value.startswith(("$", "•", "/", "./", "~")) or value.lower() in ("true", "false", "null", "none"):
            return m.group(0)
        return m.group(1) + MASK
    return INLINE_SECRET.sub(repl, mask_url(text))
