import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import App

app = App()
app.update_idletasks()
app.update()

nb = None
for w in app.winfo_children():
    for w2 in w.winfo_children():
        for w3 in w2.winfo_children():
            if w3.winfo_class() == "TNotebook":
                nb = w3
nb.select(1)                      # «2. Скачать выписки»
app.мультилист.set(True)
app._переключить_мультилист()
app.update_idletasks()
app.update()

вкладка = app.nametowidget(nb.tabs()[1])
дети = вкладка.winfo_children()
print("вкладка:", вкладка.winfo_width(), "x", вкладка.winfo_height(),
      "| видима:", вкладка.winfo_ismapped())
print("детей:", len(дети))
не_видно = 0
for d in дети:
    ок = d.winfo_ismapped() and d.winfo_width() > 1 and d.winfo_height() > 1
    if not ок:
        не_видно += 1
    print(f"   {d.winfo_class():14} mapped={d.winfo_ismapped()} "
          f"{d.winfo_width():>4}x{d.winfo_height():<3} "
          f"x={d.winfo_x():>3} y={d.winfo_y():>3}  {'' if ок else '<- не отрисован'}")

print()
print("значения полей:")
print("   файл :", app.файл2.get())
print("   лист :", app.лист2.get(), "| варианты:", list(app.лист2['values']))
print("   гео  :", app.гео.get(), f"({app.гео['state']})")
print()
print("не отрисовано виджетов:", не_видно, "(ждём 0)")
app.destroy()
