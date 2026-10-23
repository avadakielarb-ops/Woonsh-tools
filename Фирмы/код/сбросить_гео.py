"""
СБРОСИТЬ ГЕО — удалить его выписки и снять отметку «скачано», чтобы Часть 2
прошла страну заново.

Нужно, когда драйвер гео работал неверно и файлы получились негодными. Пример
Хорватии: разбор читал меню карточки вместо данных, поэтому все десять PDF
легли под одним именем «Sjedište adresa.pdf» («Местонахождение/адрес» — это
подпись поля, а не название фирмы), и по такому файлу не понять, чья это
выписка.

Что делает:
  1. удаляет PDF этого гео из папки листа;
  2. чистит «Номер в реестре», «Файл выписки» и «Платёжный профиль выписки»
     в строках этого гео — САМИ ФИРМЫ ОСТАЮТСЯ, меняется только результат;
  3. снимает отметку «использована» в реестре фирм, иначе Часть 2 скажет
     «уже скачана» и пройдёт мимо;
  4. пересобирает книги листа.

Запуск:  .venv\\Scripts\\python.exe сбросить_гео.py HR [лист]
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

from common import пути

from part1.registry import LocalFileRegistry, отпечаток
from part2.engine import папка_листа, пересобрать_книги_листа

ЧИСТИТЬ = ("Номер в реестре", "Файл выписки", "Платёжный профиль выписки",
           "Адрес по выписке")


def книга_с_листом(лист: str) -> Path | None:
    for кн in пути.книги_мультигео():
        try:
            wb = load_workbook(кн, read_only=True)
            есть = лист in wb.sheetnames
            wb.close()
            if есть:
                return кн
        except Exception:
            continue
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("укажи гео: сбросить_гео.py HR [лист]")
        return 1
    гео = sys.argv[1].upper()
    лист = sys.argv[2] if len(sys.argv) > 2 else "23-08"
    кн = книга_с_листом(лист)
    if not кн:
        print(f"не нашёл книгу с листом «{лист}»")
        return 1

    папка = папка_листа(пути.ВЫПИСКИ, лист) / гео
    файлов = list(папка.glob("*.pdf")) if папка.exists() else []
    print(f"выписок {гео} на диске: {len(файлов)}")

    wb = load_workbook(кн)
    ws = wb[лист]
    заг = {ws.cell(row=1, column=c).value: c for c in range(1, 41)
           if ws.cell(row=1, column=c).value}
    к_гео = заг.get("Гео")
    if not к_гео:
        print("на листе нет колонки «Гео»")
        return 1

    reg = LocalFileRegistry(log=print)
    строк = снято = 0
    for r in ws.iter_rows(min_row=2, max_col=max(заг.values())):
        с = r[0].row
        if str(ws.cell(row=с, column=к_гео).value or "").strip().upper() != гео:
            continue
        имя = str(ws.cell(row=с, column=3).value or "").strip()
        if not имя:
            continue
        строк += 1
        for подпись in ЧИСТИТЬ:
            if подпись in заг:
                ws.cell(row=с, column=заг[подпись]).value = None
        fp = отпечаток(имя, гео,
                       str(ws.cell(row=с, column=6).value or ""),
                       str(ws.cell(row=с, column=5).value or ""))
        # «использована» снимаем через снять_бронь: фирма снова свободна
        if fp in reg.данные.get("использованы", []):
            reg.данные["использованы"].remove(fp)
            снято += 1
    reg._save()
    wb.save(кн)
    wb.close()

    for f in файлов:
        try:
            f.unlink()
        except Exception as e:
            print(f"   не смог удалить {f.name}: {e}")

    print(f"строк {гео} очищено: {строк}")
    print(f"отметок «скачано» снято: {снято}")
    print(f"файлов удалено: {len(файлов)}")
    пересобрать_книги_листа(кн, лист)
    print(f"\nТеперь запусти Часть 2 по {гео} — она пройдёт страну заново.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
