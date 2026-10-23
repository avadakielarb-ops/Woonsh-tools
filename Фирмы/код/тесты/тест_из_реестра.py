"""
Поиск ПРЯМО В РЕЕСТРЕ, минуя dnb: отсев того, что пришло не по слову.

Все примеры сняты с живого прогона 09.09.2026 по трём реестрам. Реестры ищут
по-разному, и перекос у каждого свой: Польша отдаёт записи, где слова нет
вовсе, Эстония — записи, где слово нашлось внутри другого слова.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part1.из_реестра import по_слову

ошибок = 0

print("=== 1. Настоящие находки проходят ===")
ГОДНЫЕ = [("Aurora Advisory OÜ", "aurora"), ("AuroraBooks OÜ", "aurora"),
          ('"Ice Tower" SIA', "ice"), ('"Ice Ice Ladies"', "ice"),
          ("AMBER SZCZECIN", "amber"), ('STOWARZYSZENIE "AMBER"', "amber"),
          ("EPP - GALERIA AMBER SPÓŁKA Z O O", "amber"),
          ("LT BRAND AMBER ENERGIA CENTRUM", "amber"),
          ("SIA Aurora", "aurora")]
for имя, слово in ГОДНЫЕ:
    if not по_слову(имя, слово):
        ошибок += 1
        print(f"   ✘ выбросил настоящую находку: {имя} ← «{слово}»")
print(f"   проверено {len(ГОДНЫЕ)} настоящих")

print()
print("=== 2. Мимо слова — не наша фирма ===")
# Польша: слова в названии нет совсем. Эстония: слово внутри другого слова.
МИМО = [("VISION SHIPPING SPÓŁKA Z O O", "amber"),
        ("CHINT POLAND SPÓŁKA Z O O", "amber"),
        ("A&K KRUJA SPÓŁKA Z O O", "amber"),
        ("13July Services OÜ", "ice"),          # Serv-ice-s
        ("1Office Group OÜ", "ice"),            # Off-ice
        ("1A Kinnisvarabüroo OÜ", "ice")]
for имя, слово in МИМО:
    if по_слову(имя, слово):
        ошибок += 1
        print(f"   ✘ пропустил чужую: {имя} ← «{слово}»")
print(f"   проверено {len(МИМО)} чужих")

print()
print("=== 3. Мелочи, на которых легко ошибиться ===")
проверки = [
    ('"SK Aurora"', "aurora", True, "кавычки и вторым словом"),
    ("AuroraAssets OÜ", "aurora", True, "слитно с другим словом"),
    ("Aquarium OÜ", "aurora", False, "похоже, но не оно"),
    ("Firma", "", True, "пустое слово ничего не отсеивает"),
    ("", "aurora", False, "пустое имя не проходит"),
    ("ICE TOWER", "ice", True, "верхний регистр"),
]
for имя, слово, ждём, что in проверки:
    вышло = по_слову(имя, слово)
    if вышло != ждём:
        ошибок += 1
        print(f"   ✘ {что}: «{имя}» ← «{слово}» дало {вышло}, ждали {ждём}")
    else:
        print(f"   ✔ {что}")

print()
print("=== 4. ВЫДАЧУ ЛИСТАЕМ, А НЕ БЕРЁМ ПЕРВУЮ СТРАНИЦУ ===")
# Прогон 19.10: просили 100 фирм, набрали 14 — с одной страницы одного слова.
import part1.из_реестра as ир
from part2.core.matching import Candidate


class Браузер:
    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class Драйвер:
    title = "Тест"
    листаний = 0

    def __init__(self, br, human):
        self.стр = 0

    def _страница(self):
        return [Candidate(name=f"ASPEN {self.стр}-{i} LTD", address=f"{i} Road, London")
                for i in range(20)]

    def search(self, c):
        return self._страница()

    def следующая_страница(self):
        if self.стр >= 4:
            return False
        self.стр += 1
        Драйвер.листаний += 1
        return True

    def кандидаты_страницы(self):
        return self._страница()


class Реестр:
    def __init__(self, **_):
        pass

    def свободна(self, fp):
        return True


было = (ир.Browser, ир.DRIVERS, ир.LocalFileRegistry)
ир.Browser, ир.DRIVERS, ир.LocalFileRegistry = Браузер, {"UK": Драйвер}, Реестр
try:
    фирмы = ир.искать("UK", ["aspen"], 70, human=None, log=lambda *_: None)
finally:
    ир.Browser, ир.DRIVERS, ир.LocalFileRegistry = было
if len(фирмы) != 70:
    ошибок += 1
    print(f"   ✘ набрал {len(фирмы)} из 70 — выдачу не листал")
else:
    print(f"   ✔ набрал 70 с одного слова, листаний: {Драйвер.листаний}")

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
