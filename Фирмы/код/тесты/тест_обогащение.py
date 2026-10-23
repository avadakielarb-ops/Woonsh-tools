import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.human import HumanGate
from common.диагноз import Диагноз, ПОДСКАЗКИ

print("=== вопрос БЕЗ глаз (как было раньше) ===")
h = HumanGate()
t, m = h._обогатить("Скрипт застрял", "Не удалось выполнить шаг: клик по Search")
print("  заголовок:", t)
print("  сообщение:", m)

print()
print("=== вопрос С диагнозом «проверка бота» ===")
h2 = HumanGate()
з, ч = ПОДСКАЗКИ["бот"]
h2.диагноз = lambda *a, **k: Диагноз("бот", з, ч)
h2.снимок = lambda повод="": r"логи\скриншоты\пример.png"
t, m = h2._обогатить("Скрипт застрял", "Не удалось выполнить шаг: клик по Search")
print("  заголовок:", t)
print("  сообщение:")
for с in m.splitlines():
    print("     |", с)

print()
print("=== диагностика НЕ должна ронять вопрос ===")
h3 = HumanGate()
def взрыв(*a, **k):
    raise RuntimeError("браузер умер")
h3.диагноз = взрыв
h3.снимок = взрыв
t, m = h3._обогатить("Капча", "Реши её в браузере.")
print("  заголовок:", t, "| сообщение:", m)
print("  ✔ вопрос дошёл, несмотря на две упавшие проверки")

print()
print("=== кнопка снимка находит путь в тексте ===")
import re
from pathlib import Path
for пример in (r"📸 Снимок экрана: логи\скриншоты\a.png",
               r"📸 Снимок экрана: C:\Users\x\логи\b.png"):
    строка = пример
    путь = строка.split(":", 1)[1].strip()
    if len(путь) > 2 and путь[1] == ":":
        путь = строка.split("Снимок экрана:", 1)[-1].strip()
    print(f"  {пример!r}")
    print(f"     -> {путь!r}")
