import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pathlib import Path
from app import App
from common import пути
from part2.engine import мультилисты, run_мультилист

ошибок = 0
app = App()
app.withdraw()

print("=== обычный режим: файл по гео ===")
app.гео.set("CZ")
app._гео_в_имя_файла2()
app._обновить_листы()
print("  файл:", app.файл2.get())
print("  листы:", list(app.лист2["values"])[:6], "…")
print("  выбран:", app.лист2.get())

print()
print("=== включаю МУЛЬТИЛИСТ ===")
app.мультилист.set(True)
app._переключить_мультилист()
файл = app.файл2.get()
листы = list(app.лист2["values"])
выбран = app.лист2.get()
print("  файл подставился:", файл)
print("  листы в выборе:", листы)
print("  выбран:", выбран)
print("  гео заблокировано:", str(app.гео["state"]))

if not файл.startswith("Мультигео"):
    ошибок += 1
    print("  ✘ файл не подставился")
else:
    print("  ✔ файл мультигео подставлен сам")

if not листы:
    ошибок += 1
    print("  ✘ листов нет")
else:
    годные = мультилисты(пути.фирмы(файл))
    if set(листы) != set(годные):
        ошибок += 1
        print(f"  ✘ в выборе не только мультилисты: {листы} vs {годные}")
    else:
        print(f"  ✔ в выборе ТОЛЬКО листы с колонкой «Гео»: {годные}")

print()
print("=== выключаю обратно ===")
app.мультилист.set(False)
app._переключить_мультилист()
print("  файл:", app.файл2.get())
print("  гео:", str(app.гео["state"]))
if not app.файл2.get().startswith("Czech"):
    ошибок += 1
    print("  ✘ файл не вернулся к стране")
else:
    print("  ✔ вернулся файл по стране")

print()
print("=== понятная ошибка при неверном листе ===")
app.destroy()
try:
    run_мультилист(пути.фирмы("Czech Republic.xlsx"), "22-07 CZ",
                   пути.ВЫПИСКИ, human=None)
    ошибок += 1
    print("  ✘ должно было отказаться")
except RuntimeError as e:
    print("  ✔ отказалось, и вот что сказало:")
    for с in str(e).splitlines():
        print("     |", с)
except Exception as e:
    ошибок += 1
    print(f"  ✘ не то исключение: {type(e).__name__}: {e}")

print()
print("ошибок:", ошибок)
