"""Add to Home Screen: manifest, icons and the meta tags of the page (the files are in frontend/public and index.html)."""

import json
import struct
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


def test_manifest_and_icons():
    manifest = json.loads((FRONTEND / "public" / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/" and manifest["name"] == "X-TOOLS"
    pngs = [i for i in manifest["icons"] if i["type"] == "image/png"]
    assert {i["sizes"] for i in pngs} >= {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert icon["src"].startswith("/") and "/" not in icon["src"][1:], "icons must be top-level files (the server only serves those)"
        file = FRONTEND / "public" / icon["src"].lstrip("/")
        assert file.is_file(), icon["src"]
        if icon["type"] == "image/png":
            w, h = png_size(file)
            assert f"{w}x{h}" == icon["sizes"]
    assert png_size(FRONTEND / "public" / "apple-touch-icon.png") == (180, 180)


def test_page_is_installable_on_iphone():
    html = (FRONTEND / "index.html").read_text()
    for needle in ('viewport-fit=cover', 'rel="manifest"', 'rel="apple-touch-icon"', 'apple-mobile-web-app-capable',
                   'apple-mobile-web-app-title', 'name="theme-color"'):
        assert needle in html, needle


def test_manifest_is_served_by_the_app(admin):
    """Top-level files of the build are served without login (the browser fetches the manifest anonymously)."""
    from app.core.config import get_settings
    root = get_settings().frontend_dir
    if not (Path(root) / "manifest.webmanifest").exists():
        return  # frontend not built in this checkout
    r = admin.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    assert admin.get("/apple-touch-icon.png").headers["content-type"] == "image/png"
