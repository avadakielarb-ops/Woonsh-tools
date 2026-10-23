"""
Замена дубликатов ложится В ТОТ ЖЕ ЛИСТ и В ТЕ ЖЕ СТРОКИ.

Самая опасная ошибка здесь — уехать на новый лист с сегодняшней датой: лист
«23-08» качается 25-го, Часть 2 продолжит читать старый, и фирма выпадет.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openpyxl import Workbook, load_workbook
from part1.excel_out import ExcelWriter
from part1.models import Firm
from part2 import дубликаты as дуб

ошибок = 0
кн = Path("замена_тест.xlsx")
кн.unlink(missing_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "23-08"
ws.append(["№", "Профиль", "Организация", "Адрес", "Город", "Индекс", "Штат",
           "Website", "Номер", "Файл выписки", "Профиль выписки", "Гео"])
for n, имя, гео in ((1, "СТАРАЯ ОДИН", "PL"), (2, "СТАРАЯ ДВА", "PL"),
                    (3, "ЧУЖАЯ", "SI")):
    ws.append([n, "проф", имя, "ул. 1", "Город", "00-000", "", "", "", "",
               "", гео])
wb.save(кн)
wb.close()

print("=== 1. Освобождаем две польские строки ===")
итог = дуб.найти(кн, "23-08", ["СТАРАЯ ОДИН", "СТАРАЯ ДВА"])
дуб.освободить(кн, "23-08", итог["нашли"], None, log=lambda s: None)
места = дуб.свободные_места(кн, "23-08", "PL")
print("   свободные места PL:", места)
if места != [2, 3]:
    ошибок += 1
    print("   ✘ ожидали строки 2 и 3")
else:
    print("   ✔")

print()
print("=== 2. Часть 1 пишет В ЛИСТ «23-08», а не в новый по дате ===")
w = ExcelWriter(кн, "PL", мульти=True, лист="23-08")
print("   writer.sheet_name =", w.sheet_name)
if w.sheet_name != "23-08":
    ошибок += 1
    print("   ✘ завёл другой лист")
else:
    print("   ✔")

print()
print("=== 3. Замена встала В ОСВОБОЖДЁННЫЕ строки ===")
w.свободные_места(места)
for i, имя in enumerate(("НОВАЯ ОДИН", "НОВАЯ ДВА"), start=1):
    w.фирма(Firm(name=имя, address=f"Новая {i}", city="Варшава",
                 zip_code="00-001", state="", website=f"new{i}.pl",
                 payment_profile="проф"))
w.save()

wb = load_workbook(кн)
листы = wb.sheetnames
ws = wb["23-08"]
имена = [ws.cell(row=r, column=3).value for r in range(2, ws.max_row + 1)]
гео = [ws.cell(row=r, column=12).value for r in range(2, ws.max_row + 1)]
print("   листов в книге:", листы)
print("   строк:", ws.max_row - 1, "| имена:", имена)
print("   гео:", гео)
wb.close()

# «Лог» ExcelWriter заводит всегда — это его служебный лист отсева, не ошибка.
лишние = [л for л in листы if л not in ("23-08", "Лог", "Без сайта")]
if лишние:
    ошибок += 1
    print("   ✘ появился лишний лист:", лишние)
elif ws.max_row - 1 != 3:
    ошибок += 1
    print("   ✘ лист вырос")
elif имена != ["НОВАЯ ОДИН", "НОВАЯ ДВА", "ЧУЖАЯ"]:
    ошибок += 1
    print("   ✘ замена легла не туда")
elif гео != ["PL", "PL", "SI"]:
    ошибок += 1
    print("   ✘ гео перепутаны")
else:
    print("   ✔ лист один, не вырос, порядок стран сохранён")

print()
print("=== 4. Свободных мест больше нет ===")
осталось = дуб.свободные_места(кн, "23-08", "PL")
print("   осталось:", осталось)
if осталось:
    ошибок += 1
    print("   ✘")
else:
    print("   ✔")

кн.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
