# -*- coding: utf-8 -*-
"""Виртуальный прогон, часть 2: FR, US-FL, NL, DK, LV, NO, BG — правки аудита."""
import sys, re, os, tempfile
from pathlib import Path
# ИЗОЛЯЦИЯ обучения BG: пишем во ВРЕМЕННЫЙ файл, не в боевой словарь (ДО импортов!)
_тестфайл = Path(tempfile.gettempdir()) / "translit_bg_TEST.json"
if _тестфайл.exists():
    _тестфайл.unlink()
os.environ["TRANSLIT_BG_FILE"] = str(_тестфайл)
# ПУТЬ ОТ СЕБЯ, а не вписанный. Здесь стоял адрес полигона, и после переезда
# проекта все четыре виртуальных прогона молча падали на импорте.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.core.matching import Candidate
from part2.geos.france import France
from part2.geos.usa_florida import USAFlorida
# NL исключены из проверок по просьбе пользователя (файлы Нидерландов не трогаем)
from part2.geos.denmark import Denmark
from part2.geos.latvia import Latvia
from part2.geos.norway import Norway

ок = пров = 0
def чек(имя, усл, деталь=""):
    global ок, пров
    пров += 1
    if усл: ок += 1
    print(("  OK  " if усл else "  !!  ") + имя + (f"   -> {деталь}" if not усл and деталь else ""))

class FakeLoc:
    @property
    def first(self): return self
    def count(self): return 0
    def inner_text(self): return ""
class FakePage:
    def __init__(self, text="", url=""): self._t, self.url = text, url
    def inner_text(self, sel="body"): return self._t
    def locator(self, sel): return FakeLoc()
class FakeC:
    def __init__(self, name="AQUA X"): self.name = name

class FakeBr:
    """Драйвер спрашивает вкладку У БРАУЗЕРА (base.page — свойство без setter)."""
    def __init__(self, page): self.page = page


def пустой(Cls, text="", url=""):
    d = object.__new__(Cls)
    d.br = FakeBr(FakePage(text, url))
    return d


print("\n=== FR: данные_реестра (колонка K) ===")
fr_body = ("AQUA SERVICE\nEN ACTIVITÉ\n"
           "Sa forme juridique est SAS, société par actions simplifiée.\n"
           "Adresse\n12 RUE DES LILAS 75011 PARIS\n"
           "SIREN 812 345 678\n")
d = пустой(France, fr_body, "https://annuaire-entreprises.data.gouv.fr/entreprise/aqua-service-812345678")
d.имя = ""; d.адрес = ""; d.siren = ""; d.siret = ""
ок_, прич = d.check(FakeC())
чек("FR: EN ACTIVITÉ + SAS проходит", ок_ is True, прич)
чек("FR: SIREN из URL", d.siren == "812345678", d.siren)
r = d.данные_реестра()
чек("FR: адрес из поля Adresse", r["адрес"] == "12 RUE DES LILAS 75011 PARIS", r["адрес"])
d2 = пустой(France, fr_body.replace("SAS, société par actions simplifiée",
                                    "Association déclarée"),
            "https://x/entreprise/a-812345678")
d2.имя = d2.адрес = d2.siren = d2.siret = ""
чек("FR: Association → отсев (🔴)", d2.check(FakeC())[0] is False)

print("\n=== FR: состояние НЕ течёт между фирмами (баг KALAM→KEROPS) ===")
class H1Page:
    """FakePage, но locator('h1') отдаёт первую строку тела (как annuaire)."""
    def __init__(self, text="", url=""): self._t, self.url = text, url
    def inner_text(self, sel="body"): return self._t
    def locator(self, sel):
        первая = next((s.strip() for s in self._t.split("\n") if s.strip()), "")
        class L:
            @property
            def first(s): return s
            def count(s): return 1 if первая else 0
            def inner_text(s): return первая
        return L()
def fr_с_h1(text, url):
    d = object.__new__(France); d.br = FakeBr(H1Page(text, url))
    d.имя = d.адрес = d.siren = d.siret = ""
    return d
fr1 = fr_с_h1("KEROPS\nEN ACTIVITÉ\nAdresse\n1 rue A 75001 PARIS\nSIREN 943 736 611",
              "https://x/entreprise/kerops-943736611")
