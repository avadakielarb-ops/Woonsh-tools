# -*- coding: utf-8 -*-
"""Виртуальный прогон: проверяем парсинг/матчинг/статусы драйверов на реальных образцах."""
import sys, re
from pathlib import Path
# ПУТЬ ОТ СЕБЯ, а не вписанный: адрес полигона перестал быть корнем проекта.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.geos.registry import DRIVERS, PLAN
from part2.core.matching import Candidate, normalize
from part2.engine import _подобрать
from part2.geos.latvia import Latvia
from part2.geos.czechia import Czechia
from part2.geos.united_kingdom import UnitedKingdom, НУЖНЫЕ_ДОКУМЕНТЫ
from part2.geos.denmark import Denmark
from part2.geos.estonia import Estonia
from part2.geos.belgium import Belgium

ок = пров = 0
def чек(имя, усл, деталь=""):
    global ок, пров
    пров += 1
    if усл: ок += 1
    print(("  OK  " if усл else "  !!  ") + имя + (f"   {деталь}" if not усл and деталь else ""))


class FakeLoc:
    @property
    def first(self): return self
    def count(self): return 0
    def inner_text(self): return ""
class FakePage:
    def __init__(self, text="", url=""):
        self._t, self.url = text, url
    def inner_text(self, sel="body"):
        return self._t
    def locator(self, sel):
        return FakeLoc()
class FakeC:
    def __init__(self, name="AQUA X"): self.name = name

class FakeBr:
    """Драйвер спрашивает вкладку У БРАУЗЕРА (base.page — свойство без setter)."""
    def __init__(self, page): self.page = page


def без_инициализации(Cls, text="", url=""):
    d = object.__new__(Cls)
    d.br = FakeBr(FakePage(text, url))
    return d


print("\n=== 1. Реестр драйверов: контракт ===")
for code, cls in sorted(DRIVERS.items()):
    есть = all(hasattr(cls, m) for m in ("search", "open", "check", "fetch"))
    чек(f"{code:5} {cls.title:14} code/title/url + методы",
        bool(cls.code and cls.title and cls.url) and есть)


print("\n=== 2. Матчинг (имя → адрес/индекс, aliases) ===")
addr = "Belmont House Garnett Place, Skelmersdale, WN8 9UB"
c = Candidate
# UK: текущее имя важнее прошлого
r = _подобрать(type("C",(),{"name":"AQUA FABRICATIONS LIMITED","address":"","zip_code":""})(),
               "", [c("AQUA FABRICATIONS LIMITED", addr, aliases=("AQUA SIGNAL LTD",)),
                    c("AQUA SIGNAL & TELEGRAPHIC SYSTEMS LTD", addr, aliases=("AQUA FABRICATIONS LIMITED",))])
чек("UK: берём фирму с ТЕКУЩИМ именем", r and r.name == "AQUA FABRICATIONS LIMITED",
    f"вышло {r and r.name}")
# CAMAYA: точных тёзок двое (Nice, Saint-Remy), а наш адрес — у третьей,
# «CAMAYA (ASV AGENCE MARKETING)», с ДРУГИМ именем. Раньше её выбирал адрес.
# Правило 20.10.2026: адрес фирму не выбирает (DnB держит адрес бухгалтера,
# правда — в реестре) — решает человек.
_cam = [c("CAMAYA", "CAMAYA 96 ROUTE DE SAINT-ANTOINE 06200 NICE"),
        c("CAMAYA (ASV AGENCE MARKETING)",
          "CAMAYA (ASV AGENCE MARKETING) LA COUARDIERE 2 RUE SAINT ROCH 56800 PLOERMEL"),
        c("CAMAYA", "CAMAYA SAINT REMY DE PROVENCE 13210")]
_rc = _подобрать(type("C",(),{"name":"CAMAYA","address":"","zip_code":"56800"})(),
                 "LA COUARDIERE 2 RUE SAINT ROCH 56800", _cam)
чек("CAMAYA: другое имя адресом не выбираем → человек", _rc is None, _rc and _rc.name)
_rc2 = _подобрать(type("C",(),{"name":"CAMAYA","address":"","zip_code":"99999"})(),
                  "UNKNOWN 99999 NOWHERE", _cam)
