"""
Собрать ИТОГОВЫЕ КНИГИ в папку листа: «Мультигео <лист>.xlsx» и «не_вышло.xlsx».

Обычно их пишет сам прогон. Этот скрипт нужен, когда книги потерялись (чистка,
ручной разбор папок) или когда хочется пересобрать их по текущему состоянию
рабочей книги, ничего не перезапуская.

Источник истины — рабочая книга «Мультигео <лист>.xlsx» в корне проекта:
в ней и «Платёжный профиль выписки», и «Файл выписки», и «Гео».

Запуск:  .venv\\Scripts\\python.exe свести_книги_листа.py [лист]
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

from common import пути

from part2.engine import _обновить_свод, папка_листа

ВЫПИСКИ = Path("выписки")


def книга_листа(лист: str) -> Path | None:
    """Рабочая книга в корне проекта, где лежит этот лист."""
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
    лист = sys.argv[1] if len(sys.argv) > 1 else ""
    if not лист:
        # лист по умолчанию — тот, чья папка уже есть в выписках
        папки = [p.name for p in (ВЫПИСКИ / "Мультигео").glob("*") if p.is_dir()] \
            if (ВЫПИСКИ / "Мультигео").exists() else []
        if len(папки) == 1:
            лист = папки[0]
        else:
            print("укажи лист: свести_книги_листа.py 23-08")
            print("папки листов:", ", ".join(папки) or "нет")
            return 1

    кн = книга_листа(лист)
    if not кн:
        print(f"не нашёл рабочую книгу с листом «{лист}» в корне проекта")
        return 1
    куда = папка_листа(ВЫПИСКИ, лист)
    куда.mkdir(parents=True, exist_ok=True)
    print(f"источник: {кн}   →   {куда}")

    wb = load_workbook(кн, data_only=True)
    ws = wb[лист]
    заг = {ws.cell(row=1, column=c).value: c for c in range(1, 41)
           if ws.cell(row=1, column=c).value}
    к_гео = заг.get("Гео")
    к_проф = заг.get("Платёжный профиль выписки")
    к_файл = заг.get("Файл выписки")
    к_имя = заг.get("Организация", 3)

    по_гео: dict[str, list] = {}
    плохие: dict[str, list] = {}
    for r in ws.iter_rows(min_row=2, max_col=max(заг.values())):
        стр = r[0].row
        гео = str(ws.cell(row=стр, column=к_гео).value or "").strip().upper() \
            if к_гео else ""
        имя = str(ws.cell(row=стр, column=к_имя).value or "").strip()
        if not имя:
            continue
        проф = ws.cell(row=стр, column=к_проф).value if к_проф else None
        файл = str(ws.cell(row=стр, column=к_файл).value or "").strip() if к_файл else ""
        if проф and файл:
            по_гео.setdefault(гео, []).append([гео, проф])
        else:
            причина = "нет выписки" if not файл else "нет платёжного профиля"
            плохие.setdefault(гео, []).append([гео, имя, "не скачано", причина])
    wb.close()

    итог_проф = куда / кн.name
    итог_плохо = куда / "не_вышло.xlsx"
    итог_проф.unlink(missing_ok=True)
    итог_плохо.unlink(missing_ok=True)

    всего = 0
    for гео, строки in sorted(по_гео.items()):
        всего = _обновить_свод(итог_проф, гео,
                               ["Гео", "Платёжный профиль выписки"], строки,
                               [8, 60], перенос=1)
    n_плохих = 0
    for гео, строки in sorted(плохие.items()):
        n_плохих = _обновить_свод(итог_плохо, гео,
                                  ["Гео", "Фирма", "Что случилось", "Причина"],
                                  строки, [8, 42, 30, 50])

    print(f"  ✔ {итог_проф.name}: {всего} фирм с выписками")
    print(f"  ✔ {итог_плохо.name}: {n_плохих} фирм без выписки")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
