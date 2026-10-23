import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tkinter as tk
from common import тема

r = tk.Tk()
r.withdraw()
тема.применить(r)

print("=== покраска не падает ни на одном виджете ===")
виджеты = [("Text", tk.Text(r)), ("Listbox", tk.Listbox(r)),
           ("Canvas", tk.Canvas(r)), ("Entry", tk.Entry(r))]
плохо = 0
for имя, w in виджеты:
    try:
        тема.покрасить(w)
        # спрашиваем только те свойства, которые у виджета ЕСТЬ
        умеет = set(w.keys())
        показ = " ".join(f"{о}={w.cget(о)}" for о in ("bg", "fg") if о in умеет)
        пропущено = [о for о in ("fg", "insertbackground") if о not in умеет]
        хвост = f"  (нет свойств: {', '.join(пропущено)})" if пропущено else ""
        print(f"  ok  {имя}: {показ}{хвост}")
    except Exception as e:
        плохо += 1
        print(f"  ПЛОХО {имя}: {type(e).__name__}: {e}")

print()
print("=== окно выбора стран собирается ЦЕЛИКОМ ===")
r.destroy()
from app import App
from part1.data.countries import СПИСОК as СТРАНЫ

app = App()
app.withdraw()
app.мультигео.set(True)

# перехватываем wait_window, чтобы окно не блокировало проверку
поймано = {}
исходный = tk.Toplevel.wait_window
def не_ждать(self, *a, **k):
    поймано["окно"] = self
tk.Toplevel.wait_window = не_ждать
try:
    app._выбрать_страны()
finally:
    tk.Toplevel.wait_window = исходный

окно = поймано.get("окно")
if окно is None:
    плохо += 1
    print("  ПЛОХО: окно не создалось")
else:
    app.update_idletasks()
    списки = [w for w in окно.winfo_children()[1].winfo_children()
              if w.winfo_class() == "Listbox"]
    кнопки = []
    def обойти(w):
        for д in w.winfo_children():
            if д.winfo_class() == "TButton":
                кнопки.append(д.cget("text"))
            обойти(д)
    обойти(окно)
    if not списки:
        плохо += 1
        print("  ПЛОХО: списка стран нет")
    else:
        с = списки[0]
        print(f"  ok  список есть, стран в нём: {с.size()} (ожидаем {len(СТРАНЫ)})")
        print(f"      первые три: {[с.get(i) for i in range(3)]}")
        if с.size() != len(СТРАНЫ):
            плохо += 1
            print("  ПЛОХО: количество стран не совпало")
    print(f"  ok  кнопки в окне: {кнопки}")
    if "ОК" not in кнопки:
        плохо += 1
        print("  ПЛОХО: кнопки ОК нет")
    окно.destroy()

app.destroy()
print()
print("ошибок:", плохо)
