"""
ОТСЕВ Части 1. Только ЖЁСТКИЕ правила: взять или выбросить.

Двухэтажный:
  ЭТАЖ 1 (дёшево, по строке таблицы выдачи): бренд -> отрасль -> уже в реестре
  ЭТАЖ 2 (дорого, в движке): нет сайта

ПРАВИЛО «нет правовой формы» УБРАНО ИЗ ЧАСТИ 1: DnB показывает торговые имена
без формы (G-HEAT GROUP, BARRIQUAND HEAT EXCHANGERS) — в Части 1 оно резало всех.
Форму проверяет ЧАСТЬ 2, где фирма найдена в госреестре и форма есть всегда.
Функция has_legal_form оставлена — её импортирует Часть 2.
"""
from __future__ import annotations

import re
from pathlib import Path

from .data.countries import РЕГИОНЫ, регион
from .data.legal_forms import FORMS
from .models import Firm
from .registry import Registry, отпечаток

DATA = Path(__file__).parent / "data"


def _load_list(name: str) -> list[str]:
    lines = (DATA / name).read_text(encoding="utf-8").splitlines()
    return [ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")]


BLACKLIST = _load_list("blacklist_industries.txt")
BRANDS = _load_list("brands.txt")

# ЛИКВИДАЦИЯ ПРЯМО В НАЗВАНИИ. dnb дописывает такое к имени фирмы:
# «AHORN Vorsorge Management GmbH in Liquid...» (лог 09.09.2026, Австрия).
# Брать такую незачем: выписки на неё не будет, Часть 2 всё равно отбросит —
# но к тому времени карточка уже открыта, строка занята, время потрачено.
# Ловим на ПЕРВОМ этаже, по строке выдачи, до открытия карточки.
#
# Языки те, что встречаются в наших гео. Ищем как отдельные слова: «in
# liquidation», а не «liquid» — иначе выбросим производителя жидкостей.
ЛИКВИДАЦИЯ = [
    # dnb обрезает длинные имена многоточием: «… GmbH in Liquid...». Точка
    # после «liquid» и отличает обрубок от живого «Liquid Design GmbH».
    "in liquidation", "in liquidat", "in liquid.",
    "under liquidation", "in receivership", "in administration",
    "dissolved", "in insolvency", "insolvency proceedings",
    "i likvidation", "likvideeritud",
    "in liquidazione", "en liquidation", "en liquidación",
    "w likwidacji", "v likvidaci", "v likvidácii",
    "felszámolás", "в ликвидация", "u likvidaciji",
    "likvidācijā", "likviduojama", "in liquidatie",
    # Короткие сокращения — только с пробелом впереди, иначе «M.I.L.»
    # и подобные аббревиатуры пошли бы в брак.
    " i.l.", " in liq.", " w likw.",
]


def has_legal_form(name: str, country: str) -> bool:
    """Есть ли в названии правовая форма. Используется ЧАСТЬЮ 2."""
    forms = FORMS.get(country.upper(), [])
    low = " " + re.sub(r"[^\w\s.&/]", " ", name.lower()) + " "
    # форма может стоять и в начале, и в конце имени
    return any(re.search(rf"(^|[\s(]){re.escape(f)}($|[\s).,])", low) for f in forms)


def в_ликвидации(имя: str) -> str:
    """
    Пометка о ликвидации в названии. Возвращает найденную пометку или пусто.

    Сравниваем по словам, а не по вхождению подстроки: «liquid» встречается в
    живых названиях (жидкости, Liquid Design), а «in liquidation» — нет.
    Точки и скобки для сравнения убираем: dnb пишет и «(in Liquidation)»,
    и «i.L.», и обрезанное «in Liquidat...».
    """
    низ = " " + re.sub(r"[^\w\s.]", " ", (имя or "").lower()) + " "
    низ = re.sub(r"\s+", " ", низ)
    for метка in ЛИКВИДАЦИЯ:
        if метка in низ:
            return метка
    return ""


def этаж_1(f: Firm, country: str, reg: Registry) -> tuple[bool, str]:
    """Дешёвые проверки — по строке таблицы выдачи, до открытия карточки."""
    low = f.name.lower()
    метка = в_ликвидации(f.name)
    if метка:
        return False, f"в ликвидации: «{метка}»"
    # Негодная форма видна уже в имени (obrt, S.C., ассоциации, общества) —
    # отсекаем до карточки, бота и реестра.
    from part2.core.формы import стоп_по_имени
    причина = стоп_по_имени(country, f.name)
    if причина:
        return False, причина
    for brand in BRANDS:
        if brand in low:
            return False, f"бренд из минус-листа: {brand}"

    ind = f.industry.lower()
    for word in BLACKLIST:
        if ind and word in ind:
            return False, f"запрещённая отрасль: {word}"

    # регион: для США в DnB конкретный штат не выбрать — фильтруем выдачу сами
    разрешённые = РЕГИОНЫ.get(country.upper())
    if разрешённые:
        рег = регион(f.address) or регион(f.city)
        if рег not in разрешённые:
            return False, f"регион {рег or '—'} не из разрешённых " \
                          f"({', '.join(sorted(разрешённые))})"

    if not reg.свободна(отпечаток(f.name, country, f.zip_code, f.city)):
        return False, "уже использована ранее"

    return True, ""


def judge(f: Firm, country: str, reg: Registry) -> tuple[bool, str]:
    """Полный отсев (этаж 1 + сайт). Оставлен для совместимости/тестов."""
    ok, why = этаж_1(f, country, reg)
    if not ok:
        return False, why
    if not f.website.strip():
        return False, "нет сайта"
    return True, ""
