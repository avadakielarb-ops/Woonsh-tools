"""
«Только недостающие»: полностью скачанное гео пропускается САМО (без вопросов),
недокачанное берётся и добирает только то, чего нет.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil
from pathlib import Path
from openpyxl import Workbook
from common.human import HumanGate, SkipGeo
from part1.registry import LocalFileRegistry, отпечаток
import part2.engine as д2

песочница = Path("_песочница_недост")
shutil.rmtree(песочница, ignore_errors=True)
песочница.mkdir()
ф = песочница / "лист.xlsx"
реестр_путь = песочница / "реестр.json"

wb = Workbook(); ws = wb.active; ws.title = "23-08"
ws.append(["№", "Платёжный профиль", "Организация", "Адрес", "Город", "Индекс",
           "Штат", "Website", "Номер в реестре", "Файл выписки",
           "Платёжный профиль выписки", "Гео"])
n = 0
план = {"AU": 2, "AT": 2}          # AU скачаем целиком, AT — наполовину
for гео, сколько in план.items():
    for i in range(сколько):
        n += 1
        ws.append([n, "", f"{гео}-ФИРМА-{i+1}", "ул. Тест 1", "Город",
                   f"1000{i}", "", "http://x.com", "", "", "", гео])
wb.save(ф)

r = LocalFileRegistry(реестр_путь)
def пометить(гео, i):
    к = отпечаток(f"{гео}-ФИРМА-{i+1}", гео, f"1000{i}", "Город")
    r.забронировать(к); r.подтвердить(к, f"{гео}#{i}")
пометить("AU", 0); пометить("AU", 1)      # AU: обе скачаны
пометить("AT", 0)                          # AT: одна из двух

ошибок = 0
спрошено = []
def нельзя_спрашивать(title, message, company):
    # Вопросы ПРО ФИРМЫ тут неизбежны: данные выдуманные, а реестр настоящий.
    # Проверяем не их, а то, что не показали МЕНЮ «уже скачаны» — именно оно
    # заставляло человека жать «пропустить» по каждой готовой стране.
    raise AssertionError("вопрос по фирме (ожидаемо на выдуманных данных)")
def меню(title, message, варианты, company=""):
    спрошено.append("МЕНЮ: " + title)
    raise AssertionError("меню быть не должно: " + title)

human = HumanGate(ui_ask=нельзя_спрашивать, ui_menu=меню)
исходный = д2.LocalFileRegistry
д2.LocalFileRegistry = lambda *a, **k: LocalFileRegistry(реестр_путь, log=k.get("log"))

строки = []
def log(s): строки.append(str(s))

print("=== AU: скачано 2 из 2 — должно пропуститься САМО ===")
try:
    д2.run("AU", ф, песочница / "в", human, log=log, sheet="23-08",
           фильтр_гео="AU", только_недостающие=True)
    ошибок += 1
    print("   ✘ не пропустилось")
except SkipGeo as e:
    print(f"   ✔ пропущено само: {e}")
except Exception as e:
    ошибок += 1
    print(f"   ✘ {type(e).__name__}: {str(e)[:120]}")
for с in строки:
    if "пропускаю" in с or "уже скачан" in с:
        print("      лог:", с.strip())

print()
print("=== AT: скачано 1 из 2 — берём и добираем одну ===")
строки.clear()
взято_в_работу = {}
настоящий_обработать = None
try:
    д2.run("AT", ф, песочница / "в", human, log=log, sheet="23-08",
           фильтр_гео="AT", только_недостающие=True)
except SkipGeo:
    ошибок += 1
    print("   ✘ гео пропущено, хотя одна фирма недокачана")
except Exception as e:
    # до браузера дойти не сможем — важно, ЧТО написано в логе ДО этого
    pass
доборная = [с for с in строки if "добираю" in с]
пропуск = [с for с in строки if "уже скачаны" in с and "пропускаю" in с]
if доборная:
    print("   ✔", доборная[0].strip())
else:
    ошибок += 1
    print("   ✘ в логе нет строки про добор недостающих")
if пропуск:
    ошибок += 1
    print("   ✘ гео пропущено целиком, хотя недокачано")

print()
print("=== меню «уже скачаны» не показывалось? ===")
if спрошено:
    ошибок += 1
    print("   ✘ показывали меню:", спрошено)
else:
    print("   ✔ меню не было — жать «пропустить» руками не пришлось")

д2.LocalFileRegistry = исходный
shutil.rmtree(песочница, ignore_errors=True)
print()
print("ошибок:", ошибок)
