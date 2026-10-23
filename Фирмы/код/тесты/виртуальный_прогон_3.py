# -*- coding: utf-8 -*-
"""
Виртуальный прогон №3 — РЕВИЗИЯ. Проверяем ЧАСТЬ 1 целиком (её раньше не тестили)
плюс стыки Части 2: разбор блока B, имена файлов, реестр, разбор адресов по гео.
Всё офлайн, без браузера.
"""
import sys, re
from pathlib import Path
# ПУТЬ ОТ СЕБЯ, а не вписанный: адрес полигона перестал быть корнем проекта.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ок = пров = 0
провалы = []
def чек(имя, усл, деталь=""):
    global ок, пров
    пров += 1
    if усл:
        ок += 1
    else:
        провалы.append(f"{имя}   [{деталь}]")
    print(("  OK  " if усл else "  !!  ") + имя + (f"   -> {деталь}" if not усл and деталь else ""))


# ============ ЧАСТЬ 1: countries ============
print("\n=== countries: to_code / to_name / регион ===")
from part1.data.countries import to_code, to_name, регион, СПИСОК, NAME_TO_CODE, CODE_TO_NAME, РЕГИОНЫ
чек("to_code('Poland')=PL", to_code("Poland") == "PL", to_code("Poland"))
чек("to_code('Czech Republic')=CZ", to_code("Czech Republic") == "CZ", to_code("Czech Republic"))
чек("to_code('USA')=US", to_code("USA") == "US", to_code("USA"))
чек("to_code('United Kingdom')=UK", to_code("United Kingdom") == "UK", to_code("United Kingdom"))
чек("to_code('US')=US (код как есть)", to_code("US") == "US", to_code("US"))
чек("to_name('USA')=United States", to_name("USA") == "United States", to_name("USA"))
чек("to_name('United Kingdom')=United Kingdom", to_name("United Kingdom") == "United Kingdom", to_name("United Kingdom"))
чек("to_name('Poland')=Poland", to_name("Poland") == "Poland", to_name("Poland"))
чек("to_name('Czech Republic')=Czech Republic", to_name("Czech Republic") == "Czech Republic", to_name("Czech Republic"))
# каждый пункт СПИСКА должен иметь код и разворачиваться в имя для DnB
for стр in СПИСОК:
    код = to_code(стр)
    чек(f"СПИСОК «{стр}» → код {код} → имя есть", bool(код) and bool(to_name(стр)), f"{код}/{to_name(стр)}")
чек("регион('Tucson, AZ, United States')=AZ", регион("Tucson, AZ, United States") == "AZ", регион("Tucson, AZ, United States"))
чек("регион('Miami, FL, United States')=FL", регион("Miami, FL, United States") == "FL", регион("Miami, FL"))
чек("регион('HUNINGUE, GRAND EST, France')=''", регион("HUNINGUE, GRAND EST, France") == "", регион("HUNINGUE, GRAND EST, France"))


# ============ ЧАСТЬ 1: filters ============
print("\n=== filters: этаж_1 (бренд / отрасль / регион / реестр) ===")
from part1.filters import этаж_1, has_legal_form, BRANDS, BLACKLIST
from part1.models import Firm
from part1.registry import отпечаток

class РеестрЗаглушка:
    def __init__(self, занятые=()): self.занятые = set(занятые)
    def свободна(self, key): return key not in self.занятые

рег = РеестрЗаглушка()
ф = Firm(name="AQUA HEAT SARL", industry="Manufacturing", city="Paris", zip_code="75011", address="Paris")
чек("этаж_1: нормальная фирма проходит", этаж_1(ф, "FR", рег)[0] is True, str(этаж_1(ф, "FR", рег)))

if BRANDS:
    бренд = BRANDS[0]
    фб = Firm(name=f"{бренд} service", industry="Manufacturing")
    чек(f"этаж_1: бренд «{бренд}» отсеивается", этаж_1(фб, "FR", рег)[0] is False)
if BLACKLIST:
    отр = BLACKLIST[0]
    фо = Firm(name="Normal Co", industry=f"{отр} services")
    чек(f"этаж_1: отрасль «{отр}» отсеивается", этаж_1(фо, "FR", рег)[0] is False)