чек("CAMAYA: чужой адрес → None (не берём наугад)", _rc2 is None, _rc2 and _rc2.name)
# тёзки с одним именем — адрес различает
_rc3 = _подобрать(type("C",(),{"name":"CAMAYA","address":"","zip_code":"06200"})(),
                  "96 ROUTE DE SAINT-ANTOINE 06200 NICE", _cam)
чек("CAMAYA: полных тёзок различает адрес", _rc3 and "NICE" in _rc3.address,
    _rc3 and _rc3.address)

# ЕДИНАЯ сверка адреса: True — сходится, False — спорит, None — не знаем
from part2.core.matching import адрес_сходится
чек("FI: город реестра подтверждается нашим адресом",
    адрес_сходится("MANNERHEIMINTIE 5 00100 HELSINKI", "HELSINKI", "00100") is True)
чек("FI: чужой город НЕ подтверждается",
    адрес_сходится("MANNERHEIMINTIE 5 00100 HELSINKI", "TAMPERE", "00100") is not True)
чек("AU: индекс 4122 в «4122 QLD» подтверждает",
    адрес_сходится("ST 4122", "51 004 HEAT 4122 QLD", "4122") is True)
чек("AU: скудный адрес с чужим индексом НЕ проходит",
    адрес_сходится("X 4122", "... 2000 NSW", "4122") is not True)
чек("HU: блок с индексом+улицей подтверждает",
    адрес_сходится("Hársfavirág utca 4032 Debrecen", "F Hársfavirág utca 4032 Debrecen", "4032") is True)
чек("пустой адрес — «не знаем», а не «похоже»",
    адрес_сходится("Kortrijkstraat 26", "", "") is None)

# ACDT: точного имени нет («… (ACDT)»), и выбирать по улице среди ДРУГИХ имён
# адрес больше не может — человек.
_acdt = [c("AGENCE CONSEIL DE DEVELOPPEMENT TERRITORIAL (ACDT)",
           "AGENCE CONSEIL DE DEVELOPPEMENT TERRITORIAL (ACDT) 29 RUE DE L'ECOLE NORMALE 33000 BORDEAUX"),
         c("AGENCE DE CONSEIL EN MANAGEMENT (ACMDT)", "7 RUE DU BERRY 29200 BREST"),
         c("AGENCE CONSEIL DE DEVELOPPEMENT TERRITORIAL PRIME (ACDTP)",
           "ACDTP 8 RUE DE LA BOETIE 33000 BORDEAUX")]
_ra = _подобрать(type("C",(),{"name":"AGENCE CONSEIL DE DEVELOPPEMENT TERRITORIAL","address":"","zip_code":"33200"})(),
                 "29 RUE DE L ECOLE NORMALE 33200 BORDEAUX", _acdt)
чек("ACDT: точного имени нет → человек, а не выбор по улице", _ra is None, _ra and _ra.name)
чек("generic rue+bordeaux не подтверждает чужую фирму",
    адрес_сходится("29 RUE DE L ECOLE NORMALE 33200 BORDEAUX", "8 RUE DE LA BOETIE 33000 BORDEAUX", "33200") is not True)
# фолбэк на прежнее имя
r = _подобрать(type("C",(),{"name":"AQUALECTRICS LTD","address":"","zip_code":""})(),
               "", [c("AQUA LTD", "Coalville LE67", aliases=("AQUALECTRICS LTD","ZOOCH LIMITED"))])
чек("UK: фолбэк на прежнее имя", r and r.name == "AQUA LTD", f"вышло {r and r.name}")
# PL: полная форма == короткое имя
чек("PL: normalize срезает польскую форму",
    normalize("AQUA JANKI SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ SPÓŁKA KOMANDYTOWO- AKCYJNA")
    == normalize("Aqua Janki"))
# LV: срез формы
чек("LV: normalize срезает Sabiedrība ar ierobežotu atbildību",
    normalize('Sabiedrība ar ierobežotu atbildību "AQUA PRO"') == normalize("AQUA PRO"))
# индекс-тайбрейк (AU/US: только индекс в строке)
r = _подобрать(type("C",(),{"name":"AQUA LTD","address":"","zip_code":"4122"})(),
               "", [c("AQUA LTD","London NW1"), c("AQUA LTD","Brisbane 4122 QLD")])
