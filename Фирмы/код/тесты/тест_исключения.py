"""
Исключения и состав прогона: без браузера и без сети.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part2.исключения import Исключения
import part2.engine as д2

ошибок = 0
врем = Path("исключения_тест.txt")
врем.unlink(missing_ok=True)

и = Исключения(path=врем)
и.сохранить("OSNOVNA SOLA COL\nSI: SINDIKAT VZGOJE\nBLUE ICE SP Z O O\n"
            "ICE ENGINEERING & CONSTRUCTION PTY LTD")

print("=== 1. Правовая форма и регистр не мешают ===")
СЛУЧАИ = [
    ("OSNOVNA ŠOLA COL", "SI", True,  "точное совпадение, диакритика"),
    ("osnovna sola col", "SI", True,  "нижний регистр"),
    ("BLUE ICE Sp. z o.o.", "PL", True, "другая запись правовой формы"),
    ("SINDIKAT VZGOJE", "SI", True,  "привязка к гео совпала"),
    ("SINDIKAT VZGOJE", "PL", False, "другая страна — не исключаем"),
    ("ONE d.o.o.", "SI", False, "посторонняя фирма"),
    ("BLUE ICE INVESTMENTS", "PL", False, "похожее имя, но другая фирма"),
    # Живой промах: эти трое отсеивались, потому что их имена встречаются
    # СЛОВАМИ внутри более длинных исключений. Три живые фирмы молча выпадали.
    ("Blue Ice", "BE", False, "короткое имя внутри «BLUE ICE SP Z O O»"),
    ("ICE", "FR", False, "слово «ice» внутри австралийского исключения"),
    ("ICE SA", "BE", False, "«ice» внутри чужого длинного имени"),
]
for имя, гео, ждём, почему in СЛУЧАИ:
    факт = и.исключена(имя, гео)
    знак = "✔" if факт == ждём else "✘"
    if факт != ждём:
        ошибок += 1
    print(f"   {знак} {имя[:28]:28} {гео}  →  {факт}   ({почему})")

print()
print("=== 2. Добавление и перезагрузка ===")
и.добавить("OS Col", "SI")
и2 = Исключения(path=врем)
if not и2.исключена("OS Col", "SI"):
    ошибок += 1
    print("   ✘ добавленное не сохранилось")
else:
    print(f"   ✔ сохранилось, всего строк: {len(и2.строки)}")

print()
print("=== 3. Пустой список никого не исключает ===")
пусто = Path("исключения_пусто.txt")
пусто.unlink(missing_ok=True)
и3 = Исключения(path=пусто)
if и3.исключена("ONE d.o.o.", "SI") or и3.строки:
    ошибок += 1
    print("   ✘ пустой список кого-то исключил")
else:
    print("   ✔")

print()
print("=== 4. состав_прогона читает лист ===")
from openpyxl import Workbook
кн = Path("состав_тест.xlsx")
кн.unlink(missing_ok=True)
wb = Workbook()
ws = wb.active
ws.title = "23-08"
ws.append(["№", "Профиль", "Название", "Адрес", "Город", "Индекс", "", "Сайт",
           "", "", "", "Гео"])
ws.append([1, "", "ONE d.o.o.", "Vurnikova 2", "Ljubljana", "1000", "", "", "", "", "", "SI"])
ws.append([2, "", "BLUE ICE SP Z O O", "Krakowska 83", "Andrychów", "34-120",
           "", "", "", "", "", "PL"])
ws.append([3, "", "OSNOVNA ŠOLA COL", "Col 35", "Col", "5273", "", "", "", "", "", "SI"])
wb.save(кн)
wb.close()

все = д2.состав_прогона(кн, "23-08")
только_si = д2.состав_прогона(кн, "23-08", "SI")
print(f"   всего: {len(все)} (ждём 3), только SI: {len(только_si)} (ждём 2)")
if len(все) != 3 or len(только_si) != 2:
    ошибок += 1
    print("   ✘ разбор листа неверный:", все)
else:
    print("   ✔", [f"{с['гео']}/{с['имя']}" for с in все])

берём = [с for с in все if not и2.исключена(с["имя"], с["гео"])]
print(f"   после исключений: {len(берём)} (ждём 1 — только ONE d.o.o.)")
if len(берём) != 1 or берём[0]["имя"] != "ONE d.o.o.":
    ошибок += 1
    print("   ✘", берём)
else:
    print("   ✔", берём[0]["имя"])

for f in (врем, пусто, кн):
    f.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
