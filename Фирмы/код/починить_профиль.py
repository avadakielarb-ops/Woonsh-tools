"""
ПЕРЕЧИТАТЬ КАРТОЧКИ И ПЕРЕПИСАТЬ «Платёжный профиль выписки».

Когда драйвер гео читал страницу неверно, в колонку K уезжала чепуха. Пример
Хорватии до починки разбора карточки:

    Sjedište/adresa
    Address: Temeljni kapital, Pravni oblik
    Website: www.iceproduct.hr

Это подписи полей, а не данные: слева на карточке висит оглавление с теми же
словами, и «значением» становился следующий пункт меню.

Скрипт открывает карточку КАЖДОЙ фирмы по её номеру из колонки «Номер в
реестре», перечитывает имя и адрес уже исправленным драйвером и переписывает
колонку K. Выписки НЕ качаются заново: PDF уже есть, и бронь в реестре не
тратится.

Запуск:  .venv\\Scripts\\python.exe починить_профиль.py HR [лист]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import load_workbook

from common import пути
from openpyxl.styles import Alignment

from common.browser import Browser
from common.human import HumanGate
from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.registry import DRIVERS


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
        print("укажи гео: починить_профиль.py HR [лист]")
        return 1
    гео = sys.argv[1].upper()
    лист = sys.argv[2] if len(sys.argv) > 2 else "23-08"
    if гео not in DRIVERS:
        print(f"нет драйвера для {гео}")
        return 1
    кн = книга_с_листом(лист)
    if not кн:
        print(f"не нашёл книгу с листом «{лист}»")
        return 1

    wb = load_workbook(кн)
    ws = wb[лист]
    заг = {ws.cell(row=1, column=c).value: c for c in range(1, 41)
           if ws.cell(row=1, column=c).value}
    к_гео = заг.get("Гео")
    к_проф = заг.get("Платёжный профиль выписки")
    к_номер = заг.get("Номер в реестре")
    к_сайт = заг.get("Website", 8)
    if not (к_гео and к_проф and к_номер):
        print("на листе нет нужных колонок")
        return 1

    цели = []
    for r in ws.iter_rows(min_row=2, max_col=max(заг.values())):
        стр = r[0].row
        if str(ws.cell(row=стр, column=к_гео).value or "").strip().upper() != гео:
            continue
        номер = str(ws.cell(row=стр, column=к_номер).value or "").strip()
        if номер:
            цели.append((стр, номер,
                         str(ws.cell(row=стр, column=3).value or "").strip(),
                         str(ws.cell(row=стр, column=к_сайт).value or "").strip()))
    if not цели:
        print(f"на листе «{лист}» нет строк {гео} с номером в реестре")
        return 0
    print(f"перечитаю карточек: {len(цели)}")

    human = HumanGate()
    исправлено = 0
    with Browser(profile=гео, human=human, log=print) as br:
        d = DRIVERS[гео](br, human)
        d.log = print
        for стр, номер, имя, сайт in цели:
            c = Company(row=стр, name=имя, address="", city="", zip_code="",
                        website=сайт)
            try:
                d.open(Candidate(name=имя, address="", ref=номер))
                d.check(c)
                данные = d.данные_реестра() or {}
            except Exception as e:
                print(f"  ✘ стр.{стр} {имя[:30]}: {type(e).__name__}: {e}")
                continue
            новое_имя = (данные.get("имя") or "").strip()
            адрес = (данные.get("адрес") or "").strip()
            if not новое_имя or not адрес:
                print(f"  ⚠ стр.{стр} {имя[:30]}: карточка не прочиталась")
                continue
            чистый = re.sub(r"^https?://", "", сайт).rstrip("/") if сайт else ""
            блок = f"{новое_имя}\nAddress: {адрес}\nWebsite: {чистый}"
            яч = ws.cell(row=стр, column=к_проф, value=блок)
            яч.alignment = Alignment(wrap_text=True, vertical="top")
            исправлено += 1
            print(f"  ✔ стр.{стр}: {новое_имя[:44]} | {адрес[:40]}")
    wb.save(кн)
    wb.close()
    print(f"\nисправлено строк: {исправлено} из {len(цели)}  →  {кн}")

    from part2.engine import пересобрать_книги_листа
    пересобрать_книги_листа(кн, лист)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
