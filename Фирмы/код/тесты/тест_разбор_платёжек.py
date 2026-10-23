"""
Разбор вставленных платёжек и поиск этих фирм в таблице.

Два случая из жизни, 10.09.2026, оба ломали «Взять в работу»:

1. Платёжки скопированы из таблицы — они приходят В КАВЫЧКАХ и вплотную,
   без пустых строк между блоками. Из четырёх фирм разбиралась ОДНА.

2. В таблице у фирмы имя С DNB («BRINDAMOUR BENJAMIN»), а в платёжке — имя
   ИЗ РЕЕСТРА («Benjamin BRINDAMOUR (POLITICAL HEAT)»). Совпадали они
   случайно, и три фирмы из четырёх «не нашлись».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from окно import имена_из_платёжек, первая_строка

ошибок = 0

print("=== 1. Платёжки в кавычках, вплотную ===")
ИЗ_ТАБЛИЦЫ = '''"Benjamin BRINDAMOUR (POLITICAL HEAT)
Address: 27 BOULEVARD SAINT-MARTIN, 75003 PARIS
Website:"
"Maria GARDINAL (CEREZO RIZO)
Address: 66 IMPASSE DE PEYREBRUNE, 81220 SERVIES
Website:"
"COOL-HEAT SERVICES SAS
Address: 6 RUE DERRIERE L'HATE 57050 PLAPPEVILLE
Website:"
"Fabian DAURES (ALOE HEAT)
Address: 629 CHEMIN DE CANTELOUP, 14290 LA VESPIERE-FRIARDEL
Website:"'''
вышло = имена_из_платёжек(ИЗ_ТАБЛИЦЫ)
ждём = ["Benjamin BRINDAMOUR (POLITICAL HEAT)", "Maria GARDINAL (CEREZO RIZO)",
        "COOL-HEAT SERVICES SAS", "Fabian DAURES (ALOE HEAT)"]
if вышло != ждём:
    ошибок += 1
    print(f"   ✘ разобрано {len(вышло)}: {вышло}")
else:
    print(f"   ✔ все четыре: {[и[:22] for и in вышло]}")

print()
print("=== 2. Платёжки через пустую строку — как было раньше ===")
СТАРЫЙ_ВИД = """Altmer Energy OU
Address: Tartu mnt 1
Website: altmer.ee

Bronze Land LTD
Address: Baker st 5
Website: bronze.uk"""
вышло2 = имена_из_платёжек(СТАРЫЙ_ВИД)
if вышло2 != ["Altmer Energy OU", "Bronze Land LTD"]:
    ошибок += 1
    print(f"   ✘ {вышло2}")
else:
    print(f"   ✔ {вышло2}")

print()
print("=== 3. Просто список названий ===")
вышло3 = имена_из_платёжек("ФИРМА ОДИН\nФИРМА ДВА\nФИРМА ТРИ")
if вышло3 != ["ФИРМА ОДИН", "ФИРМА ДВА", "ФИРМА ТРИ"]:
    ошибок += 1
    print(f"   ✘ {вышло3}")
else:
    print("   ✔ три названия, ничего не съедено")

print()
print("=== 4. Служебные строки не уходят в поиск как имена ===")
вышло4 = имена_из_платёжек("ФИРМА\nAddress: ул. 1\nWebsite: site.ru\nVAT: 123")
if вышло4 != ["ФИРМА"]:
    ошибок += 1
    print(f"   ✘ {вышло4}")
else:
    print("   ✔ ['ФИРМА'] — адрес, сайт и НДС не приняты за фирмы")

print()
print("=== 5. Имя фирмы — первая строка платёжки ===")
проверки = [
    ("Benjamin BRINDAMOUR (POLITICAL HEAT)\nAddress: 27 BLD\nWebsite:",
     "Benjamin BRINDAMOUR (POLITICAL HEAT)"),
    ("\n\n  ФИРМА С ПУСТЫМИ СВЕРХУ  \nAddress: x", "ФИРМА С ПУСТЫМИ СВЕРХУ"),
    ("", ""),
]
for текст, ждём_имя in проверки:
    if первая_строка(текст) != ждём_имя:
        ошибок += 1
        print(f"   ✘ {текст[:24]!r} → {первая_строка(текст)!r}")
if not ошибок:
    print("   ✔ имя берётся верно, пустой текст даёт пусто")

print()
print("=== 6. Платёжка без сайта — без строки «Website» ===")
from part1.models import Firm

# так её собирает реестровая линия
имя, адрес = "OU Z-telg", "Harju maakond, Tallinn"
ф = Firm(name=имя, address=адрес,
         payment_profile=f"{имя}\nAddress: {адрес}")
if "Website" in ф.payment_profile:
    ошибок += 1
    print(f"   ✘ строка про сайт осталась: {ф.payment_profile!r}")
else:
    print(f"   ✔ {ф.payment_profile!r}")

print()
print("ошибок:", ошибок)
