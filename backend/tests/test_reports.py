from app.core.pdf import Document, wrap
from conftest import csrf_headers


def test_pdf_writer_makes_valid_multi_page_file():
    doc = Document("Test (x)", "footer ü", "Page")
    doc.heading("Überschrift – Test")
    doc.table(["A", "B"], [[f"row {i} ä ö ü ß (paren) \\ back", "x" * 300] for i in range(120)], [1, 2])
    data = doc.render()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"/Type /Page ") > 1
    assert b"startxref" in data
    assert all(len(line) < 500 for line in wrap("a" * 900, 9, 200))  # long words are cut, not overflowing


def test_report_overall_and_customer(admin):
    c = admin.post("/api/customers", json={"name": "Müller GmbH", "contacts": [{"name": "Eva", "role": "Technik"}], "agreements": "24/7"}, headers=csrf_headers(admin))
    cid = c.json()["id"]
    admin.post("/api/services", json={"name": "Shop", "host": "web1", "domains": ["shop.example.org"], "ports": [{"port": 443, "label": "https"}],
                                      "customer_id": cid, "notes": "internal-secret-note"}, headers=csrf_headers(admin))
    r = admin.get("/api/reports/pdf?lang=de")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert b"internal-secret-note" not in r.content
    r = admin.get(f"/api/reports/pdf?customer={cid}&servers=false")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and b"Shop" in r.content
    assert admin.get("/api/reports/pdf?customer=nope").status_code == 404
    assert admin.get("/api/reports/pdf?servers=false&services=false").status_code == 422
    assert admin.get("/api/reports/pdf?lang=xx").status_code == 422
