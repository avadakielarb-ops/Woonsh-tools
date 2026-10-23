"""Имена файлов. Глобальное правило Части 2: КАЖДАЯ выписка называется по фирме."""
from __future__ import annotations

import re
from pathlib import Path

BAD = r'[\\/:*?"<>|]'


def safe_name(company: str) -> str:
    """
    Имя фирмы → безопасное имя файла.
    ПУСТЫМ НЕ БЫВАЕТ: иначе получались файлы «.pdf», «(2).pdf», «(3).pdf» —
    выписки без названия, которые невозможно сопоставить с фирмой.
    """
    # точки НЕ трогаем: правовая форма — часть имени («INVITAL aqua s.r.o.»)
    s = re.sub(BAD, " ", company or "").strip()
    s = re.sub(r"\s+", " ", s)[:120].strip()
    return s or "БЕЗ ИМЕНИ"


def target_path(out_dir: Path, company: str, ext: str = ".pdf") -> Path:
    """
    Куда класть выписку. ПАПКУ СОЗДАЁМ ИМЕННО ЗДЕСЬ — в тот момент, когда файл
    реально понадобился.

    Раньше папку прогона создавали заранее, до первой фирмы, и каждый
    сорвавшийся запуск оставлял пустышку: на диске нашлось шесть таких (DK, HU,
    PL и три датированные). Открывать их, чтобы убедиться в пустоте, —
    ровно та работа, которой быть не должно.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{safe_name(company)}{ext}"
    i = 2
    while p.exists():                       # дубли не перетираем
        p = out_dir / f"{safe_name(company)} ({i}){ext}"
        i += 1
    return p
