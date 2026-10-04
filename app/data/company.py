"""Facts about the company read from the workspace's COMPANY.md (name, people, approval rule, email
domain), so the app carries no company-specific constants."""

import re
from pathlib import Path

from app.data import workspace


def text() -> str:
    for base in (workspace.root(), workspace.seed()):
        p = Path(base) / "COMPANY.md"
        if p.exists():
            return p.read_text()
    return ""


def name() -> str:
    m = re.search(r"^# COMPANY\.md - (.+?)(?: \(|$)", text(), re.M)
    return m.group(1).strip() if m else "the company"


def domain() -> str:
    m = re.search(r"^Email domain: (\S+)", text(), re.M)
    return m.group(1).strip() if m else "example.com"


def people() -> list[dict]:
    """[{name, role, email}] from the '## People' section, in file order."""
    section = re.search(r"^## People\n(.*?)(?:\n## |\Z)", text(), re.M | re.S)
    out = []
    for m in re.finditer(r"^- (.+?) - (.+)$", section.group(1) if section else "", re.M):
        person = m.group(1).strip()
        email = ".".join(person.lower().split()) + "@" + domain()
        out.append(dict(name=person, role=m.group(2).strip(), email=email))
    return out


def short(person: str) -> str:
    """'Victoria Cheung' -> 'V. Cheung'."""
    first, *rest = person.split()
    return f"{first[0]}. {' '.join(rest)}" if rest else person


def approver() -> tuple[str | None, float | None, str | None]:
    """(person, limit in HKD, the line it came from) for 'Approves anything above HK$...'."""
    m = re.search(r"^- (.+?) - .*?(Approves anything above HK\$([\d,]+)\.?)", text(), re.M)
    if not m:
        return None, None, None
    return m.group(1).strip(), float(m.group(3).replace(",", "")), m.group(2)


def forecast_range() -> tuple[str, str]:
    """(named range, workbook) for the rent forecast cells: 'named range X in sheets/....xlsx'."""
    m = re.search(r"named range (\w+) in (\S+\.xlsx)", text())
    return (m.group(1), m.group(2)) if m else ("RENT_FORECAST", "sheets/forecast_2027_2028.xlsx")
