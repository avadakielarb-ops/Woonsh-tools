"""
Папка прогона: одна папка на ПАРТИЮ (имя листа), лишних не заводим.

Раскладка переделана 08.09.2026: уровня «Мультигео» больше нет, одиночное гео
и мультигео ложатся одинаково. Подробности — в тест_папки_прогона.py, здесь
проверяется само имя папки и уборка пустых.
"""
import sys
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import part2.engine as д2

ошибок = 0
корень = Path("проба_выписки")
shutil.rmtree(корень, ignore_errors=True)

print("=== 1. Имя папки — это имя листа ===")
п = д2.папка_листа(корень, "23-08")
ждём = корень / "23-08"
print(f"   {п}")
if п != ждём:
    ошибок += 1
    print("   ✘ ждали", ждём)
else:
    print("   ✔")

print()
print("=== 2. Спросили путь — папка НЕ создалась ===")
if п.exists():
    ошибок += 1
    print("   ✘ создалась заранее — так и заводится пустая лишняя папка")
else:
    print("   ✔ пусто, создаст тот, кто пишет")

print()
print("=== 3. Один лист — одна папка, сколько ни спрашивай ===")
for _ in range(5):
    д2.папка_листа(корень, "23-08")
д2.папка_листа(корень, "23-08").mkdir(parents=True, exist_ok=True)
листы = sorted(x.name for x in корень.iterdir() if x.is_dir())
print("   папок листов:", листы)
if листы != ["23-08"]:
    ошибок += 1
    print("   ✘ завелись лишние")
else:
    print("   ✔")

print()
print("=== 4. Пустое имя листа не подменяется датой ===")
п2 = д2.папка_листа(корень, "")
print(f"   {п2.name}")
import re
if re.fullmatch(r"\d{2}-\d{2}", п2.name):
    ошибок += 1
    print("   ✘ подставилась дата — партия расползётся по двум папкам")
else:
    print("   ✔ честное «без-листа», видно и чинится")

print()
print("=== 5. Пустые папки гео убираются ===")
база = д2.папка_листа(корень, "23-08")
(база / "PL").mkdir(parents=True, exist_ok=True)
(база / "LV").mkdir(parents=True, exist_ok=True)
(база / "SI").mkdir(parents=True, exist_ok=True)
(база / "PL" / "фирма.pdf").write_bytes(b"%PDF-1.4 ")
убрано = д2.прибрать_пустые(база, log=lambda s: print("   ", s.strip()))
осталось = sorted(x.name for x in база.iterdir() if x.is_dir())
print(f"   убрано: {убрано}, осталось: {осталось}")
if осталось != ["PL"]:
    ошибок += 1
    print("   ✘ убрал не то")
else:
    print("   ✔ остался только гео с файлами")

shutil.rmtree(корень, ignore_errors=True)
print()
print("ошибок:", ошибок)
