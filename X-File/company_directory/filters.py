""
from __future__ import annotations
import re
from pathlib import Path
from .data.countries import РЕГИОНЫ, регион
from .data.legal_forms import FORMS
from .models import Firm
from .fingerprints import Registry, отпечаток
DATA = Path(__file__).parent / "data"
def _load_list(name: str) -> list[str]:
    lines = (DATA / name).read_text(encoding="utf-8").splitlines()
    return [ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")]
BLACKLIST = _load_list("blacklist_industries.txt")
BRANDS = _load_list("brands.txt")
ЛИКВИДАЦИЯ = [
    "in liquidation", "in liquidat", "in liquid.",
    "under liquidation", "in receivership", "in administration",
    "dissolved", "in insolvency", "insolvency proceedings",
    "i likvidation", "likvideeritud",
    "in liquidazione", "en liquidation", "en liquidación",
    "w likwidacji", "v likvidaci", "v likvidácii",
    "felszámolás", "в ликвидация", "u likvidaciji",
    "likvidācijā", "likviduojama", "in liquidatie",
    " i.l.", " in liq.", " w likw.",
]
def has_legal_form(name: str, country: str) -> bool:
    ""
    forms = FORMS.get(country.upper(), [])
    low = " " + re.sub(r"[^\w\s.&/]", " ", name.lower()) + " "
    return any(re.search(rf"(^|[\s(]){re.escape(f)}($|[\s).,])", low) for f in forms)
def в_ликвидации(имя: str) -> str:
    ""
    низ = " " + re.sub(r"[^\w\s.]", " ", (имя or "").lower()) + " "
    низ = re.sub(r"\s+", " ", низ)
    for метка in ЛИКВИДАЦИЯ:
        if метка in низ:
            return метка
    return ""
def этаж_1(f: Firm, country: str, reg: Registry) -> tuple[bool, str]:
    ""
    low = f.name.lower()
    метка = в_ликвидации(f.name)
    if метка:
        return False, f"в ликвидации: «{метка}»"
    for brand in BRANDS:
        if brand in low:
            return False, f"бренд из минус-листа: {brand}"
    ind = f.industry.lower()
    for word in BLACKLIST:
        if ind and word in ind:
            return False, f"запрещённая отрасль: {word}"
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
    ""
    ok, why = этаж_1(f, country, reg)
    if not ok:
        return False, why
    if not f.website.strip():
        return False, "нет сайта"
    return True, ""
