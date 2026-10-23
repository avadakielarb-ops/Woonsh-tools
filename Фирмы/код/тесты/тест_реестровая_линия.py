"""
Реестровая линия целиком: находка доезжает до книги со словом и номером.

Смысл проверки. Линия «без сайта» из реестра — это отдельный путь, и он молча
терял то, что делает вчерашняя работа: колонку «Слово» (без неё выхлоп слова
не посчитать) и «ID» (без него строку потом не найти, если имя поменяется).
Лист «Без сайта» к тому же старше этих колонок, и на уже заведённых книгах
шапку надо дошивать, а не писать в безымянные клетки.
"""
import sys
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook, load_workbook

from part1.excel_out import ExcelWriter
from part1.models import Firm

ошибок = 0


def фирма(имя, слово="", город="Tallinn"):
    return Firm(name=имя, address="Tartu mnt 1", city=город, zip_code="10115",
                слово=слово)


print("=== 1. Новый лист «Без сайта» заводится со словом и номером ===")
книга = Path(mkdtemp()) / "EE.xlsx"
w = ExcelWriter(книга, "EE", только_без_сайта=True)
w.без_сайта(фирма("Aurora Advisory OÜ", "aurora"))
w.без_сайта(фирма("Ice Tower OÜ", "ice"))
л = w.wb["Без сайта"]
шапка = [c.value for c in л[1]]
if "Слово" not in шапка or "ID" not in шапка:
    ошибок += 1
    print(f"   ✘ колонок нет: {шапка}")
else:
    iс, iи = шапка.index("Слово") + 1, шапка.index("ID") + 1
    слова = [л.cell(row=r, column=iс).value for r in (2, 3)]
    номера = [л.cell(row=r, column=iи).value for r in (2, 3)]
    if слова != ["aurora", "ice"]:
        ошибок += 1
        print(f"   ✘ слова не те: {слова}")
    elif not all(номера) or len(set(номера)) != 2:
        ошибок += 1
        print(f"   ✘ номера не проставились: {номера}")
    else:
        print(f"   ✔ шапка {шапка}")
        print(f"     слова {слова}, номера {номера}")

print()
print("=== 2. Старая книга: шапка дошивается, значения не съезжают ===")
старая = Path(mkdtemp()) / "старая.xlsx"
wb = Workbook()
ws = wb.active
ws.title = "Без сайта"
ws.append(["Организация", "Адрес", "Город", "Индекс"])      # как писали раньше
ws.append(["STARA OÜ", "Vana 1", "Tartu", "50050"])
wb.save(старая)

w2 = ExcelWriter(старая, "EE", только_без_сайта=True)
w2.без_сайта(фирма("Aurora Nova OÜ", "aurora", город="Narva"))
л2 = w2.wb["Без сайта"]
ш2 = [c.value for c in л2[1]]
строка = [л2.cell(row=3, column=i).value for i in range(1, len(ш2) + 1)]
пары = dict(zip(ш2, строка))
if "Слово" not in ш2 or "ID" not in ш2:
    ошибок += 1
    print(f"   ✘ шапку не дошили: {ш2}")
elif пары.get("Организация") != "Aurora Nova OÜ" or пары.get("Город") != "Narva":
    ошибок += 1
    print(f"   ✘ значения съехали: {пары}")
elif пары.get("Слово") != "aurora" or not пары.get("ID"):
    ошибок += 1
    print(f"   ✘ слово/номер не записались: {пары}")
elif л2.cell(row=2, column=1).value != "STARA OÜ":
    ошибок += 1
    print("   ✘ старая строка потерялась")
else:
    print(f"   ✔ шапка стала {ш2}")
    print(f"     новая строка: {пары}, старая на месте")

print()
print("=== 3. Дубль в «Без сайта» не пишется дважды ===")
было = w2.wb["Без сайта"].max_row
if w2.без_сайта(фирма("Aurora Nova OÜ", "aurora", город="Narva")):
    ошибок += 1
    print("   ✘ записал дубль")
elif w2.wb["Без сайта"].max_row != было:
    ошибок += 1
    print("   ✘ строк прибавилось")
else:
    print("   ✔ повтор отброшен, строк столько же")

print()
print("=== 4. Слово едет с фирмой, а не берётся из состояния писаря ===")
# В реестровой линии один прогон перебирает несколько слов подряд: если брать
# «текущее слово» писаря, все находки получат последнее.
книга3 = Path(mkdtemp()) / "три.xlsx"
w3 = ExcelWriter(книга3, "LV", только_без_сайта=True)
w3.слово = "последнее"
for имя, сл in (("Ice Wolves", "ice"), ("SK Aurora", "aurora"),
                ("Amber Line", "amber")):
    w3.без_сайта(фирма(имя, сл, город="Riga"))
л3 = w3.wb["Без сайта"]
iс = [c.value for c in л3[1]].index("Слово") + 1
вышло = [л3.cell(row=r, column=iс).value for r in (2, 3, 4)]
if вышло != ["ice", "aurora", "amber"]:
    ошибок += 1
    print(f"   ✘ слова перепутались: {вышло}")
else:
    print(f"   ✔ у каждой фирмы своё слово: {вышло}")

print()
print("=== 5. Перенос читает такую книгу правильно ===")
import перенос_в_таблицу as перенос

перенос.выписки_на_диске = lambda папка, log=print: ({}, {})
итог = перенос.собрать(log=lambda s: None, только_книга=книга,
                       только_лист="Без сайта")
записи = list(итог["фирмы"].values())
if len(записи) != 2:
    ошибок += 1
    print(f"   ✘ собралось {len(записи)} вместо 2")
elif not all(з["ид_из_книги"] for з in записи):
    ошибок += 1
    print("   ✘ номер из книги не признан своим")
elif {з["строка"][14] for з in записи} != {"aurora", "ice"}:
    ошибок += 1
    print(f"   ✘ слово не доехало: {[з['строка'][14] for з in записи]}")
elif {з["лист"] for з in записи} != {"EE.БС"}:
    ошибок += 1
    print(f"   ✘ не тот лист: {[з['лист'] for з in записи]}")
else:
    print("   ✔ обе фирмы → лист EE.БС, слово и номер свои")

print()
print("ошибок:", ошибок)
