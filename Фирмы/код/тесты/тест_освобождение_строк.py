"""
Фирма закончилась без выписки — её место освобождается под замену.

По прогону 25.08 так зависли четыре строки: CH «не нашёл фирму»,
UK «не читается статус» дважды и «Incorporation не выложен онлайн».
Место за страной оставалось, но пустым его никто не считал: в листе стояла
фирма, для которой выписки не будет никогда.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openpyxl import Workbook, load_workbook
import part2.engine as д2
from part2 import дубликаты as дуб

ошибок = 0
кн = Path("освобождение_тест.xlsx")
кн.unlink(missing_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "23-08"
ws.append(["№", "Профиль", "Организация", "Адрес", "Город", "Индекс", "Штат",
           "Website", "Номер", "Файл выписки", "Профиль выписки", "Гео"])
ws.append([1, "проф", "СКАЧАННАЯ", "ул.1", "Г", "111", "", "s.uk", "N1",
           "файл.pdf", "блок", "UK"])
ws.append([2, "проф", "ПРОПУЩЕННАЯ", "ул.2", "Г", "222", "", "s.uk", "", "",
           "", "UK"])
ws.append([3, "проф", "ЧУЖАЯ", "ул.3", "Г", "333", "", "s.pl", "", "", "", "PL"])
wb.save(кн)
wb.close()


class ФейкЧеловек:
    pass


print("=== 1. Освобождаем строку пропущенной фирмы ===")
wb = load_workbook(кн)
ws = wb["23-08"]
д2._освободить_строку(ws, wb, кн, 3, ФейкЧеловек(), print,
                      "не читается статус")
wb.close()

wb = load_workbook(кн, data_only=True)
ws = wb["23-08"]
имена = [ws.cell(row=r, column=3).value for r in range(2, 5)]
номера = [ws.cell(row=r, column=1).value for r in range(2, 5)]
гео = [ws.cell(row=r, column=12).value for r in range(2, 5)]
файлы = [ws.cell(row=r, column=10).value for r in range(2, 5)]
wb.close()
print("   имена :", имена)
print("   № и гео:", list(zip(номера, гео)))

if имена[1] is not None:
    ошибок += 1
    print("   ✘ пропущенная фирма осталась в листе")
elif номера[1] != 2 or гео[1] != "UK":
    ошибок += 1
    print("   ✘ потеряли № или гео — место больше не закреплено за страной")
else:
    print("   ✔ фирма убрана, место осталось за UK")

print()
print("=== 2. Скачанную и чужую не тронули ===")
if имена[0] != "СКАЧАННАЯ" or файлы[0] != "файл.pdf":
    ошибок += 1
    print("   ✘ задели скачанную фирму")
elif имена[2] != "ЧУЖАЯ":
    ошибок += 1
    print("   ✘ задели фирму другой страны")
else:
    print("   ✔ обе на месте")

print()
print("=== 3. Освобождённое место видно как свободное ===")
своб_uk = дуб.свободные_места(кн, "23-08", "UK")
своб_pl = дуб.свободные_места(кн, "23-08", "PL")
print(f"   UK: {своб_uk}, PL: {своб_pl}")
if своб_uk != [3] or своб_pl:
    ошибок += 1
    print("   ✘ свободные места посчитаны неверно")
else:
    print("   ✔ ровно одно свободное место, в UK")

кн.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
