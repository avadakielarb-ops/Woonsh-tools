"""
Вставка из буфера работает при ЛЮБОЙ раскладке.

Tk вешает Ctrl+V на символ «v»; на русской раскладке та же клавиша шлёт «м»,
и вставка не срабатывает — ни сочетанием, ни правой кнопкой.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tkinter as tk
from common import ввод

ошибок = 0
root = tk.Tk()
root.withdraw()

поле = tk.Text(root, width=40, height=10)
ввод.включить(поле)

СПИСОК = "ASAHI BEVERAGES PTY LTD\nSUPAGAS PTY LIMITED\nIce Dream GmbH"
root.clipboard_clear()
root.clipboard_append(СПИСОК)

print("=== 1. Кнопка «Вставить из буфера» ===")
n = ввод.вставить(поле)
внутри = поле.get("1.0", "end").strip()
print(f"   вставлено строк: {n}")
print(f"   в поле: {внутри.splitlines()}")
if n != 3 or внутри != СПИСОК:
    ошибок += 1
    print("   ✘ вставилось не то")
else:
    print("   ✔")

print()
print("=== 2. Повторная вставка дописывает, а не затирает ===")
ввод.вставить(поле)
строк = len(поле.get("1.0", "end").strip().splitlines())
print(f"   строк стало: {строк} (ждём 6)")
if строк != 6:
    ошибок += 1
    print("   ✘")
else:
    print("   ✔")

print()
print("=== 3. Ctrl+V по КОДУ клавиши (раскладка не важна) ===")
поле2 = tk.Text(root, width=40, height=10)
ввод.включить(поле2)
поле2.focus_set()


class СобытиеРусскойРаскладки:
    """Клавиша V нажата при русской раскладке: символ «м», код тот же 86."""
    keycode = ввод.КОД_V
    char = "м"
    keysym = "Cyrillic_em"
    state = 4                       # Ctrl

    def __init__(self, w):
        self.widget = w


до = поле2.get("1.0", "end").strip()
итог = ввод._по_коду(СобытиеРусскойРаскладки(поле2))
root.update()
после = поле2.get("1.0", "end").strip()
print(f"   было {len(до)} символов, стало {len(после)}; вернул {итог!r}")
if not после or итог != "break":
    ошибок += 1
    print("   ✘ вставка по коду клавиши не сработала")
else:
    print("   ✔ вставилось при русской раскладке")

print()
print("=== 4. Пустой буфер не роняет ===")
root.clipboard_clear()
try:
    n = ввод.вставить(поле2)
    print(f"   вернул {n} — не упал ✔")
except Exception as e:
    ошибок += 1
    print(f"   ✘ {type(e).__name__}: {e}")

root.destroy()
print()
print("ошибок:", ошибок)
