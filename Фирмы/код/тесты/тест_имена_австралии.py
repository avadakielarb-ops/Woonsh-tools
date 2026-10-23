"""
Австралия: «PTY» — не часть имени, а правовая форма.

У каждой австралийской фирмы имя кончается на «PTY LTD». «ltd» мы срезали,
«pty» — нет, и наше имя вечно несло лишнее слово. ABR при этом показывает
фирму то полным именем, то торговым: по «ANDREW SYDES GRANITE & MARBLE PTY
LTD» реестр отдаёт «ANDREW SYDES» и «Andrew Sydes Granite & Marble» (проверено
живым запросом 16.09.2026). Точного совпадения не выходило никогда, улицы в
выдаче ABR нет — и фирма уходила человеку с «неоднозначным совпадением», хотя
на экране висело её имя. По логам 11–12.09: 74 остановки на 100 фирм.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.core.matching import Candidate, normalize, pick

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


class Человек:
    def __init__(self):
        self.спрошено = 0

    def choose(self, *a, **к):
        self.спрошено += 1


print("=== 1. «PTY» срезается, как и всякая правовая форма ===")
проверить("наше имя", normalize("ANDREW SYDES GRANITE & MARBLE PTY LTD"),
          "andrew sydes granite & marble")
проверить("торговое имя из ABR", normalize("Andrew Sydes Granite & Marble"),
          "andrew sydes granite & marble")
проверить("точки не мешают", normalize("AC GRANITE PTY. LTD."), "ac granite")
проверить("«Pty Limited» тоже", normalize("BIRCH HOLDINGS Pty Limited"),
          "birch holdings")

print()
print("=== 2. Та же фирма в выдаче — берём молча, человека не зовём ===")
ч = Человек()
кандидаты = [
    Candidate(name="Andrew Sydes Granite & Marble", address="2170 NSW", ref="1"),
    Candidate(name="ASG CO PTY LTD", address="4122 QLD", ref="2"),
    Candidate(name="A & C PTY LTD", address="3000 VIC", ref="3"),
]
выбран = pick("ANDREW SYDES GRANITE & MARBLE PTY LTD", "2170 NSW", кандидаты, ч)
проверить("выбрали нужную", выбран.ref, "1")
проверить("человека не дёргали", ч.спрошено, 0)

print()
print("=== 3. Настоящих однофамильцев по-прежнему решает человек ===")
# Две РАЗНЫЕ фирмы с одинаковым именем в разных штатах — тут молча выбирать
# нельзя: ошибка стоит чужой выписки и сожжённой фирмы.
ч2 = Человек()
двое = [Candidate(name="BIRCH HOLDINGS PTY LTD", address="4122 QLD", ref="1"),
        Candidate(name="BIRCH HOLDINGS PTY LTD", address="3000 VIC", ref="2")]
pick("BIRCH HOLDINGS PTY LTD", "6000 WA", двое, ч2)
проверить("спросили человека", ч2.спрошено, 1)

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