чек("AU/US: различаем однофамильцев по индексу", r and "4122" in r.address, f"вышло {r and r.address}")


print("\n=== 3. Латвия — разбор выдачи (только inner_text) ===")
lv_текст = (
    "Meklē datus par uzņēmumu\n"
    "SIA AFQ Ltd.\nRīga, Biķernieku iela 81 - 39\n"
    "Reģ. Nr. : 40203165055, Reģistrēts : 30.08.2018\nIzslēgts : 02.11.2021\n"
    "Sabiedrība ar ierobežotu atbildību \"AQUA PRO\"\nRīga, Garozes iela 1\n"
    "Reg. Nr. : 40103152891, Registered : 17.02.1995\n")
d = без_инициализации(Latvia, lv_текст)
cands = d.кандидаты_страницы()
чек("LV: струк-офф (Izslēgts) отсеян, взят 1", len(cands) == 1, f"вышло {len(cands)}")
if cands:
    чек("LV: рег.номер верный", cands[0].ref == "40103152891", f"вышло {cands[0].ref}")
    чек("LV: адрес верный", cands[0].address == "Rīga, Garozes iela 1", f"вышло {cands[0].address}")
    чек("LV: имя матчит DnB «AQUA PRO»", normalize(cands[0].name) == normalize("AQUA PRO"))


print("\n=== 4. Чехия — разбор полей выдачи ===")
cz = ("Počet nalezených subjektů: 1\n"
      "Název subjektu:\tINVITAL aqua s.r.o.\tIČO:\t027 79 897\n"
      "Sídlo:\tRybníčky 453, 747 81 Otice\n")
чек("CZ: имя без хвоста IČO", Czechia._поле(cz, "Název subjektu") == "INVITAL aqua s.r.o.",
    f"вышло {Czechia._поле(cz,'Název subjektu')!r}")
чек("CZ: адрес целиком (с городом)", Czechia._поле(cz, "Sídlo") == "Rybníčky 453, 747 81 Otice",
    f"вышло {Czechia._поле(cz,'Sídlo')!r}")


print("\n=== 5. Британия — имя/даты/фильтр документов ===")
uk_overview = ("ROXANE UK LIMITED\nCompany status\nActive\n"
               "Previous company names\nName Period\n"
               "NEPTUNE (UK) LIMITED 08 Jun 1994 - 02 Jul 2012\n"
               "PIERVAL (UK) LIMITED 30 Jun 1993 - 08 Jun 1994\n"
               "EQUALMOST ENTERPRISES LIMITED 24 May 1993 - 30 Jun 1993\n")
d = без_инициализации(UnitedKingdom)
чек("UK: старейшее имя (инкорп)", d._старейшее_имя(uk_overview) == "EQUALMOST ENTERPRISES LIMITED",
    f"вышло {d._старейшее_имя(uk_overview)!r}")
чек("UK: дата сортировки", UnitedKingdom._дата("05 Jun 1998 Incorporation") == (1998, 6, 5))
gael = [
    ("05 Jun 1998 Incorporation View PDF", True),
    ("08 Jun 2007 Company name changed gael force aquaculture LTD. View PDF", True),
    ("24 Dec 2024 Resolutions Resolution of reduction in issued share capital View PDF", False),
    ("11 Jun 2007 Memorandum and Articles of Association View PDF", False),
]
плохо = [s for s, ждём in gael
         if (any(k in s.lower() for k in НУЖНЫЕ_ДОКУМЕНТЫ)) != ждём]
чек("UK: фильтр берёт инкорп+смены имени, отсекает мусор", not плохо, f"ошиблись: {плохо}")


print("\n=== 6. Дания — поля карточки (HUMAN-ветка) ===")
dk = ("HYDRO PRECISION TUBING TØNDER A/S\nCVR-nummer\n37488410\n"
      "Adresse\nHydrovej 6\nPostnummer og by\n6270 Tønder\nStatus\nNormal\n")