fr1.check(FakeC()); r1 = fr1.данные_реестра()
чек("FR: фирма1 → имя KEROPS", r1["имя"] == "KEROPS", r1["имя"])
чек("FR: фирма1 → SIREN 943736611", fr1.siren == "943736611", fr1.siren)
# следующая фирма = СВЕЖИЙ инстанс (как теперь делает движок)
fr2 = fr_с_h1("KALAM CONSEIL\nEN ACTIVITÉ\nAdresse\n2 rue B 69001 LYON\nSIREN 831 822 655",
              "https://x/entreprise/kalam-831822655")
fr2.check(FakeC()); r2 = fr2.данные_реестра()
чек("FR: фирма2 → имя KALAM CONSEIL (НЕ утекло KEROPS)", r2["имя"] == "KALAM CONSEIL", r2["имя"])
чек("FR: фирма2 → SIREN 831822655", fr2.siren == "831822655", fr2.siren)

print("\n=== US-FL: check по полю Status ===")
us_body = ("Detail by Entity Name\nFlorida Profit Corporation\nAQUA GROUP INC\n"
           "Filing Information\nDocument Number\nP23000040761\n"
           "Status\nACTIVE\n"
           "Principal Address\n100 MAIN ST, MIAMI, FL 33101\n")
d = пустой(USAFlorida, us_body)
d.имя = d.адрес = ""
ок_, прич = d.check(FakeC())
чек("US: ACTIVE проходит", ок_ is True, прич)
чек("US: адрес из Principal Address", d.адрес == "100 MAIN ST, MIAMI, FL 33101", d.адрес)
d = пустой(USAFlorida, us_body.replace("Status\nACTIVE", "Status\nINACTIVE"))
d.имя = d.адрес = ""
чек("US: INACTIVE → отсев", d.check(FakeC())[0] is False)
# ловушка: слово ACTIVE где-то ещё, но поле Status = INACT
d = пустой(USAFlorida, "Search Active Filings\n" + us_body.replace("Status\nACTIVE", "Status\nINACT"))
d.имя = d.адрес = ""
чек("US: ACTIVE в меню НЕ спасает мёртвую фирму", d.check(FakeC())[0] is False)

# NL (Нидерланды) ИСКЛЮЧЕНЫ из проверок по просьбе пользователя — файлы NL не трогаем.

print("\n=== DK: статус только из поля ===")
d = пустой(Denmark, "")
d.статус = "Normal"
чек("DK: Normal проходит", d.check(FakeC())[0] is True)
d = пустой(Denmark, "")
d.статус = "Under konkurs"
чек("DK: konkurs → отсев", d.check(FakeC())[0] is False)
# ловушка: статус пуст, но на странице есть слово konkurs в меню — берём ПОЛЕ Status
d = пустой(Denmark, "Menu: Konkurs og gældssanering\nStatus\nNormal\n")
d.статус = ""
чек("DK: слово konkurs в меню не отсеивает (читаем поле)", d.check(FakeC())[0] is True,
    str(d.check(FakeC())))
d = пустой(Denmark, "нет тут ничего")
d.статус = ""
чек("DK: статус не найден → честный отказ", d.check(FakeC())[0] is False)

print("\n=== LV: прежние имена (Iepriekš) ===")
lv_text = ("SIA AQUA JAUNAIS\nBrivibas iela 1, Riga, LV-1010\n"
           "Reģ. Nr. : 40003456789\nIepriekš: SIA AQUA VECAIS\n")
d = пустой(Latvia, lv_text)
cands = d.кандидаты_страницы()
чек("LV: один кандидат", len(cands) == 1, str(len(cands)))
чек("LV: рег.номер", cands and cands[0].ref == "40003456789", cands and cands[0].ref)
чек("LV: прежнее имя в aliases",
    cands and cands[0].aliases and "VECAIS" in cands[0].aliases[0],
    cands and cands[0].aliases)
d = пустой(Latvia, lv_text.replace("Iepriekš: SIA AQUA VECAIS", "Izslēgts"))
чек("LV: Izslēgts → кандидат отброшен", len(d.кандидаты_страницы()) == 0)

print("\n=== NO: сайт из реестра ===")
no_text = ("Organisation number:\n926 457 438\n"
           "Business address:\nRisyxegatan 6\nSE21376 Malmö\n"
           "Country:\nSverige\n"
           "Type of organisation:\nUtenlandsk enhet\n"
           "Web address:\nwww.powerheat.se\n")
