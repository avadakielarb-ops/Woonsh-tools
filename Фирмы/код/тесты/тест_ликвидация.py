"""
Фирмы в ликвидации не берём — и ловим их ДО открытия карточки.

Из лога 09.09.2026: «AHORN Vorsorge Management GmbH in Liquid...» ушла в лист.
Выписки на неё не будет, Часть 2 её всё равно отбросит — но к тому моменту
карточка открыта, строка в листе занята, время потрачено. Пометка стоит прямо
в названии, и видно её в строке выдачи.

Осторожность здесь важнее полноты: «liquid» бывает в живых названиях, и
выбросить производителя жидкостей хуже, чем пропустить одну ликвидированную.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part1.filters import в_ликвидации, этаж_1
from part1.models import Firm

ошибок = 0

print("=== 1. Пометки ликвидации ловятся ===")
МЁРТВЫЕ = [
    "AHORN Vorsorge Management GmbH in Liquid...",   # ровно из лога, обрезанное
    "AHORN Vorsorge Management GmbH in Liquidation",
    "Baltic Trade OÜ (in Liquidation)",
    "Nordic AB i likvidation",
    "Firma Sp. z o.o. w likwidacji",
    "Podnik s.r.o. v likvidaci",
    "Kereskedelmi Kft. felszámolás alatt",
    "Handel GmbH i.L.",
    "Something Ltd — dissolved",
    "Bouwbedrijf BV in liquidatie",
]
for имя in МЁРТВЫЕ:
    if not в_ликвидации(имя):
        ошибок += 1
        print(f"   ✘ пропустил ликвидацию: {имя}")
print(f"   проверено {len(МЁРТВЫЕ)} ликвидированных")

print()
print("=== 2. Живые фирмы не задеты ===")
ЖИВЫЕ = [
    "Liquid Design GmbH",              # «liquid» само по себе — не приговор
    "Aqua Liquid Solutions Ltd",
    "Liquidity Partners OY",
    "Nordic Liquids AB",
    "Ahorn Vorsorge Management GmbH",  # та же фирма без пометки
    "Hirsch Maschinenbau GmbH",
    "Konkursbo Nielsen ApS",           # «konkursbo» — имя, а не статус
]
for имя in ЖИВЫЕ:
    метка = в_ликвидации(имя)
    if метка:
        ошибок += 1
        print(f"   ✘ забраковал живую: {имя} — по метке «{метка}»")
print(f"   проверено {len(ЖИВЫЕ)} живых")

print()
print("=== 3. Отсев идёт на ПЕРВОМ этаже, до карточки ===")


class РеестрВсёСвободно:
    def свободна(self, fp):
        return True


ф = Firm(name="AHORN Vorsorge Management GmbH in Liquid...",
         industry="management services", city="Wien", zip_code="1010",
         address="Austria")
ок, почему = этаж_1(ф, "AT", РеестрВсёСвободно())
if ок:
    ошибок += 1
    print("   ✘ этаж 1 пропустил ликвидированную дальше — карточка откроется зря")
elif "ликвидац" not in почему:
    ошибок += 1
    print(f"   ✘ причина не та: {почему}")
else:
    print(f"   ✔ не пущена дальше: {почему}")

живая = Firm(name="Hirsch Maschinenbau GmbH", industry="manufacturing",
             city="Wien", zip_code="1010", address="Austria")
ок2, почему2 = этаж_1(живая, "AT", РеестрВсёСвободно())
if not ок2:
    ошибок += 1
    print(f"   ✘ живую не пустил: {почему2}")
else:
    print("   ✔ живая проходит как раньше")

print()
print("ошибок:", ошибок)
