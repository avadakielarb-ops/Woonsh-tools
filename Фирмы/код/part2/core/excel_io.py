"""Чтение списка фирм из Excel Части 1 (лист = дата прогона)."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from part2.core.models import Company

# Ищем эти заголовки, регистр не важен
HEADERS = {
    "название": "name", "name": "name",
    "адрес": "address", "address": "address",
    "город": "city", "индекс": "zip_code",
    "вебсайт": "website", "сайт": "website", "website": "website",
}


def read_companies(path: Path, sheet: str | None = None) -> list[Company]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[-1]]   # по умолчанию последний лист

    rows = ws.iter_rows(values_only=False)
    header_row = next(rows)
    cols: dict[str, int] = {}
    for cell in header_row:
        key = HEADERS.get(str(cell.value or "").strip().lower())
        if key:
            cols[key] = cell.column - 1

    companies: list[Company] = []
    for r in rows:
        vals = [c.value for c in r]

        def get(k: str) -> str:
            i = cols.get(k)
            return str(vals[i]).strip() if i is not None and i < len(vals) and vals[i] else ""

        name = get("name")
        if not name:
            continue
        companies.append(Company(
            row=r[0].row, name=name, address=get("address"),
            city=get("city"), zip_code=get("zip_code"), website=get("website"),
        ))
    return companies
