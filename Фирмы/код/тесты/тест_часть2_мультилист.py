import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from part1.excel_out import ExcelWriter
from part1.models import Firm
import part2.engine as д2

ф = Path("_проверка_ч2.xlsx")
if ф.exists():
    ф.unlink()

# Мультилист: FR, PL, DE и «XX» — гео, для которого драйвера нет
w = ExcelWriter(ф, "", мульти=True)
for гео, сколько in (("FR", 2), ("PL", 3), ("DE", 1), ("XX", 2)):
    w.гео = гео
    for i in range(сколько):
        w.фирма(Firm(name=f"{гео}-ФИРМА-{i+1}", industry="", location_type="",
                     city="Город", zip_code="1000" + str(i), address="ул. Тест 1",
                     url="", website=f"http://{гео.lower()}{i}.com"))
print("лист:", w.sheet_name)
print("порядок стран:", д2.гео_на_листе(ф, w.sheet_name))
print("драйверы есть для:", [г for г in д2.гео_на_листе(ф, w.sheet_name) if г in д2.DRIVERS])
print()

# --- подменяем run(), чтобы не поднимать браузер ---
вызовы = []
настоящий = д2.run

def фейк(geo, excel, out_dir, human, log=print, sheet=None, stop=None,
         pause=None, фильтр_гео=None, папка_прогона=None,
         только_недостающие=False, мультигео=False):
    # честно читаем лист тем же способом, что и настоящий run
    from openpyxl import load_workbook
    wb = load_workbook(excel)
    ws = wb[sheet]
    к = д2._найти_столбец(ws, д2.ГЕО)
    свои = []
    for r in ws.iter_rows(min_row=2, min_col=1, max_col=11):
        з = str(ws.cell(row=r[0].row, column=к).value or "").strip().upper()
        if фильтр_гео and з != фильтр_гео.upper():
            continue
        if r[2].value:
            свои.append(str(r[2].value))
    вызовы.append({"гео": geo, "лист": sheet, "фильтр": фильтр_гео, "фирмы": свои})
    log(f"   (фейк) гео {geo}: взял {len(свои)} фирм — {свои}")
    return {"скачано": len(свои), "всего": len(свои)}

д2.run = фейк
try:
    итог = д2.run_мультилист(ф, w.sheet_name, Path("выписки"), human=None,
                             log=lambda s: print(s))
finally:
    д2.run = настоящий

print()
print("=== ПРОВЕРКА ===")
ошибки = 0
for в in вызовы:
    чужие = [имя for имя in в["фирмы"] if not имя.startswith(в["гео"] + "-")]
    if чужие:
        ошибки += 1
        print(f"  ✘ гео {в['гео']}: затесались чужие фирмы {чужие}")
    else:
        print(f"  ok гео {в['гео']}: {len(в['фирмы'])} фирм, все свои")
if any(в["гео"] == "XX" for в in вызовы):
    ошибки += 1
    print("  ✘ XX без драйвера всё-таки запустился")
else:
    print("  ok XX без драйвера пропущен")
print()
print("ошибок:", ошибки)
print("итог:", итог["скачано"], "из", итог["всего"], "| без драйвера:", итог["без_драйвера"])

ф.unlink()
print("временный файл удалён")
