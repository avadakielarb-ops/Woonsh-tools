"""
Страны, с которыми работаем. Один пункт списка = одно ГЕО.

СПИСОК   — что видно в выпадающем списке Части 1 (порядок как у пользователя).
КОД      — им помечается лист Excel («21-07 PL») и по нему Часть 2 берёт драйвер.
DNB_NAME — что вбивать в поле «Enter Country/Region» на dnb.com.

США разбиты ПО ШТАТАМ: гео у каждого своё (US-FL, US-NY…), потому что выписки
качаются в реестре конкретного штата.
"""

# по алфавиту
СПИСОК = [
    "Australia", "Austria", "Belgium", "Bulgaria", "Croatia", "Czech Republic",
    "Denmark", "Estonia", "Finland", "France", "Germany", "Hungary",
    "Latvia", "Netherlands", "Norway", "Poland", "Slovenia", "Sweden",
    "Switzerland", "United Kingdom", "USA",
]

NAME_TO_CODE = {
    "poland": "PL", "sweden": "SE", "latvia": "LV", "estonia": "EE",
    "france": "FR", "australia": "AU", "denmark": "DK",
    "czech republic": "CZ", "czechia": "CZ",      # файл называем «Czech Republic»
    "finland": "FI", "switzerland": "CH", "belgium": "BE", "bulgaria": "BG",
    "hungary": "HU", "croatia": "HR", "norway": "NO", "germany": "DE",
    "netherlands": "NL", "austria": "AT", "slovenia": "SI",
    "usa": "US", "united kingdom": "UK",
}

CODE_TO_NAME = {NAME_TO_CODE[имя.lower()]: имя for имя in СПИСОК}

# Что вбивать в фильтр «Enter Country/Region» на dnb.com.
DNB_NAME = {"US": "United States", "UK": "United Kingdom"}

# РАЗРЕШЁННЫЕ РЕГИОНЫ. Конкретный регион в DnB не выбрать, поэтому фильтруем
# выдачу сами: в колонке Country/Region стоит код штата («Tucson, AZ, United
# States»). Берём только фирмы из этих штатов, остальные отсеиваем.
РЕГИОНЫ = {
    "US": {"FL", "NY", "WA", "GA"},      # Флорида, Нью-Йорк, Вашингтон, Джорджия
}


def регион(текст: str) -> str:
    """Код региона из «Tucson, AZ, United States» → «AZ». Нет — пусто."""
    for часть in (текст or "").split(","):
        ч = часть.strip().upper()
        if len(ч) == 2 and ч.isalpha():
            return ч
    return ""


def to_code(country: str) -> str:
    """«Poland» -> «PL», «USA Florida» -> «US-FL». Код вернётся как есть."""
    c = (country or "").strip()
    if c.upper() in CODE_TO_NAME:
        return c.upper()
    return NAME_TO_CODE.get(c.lower(), c.upper()[:2])


def to_name(country: str) -> str:
    """Имя для поля «Enter Country/Region» на DnB. У штатов США — имя штата."""
    код = to_code(country)
    if код in DNB_NAME:
        return DNB_NAME[код]
    return CODE_TO_NAME.get(код, country)
