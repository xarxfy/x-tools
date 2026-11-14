"""POST JSON with the standard library (used by notifications and the agent)."""

import json
import urllib.error
import urllib.request


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "x-tools",
                                          **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read() or b"{}")
            detail = data.get("description") or data.get("error") or data.get("detail")
        except (ValueError, AttributeError):
            detail = None
        raise OSError(f"HTTP {error.code}{': ' + str(detail) if detail else ''}") from None
    except urllib.error.URLError as error:
        raise OSError(f"not reachable ({error.reason})") from None