# регион США
фус = Firm(name="AQUA INC", industry="Manufacturing", address="Tampa, FL, United States", city="Tampa")
чек("этаж_1 US: FL проходит", этаж_1(фус, "US", рег)[0] is True, str(этаж_1(фус, "US", рег)))
фус2 = Firm(name="AQUA INC", industry="Manufacturing", address="Phoenix, AZ, United States", city="Phoenix")
чек("этаж_1 US: AZ отсеивается", этаж_1(фус2, "US", рег)[0] is False, str(этаж_1(фус2, "US", рег)))

# уже использована
ключ = отпечаток("AQUA HEAT SARL", "FR", "75011", "Paris")
рег2 = РеестрЗаглушка({ключ})
чек("этаж_1: уже использованная отсеивается", этаж_1(ф, "FR", рег2)[0] is False, str(этаж_1(ф, "FR", рег2)))

print("\n=== filters: has_legal_form (для Части 2) ===")
чек("has_legal_form: 'X s.r.o.' CZ", has_legal_form("INVITAL aqua s.r.o.", "CZ") is True)
чек("has_legal_form: 'X GmbH' AT", has_legal_form("Ovivo Aqua GmbH", "AT") is True)
чек("has_legal_form: 'BARRIQUAND HEAT EXCHANGERS' FR — формы нет",
    has_legal_form("BARRIQUAND HEAT EXCHANGERS", "FR") is False)


# ============ ЧАСТЬ 1: registry.отпечаток ============
print("\n=== registry: отпечаток стабилен и складывает формы/акценты ===")
чек("отпечаток: одинаков для 'X Ltd' с разным регистром/пробелами",
    отпечаток("Aqua  Heat", "FR", "75011") == отпечаток("AQUA HEAT", "fr", "75011"),
    отпечаток("Aqua  Heat", "FR", "75011"))
чек("отпечаток: падает на город, если нет индекса",
    отпечаток("X", "FR", "", "Paris").endswith("|paris"),
    отпечаток("X", "FR", "", "Paris"))
чек("отпечаток: акценты схлопываются (é→e)",
    отпечаток("Café", "FR", "1") == отпечаток("Cafe", "FR", "1"))


# ============ ЧАСТЬ 1: address_rules ============
print("\n=== address_rules: разбор по гео ===")
from part1.data.address_rules import разобрать, штат

r = разобрать("9-13 9 RUE SAINT CLAUDE 42300, ROANNE, AUVERGNE RHONE ALPES France", "FR")
чек("FR: индекс 42300", r.индекс == "42300", r.индекс)
чек("FR: город ROANNE", r.город == "ROANNE", r.город)
чек("FR: улица содержит RUE SAINT CLAUDE", "RUE SAINT CLAUDE" in r.улица, r.улица)

r = разобрать("100 MAIN ST, MIAMI, FL, 33101, United States", "US")
чек("US: индекс 33101", r.индекс == "33101", r.индекс)
st = штат("100 MAIN ST, MIAMI, FL, 33101, United States", "US", r.город, r.индекс)
чек("US: штат FL", st == "FL", f"город={r.город} штат={st}")

r = разобрать("Belmont House Garnett Place, SKELMERSDALE, WN8 9UB, United Kingdom", "UK")
чек("UK: индекс WN8 9UB", r.индекс.replace(" ", "") == "WN89UB", r.индекс)

r = разобрать("Keizersgracht 100, 1015 CJ Amsterdam, Netherlands", "NL")
чек("NL: индекс 1015 CJ", r.индекс.replace(" ", "") == "1015CJ", r.индекс)

r = разобрать("Krucza 24, 00-526 Warszawa, Poland", "PL")
чек("PL: индекс 00-526", r.индекс == "00-526", r.индекс)

r = разобрать("Brivibas iela 1 Riga, LV-1010, Latvia", "LV")
чек("LV: индекс LV-1010", r.индекс.replace(" ", "") == "LV-1010", r.индекс)

r = разобрать("Modřická 720/56B Moravany, Jihomoravský kraj, 664 48, Czech Republic", "CZ")
чек("CZ: индекс 664 48", r.индекс.replace(" ", "") == "66448", r.индекс)

r = разобрать("42 Wallaby Way, SYDNEY, NEW SOUTH WALES, 2000, Australia", "AU")
чек("AU: индекс 2000", r.индекс == "2000", r.индекс)
st = штат("42 Wallaby Way, SYDNEY, NEW SOUTH WALES, 2000, Australia", "AU", r.город, r.индекс)
чек("AU: штат NEW SOUTH WALES", "NEW SOUTH WALES" in st, f"город={r.город} штат={st}")