чек("DK: адрес", Denmark._поле(dk, "Adresse") == "Hydrovej 6", f"вышло {Denmark._поле(dk,'Adresse')!r}")
чек("DK: статус", Denmark._поле(dk, "Status") == "Normal")
d = без_инициализации(Denmark); d.статус = "Under konkurs"; d.имя=""; d.адрес=""
чек("DK: konkurs → отсев", d.check(None)[0] is False)
d.статус = "Normal"
чек("DK: Normal → проходит", d.check(None)[0] is True)


print("\n=== 7. Эстония — статус/НДС/красные флаги ===")
ee_ok = ("Osaühing AA Aqua (10795288)\nRegistry code\n10795288\n"
         "Legal form\nPrivate limited company\nStatus\nEntered into the register\n"
         "VAT number\nEE100716922\nAddress\nViljandi maakond, Viljandi linn, Väike-Turu tn 3, 71003\n")
d = без_инициализации(Estonia, ee_ok)
d.имя=""; d.адрес=""; d.код=""
res = d.check(FakeC())
чек("EE: активная с НДС проходит", res[0] is True, f"вышло {res}")
чек("EE: номер (Registry code) считан", d.код == "10795288", f"вышло {d.код}")
# НЕСДАННЫЕ ОТЧЁТЫ БОЛЬШЕ НЕ ОТСЕИВАЮТ (решение 16.09.2026): «если фирма
# активна — берём». Это была самая частая причина отказа по Эстонии: 131 фирма
# за прогоны 11–12.09. Отсев остался только за объявленным удалением из реестра.
ee_flag = ee_ok + "\nLegal person has non-submitted annual reports\n"
d2 = без_инициализации(Estonia, ee_flag); d2.имя=d2.адрес=d2.код=""
чек("EE: несданные отчёты — фирма активна, берём", d2.check(FakeC())[0] is True)
# ПРЕДУПРЕЖДЕНИЕ ОБ УДАЛЕНИИ ТОЖЕ НЕ ОТСЕИВАЕТ (правило уточнено 17.09.2026:
# «просрочила годовой отчёт — берём, не берём только тех, кто в ликвидации»).
# В Эстонии предупреждение выносят ИМЕННО за несданные отчёты — та же причина,
# просто следующим шагом. Отсев остался за ликвидацией и за «Deleted».
ee_del = ee_ok + "\nDeletion warning\n"
d2b = без_инициализации(Estonia, ee_del); d2b.имя=d2b.адрес=d2b.код=""
чек("EE: предупреждение об удалении — берём", d2b.check(FakeC())[0] is True)
ee_liq = ee_ok.replace("Entered into the register", "In liquidation")
d2c = без_инициализации(Estonia, ee_liq); d2c.имя=d2c.адрес=d2c.код=""
чек("EE: ликвидация → отсев", d2c.check(FakeC())[0] is False)
ee_novat = ee_ok.replace("EE100716922", "—")
d3 = без_инициализации(Estonia, ee_novat); d3.имя=d3.адрес=d3.код=""
# НДС БОЛЬШЕ НЕ ПРИЧИНА ОТСЕВА (решение 08.09.2026). В Эстонии номер дают
# только с оборота ~40 000 €, живая мелкая OÜ его не имеет, и сам номер мы
# нигде не храним: 49 фирм было выброшено зря. Проверка ждала старого
# поведения и падала — значит правило поменяли, а её забыли.
чек("EE: без НДС всё равно проходит (мелкая OÜ — норма)",
    d3.check(FakeC())[0] is True, f"вышло {d3.check(FakeC())}")


print("\n=== 8. Бельгия — статус по полям (не по всей странице) ===")
be = ("Ondernemingsnummer: 0897.961.464\nStatus: Actief\n"
      "Rechtstoestand: Normale toestand\nSinds 16 mei 2008\n"
      "Naam: COMPACT HEAT EXCHANGER COMPANY\n"
      "Btw-activiteiten ... stopgezet\n")   # «stopgezet» есть, но НЕ в статусе
d = без_инициализации(Belgium, be)
чек("BE: активная проходит, несмотря на 'stopgezet' в тексте", d.check(None)[0] is True,
    f"вышло {d.check(None)}")
be_bad = be.replace("Normale toestand", "Faillissement")
d2 = без_инициализации(Belgium, be_bad)
чек("BE: банкротство (не Normale toestand) → отсев", d2.check(None)[0] is False)


