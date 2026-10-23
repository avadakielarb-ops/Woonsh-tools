"""
Негодная форма видна уже в имени — Часть 1 не берёт такую фирму.

Решение пользователя 20.10.2026 после проверочного прогона: хорватские obrt
(«vl. …») и польские spółka cywilna («S C») в наших реестрах не ищутся
вовсе, французские ассоциации и SCI Google Ads не верифицирует. Прогон по
этим странам давал 0 из 10, а время уходило на бота и реестр.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.core.формы import стоп_по_имени
from part1.filters import этаж_1
from part1.models import Firm

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


print("=== 1. ОТСЕКАЕМ ===")
for г, имя in [("HR", '"AURORA", VL. MARIJA BAKRAN'), ("HR", "Caps Lock, vl. Marko Sandalj"),
               ("PL", "A D T MARMUR I GRANIT S C JANISZEWSKI DA..."),
               ("PL", "AGENCJA TURYSTYCZNA VOYAGE S.C."), ("FR", "AERO CLUB DE FALAISE"),
               ("FR", "SCI DU MOULIN"), ("SI", "ŠPORTNO DRUŠTVO ZARJA"),
               ("LV", "Biedrība Latvijas Saule"), ("AU", "THE ROWAN JAMES CLARK INVESTMENT TRUST")]:
    проверить(f"{г} {имя}", bool(стоп_по_имени(г, имя)), True)

print()
print("=== 2. НОРМАЛЬНЫЕ ФИРМЫ ПРОХОДЯТ ===")
for г, имя in [("HR", "AQUA KEM d.o.o."), ("PL", "ARBOR BG SP Z O O SPÓŁKA KOMANDYTOWA"),
               ("PL", "AMETYST HENRYK GRZYBOWSKI I GRAŻYNA KARA..."), ("FR", "AQUA SENART"),
               ("SI", "AQUA INSTALL Milos Kerzan s.p."), ("UK", "ALDER HEY CHILDREN'S CHARITY"),
               ("AU", "ANVIL ADVISORY PTY LTD"), ("HR", "društvo s ograničenom odgovornošću ICE")]:
    проверить(f"{г} {имя}", стоп_по_имени(г, имя), "")

print()
print("=== 3. ЧАСТЬ 1 ОТСЕКАЕТ ДО КАРТОЧКИ ===")


class Реестр:
    def свободна(self, fp):
        return True


ok, why = этаж_1(Firm(name='"GALEB" vl. ZORAN ATANASKOVIC', country="HR"), "HR", Реестр())
проверить("obrt отсечён на этаже 1", (ok, "obrt" in why), (False, True))

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