d = пустой(Norway, no_text)
d.имя = "POWERHEAT AB"; d.адрес = ""; d.orgnr = "926457438"; d.сайт = ""
ок_, прич = d.check(FakeC())
чек("NO: иностранная сущность проходит", ок_ is True, прич)
r = d.данные_реестра()
чек("NO: сайт из brreg", r.get("сайт") == "www.powerheat.se", r.get("сайт"))
чек("NO: адрес в две строки", r["адрес"] == "Risyxegatan 6, SE21376 Malmö", r["адрес"])
d = пустой(Norway, no_text.replace("Utenlandsk enhet", "Stiftelse"))
d.имя = d.адрес = d.orgnr = d.сайт = ""
чек("NO: Stiftelse → отсев (🔴)", d.check(FakeC())[0] is False)

print("\n=== BG: транслит (словарь+правила+обучение) / K / сверка / выписка ===")
from part2.geos.bulgaria import Bulgaria, bg_имя_адрес, _норм_bg
from part2.geos.translit_bg import транслит, транслит_адрес, запомнить, _ядро, ВЫУЧЕНО
from part2.core.models import Company as Co2
# ядро/норм
чек("BG: _ядро снимает форму OOD (латиница)", _ядро("HEAT ENERGY OOD") == "heat energy", _ядро("HEAT ENERGY OOD"))
чек("BG: _норм снимает кавычки и ООД (кириллица)",
    _норм_bg('"ХИЙТ ЕНЕРДЖИ" ООД') == "хийт енерджи", _норм_bg('"ХИЙТ ЕНЕРДЖИ" ООД'))
# словарь (возврат — кортеж (строка, уверенно))
чек("BG: HEAT ENERGY → ХИЙТ ЕНЕРДЖИ (уверенно)", транслит("HEAT ENERGY") == ("ХИЙТ ЕНЕРДЖИ", True), транслит("HEAT ENERGY"))
чек("BG: LN SOLUTIONS OOD → ЛН СЪЛЮШЪНС", транслит("LN SOLUTIONS OOD")[0] == "ЛН СЪЛЮШЪНС", транслит("LN SOLUTIONS OOD"))
чек("BG: AQUA ENGINEERING GROUP", транслит("AQUA ENGINEERING GROUP OOD")[0] == "АКВА ИНЖЕНЕРИНГ ГРУП", транслит("AQUA ENGINEERING GROUP OOD"))
# правила окончаний (слово не в словаре) → уверенно=False
им, ув = транслит("ZORNITSA CONSTRUCTIONS")
чек("BG: -tions → -шънс (правило окончаний)", "ШЪНС" in им, им)
чек("BG: незнакомое слово → не уверен (флаг проверки)", ув is False, str(ув))
# латинизированный болгарский (тип B) из словаря
чек("BG: STROITELSTVO → СТРОИТЕЛСТВО (болг. латиницей)", транслит("STROITELSTVO INVEST OOD")[0] == "СТРОИТЕЛСТВО ИНВЕСТ", транслит("STROITELSTVO INVEST OOD"))
# адрес
чек("BG: адрес — Sofia→София + индекс", "СОФИЯ" in транслит_адрес("1 Yerusalim str, Sofia, 1784").upper() and "1784" in транслит_адрес("1 Yerusalim str, Sofia, 1784"), транслит_адрес("1 Yerusalim str, Sofia, 1784"))
# bg_имя_адрес возвращает (имя, адрес, уверенно)
n, a, u = bg_имя_адрес(Co2(row=2, name="LN SOLUTIONS OOD", address="1 Yerusalim str", city="Sofia", zip_code="1784"))
чек("BG: bg_имя_адрес — имя из словаря", n == "ЛН СЪЛЮШЪНС", n)
чек("BG: bg_имя_адрес — адрес с индексом", "1784" in a, a)
чек("BG: bg_имя_адрес — флаг уверенности есть", isinstance(u, bool), str(u))
# ОБУЧЕНИЕ: реестр показал реальное имя → запомнили пословно
запомнить("QRZX BRANDONIX OOD", '"КРЗ БРАНДОНИКС" ООД')
чек("BG: обучение — фраза выучена", транслит("QRZX BRANDONIX")[0] == "КРЗ БРАНДОНИКС", транслит("QRZX BRANDONIX"))
чек("BG: обучение — уверенность стала True", транслит("QRZX BRANDONIX")[1] is True)
чек("BG: обучение — отдельное слово выучено", ВЫУЧЕНО["слова"].get("brandonix") == "брандоникс", ВЫУЧЕНО["слова"].get("brandonix"))

