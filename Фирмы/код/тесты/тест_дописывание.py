"""Возобновление: добранные фирмы обязаны лечь В ТОТ ЖЕ лист."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from openpyxl import load_workbook
from part1.excel_out import ExcelWriter
from part1.models import Firm
from part2.engine import разбор_листа, гео_на_листе

ф = Path("_тест_дописывание.xlsx")
if ф.exists():
    ф.unlink()

def фирма(имя):
    return Firm(name=имя, industry="", location_type="", city="Город",
                zip_code="12345", address="ул. Тест 1", url="",
                website=f"http://{имя.lower()}.com")

print("=== ПРОГОН 1: собрали 3 фирмы и «упали» ===")
w1 = ExcelWriter(ф, "", мульти=True)
print("  лист:", w1.sheet_name)
w1.гео = "FR"
for i in (1, 2):
    w1.фирма(фирма(f"FR-{i}"))
w1.гео = "PL"
w1.фирма(фирма("PL-1"))
print("  записано строк:", w1.n)

print()
print("=== ПРОГОН 2 (возобновление): добираем ===")
w2 = ExcelWriter(ф, "", мульти=True)
print("  лист:", w2.sheet_name, "  <- должен быть ТОТ ЖЕ")
print("  нумерация продолжается с:", w2.n)
w2.гео = "PL"
for i in (2, 3):
    w2.фирма(фирма(f"PL-{i}"))

wb = load_workbook(ф)
print()
print("  листов в файле:", wb.sheetnames)
ws = wb[w2.sheet_name]
print("  строк на листе:", ws.max_row - 1)
print()
print("  содержимое:")
for r in ws.iter_rows(min_row=2, max_col=12, values_only=True):
    print(f"     № {r[0]}  {str(r[2]):8}  гео={r[11]}")

ошибок = 0
if w1.sheet_name != w2.sheet_name:
    ошибок += 1
    print("\n  ✘ ЛИСТЫ РАЗНЫЕ — фирмы разъехались бы, Часть 2 половину не увидела")
else:
    print("\n  ✔ лист тот же")
if len([s for s in wb.sheetnames if s not in ("Лог", "Без сайта")]) != 1:
    ошибок += 1
    print("  ✘ появился лишний лист вида «23-08 (2)»")
else:
    print("  ✔ лишних листов нет")
номера = [r[0] for r in ws.iter_rows(min_row=2, max_col=1, values_only=True)]
if номера != list(range(1, len(номера) + 1)):
    ошибок += 1
    print("  ✘ нумерация сбилась:", номера)
else:
    print("  ✔ нумерация сквозная:", номера)

print()
print("  разбор для Части 2:")
for б in разбор_листа(ф, w2.sheet_name):
    print(f"     строки {б['первая']}–{б['последняя']}  {б['гео']}  {len(б['строки'])} фирм")
print("  порядок стран:", гео_на_листе(ф, w2.sheet_name))

ф.unlink()
print()
print("ошибок:", ошибок)