print("\n=== 9. Финляндия — поля карточки Virre ===")
from part2.geos.finland import Finland
fi = ("Company names\nLines of business\n"                 # ← меню-ловушка для «Name»
      "Basic details of the company\n"
      "Name\nFortum Power and Heat Oy\n01.03.1999\n"
      "Business ID\n0109160-2\n"
      "Registered office\nEspoo\n26.03.2002\n"
      "Company type\nLimited company\n01.01.1000\n"
      "Status of company\nIn the register\n05.07.1932\n"
      "Postal address\nPL 100 00048 Fortum Finland\n")
чек("FI: имя (не поймало «Company names»)",
    Finland._поле(fi, "Name") == "Fortum Power and Heat Oy", Finland._поле(fi, "Name"))
чек("FI: тип компании", Finland._поле(fi, "Company type") == "Limited company",
    Finland._поле(fi, "Company type"))
чек("FI: статус", Finland._поле(fi, "Status of company") == "In the register")
чек("FI: адрес", Finland._поле(fi, "Postal address") == "PL 100 00048 Fortum Finland")
d = без_инициализации(Finland, fi); d.имя=d.адрес=d.bid=""
чек("FI: действующая Limited company проходит", d.check(FakeC())[0] is True, str(d.check(FakeC())))
чек("FI: Business ID считан", d.bid == "0109160-2", d.bid)
fi_bad = fi.replace("Limited company", "Association")
d2 = без_инициализации(Finland, fi_bad); d2.имя=d2.адрес=d2.bid=""
чек("FI: Association → отсев (🔴)", d2.check(FakeC())[0] is False)

print("\n=== 10. Швейцария — поля карточки Zefix ===")
from part2.geos.switzerland import Switzerland
ch = ("Heatbox GmbH\n"
      "address\nSt. Gallerstrasse 25\n"
      "ZIP / Town\n8645 Jona\n"
      "legal form\nLimited Liability Company\n"
      "seat\nRapperswil-Jona\n"
      "status\nactive\n"
      "UID\nCHE-123.456.789\n")
чек("CH: адрес", Switzerland._поле(ch, "address") == "St. Gallerstrasse 25",
    Switzerland._поле(ch, "address"))
чек("CH: ZIP / Town", Switzerland._поле(ch, "ZIP / Town") == "8645 Jona")
чек("CH: правовая форма",
    Switzerland._поле(ch, "legal form") == "Limited Liability Company")
чек("CH: статус", Switzerland._поле(ch, "status") == "active")
d = без_инициализации(Switzerland, ch); d.имя=d.адрес=d.uid=""
чек("CH: активная GmbH проходит", d.check(FakeC())[0] is True, str(d.check(FakeC())))
чек("CH: UID считан", d.uid == "CHE-123.456.789", d.uid)
чек("CH: адрес собран (улица + индекс/город)",
    d.адрес == "St. Gallerstrasse 25, 8645 Jona", d.адрес)
d2 = без_инициализации(Switzerland, ch.replace("Limited Liability Company", "Association"))
d2.имя=d2.адрес=d2.uid=""
чек("CH: Association → отсев (🔴)", d2.check(FakeC())[0] is False)
d3 = без_инициализации(Switzerland, ch.replace("status\nactive", "status\nin liquidation"))
d3.имя=d3.адрес=d3.uid=""
чек("CH: ликвидация → отсев", d3.check(FakeC())[0] is False)

print("\n=== 11. Хорватия — поля карточки Sudski registar ===")
from part2.geos.croatia import Croatia
hr = ("Podaci o subjektu / objave\n"
      "Nadležni sud\nTrgovački sud u Zagrebu\n"
      "MBS\n081716640\n"
      "OIB\n66690755128\n"
      "EUID\nHRSR.081716640\n"
      "Status\nBez postupka\n"
      "Tvrtka\nCOOL HEAT SYSTEM d.o.o. za usluge\nCOOL HEAT SYSTEM d.o.o.\n"
      "Sjedište/adresa\nZagreb (Grad Zagreb)\nRadnička cesta 80\n"
      "Pravni oblik\nDruštvo s ograničenom odgovornošću\n")
