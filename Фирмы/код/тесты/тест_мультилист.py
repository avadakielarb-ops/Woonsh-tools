import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from part1.excel_out import ExcelWriter
from part1.models import Firm
from part2.engine import гео_на_листе, _найти_столбец, ГЕО
from openpyxl import load_workbook

for мусор in ("_тест_мультигео.xlsx", "_проверка_мультилист.xlsx"):
    p = Path(мусор)
    if p.exists():
        p.unlink()

ф = Path("_проверка_мультилист.xlsx")
w = ExcelWriter(ф, "", мульти=True)
print("лист:", repr(w.sheet_name), "— должен быть просто датой, без кода страны")

for гео, имена in (("FR", ["ALPHA SAS", "BETA SARL"]),
                   ("PL", ["GAMMA SP Z O O"]),
                   ("DE", ["DELTA GMBH"])):
    w.гео = гео
    for имя in имена:
        w.фирма(Firm(name=имя, industry="", location_type="", city="Город",
                     zip_code="12345", address="ул. Тестовая 1", url="",
                     website="http://" + имя.split()[0].lower() + ".com"))
    w.без_сайта(Firm(name="БЕЗСАЙТА-" + гео, industry="", location_type="",
                     city="Город", zip_code="00000", address="ул. Без 2", url=""))

wb = load_workbook(ф)
ws = wb[w.sheet_name]
print()
print("шапка:", [c.value for c in ws[1]])
к = _найти_столбец(ws, ГЕО)
print("колонка", ГЕО, "найдена под номером:", к, "(ждём 12 = L)")
print()
print("строки листа (нумерация должна быть сквозной 1..4):")
for r in ws.iter_rows(min_row=2, max_col=12, values_only=True):
    print("   N", r[0], " ", str(r[2])[:22].ljust(22),
          "website=", str(r[7])[:26].ljust(26), "гео=", r[11])
print()
print("порядок стран на листе:", гео_на_листе(ф, w.sheet_name))
print()
print("лист «Без сайта» (последняя колонка — гео):")
for r in wb["Без сайта"].iter_rows(min_row=1, max_col=5, values_only=True):
    print("   ", r)

# Часть 3 читает «Без сайта» по индексам 0..3 — проверим, что гео ей не мешает
print()
print("проверка совместимости с Частью 3 (читает колонки A..D):")
for r in wb["Без сайта"].iter_rows(min_row=2, max_col=4, values_only=True):
    орг, адрес, город, индекс = r
    ок = bool(орг) and bool(адрес)
    print("   ", "ok " if ок else "ПЛОХО", orgs := (орг, адрес, город, индекс))

ф.unlink()
print()
print("готово, временный файл удалён")
