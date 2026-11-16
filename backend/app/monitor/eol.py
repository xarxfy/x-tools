"""End of support of the common Linux distributions – a hint in the inventory, not a promise.

Dates are the end of standard security support as announced by the distributions; check the vendor if it matters.
"""

from datetime import date, timedelta

# (distribution id from /etc/os-release, VERSION_ID) → last day of security support
SUPPORT_END: dict[tuple[str, str], date] = {
    ("debian", "9"): date(2020, 7, 6), ("debian", "10"): date(2024, 6, 30), ("debian", "11"): date(2026, 8, 31),
    ("debian", "12"): date(2028, 6, 30), ("debian", "13"): date(2030, 6, 30),
    ("ubuntu", "16.04"): date(2021, 4, 30), ("ubuntu", "18.04"): date(2023, 5, 31),
    ("ubuntu", "20.04"): date(2025, 5, 31), ("ubuntu", "22.04"): date(2027, 4, 30),
    ("ubuntu", "24.04"): date(2029, 4, 30),
    ("centos", "7"): date(2024, 6, 30), ("centos", "8"): date(2021, 12, 31),
    ("rocky", "8"): date(2029, 5, 31), ("rocky", "9"): date(2032, 5, 31),
    ("almalinux", "8"): date(2029, 3, 1), ("almalinux", "9"): date(2032, 5, 31),
    ("rhel", "8"): date(2029, 5, 31), ("rhel", "9"): date(2032, 5, 31),
}
SOON = timedelta(days=120)


def support(os_id: str, version: str, today: date | None = None) -> dict:
    """{"state": "ok" | "soon" | "eol" | "unknown", "until": "YYYY-MM-DD" | ""}"""
    end = SUPPORT_END.get(((os_id or "").lower(), version or ""))
    if end is None:
        return {"state": "unknown", "until": ""}
    today = today or date.today()
    state = "eol" if end < today else "soon" if end - today <= SOON else "ok"
    return {"state": state, "until": end.isoformat()}
