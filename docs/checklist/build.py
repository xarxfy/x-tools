"""Build the beta checklist files from checklist.py (standard library only)."""

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from checklist import SECTIONS, SETUP_FIELDS, VERSION  # noqa: E402

REPORT = """\
## Reporting a problem

Open an issue (or message the maintainer) with:

```
What I did:        (steps)
What I expected:
What happened:     (error message, screenshot)
Section:           (e.g. Agents – Proxmox host)
Setup:             (see "Your setup")
Logs (if useful):  sudo docker logs --tail 50 x-tools
                   sudo docker logs --tail 50 x-tools-collector
                   journalctl -u x-tools-agent -n 50
```

**Never post passwords, tokens, agent keys or setup codes** – remove them from logs and screenshots.
"""


def markdown(for_issue: bool) -> str:
    out = []
    if for_issue:
        out.append(f"<!-- Beta test of X-TOOLS {VERSION}. Tick what works; for problems add a comment below the item "
                   "or a separate issue. The full instructions: docs/beta-testing.md -->\n")
    else:
        out.append("# Beta testing checklist\n")
        out.append("Thank you for testing X-TOOLS! Pick the sections that fit your setup – nobody needs to do "
                   "everything.\n")
        out.append("**Three ways to tick the boxes:**\n")
        out.append("- Open [`beta-checklist.html`](beta-checklist.html) in your browser (download it and open the file): "
                   "tick items, mark problems with a note, your progress is kept; at the end copy or download the "
                   "report.")
        out.append("- Create an issue from the template **Beta test** (GitLab: *New issue → Description → "
                   "Beta test*) and tick the boxes in the issue.")
        out.append("- Print this page.\n")
        out.append("**Please test on a non-critical machine or with test containers** – start/stop and Proxmox changes "
                   "work on real systems.\n")
    out.append("## Your setup\n")
    for _, label in SETUP_FIELDS:
        out.append(f"- {label}: " if for_issue else f"- {label}")
    out.append("")
    for i, (_, title, items) in enumerate(SECTIONS, 1):
        out.append(f"## {i}. {title}\n")
        for item in items:
            text = item
            if for_issue:  # relative links do not work inside issues – name the file instead
                text = re.sub(r"\[([^\]]+)\]\((?!https?://)([^)#]+)[^)]*\)", r"docs/\2", text)
            out.append(f"- [ ] {text}")
        out.append("")
    if for_issue:
        out.append("## Notes\n\n(anything else – confusing, missing, in the way)\n")
    else:
        out.append("---\n")
        out.append(REPORT)
    return "\n".join(out)


def inline(text: str) -> str:
    """Tiny markdown → HTML for checklist items."""
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noreferrer">\1</a>', t)
    return t


def build_html() -> str:
    data = {
        "version": VERSION,
        "setup": [{"id": i, "label": inline(l), "plain": l} for i, l in SETUP_FIELDS],
        "sections": [{"id": sid, "title": title, "items": [{"html": inline(x), "plain": x} for x in items]}
                     for sid, title, items in SECTIONS],
    }
    template = (HERE / "template.html").read_text(encoding="utf-8")
    return template.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__VERSION__", VERSION)


def main() -> None:
    (ROOT / "docs" / "beta-testing.md").write_text(markdown(False), encoding="utf-8")
    issue = markdown(True)
    gl = ROOT / ".gitlab" / "issue_templates"
    gl.mkdir(parents=True, exist_ok=True)
    (gl / "Beta test.md").write_text(issue + "\n/label ~beta\n", encoding="utf-8")
    gh = ROOT / ".github" / "ISSUE_TEMPLATE"
    gh.mkdir(parents=True, exist_ok=True)
    (gh / "beta-test.md").write_text(
        "---\nname: Beta test\nabout: Checklist for beta testers\ntitle: \"Beta test: <your setup>\"\n"
        "labels: beta\n---\n\n" + issue, encoding="utf-8")
    (ROOT / "docs" / "beta-checklist.html").write_text(build_html(), encoding="utf-8")
    print("written: docs/beta-testing.md, docs/beta-checklist.html, .gitlab/issue_templates/Beta test.md, "
          ".github/ISSUE_TEMPLATE/beta-test.md")


if __name__ == "__main__":
    main()
