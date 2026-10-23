import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from part1.excel_out import ExcelWriter
from part1.models import Firm
import part2.engine as д2

ф = Path("_проверка_разбор.xlsx")
if ф.exists():
    ф.unlink()

# 10 Франции, затем 10 Польши — ровно твой пример
w = ExcelWriter(ф, "", мульти=True)
for гео, n in (("FR", 10), ("PL", 10)):
    w.гео = гео
    for i in range(n):
        w.фирма(Firm(name=f"{гео}-ФИРМА-{i+1}", industry="", location_type="",
                     city="Город", zip_code=f"1000{i}", address="ул. Тест 1",
                     url="", website=f"http://{гео.lower()}{i}.com"))

print("лист:", w.sheet_name)
print()
print("=== РАЗБОР ЛИСТА ===")
for б in д2.разбор_листа(ф, w.sheet_name):
    print(f"   строки {б['первая']}–{б['последняя']}  {б['гео']}  "
          f"{len(б['строки'])} фирм")
print()
ожидание = {"FR": (2, 11), "PL": (12, 21)}
ошибок = 0
for б in д2.разбор_листа(ф, w.sheet_name):
    ждём = ожидание.get(б["гео"])
    вышло = (б["первая"], б["последняя"])
    if ждём != вышло:
        ошибок += 1
        print(f"   ✘ {б['гео']}: ждали строки {ждём}, вышло {вышло}")
    else:
        print(f"   ok {б['гео']}: строки {вышло[0]}–{вышло[1]} — как ожидалось")

print()
print("порядок стран:", д2.гео_на_листе(ф, w.sheet_name))

# --- страна кусками: дописываем ещё немного Франции в конец ---
w2 = ExcelWriter(ф, "", мульти=True)
w2.гео = "FR"
for i in range(2):
    w2.фирма(Firm(name=f"FR-ДОБОР-{i+1}", industry="", location_type="",
                  city="Город", zip_code="99999", address="ул. Добор 1",
                  url="", website=f"http://frd{i}.com"))
print()
print("=== ВТОРОЙ ЛИСТ (проверка разрыва блоков) ===")
# на новом листе FR один блок; смешаем руками на первом листе
from openpyxl import load_workbook
wb = load_workbook(ф)
ws = wb[w.sheet_name]
ws.cell(row=22, column=1, value=21)
ws.cell(row=22, column=3, value="FR-ХВОСТ")
ws.cell(row=22, column=12, value="FR")
wb.save(ф)
блоки = д2.разбор_листа(ф, w.sheet_name)
for б in блоки:
    print(f"   строки {б['первая']}–{б['последняя']}  {б['гео']}  {len(б['строки'])}")
кусков_fr = sum(1 for б in блоки if б["гео"] == "FR")
print(f"   FR лежит {кусков_fr} кусками — должно быть 2")
if кусков_fr != 2:
    ошибок += 1

print()
print("ошибок:", ошибок)
ф.unlink()
print("временный файл удалён")
