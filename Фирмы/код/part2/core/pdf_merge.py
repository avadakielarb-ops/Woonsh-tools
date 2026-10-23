"""
Склейка нескольких PDF в один.

Нужна Британии: у переименованной фирмы выписка = Incorporation + все документы
о смене имени, склеенные по возрастанию даты (Incorporation всегда первым).

Если библиотеки нет или склейка упала — возвращаем None, и драйвер положит файлы
в папку с названием фирмы (склеишь вручную). Фирма в любом случае не теряется.
"""
from __future__ import annotations

from pathlib import Path


def склеить(файлы: list[Path], dest: Path) -> Path | None:
    """Склеить PDF в порядке списка. Не вышло — None."""
    if not файлы:
        return None
    try:
        from pypdf import PdfWriter
    except Exception:
        try:
            from PyPDF2 import PdfWriter          # старое имя пакета
        except Exception:
            return None
    try:
        writer = PdfWriter()
        for f in файлы:
            writer.append(str(f))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            writer.write(fh)
        return dest if dest.exists() and dest.stat().st_size > 0 else None
    except Exception:
        return None
