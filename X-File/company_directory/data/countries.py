""
СПИСОК = [
    "Australia", "Austria", "Belgium", "Bulgaria", "Croatia", "Czech Republic",
    "Denmark", "Estonia", "Finland", "France", "Germany", "Hungary",
    "Latvia", "Netherlands", "Norway", "Poland", "Slovenia", "Sweden",
    "Switzerland", "United Kingdom", "USA",
]
NAME_TO_CODE = {
    "poland": "PL", "sweden": "SE", "latvia": "LV", "estonia": "EE",
    "france": "FR", "australia": "AU", "denmark": "DK",
    "czech republic": "CZ", "czechia": "CZ",
    "finland": "FI", "switzerland": "CH", "belgium": "BE", "bulgaria": "BG",
    "hungary": "HU", "croatia": "HR", "norway": "NO", "germany": "DE",
    "netherlands": "NL", "austria": "AT", "slovenia": "SI",
    "usa": "US", "united kingdom": "UK",
}
CODE_TO_NAME = {NAME_TO_CODE[имя.lower()]: имя for имя in СПИСОК}
DNB_NAME = {"US": "United States", "UK": "United Kingdom"}
РЕГИОНЫ = {
    "US": {"FL", "NY", "WA", "GA"},
}
def регион(текст: str) -> str:
    ""
    for часть in (текст or "").split(","):
        ч = часть.strip().upper()
        if len(ч) == 2 and ч.isalpha():
            return ч
    return ""
def to_code(country: str) -> str:
    ""
    c = (country or "").strip()
    if c.upper() in CODE_TO_NAME:
        return c.upper()
    return NAME_TO_CODE.get(c.lower(), c.upper()[:2])
def to_name(country: str) -> str:
    ""
    код = to_code(country)
    if код in DNB_NAME:
        return DNB_NAME[код]
    return CODE_TO_NAME.get(код, country)
