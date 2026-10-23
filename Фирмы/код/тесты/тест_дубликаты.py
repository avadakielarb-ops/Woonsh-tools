"""
Замена дубликатов: находим по имени, освобождаем место, Часть 1 кладёт замену
ИМЕННО ТУДА, а не в конец листа.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openpyxl import Workbook, load_workbook
from part2 import дубликаты as дуб

ошибок = 0
кн = Path("дубли_тест.xlsx")
папка = Path("дубли_тест_выписки")
кн.unlink(missing_ok=True)
import shutil
shutil.rmtree(папка, ignore_errors=True)

wb = Workbook()
ws = wb.active
ws.title = "23-08"
ws.append(["№", "Профиль", "Организация", "Адрес", "Город", "Индекс", "Штат",
           "Website", "Номер", "Файл выписки", "Профиль выписки", "Гео"])
данные = [
    (1, "ASAHI BEVERAGES PTY LTD", "AU", "asahi.pdf"),
    (2, "SUPAGAS PTY LIMITED", "AU", "supagas.pdf"),
    (3, "ICE ENGINEERING & CONSTRUCTION PTY LTD", "AU", ""),
    (4, "Ice Dream GmbH", "DE", "icedream.pdf"),
    (5, "dry ice GmbH", "DE", ""),
    (6, "Blue Ice", "BE", ""),
]
for n, имя, гео, файл in данные:
    ws.append([n, "профиль", имя, "ул. Такая 1", "Город", "12345", "", "",
               "НОМЕР", файл, "выписка", гео])
wb.save(кн)
wb.close()

for гео, файл in (("AU", "asahi.pdf"), ("AU", "supagas.pdf"), ("DE", "icedream.pdf")):
    (папка / гео).mkdir(parents=True, exist_ok=True)
    (папка / гео / файл).write_bytes(b"%PDF-1.4 ")

print("=== 1. Поиск по именам, с гео ===")
итог = дуб.найти(кн, "23-08", [
    "ASAHI BEVERAGES PTY LTD", "Ice Dream GmbH", "dry ice GmbH",
    "ТАКОЙ ФИРМЫ НЕТ"])
нашли = итог["нашли"]
print(f"   нашли {len(нашли)}, не нашли {len(итог['не_нашли'])}")
for с in нашли:
    print(f"      стр.{с['строка']} {с['гео']} {с['имя'][:30]}")
if len(нашли) != 3 or итог["не_нашли"] != ["ТАКОЙ ФИРМЫ НЕТ"]:
    ошибок += 1
    print("   ✘ ожидали 3 найденных и одно ненайденное")
else:
    print("   ✔")

print()
print("=== 2. «Blue Ice» НЕ ловится по «BLUE ICE SP Z O O» ===")
и2 = дуб.найти(кн, "23-08", ["BLUE ICE SP Z O O"])
if и2["нашли"]:
    ошибок += 1
    print("   ✘ поймал чужую:", и2["нашли"])
else:
    print("   ✔ не тронул")

print()
print("=== 3. Освобождение: данные стёрты, № и Гео на месте ===")
по_гео = дуб.освободить(кн, "23-08", нашли, папка, log=lambda s: print("  ", s))
print("   по гео:", по_гео)
wb = load_workbook(кн)
ws = wb["23-08"]
стр = нашли[0]["строка"]
имя_после = ws.cell(row=стр, column=3).value
номер_после = ws.cell(row=стр, column=1).value
гео_после = ws.cell(row=стр, column=12).value
print(f"   строка {стр}: №={номер_после} гео={гео_после} имя={имя_после!r}")
if имя_после or not гео_после or not номер_после:
    ошибок += 1
    print("   ✘ очистка неверная")
else:
    print("   ✔")
wb.close()

print()
print("=== 4. Старые выписки удалены ===")
остались = sorted(p.name for p in папка.rglob("*.pdf"))
print("   осталось:", остались)
if остались != ["supagas.pdf"]:
    ошибок += 1
    print("   ✘ удалили не то")
else:
    print("   ✔ удалены только выписки дубликатов")

print()
print("=== 5. Свободные места видны по гео ===")
au = дуб.свободные_места(кн, "23-08", "AU")
de = дуб.свободные_места(кн, "23-08", "DE")
print(f"   AU: {au}, DE: {de}")
if len(au) != 1 or len(de) != 2:
    ошибок += 1
    print("   ✘ ожидали AU 1 и DE 2")
else:
    print("   ✔")

print()
print("=== 6. Часть 1 кладёт замену В СВОБОДНУЮ строку ===")
from part1.excel_out import ExcelWriter
from part1.models import Firm
w = ExcelWriter(кн, "AU", мульти=True)
w.sheet_name = "23-08"
w.ws = w.wb["23-08"]
w.свободные_места(au)
w.фирма(Firm(name="НОВАЯ ФИРМА AU", address="Новая 5", city="Сидней",
             zip_code="2000", state="", website="new.au",
             payment_profile="профиль"))
w.save()
wb = load_workbook(кн)
ws = wb["23-08"]
print(f"   строк на листе: {ws.max_row - 1} (было 6, ждём 6)")
куда = ws.cell(row=au[0], column=3).value
print(f"   в строку {au[0]} легло: {куда!r}")
if ws.max_row - 1 != 6 or куда != "НОВАЯ ФИРМА AU":
    ошибок += 1
    print("   ✘ замена ушла не туда")
else:
    print("   ✔ замена встала на освобождённое место, лист не вырос")
wb.close()

кн.unlink(missing_ok=True)
shutil.rmtree(папка, ignore_errors=True)
print()
print("ошибок:", ошибок)