чек("HR: статус «Bez postupka»", Croatia._поле(hr, "Status") == "Bez postupka",
    Croatia._поле(hr, "Status"))
чек("HR: имя (первая, полная строка Tvrtka)",
    Croatia._поле(hr, "Tvrtka") == "COOL HEAT SYSTEM d.o.o. za usluge",
    Croatia._поле(hr, "Tvrtka"))
чек("HR: адрес из двух строк",
    Croatia._адрес(hr) == "Zagreb (Grad Zagreb), Radnička cesta 80", Croatia._адрес(hr))
d = без_инициализации(Croatia, hr); d.имя=d.адрес=d.mbs=""
чек("HR: действующая d.o.o. проходит", d.check(FakeC())[0] is True, str(d.check(FakeC())))
d2 = без_инициализации(Croatia, hr.replace("Bez postupka", "Stečaj"))
d2.имя=d2.адрес=d2.mbs=""
чек("HR: стечай → отсев", d2.check(FakeC())[0] is False)
d3 = без_инициализации(Croatia, hr.replace("Društvo s ograničenom odgovornošću", "Udruga"))
d3.имя=d3.адрес=d3.mbs=""
чек("HR: udruga → отсев (🔴)", d3.check(FakeC())[0] is False)

print("\n=== 12. Норвегия — поля карточки brreg ===")
from part2.geos.norway import Norway
no = ("POWER HEAT PIPING SOUTH AB\n"
      "Organisation number:\n926 457 438\n"
      "Business address:\nRisyxegatan 6\nSE21376 Malmö\n"
      "Country:\nSverige\n"
      "Type of organisation:\nUtenlandsk enhet\n"
      "Web address:\nwww.powerheat.se\n")
чек("NO: адрес из двух строк",
    Norway._адрес(no) == "Risyxegatan 6, SE21376 Malmö", Norway._адрес(no))
чек("NO: тип организации",
    Norway._поле(no, "Type of organisation") == "Utenlandsk enhet")
d = без_инициализации(Norway, no); d.имя=d.адрес=d.orgnr=""
чек("NO: «Utenlandsk enhet» ПРОХОДИТ (решение проекта)",
    d.check(FakeC())[0] is True, str(d.check(FakeC())))
d2 = без_инициализации(Norway, no.replace("Utenlandsk enhet", "Stiftelse"))
d2.имя=d2.адрес=d2.orgnr=""
чек("NO: Stiftelse → отсев (🔴)", d2.check(FakeC())[0] is False)
d3 = без_инициализации(Norway, no + "\nKonkurs\n"); d3.имя=d3.адрес=d3.orgnr=""
чек("NO: konkurs → отсев", d3.check(FakeC())[0] is False)

print("\n=== 13. Венгрия — поля карточки e-cegjegyzek ===")
from part2.geos.hungary import Hungary
hu = ("AQUA SERVICE ECO 83 Kft.\n"
      "AQUA SERVICE ECO 83 Kereskedelmi, Szolgáltató és Vízkezelési Korlátolt Felelősségű Társaság\n"
      "Cégjegyzékszám\n20-09-063203\n"
      "Adószám\n11359975-2-20\n"
      "Székhely\n8800 Nagykanizsa, Tavasz utca 4. Térkép\n")
чек("HU: номер (Cégjegyzékszám)",
    Hungary._поле(hu, "Cégjegyzékszám") == "20-09-063203")
чек("HU: адрес без хвоста «Térkép»",
    Hungary._поле(hu, "Székhely") == "8800 Nagykanizsa, Tavasz utca 4.",
    Hungary._поле(hu, "Székhely"))
# «felszámolás alatt» в НАЗВАНИИ → отсев (как у AQUARIUS-AQUA из DnB)
d = без_инициализации(Hungary, hu); d.имя=d.адрес=d.cegjegyzek=""
res = d.check(FakeC())
чек("HU: действующая Kft. проходит", res[0] is True, str(res))
hu_bad = hu.replace("Korlátolt Felelősségű Társaság",
                    "Korlátolt Felelősségű Társaság \"felszámolás alatt\"")
