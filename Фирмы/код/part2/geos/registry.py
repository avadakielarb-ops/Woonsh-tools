"""Реестр драйверов + карта готовности по всем гео."""
from __future__ import annotations

from part2.geos.australia import Australia
from part2.geos.austria import Austria
from part2.geos.belgium import Belgium
from part2.geos.bulgaria import Bulgaria
from part2.geos.croatia import Croatia
from part2.geos.czechia import Czechia
from part2.geos.denmark import Denmark
from part2.geos.estonia import Estonia
from part2.geos.finland import Finland
from part2.geos.france import France
from part2.geos.hungary import Hungary
from part2.geos.latvia import Latvia
from part2.geos.netherlands import Netherlands
from part2.geos.norway import Norway
from part2.geos.poland import Poland
from part2.geos.slovenia import Slovenia
from part2.geos.switzerland import Switzerland
from part2.geos.united_kingdom import UnitedKingdom
from part2.geos.usa_florida import USAFlorida

DRIVERS = {d.code: d for d in [
    Czechia, Switzerland, Norway, Hungary, Slovenia, Austria, Poland, Denmark,
    UnitedKingdom, Estonia, France, Netherlands,
    # волна «простые» — написаны по спеке, ЖИВЬЁМ ещё не проверены
    Belgium, Croatia, Latvia, Australia, USAFlorida, Finland, Bulgaria,
]}

# Карта всех гео: волна внедрения + способ получения документа.
# ✔ — написан и проверен вживую. ✔? — написан по спеке, НЕ проверен. ○ — не написан.
PLAN = {
    # волна 1 — документ отдаётся кнопкой/ссылкой
    "CZ": ("Чехия",        1, "download", "✔"),
    "NO": ("Норвегия",     1, "download", "✔"),
    "SI": ("Словения",     1, "download", "✔"),   # + логин при пустом поиске
    "AT": ("Австрия",      1, "download", "✔"),
    "PL": ("Польша",       1, "download", "✔"),
    "DK": ("Дания",        1, "download", "✔"),
    "EE": ("Эстония",      1, "download", "✔"),
    "FR": ("Франция",      1, "download", "✔"),
    "UK": ("Британия",     1, "download", "✔"),   # + переименованные фирмы
    "LV": ("Латвия",       1, "download", "✔?"),  # написан, НЕ проверен вживую (+ возможен логин)
    # США: Часть 1 берёт только штаты FL/NY/WA/GA (РЕГИОНЫ в part1/data/countries.py).
    # Драйвер пока умеет ФЛОРИДУ; NY/WA/GA — предстоит дописать.
    "US": ("США (Флорида)", 1, "print",    "✔?"),  # написан, НЕ проверен вживую
    # волна 2 — печать страницы в PDF
    "CH": ("Швейцария",    2, "print",    "✔"),
    "HU": ("Венгрия",      2, "print",    "✔"),
    "BE": ("Бельгия",      2, "print",    "✔?"),  # написан, НЕ проверен вживую
    "HR": ("Хорватия",     2, "print",    "✔?"),  # написан, НЕ проверен вживую (APEX, JS)
    # волна 3 — сложная механика
    "BG": ("Болгария",     3, "print",    "✔?"),  # шаг 1 (hithorizons) по записи; реестр — ждёт записи
    "FI": ("Финляндия",    3, "download", "✔?"),  # написан по записи, НЕ проверен
    "AU": ("Австралия",    3, "download", "✔?"),  # написан по записи, НЕ проверен
    # волна 4 — шаблоны
    "SE": ("Швеция",       4, "template", "○"),
    "NL": ("Нидерланды",   4, "template", "✔"),
    # выключено
    "DE": ("Германия",     0, "—",        "✘"),   # реестр нерабочий
}