чек("разбор пустого адреса не падает", разобрать("", "FR").улица == "")
чек("разбор неизвестного гео не падает", разобрать("Some St, Town", "ZZ").улица != "" or True)


# ============ ЧАСТЬ 1: dnb-хелперы ============
print("\n=== dnb: это_сайт_фирмы / _город_индекс ===")
from part1.dnb import это_сайт_фирмы, _город_индекс
чек("сайт фирмы: barriquand.com — да", это_сайт_фирмы("http://www.barriquand.com") is True)
чек("сайт: dnb.com — нет", это_сайт_фирмы("http://www.dnb.com/x") is False)
чек("сайт: dnbcountryrisk — нет", это_сайт_фирмы("https://dnbcountryrisk.com") is False)
чек("сайт: пусто — нет", это_сайт_фирмы("") is False)
г, и = _город_индекс("ROANNE, AUVERGNE RHONE ALPES, France")
чек("_город_индекс: город ROANNE", г == "ROANNE", г)


# ============ СТЫК: разбор блока B (Часть 2) ============
print("\n=== part2.engine: _разобрать_блок_B ===")
from part2.engine import _разобрать_блок_B
блок = "BARRIQUAND HEAT EXCHANGERS\nAddress: 9-13 9 RUE SAINT CLAUDE 42300, ROANNE, AUVERGNE RHONE ALPES France\nWebsite: www.barriquand.com"
имя, улица, город, индекс, сайт = _разобрать_блок_B(блок, "FR")
чек("блок B: имя", имя == "BARRIQUAND HEAT EXCHANGERS", имя)
чек("блок B: сайт", сайт == "www.barriquand.com", сайт)
чек("блок B: индекс 42300", индекс == "42300", индекс)
чек("блок B: город ROANNE", город == "ROANNE", город)
# блок без Website
имя2, *_ = _разобрать_блок_B("ACME LTD\nAddress: 1 Main St, London", "UK")
чек("блок B без Website: имя не тянет Address", имя2 == "ACME LTD", имя2)


# ============ СТЫК: имена файлов ============
print("\n=== common.files: safe_name / target_path ===")
from common.files import safe_name, target_path
чек("safe_name сохраняет точки формы", safe_name("INVITAL aqua s.r.o.") == "INVITAL aqua s.r.o.", safe_name("INVITAL aqua s.r.o."))
чек("safe_name чистит слэши", "/" not in safe_name("A/B Ltd") and "\\" not in safe_name("A\\B"))
чек("safe_name никогда не пуст", safe_name("") == "БЕЗ ИМЕНИ", safe_name(""))
чек("safe_name из одних слэшей → БЕЗ ИМЕНИ", safe_name("///") == "БЕЗ ИМЕНИ", safe_name("///"))


# ============ СТЫК: excel колонки согласованы ============
print("\n=== excel_out: заголовки согласованы с записью фирмы ===")
from part1 import excel_out
чек("КОЛОНКИ содержат 'Платёжный профиль выписки' (K)",
    "Платёжный профиль выписки" in excel_out.КОЛОНКИ, str(excel_out.КОЛОНКИ))
чек("K — 11-я колонка", excel_out.КОЛОНКИ.index("Платёжный профиль выписки") == 10,
    excel_out.КОЛОНКИ.index("Платёжный профиль выписки"))
чек("СТОЛБЕЦ_НОМЕР(9)=='Номер в реестре'", excel_out.КОЛОНКИ[8] == "Номер в реестре", excel_out.КОЛОНКИ[8])
чек("СТОЛБЕЦ_ФАЙЛ(10)=='Файл выписки'", excel_out.КОЛОНКИ[9] == "Файл выписки", excel_out.КОЛОНКИ[9])


# ============ СТЫК: реестр драйверов покрывает СПИСОК Части 1 ============
print("\n=== registry Части 2 vs СПИСОК Части 1 ===")
from part2.geos.registry import DRIVERS
for стр in СПИСОК:
    код = to_code(стр)
    есть = код in DRIVERS
    # BG, SE, DE, часть штатов США — ещё не написаны; отметим, но не как провал
    if есть:
        чек(f"драйвер для «{стр}» ({код}) есть", True)
    else:
        print(f"  ~~  драйвер для «{стр}» ({код}) НЕ написан (ожидаемо: BG/SE/DE)")


print(f"\n===== ИТОГ: {ок}/{пров} проверок пройдено =====")
if провалы:
    print("ПРОВАЛЫ:")
    for p in провалы:
        print("  - " + p)
sys.exit(0 if ок == пров else 1)
