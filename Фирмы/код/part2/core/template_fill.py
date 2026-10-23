"""
Шаблонные гео (Швеция, Нидерланды): официальный PDF реестр не отдаёт бесплатно,
поэтому данные вытаскиваются со страницы и подставляются в .docx-шаблон.

Идея: в шаблоне стоят плейсхолдеры {{НАЗВАНИЕ}}, {{НОМЕР}}, {{АДРЕС}} и т.д.
Скрипт делает копию шаблона, подменяет их и (если есть LibreOffice) сохраняет PDF.

Замена идёт по runs, чтобы не убить форматирование.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from docx import Document


def fill(template: Path, data: dict[str, str], dest_docx: Path) -> Path:
    doc = Document(str(template))

    def replace_in(paragraph):
        full = "".join(run.text for run in paragraph.runs)
        new = full
        for key, val in data.items():
            new = new.replace("{{" + key + "}}", val or "")
        if new != full and paragraph.runs:
            paragraph.runs[0].text = new
            for run in paragraph.runs[1:]:
                run.text = ""

    for p in doc.paragraphs:
        replace_in(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    replace_in(p)

    dest_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest_docx))
    return dest_docx


def to_pdf(docx_path: Path) -> Path | None:
    """Конвертация через LibreOffice. Нет LibreOffice — остаёмся с .docx."""
    if not shutil.which("soffice"):
        return None
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         "--outdir", str(docx_path.parent), str(docx_path)],
        check=True, capture_output=True,
    )
    pdf = docx_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None
