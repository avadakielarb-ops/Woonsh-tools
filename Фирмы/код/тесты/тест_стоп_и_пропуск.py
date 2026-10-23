"""
Три беды из живого лога — проверяем, что вылечены:
  1. «Стоп» не останавливал мультилист (шёл по всем 18 странам);
  2. смерть браузера ломала ВСЕ следующие гео («Sync API inside asyncio loop»);
  3. проверка говорила «✔ сходится», когда не скачалось ничего.
Плюс новая кнопка «пропустить страну».
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from openpyxl import Workbook, load_workbook
from common.human import AbortRun, SkipGeo, HumanChoice
import part2.engine as д2

ф = Path("_тест_стоп.xlsx")
ф.unlink(missing_ok=True)
wb = Workbook(); ws = wb.active; ws.title = "23-08"
ws.append(["№", "Платёжный профиль", "Организация", "Адрес", "Город", "Индекс",
           "Штат", "Website", "Номер в реестре", "Файл выписки",
           "Платёжный профиль выписки", "Гео"])
n = 0
for гео in ("FR", "PL", "CZ"):
    for i in range(2):
        n += 1
        ws.append([n, f"{гео}-ФИРМА-{i+1}\nAddress: ул. Тест 1\nWebsite: x.com",
                   f"{гео}-ФИРМА-{i+1}", "ул. Тест 1", "Город", "10000", "",
                   "http://x.com", "", "", "", гео])
wb.save(ф)

ошибок = 0
настоящий = д2.run

# ---------- 1. «Стоп» на первой стране ----------
print("=== 1. «Стоп» должен остановить ВЕСЬ мультилист ===")
вызовы = []
def стоп_на_первой(geo, *a, **k):
    вызовы.append(geo)
    if len(вызовы) == 1:
        raise AbortRun("человек нажал стоп")
    return {"скачано": 0, "всего": 0}
д2.run = стоп_на_первой
try:
    д2.run_мультилист(ф, "23-08", Path("выписки"), human=None, log=lambda s: None)
except Exception as e:
    print("   исключение наружу:", type(e).__name__)
print("   стран обработано:", вызовы)
if len(вызовы) != 1:
    ошибок += 1
    print(f"   ✘ прогон пошёл дальше: {вызовы}")
else:
    print("   ✔ встал на первой же стране")

# ---------- 2. «Пропустить страну» ----------
print()
print("=== 2. «Пропустить страну» — одна мимо, остальные работают ===")
вызовы = []
def пропуск_первой(geo, *a, **k):
    вызовы.append(geo)
    if len(вызовы) == 1:
        raise SkipGeo("человек пропустил страну")
    return {"скачано": 2, "всего": 2}
д2.run = пропуск_первой
итог = д2.run_мультилист(ф, "23-08", Path("выписки"), human=None, log=lambda s: None)
print("   стран обработано:", вызовы)
print("   итог:", итог["скачано"], "из", итог["всего"])
if len(вызовы) != 3:
    ошибок += 1
    print("   ✘ прогон не дошёл до остальных стран")
else:
    print("   ✔ первая пропущена, две другие отработали")
пометки = [и.get("ошибка", "") for и in итог["гео"]]
if "пропущено человеком" not in пометки:
    ошибок += 1
    print("   ✘ пропуск не отмечен в сводке:", пометки)
else:
    print("   ✔ в сводке помечено «пропущено человеком»")

д2.run = настоящий

# ---------- 3. Проверка не должна врать ----------
print()
print("=== 3. Проверка при нуле скачанных ===")
wb = load_workbook(ф)
ws = wb["23-08"]
for r in range(2, 4):                     # FR: имена файлов «от прошлого прогона»
    ws.cell(row=r, column=10, value="старый.pdf")
wb.save(ф)
строки = []
замечания = д2._проверить_гео(ф, "23-08", "FR", [2, 3], Path("_нет_такой_папки"),
                              {"скачано": 0, "всего": 2}, строки.append)
for с in строки:
    print("   ", с)
if not замечания:
    ошибок += 1
    print("   ✘ проверка сказала «сходится», хотя не скачано ничего")
else:
    print(f"   ✔ проверка возразила ({len(замечания)} замечания)")

# ---------- 4. Браузер закрыли — следующий запуск должен жить ----------
print()
print("=== 4. Смерть браузера не должна ломать следующие гео ===")
from common.browser import Browser
from common.human import HumanGate
try:
    br = Browser(profile="_смерть", human=HumanGate(), log=lambda s: None)
    br.__enter__()
    br.ctx.close()                        # имитируем: человек закрыл окно
    br.__exit__(None, None, None)         # раньше тут падало и НЕ звало stop()
    print("   первый браузер закрыт после смерти контекста")
    with Browser(profile="_смерть2", human=HumanGate(), log=lambda s: None) as br2:
        br2.page.goto("about:blank")
        print("   ✔ второй браузер поднялся в том же потоке")
except Exception as e:
    ошибок += 1
    print(f"   ✘ {type(e).__name__}: {str(e)[:120]}")
finally:
    import shutil
    for p in ("_смерть", "_смерть2"):
        shutil.rmtree(Path(".профиль_браузера") / p, ignore_errors=True)

ф.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
