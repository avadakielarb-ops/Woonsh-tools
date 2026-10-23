"""
ПРАВОВЫЕ ФОРМЫ под Google Ads Advertiser Verification.

РЕШЕНИЕ (v2): жёсткий «белый список» СНЯТ. Берём 🟢 и 🟡, отсеиваем только 🔴.
  🟢 компании с ограниченной ответственностью (LLC/Ltd/GmbH/AG/SA/SAS/BV/Oy/OÜ/
     SIA/AB/Sp. z o.o./Kft./d.o.o./Pty Ltd …) — берём всегда;
  🟡 ИП и коммерческие партнёрства (Sole Trader, Einzelfirma, JDG, OSVČ, FIE,
     s.p., obrt, Micro-entrepreneur, OHG, KG, VOF, Bt., Sp.k. …) — тоже берём,
     они реально проходят верификацию;
  🔴 фонды, ассоциации, общественные организации, кооперативы — ОТСЕВ,
     плюс любой статус ликвидации/банкротства/закрытия.

Так база получается на 15–30% больше при том же качестве.
"""
from __future__ import annotations

import re
import unicodedata

# 🔴 ФОРМЫ-СТОП по гео (в нижнем регистре, без диакритики — см. _фолд)
ЗАПРЕЩЁННЫЕ_ФОРМЫ: dict[str, tuple[str, ...]] = {
    "UK": ("community interest company", "limited by guarantee", "dormant",
           "charitable incorporated"),
    "CH": ("verein", "stiftung", "genossenschaft", "association", "foundation",
           "cooperative"),
    "FR": ("association", "societe civile", "sci", "snc",
           "societe en nom collectif"),
    "PL": ("fundacja", "stowarzyszenie", "spoldzielnia"),
    "SE": ("ideell forening", "stiftelse", "forening"),
    "LV": ("biedriba", "nodibinajums"),
    "EE": ("mtu", "sihtasutus", "foundation"),
    "AU": ("incorporated association", "trust", "deregistered"),
    "DK": ("fond", "forening"),
    "CZ": ("z.s.", "o.p.s.", "druzstvo", "spolek"),
    "FI": ("yhdistys", "saatio", "association", "foundation"),   # сайт бывает на EN
    "BE": ("asbl", "vzw", "stichting"),
    "BG": ("fondaciya", "sdruzhenie", "фондация", "сдружение"),
    "HU": ("egyesulet", "alapitvany"),
    "HR": ("udruga", "zadruga"),
    "NO": ("stiftelse", "forening"),
    "DE": ("e.v.", "stiftung"),
    "NL": ("stichting", "vereniging"),
    "AT": ("verein", "stiftung"),
    "SI": ("drustvo", "zavod", "zadruga"),
    "US": ("nonprofit", "non-profit", "cooperative"),
}

# 🔴 СТАТУСЫ-СТОП — общие для всех гео (ликвидация / банкротство / закрытие)
ЗАПРЕЩЁННЫЕ_СТАТУСЫ: tuple[str, ...] = (
    "likvidac", "likwidac", "liquidation", "liquidat",   # корни: likvidaci/likvidacij…
    # Австрия пишет сокращённо: «PRISMA … m.b.H. in Liqu.» — скачали фирму в
    # ликвидации (живой прогон 20.10.2026). Только с «in », чтобы «Liquid
    # Gold GmbH» не стала ликвидированной.
    "in liqu",
    "upadlo", "konkurs", "konkurssi", "insolven", "insolvenz", "bankrupt",
    "dissolved", "deregistered", "radiee", "felszamol", "likvideerimisel",
    "faillissement", "faillite", "opholrt", "ophort", "ceased",
)


def _фолд(s: str) -> str:
    """«Société civile» → «societe civile»; «Likvidācijā» → «likvidacija»."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ł", "l"), ("ø", "o"), ("đ", "d"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def проверить_форму(geo: str, форма: str) -> str:
    """
    Пусто = форма подходит (🟢 или 🟡). Иначе — причина отсева (🔴).
    Проверяем ТОЛЬКО строку правовой формы, а не всю страницу.
    """
    ф = _фолд(форма)
    if not ф:
        return ""
    for стоп in ЗАПРЕЩЁННЫЕ_ФОРМЫ.get((geo or "").upper(), ()):
        if _фолд(стоп) in ф:
            return f"форма не подходит для Google Ads: {форма.strip()}"
    return ""


# 🔴 ПО ИМЕНИ — то, что видно уже в имени DnB и чего в нашем реестре нет или
# что не годится для Google Ads (решение пользователя 20.10.2026):
#   HR — obrt («"AURORA", vl. Marija Bakran»): их нет в судебном реестре,
#        они в Obrtni registar; верификация ИП под вопросом — не берём;
#   PL — spółka cywilna («… S C …»): её нет в KRS, она в CEIDG на каждого
#        партнёра — не берём;
#   FR — ассоциации, клубы, SCI: Google Ads их не верифицирует, а Часть 1
#        набирала их пачками (прогон 20.10: 10 из 10 французских — отсев).
СТОП_ПО_ИМЕНИ: dict[str, str] = {
    "HR": r"(^|[\s,])vl\.|\bvlasni|\bobrt\b",
    "PL": r"\bs\s?c\b|\bspolka cywilna\b",
    "FR": (r"\b(association|amicale|club|comite|federation|syndicat|sci|aful|"
           r"asl|paroisse|eglise|cooperative|mutuelle|fondation)\b"),
}


def стоп_по_имени(geo: str, имя: str) -> str:
    """
    Пусто — имя не выдаёт негодную форму. Иначе — причина.

    Кроме особых правил выше — запрещённые формы страны, если они стоят в
    имени отдельным словом («ŠPORTNO DRUŠTVO ZARJA», «Biedrība …»).
    """
    гео = (geo or "").upper()
    ф = " " + re.sub(r"[^\w]+", " ", _фолд(имя)) + " "
    шаблон = СТОП_ПО_ИМЕНИ.get(гео)
    if шаблон and re.search(шаблон, _фолд(имя).replace(".", ". ").replace("  ", " ")
                            if гео == "HR" else ф):
        return {"HR": "obrt (ремесленник) — нет в судебном реестре",
                "PL": "spółka cywilna — нет в KRS",
                "FR": "ассоциация/клуб/SCI — не для Google Ads"}[гео]
    for стоп in ЗАПРЕЩЁННЫЕ_ФОРМЫ.get(гео, ()):
        с = " " + re.sub(r"[^\w]+", " ", _фолд(стоп)).strip() + " "
        if с.strip() and с in ф:
            return f"форма не подходит для Google Ads: {стоп}"
    return ""


def проверить_статус(статус: str) -> str:
    """Пусто = статус нормальный. Иначе — причина (ликвидация/банкротство/закрытие)."""
    с = _фолд(статус)
    if not с:
        return ""
    for стоп in ЗАПРЕЩЁННЫЕ_СТАТУСЫ:
        if стоп in с:
            return f"статус-стоп: {статус.strip()}"
    return ""
