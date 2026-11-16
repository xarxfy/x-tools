"""A tiny PDF writer for reports: text, headings and tables on A4 pages with the built-in Helvetica fonts.

No dependency on purpose. Text is encoded as Windows-1252 (umlauts work, characters outside it become '?').
"""

W, H, M = 595.0, 842.0, 42.0  # A4 in points, margin

_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + [
    278, 278, 584, 584, 584, 556, 1015,
    667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
    667, 667, 611, 278, 278, 278, 469, 556, 333,
    556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
    500, 500, 500, 334, 260, 334, 584]


def clean(text) -> str:
    s = str(text if text is not None else "").replace("\r", "").replace("\t", " ")
    s = "".join(c if c == "\n" or c >= " " else " " for c in s)
    return s.encode("cp1252", "replace").decode("cp1252")


def width(text: str, size: float, bold: bool = False) -> float:
    total = 0
    for c in text:
        o = ord(c)
        total += _W[o - 32] if 32 <= o < 127 else 556
    return total * size / 1000 * (1.06 if bold else 1.0)


def wrap(text: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    for para in clean(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            while width(word, size, bold) > max_w and len(word) > 1:  # a word longer than the cell: cut it
                cut = len(word)
                while cut > 1 and width(word[:cut], size, bold) > max_w:
                    cut -= 1
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:cut])
                word = word[cut:]
            trial = f"{cur} {word}" if cur else word
            if cur and width(trial, size, bold) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines or [""]


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Document:
    def __init__(self, title: str, footer: str, page_word: str = "Page"):
        self.title, self.footer, self.page_word = clean(title), clean(footer), page_word
        self.pages: list[list[str]] = []
        self.y = 0.0
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = H - M

    def _put(self, cmd: str) -> None:
        self.pages[-1].append(cmd)

    def _text(self, x: float, y: float, s: str, size: float, bold: bool = False, gray: float = 0.0) -> None:
        self._put(f"BT /{'F2' if bold else 'F1'} {size:.1f} Tf {gray:.2f} g {x:.1f} {y:.1f} Td ({_esc(s)}) Tj ET")

    def _rect(self, x: float, y: float, w: float, h: float, gray: float) -> None:
        self._put(f"{gray:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def _line(self, x1: float, y: float, x2: float, gray: float = 0.8) -> None:
        self._put(f"{gray:.2f} G 0.5 w {x1:.1f} {y:.1f} m {x2:.1f} {y:.1f} l S")

    def space(self, h: float) -> None:
        self.y -= h

    def ensure(self, h: float) -> None:
        if self.y - h < M + 20:
            self._new_page()

    def heading(self, text: str, size: float = 15) -> None:
        self.ensure(size * 3)
        self.y -= size
        self._text(M, self.y, clean(text), size, bold=True)
        self.y -= size * 0.5

    def paragraph(self, text: str, size: float = 9.5, gray: float = 0.25) -> None:
        for line in wrap(text, size, W - 2 * M):
            self.ensure(size * 1.5)
            self.y -= size * 1.35
            self._text(M, self.y, line, size, gray=gray)

    def facts(self, pairs: list[tuple[str, str]], size: float = 9.5) -> None:
        for label, value in pairs:
            if not value:
                continue
            lines = wrap(value, size, W - 2 * M - 110)
            self.ensure(size * 1.5 * len(lines))
            self.y -= size * 1.4
            self._text(M, self.y, clean(label), size, gray=0.45)
            self._text(M + 110, self.y, lines[0], size)
            for extra in lines[1:]:
                self.y -= size * 1.4
                self._text(M + 110, self.y, extra, size)

    def table(self, headers: list[str], rows: list[list[str]], weights: list[float], size: float = 8.5) -> None:
        avail = W - 2 * M
        total = sum(weights)
        widths = [avail * w / total for w in weights]
        pad = 4.0
        lead = size * 1.3

        def head() -> None:
            self.ensure(lead * 3)
            self._rect(M, self.y - lead - pad, avail, lead + pad, 0.93)
            x = M
            for h, cw in zip(headers, widths):
                self._text(x + pad, self.y - lead + 1, wrap(h, size, cw - 2 * pad, True)[0], size, bold=True, gray=0.3)
                x += cw
            self.y -= lead + pad

        head()
        for row in rows:
            cells = [wrap(c, size, cw - 2 * pad) for c, cw in zip(row, widths)]
            height = max(len(c) for c in cells) * lead + pad
            if self.y - height < M + 20:
                self._new_page()
                head()
            x = M
            for lines, cw in zip(cells, widths):
                for i, line in enumerate(lines):
                    self._text(x + pad, self.y - lead * (i + 1) + 2, line, size)
                x += cw
            self.y -= height
            self._line(M, self.y, W - M)
        self.y -= 6

    def render(self) -> bytes:
        objs: list[bytes] = []

        def add(body: bytes) -> int:
            objs.append(body)
            return len(objs)

        add(b"<< /Type /Catalog /Pages 2 0 R >>")
        add(b"")  # pages, filled below
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        count = len(self.pages)
        for n, page in enumerate(self.pages, 1):
            foot = [f"0.5 G 0.5 w {M:.1f} {M - 8:.1f} m {W - M:.1f} {M - 8:.1f} l S"]
            left = _esc(self.footer)
            right = _esc(f"{self.page_word} {n}/{count}")
            foot.append(f"BT /F1 8 Tf 0.5 g {M:.1f} {M - 20:.1f} Td ({left}) Tj ET")
            foot.append(f"BT /F1 8 Tf 0.5 g {W - M - width(right, 8):.1f} {M - 20:.1f} Td ({right}) Tj ET")
            stream = "\n".join(page + foot).encode("cp1252", "replace")
            sid = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            pid = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W:.0f} {H:.0f}] /Contents {sid} 0 R "
                      f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> >>".encode())
            kids.append(pid)
        objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
        info = add(f"<< /Title ({_esc(self.title)}) /Producer (X-TOOLS) >>".encode("cp1252", "replace"))
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)
