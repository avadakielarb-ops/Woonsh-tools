"""
ЦЕПОЧКА ЗАМЕНЫ ЦЕЛИКОМ — то, ради чего всё и делалось.

    фирма отказала (ликвидация / негодная форма / не нашлась / пропустил человек)
        → её место освободилось
        → место видно как свободное
        → Часть 1 кладёт туда замену, лист не растёт и порядок стран цел
        → новые строки помечены, их можно отдать на проверку отдельно

Проверяем без браузера и без сети: все звенья — работа с листом.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openpyxl import Workbook, load_workbook
import part2.engine as д2
from part2 import дубликаты as дуб
from part1.excel_out import ExcelWriter
from part1.models import Firm

ошибок = 0
кн = Path("цепочка_тест.xlsx")
кн.unlink(missing_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "23-08"
ws.append(["№", "Профиль", "Организация", "Адрес", "Город", "Индекс", "Штат",
           "Website", "Номер", "Файл выписки", "Профиль выписки", "Гео"])
ИСХОДНЫЕ = [
    (1, "ЖИВАЯ ШВЕЙЦАРСКАЯ", "CH", "N1", "живая.pdf"),
    (2, "ASSOCIATION USTER", "CH", "", ""),          # негодная форма
    (3, "EXOTIC ICE IN LIQUIDATION", "CH", "", ""),  # ликвидация
    (4, "ПРОПАВШАЯ НОРВЕЖСКАЯ", "NO", "", ""),       # не нашлась
    (5, "ЖИВАЯ ПОЛЬСКАЯ", "PL", "N2", "живая2.pdf"),
]
for n, имя, гео, номер, файл in ИСХОДНЫЕ:
    ws.append([n, "проф", имя, "ул. 1", "Город", "00-000", "", "site", номер,
               файл, "блок" if файл else "", гео])
wb.save(кн)
wb.close()


class ФейкЧеловек:
    pass


print("=== 1. Отказы освобождают свои строки ===")
wb = load_workbook(кн)
ws = wb["23-08"]
for строка, почему in ((3, "форма не подходит для Google Ads: Association"),
                       (4, "статус: in liquidation"),
                       (5, "в реестре не нашлась")):
    д2._освободить_строку(ws, wb, кн, строка, ФейкЧеловек(),
                          lambda s: None, почему)
wb.close()

wb = load_workbook(кн, data_only=True)
ws = wb["23-08"]
имена = [ws.cell(row=r, column=3).value for r in range(2, 7)]
wb.close()
print("   имена на листе:", имена)
if имена != ["ЖИВАЯ ШВЕЙЦАРСКАЯ", None, None, None, "ЖИВАЯ ПОЛЬСКАЯ"]:
    ошибок += 1
    print("   ✘ освобождены не те строки")
else:
    print("   ✔ три отказа убраны, обе живые фирмы целы")

print()
print("=== 2. Места видны как свободные, по своим странам ===")
ch = дуб.свободные_места(кн, "23-08", "CH")
no = дуб.свободные_места(кн, "23-08", "NO")
pl = дуб.свободные_места(кн, "23-08", "PL")
print(f"   CH: {ch}, NO: {no}, PL: {pl}")
if ch != [3, 4] or no != [5] or pl:
    ошибок += 1
    print("   ✘ свободные места посчитаны неверно")
else:
    print("   ✔ CH 2 места, NO 1, у Польши ничего не пропало")

print()
print("=== 3. Часть 1 кладёт замену В ЭТИ ЖЕ строки ===")
for гео, места, замены in (("CH", ch, ("НОВАЯ ШВЕЙЦАРСКАЯ 1", "НОВАЯ ШВЕЙЦАРСКАЯ 2")),
                           ("NO", no, ("НОВАЯ НОРВЕЖСКАЯ",))):
    w = ExcelWriter(кн, гео, мульти=True, лист="23-08")
    w.свободные_места(места)
    for имя in замены:
        w.фирма(Firm(name=имя, address="Новая 1", city="Город",
                     zip_code="11111", state="", website="new.site",
                     payment_profile="проф"))
    w.save()

wb = load_workbook(кн, data_only=True)
ws = wb["23-08"]
строк = ws.max_row - 1
имена = [ws.cell(row=r, column=3).value for r in range(2, 7)]
гео_ст = [ws.cell(row=r, column=12).value for r in range(2, 7)]
номера = [ws.cell(row=r, column=1).value for r in range(2, 7)]
wb.close()
print("   строк:", строк, "(было 5)")
print("   имена:", имена)
print("   гео  :", гео_ст)
print("   №    :", номера)

if строк != 5:
    ошибок += 1
    print("   ✘ лист вырос — замена ушла в конец, а не на место")
elif None in имена:
    ошибок += 1
    print("   ✘ не все места закрыты")
elif гео_ст != ["CH", "CH", "CH", "NO", "PL"]:
    ошибок += 1
    print("   ✘ порядок стран сломался")
elif номера != [1, 2, 3, 4, 5]:
    ошибок += 1
    print("   ✘ нумерация сбилась")
else:
    print("   ✔ лист не вырос, страны и нумерация целы")

print()
print("=== 4. Свободных мест не осталось ===")
осталось = {г: len(дуб.свободные_места(кн, "23-08", г)) for г in ("CH", "NO", "PL")}
print("   ", осталось)
if any(осталось.values()):
    ошибок += 1
    print("   ✘")
else:
    print("   ✔ цикл замкнулся")

print()
print("=== 5. Живые фирмы не пострадали: файлы выписок на месте ===")
wb = load_workbook(кн, data_only=True)
ws = wb["23-08"]
файлы = {ws.cell(row=r, column=3).value: ws.cell(row=r, column=10).value
         for r in range(2, 7)}
wb.close()
print("   ", {и: ф for и, ф in файлы.items() if ф})
if файлы.get("ЖИВАЯ ШВЕЙЦАРСКАЯ") != "живая.pdf" or \
        файлы.get("ЖИВАЯ ПОЛЬСКАЯ") != "живая2.pdf":
    ошибок += 1
    print("   ✘ у живых фирм пропали выписки")
else:
    print("   ✔ выписки живых фирм на месте")

кн.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