# выписка «State of play»
выписка = ("\"ХИЙТ ЕНЕРДЖИ\" LLC\nUIC 200591594, state by date: 24/07/2026\n"
           "Main circumstances\n1. UIC/PIC\n200591594\n"
           "2. Company/Name\nХИЙТ ЕНЕРДЖИ\n"
           "3. Legal form\nДружество с ограничена отговорност\n"
           "5. Head office and registered office\n"
           "Country: БЪЛГАРИЯ Region: Перник Municipality: Перник City/Village: гр. Перник, п.с. 2300\n"
           "6. Scope of business activity\nТърговия\n")
d = пустой(Bulgaria, выписка, "https://portal.registryagency.bg/CR/en/Reports/ActiveConditionTabResult?uic=200591594")
d.имя = "HEAT ENERGY OOD"; d.адрес = "1 Test str, Pernik, 2300"
d.uic = d.bg_name = d.имя_реестра = d.адрес_реестра = ""
ок_, прич = d.check(FakeC("HEAT ENERGY OOD"))   # имя ↔ карточка совпадают → обучение корректно
чек("BG: активная выписка проходит", ок_ is True, прич)
чек("BG: UIC 200591594", d.номер() == "200591594", d.номер())
чек("BG: колонка K на АНГЛИЙСКОМ (имя из Части 1)", d.данные_реестра()["имя"] == "HEAT ENERGY OOD", d.данные_реестра()["имя"])
чек("BG: реестр имя (кириллица) для сверки", d.extra_fields().get("Реестр имя BG") == "ХИЙТ ЕНЕРДЖИ", d.extra_fields())
чек("BG: реестр адрес (кириллица) для сверки", "Перник" in d.extra_fields().get("Реестр адрес BG",""), d.extra_fields())
d = пустой(Bulgaria, выписка + "\nДружеството е в ликвидация\n")
d.имя = d.адрес = d.uic = d.bg_name = d.имя_реестра = d.адрес_реестра = ""
чек("BG: ликвидация → отсев", d.check(FakeC())[0] is False)
чек("BG: контракт полон",
    all(hasattr(Bulgaria, m) for m in ("search","open","check","fetch","номер","данные_реестра","кандидаты_страницы","extra_fields")))
# РАЗЛИЧЕНИЕ ТЁЗОК по правовой форме (случай AQUA SYSTEMS: ООД/ЕООД/ЕАД)
from part2.geos.bulgaria import подобрать_по_форме, _форма_dnb, _форма_канд
чек("BG: форма из DnB — EAD→ЕАД", _форма_dnb("AQUA SYSTEMS EAD") == "ЕАД", _форма_dnb("AQUA SYSTEMS EAD"))
чек("BG: форма кандидата — '\"АКВА СИСТЕМС\" ЕАД'→ЕАД", _форма_канд('"АКВА СИСТЕМС" ЕАД') == "ЕАД", _форма_канд('"АКВА СИСТЕМС" ЕАД'))
тёзки = [Candidate('"АКВА СИСТЕМС" ООД', ref="1"),
         Candidate('"АКВА СИСТЕМС" ЕООД', ref="2"),
         Candidate('"АКВА СИСТЕМС" ЕАД', ref="3")]
выбр = подобрать_по_форме(тёзки, "аква системс", "ЕАД")
чек("BG: из ООД/ЕООД/ЕАД по форме выбран ЕАД", len(выбр) == 1 and выбр[0].ref == "3", [x.name for x in выбр])
# формы нет → возвращает всех тёзок (дальше их различит адрес/человек)
выбр2 = подобрать_по_форме(тёзки, "аква системс", "")
чек("BG: без формы — все тёзки остаются (для адреса/человека)", len(выбр2) == 3, len(выбр2))

print(f"\n===== ИТОГ: {ок}/{пров} проверок пройдено =====")
sys.exit(0 if ок == пров else 1)