d2 = без_инициализации(Hungary, hu_bad); d2.имя=d2.адрес=d2.cegjegyzek=""
чек("HU: «felszámolás alatt» в имени → отсев", d2.check(FakeC())[0] is False)

print("\n=== 14. Словения — поля карточки AJPES ===")
from part2.geos.slovenia import Slovenia
si = ("AQUA - SO 23 vodne storitve in inženiring d.o.o. | Identification Number 6329632000\n"
      "Basic Information about the Entity\n"
      "Entity status\nregistered\n"
      "Court/business register entry date\n04.03.2013\n"
      "Registration number\n6329632000\n"
      "Tax number\nSI 40025683\n"
      "Full company name\nAQUA - SO 23 vodne storitve in inženiring d.o.o.\n"
      "Short company name\nAQUA - SO 23 d.o.o\n"
      "Registered office\nSodji Vrh\n"
      "Business address\nSodji Vrh 24, 8333 Semič\n"
      "Legal organizational form\nLimited liability company (d.o.o.)\n")
чек("SI: статус", Slovenia._поле(si, "Entity status") == "registered")
чек("SI: полное имя",
    Slovenia._поле(si, "Full company name") == "AQUA - SO 23 vodne storitve in inženiring d.o.o.")
чек("SI: адрес", Slovenia._поле(si, "Business address") == "Sodji Vrh 24, 8333 Semič")
d = без_инициализации(Slovenia, si); d.имя=d.адрес=d.рег=""
res = d.check(FakeC())
чек("SI: действующая d.o.o. проходит", res[0] is True, str(res))
чек("SI: номер (Registration number)", d.рег == "6329632000", d.рег)
d2 = без_инициализации(Slovenia, si.replace("Limited liability company (d.o.o.)", "Društvo"))
d2.имя=d2.адрес=d2.рег=""
чек("SI: društvo → отсев (🔴)", d2.check(FakeC())[0] is False)
d3 = без_инициализации(Slovenia, si.replace("registered", "in liquidation"))
d3.имя=d3.адрес=d3.рег=""
чек("SI: не registered → отсев", d3.check(FakeC())[0] is False)

print("\n=== 15. Австрия — разбор строки выдачи GISA ===")
from part2.geos.austria import Austria
at_row = ("GISA extract\nGISA extract incl. historical data\n"
          "19942254\nLicence valid\n"
          "Holder of the business licence\nOvivo Aqua Austria GmbH;093915k\n"
          "Generate business licence\nfrom: 02.02.2013\n"
          "Location\n8074 Raaba-Grambach\n"
          "Entwicklung und Herstellung von Wasseraufbereitungsanlagen\n")
m = re.search(r"Holder of the business licence\s*\n?\s*([^;\n]+?)\s*(?:;\s*([^\s\n]+))?\s*\n",
              at_row, re.I)
чек("AT: имя держателя", m and m.group(1).strip() == "Ovivo Aqua Austria GmbH",
    m and m.group(1))
чек("AT: номер Фирменбуха", m and (m.group(2) or "").strip() == "093915k",
    m and m.group(2))
ma = re.search(r"Location\s*\n?\s*([^\n]+)", at_row, re.I)
чек("AT: адрес", ma and ma.group(1).strip() == "8074 Raaba-Grambach")
d = без_инициализации(Austria, at_row)
d.имя = "Ovivo Aqua Austria GmbH"; d.адрес=""; d.фб="093915k"; d._текст = at_row
чек("AT: действующая лицензия проходит", d.check(FakeC())[0] is True, str(d.check(FakeC())))
d2 = без_инициализации(Austria, at_row)
d2.имя = "Wasser Verein"; d2.адрес=""; d2.фб=""; d2._текст = at_row
чек("AT: Verein → отсев (🔴)", d2.check(FakeC())[0] is False)
d3 = без_инициализации(Austria, at_row.replace("Licence valid", "Licence terminated"))
d3.имя = "Ovivo Aqua Austria GmbH"; d3.адрес=""; d3.фб=""
d3._текст = at_row.replace("Licence valid", "Licence terminated")
чек("AT: недействующая лицензия → отсев", d3.check(FakeC())[0] is False)

print(f"\n===== ИТОГ: {ок}/{пров} проверок пройдено =====")
sys.exit(0 if ок == пров else 1)
