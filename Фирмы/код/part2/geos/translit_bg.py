"""
ТРАНСЛИТЕРАЦИЯ имён болгарских фирм: латиница → кириллица.
Система из 4 уровней + САМООБУЧЕНИЕ от реестра.

Уровни (по убыванию точности):
  1. ВЫУЧЕННОЕ — что реестр уже показал в прошлых прогонах (translit_bg_выучено.json).
     Реестр — истина: открыв карточку, драйвер зовёт запомнить() и копит написания.
  2. СЛОВАРЬ   — готовые написания частых слов (бизнес-термины + болгарские слова,
     записанные латиницей: STROITELSTVO→СТРОИТЕЛСТВО и т.п.).
  3. ОКОНЧАНИЯ — правила окончаний (-tion→шън, -ing→инг, -ment→мънт, -er→ър…).
  4. БУКВЫ     — побуквенно (ch→ч, sh→ш, c перед e/i→с, x→кс…).

  транслит(name) -> (кандидат: str, уверенно: bool)
      уверенно=False → хоть одно слово ушло в побуквенный фолбэк, пометить «проверь».
  транслит_адрес(addr) -> str
  запомнить(латиница, кириллица) -> None   (учит из карточки реестра)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# правовые формы — латиницей (из DnB) и кириллицей (в реестре); срезаем при разборе
ФОРМЫ = ("eood", "ood", "ead", "ad", "et", "dzzd", "adsic", "kd", "kda", "sd", "kdа",
         "еоод", "оод", "еад", "ад", "ет", "дззд", "ад сиц", "кд", "кда", "сд",
         "ltd", "limited", "llc", "inc", "corp", "plc", "llp", "co", "jsc")

# --- уровень 2: СЛОВАРЬ (значения строчными, на выходе поднимаем в ВЕРХНИЙ) ---
СЛОВАРЬ = {
    # A. частые английские бизнес-слова (устоявшаяся болгарская запись)
    "solutions": "сълюшънс", "solution": "сълюшън",
    "consulting": "консултинг", "consult": "консулт", "consultants": "консултантс",
    "engineering": "инженеринг", "engineers": "инженерс",
    "group": "груп", "services": "сървисиз", "service": "сървис",
    "systems": "системс", "system": "систем",
    "technologies": "технолоджис", "technology": "технолоджи", "tech": "тек",
    "management": "мениджмънт", "business": "бизнес", "company": "къмпани",
    "corporation": "корпорейшън", "enterprise": "ентърпрайз", "enterprises": "ентърпрайзис",
    "international": "интернешънъл", "global": "глобъл", "worldwide": "уърлдуайд",
    "partners": "партнърс", "associates": "асошиейтс",
    "holdings": "холдингс", "holding": "холдинг", "ventures": "венчърс",
    "industries": "индъстрис", "industry": "индъстри", "industrial": "индъстриъл",
    "trading": "трейдинг", "trade": "трейд", "commerce": "комерс", "commercial": "комършъл",
    "import": "импорт", "export": "експорт", "supply": "съплай", "supplies": "съплайс",
    "agency": "ейджънси", "office": "офис", "center": "сентър", "centre": "сентър",
    "union": "юниън", "alliance": "алайънс", "network": "нетуърк", "networks": "нетуъркс",
    "concept": "консепт", "standard": "стандарт", "quality": "куолити",
    "team": "тийм", "works": "уъркс", "factory": "фактори",
    "market": "маркет", "retail": "ритейл", "brand": "бранд", "line": "лайн",
    "house": "хаус", "home": "хоум", "world": "уърлд", "studio": "студио",
    "energy": "енерджи", "power": "пауър", "solar": "солар",
    "electric": "електрик", "electronics": "електроникс",
    "finance": "финанс", "financial": "файненшъл", "investment": "инвестмънт",
    "investments": "инвестмънтс", "invest": "инвест", "capital": "капитал",
    "fund": "фонд", "leasing": "лизинг", "insurance": "иншурънс",
    "accounting": "акаунтинг", "audit": "одит", "legal": "лигъл",
    "software": "софтуер", "hardware": "хардуер", "digital": "диджитъл",
    "data": "дейта", "cloud": "клауд", "web": "уеб", "net": "нет", "online": "онлайн",
    "cyber": "кибър", "security": "секюрити", "mobile": "мобайл", "smart": "смарт",
    "innovation": "иновейшън", "innovations": "иновейшънс",
    "automation": "аутомейшън", "analytics": "аналитикс", "platform": "платформа",
    "server": "сървър", "hosting": "хостинг", "matrix": "матрикс",
    "communications": "комюникейшънс", "telecom": "телеком",
    "construction": "констракшън", "building": "билдинг", "development": "девелопмънт",
    "property": "пропърти", "properties": "пропъртис", "estate": "естейт",
    "design": "дизайн", "project": "проджект", "architect": "архитект",
    "interior": "интериор", "materials": "материалс", "metal": "метал",
    "logistics": "логистикс", "transport": "транспорт", "cargo": "карго",
    "shipping": "шипинг", "delivery": "деливъри", "express": "експрес",
    "auto": "ауто", "motors": "моторс", "parts": "партс",
    "production": "продъкшън", "manufacturing": "мануфакчъринг",
    "equipment": "екуипмънт", "machinery": "машинъри", "packaging": "пакиджинг",
    "print": "принт", "printing": "принтинг", "textile": "текстил", "furniture": "фърничър",
    "green": "грийн", "eco": "еко", "bio": "био", "water": "уотър", "gas": "газ",
    "oil": "ойл", "fuel": "фюел", "thermo": "термо", "climate": "клаймът",
    "medical": "медикъл", "health": "хелт", "clinic": "клиник", "pharma": "фарма",
    "dental": "дентал", "care": "кеър", "life": "лайф", "vita": "вита",
    "beauty": "бюти", "cosmetics": "козметикс", "fitness": "фитнес", "sport": "спорт",
    "food": "фуд", "foods": "фудс", "agro": "агро", "farm": "фарм",
    "media": "медия", "marketing": "маркетинг", "creative": "криейтив",
    "travel": "травъл", "tour": "тур", "tours": "турс", "tourism": "туризъм",
    "hotel": "хотел", "resort": "резорт", "restaurant": "ресторант", "catering": "кетъринг",
    "cleaning": "клийнинг", "training": "трейнинг",
    # усилители/прилагательные
    "advanced": "адвансд", "alpha": "алфа", "beta": "бета", "best": "бест",
    "blue": "блу", "black": "блак", "white": "уайт", "classic": "класик",
    "diamond": "даймънд", "elite": "елит", "euro": "евро", "expert": "експерт",
    "first": "фърст", "fast": "фаст", "gold": "голд", "golden": "голдън",
    "grand": "гранд", "ideal": "идеал", "king": "кинг", "royal": "роял",
    "leader": "лидер", "lux": "лукс", "master": "мастър", "max": "макс",
    "mega": "мега", "modern": "модерн", "multi": "мулти", "new": "ню",
    "next": "некст", "nova": "нова", "optima": "оптима", "perfect": "пърфект",
    "premium": "премиум", "prime": "прайм", "pro": "про", "silver": "силвър",
    "star": "стар", "super": "супер", "top": "топ", "total": "тотал",
    "ultra": "ултра", "united": "юнайтед", "universal": "универсал", "vip": "вип",
    "plus": "плюс", "sun": "сън", "sky": "скай",
    "heat": "хийт", "aqua": "аква", "park": "парк", "bg": "бг", "eu": "еу",
    "cool": "кул", "hot": "хот", "air": "еър", "tech": "тек",
    # B. болгарские слова, записанные латиницей (в реестре — кириллицей)
    "stroitelstvo": "строителство", "stroy": "строй", "imoti": "имоти",
    "targovia": "търговия", "proizvodstvo": "производство", "uslugi": "услуги",
    "mebel": "мебел", "mebeli": "мебели", "darvo": "дърво", "plast": "пласт",
    "moda": "мода", "zdrave": "здраве", "apteka": "аптека", "klinika": "клиника",
    "schetovodstvo": "счетоводство", "konsult": "консулт", "pechat": "печат",
    "reklama": "реклама", "ohrana": "охрана", "sigurnost": "сигурност",
    "pochistvane": "почистване", "hrani": "храни", "mlyako": "мляко", "meso": "месо",
    "sirene": "сирене", "zarno": "зърно", "semena": "семена", "ferma": "ферма",
    "gora": "гора", "riba": "риба", "med": "мед", "gradina": "градина",
    "voda": "вода", "slantse": "слънце", "zvezda": "звезда", "more": "море",
    "planina": "планина", "reka": "река", "izvor": "извор", "zlato": "злато",
    "zlaten": "златен", "srebro": "сребро", "kristal": "кристал", "perla": "перла",
    "feniks": "феникс", "nadezhda": "надежда", "uspeh": "успех", "mladost": "младост",
    # география (города/регионы)
    "sofia": "софия", "plovdiv": "пловдив", "varna": "варна", "burgas": "бургас",
    "ruse": "русе", "pernik": "перник", "pleven": "плевен", "sliven": "сливен",
    "shumen": "шумен", "haskovo": "хасково", "yambol": "ямбол", "vratsa": "враца",
    "gabrovo": "габрово", "vidin": "видин", "montana": "монтана", "lovech": "ловеч",
    "razgrad": "разград", "silistra": "силистра", "smolyan": "смолян",
    "targovishte": "търговище", "kardzhali": "кърджали", "kyustendil": "кюстендил",
    "blagoevgrad": "благоевград", "dobrich": "добрич", "pazardzhik": "пазарджик",
    "trakia": "тракия", "balkan": "балкан", "rodopi": "родопи", "pirin": "пирин",
    "rila": "рила", "vitosha": "витоша", "dunav": "дунав", "maritsa": "марица",
    "bulgaria": "българия",
    # уличные слова
    "str": "ул", "blvd": "бул", "ul": "ул", "bul": "бул", "distr": "район",
    "district": "район", "kv": "кв", "bl": "бл", "et": "ет",
}

# --- уровень 3: ОКОНЧАНИЯ (проверяем от длинных к коротким) ---
ОКОНЧАНИЯ = [
    ("tions", "шънс"), ("tion", "шън"), ("sions", "жънс"), ("sion", "жън"),
    ("ments", "мънтс"), ("ment", "мънт"), ("ings", "ингс"), ("ing", "инг"),
    ("ical", "икъл"), ("ance", "анс"), ("ence", "енс"), ("ture", "чър"),
    ("sure", "жър"), ("ize", "айз"), ("ise", "айз"), ("ous", "ъс"),
    ("ity", "ити"), ("age", "идж"), ("ate", "ейт"), ("ers", "ърс"),
    ("ors", "орс"), ("er", "ър"), ("or", "ор"), ("ow", "оу"), ("y", "и"),
]

# --- уровень 4: побуквенно ---
_ДИГРАФЫ = [("sht", "щ"), ("zh", "ж"), ("ch", "ч"), ("sh", "ш"), ("ts", "ц"),
            ("ph", "ф"), ("th", "т"), ("ck", "к"), ("kh", "х"), ("qu", "кв"),
            ("ya", "я"), ("yu", "ю"), ("yo", "йо"), ("ee", "и"), ("ea", "и"),
            ("oo", "у"), ("ou", "у"), ("x", "кс")]
_БУКВЫ = {"a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
          "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н",
          "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
          "v": "в", "w": "у", "y": "и", "z": "з"}

# файл обучения. Тесты подменяют путь через env TRANSLIT_BG_FILE, чтобы не писать
# в боевой словарь.
_ФАЙЛ = Path(os.environ.get("TRANSLIT_BG_FILE",
             str(Path(__file__).parent / "translit_bg_выучено.json")))


def _загрузить() -> dict:
    if _ФАЙЛ.exists():
        try:
            d = json.loads(_ФАЙЛ.read_text(encoding="utf-8"))
            d.setdefault("слова", {})
            d.setdefault("фразы", {})
            return d
        except Exception:
            pass
    return {"слова": {}, "фразы": {}}


ВЫУЧЕНО = _загрузить()


def _ядро(имя: str) -> str:
    """Строчными, без кавычек/пунктуации, без правовых форм; слова через пробел."""
    s = re.sub(r"[«»\"'`]", " ", (имя or "").lower())
    s = re.sub(r"[.,]", " ", s)
    return " ".join(w for w in s.split() if w and w not in ФОРМЫ)


def _побуквенно(w: str) -> str:
    s = w.lower()
    for a, b in _ДИГРАФЫ:
        s = s.replace(a, b)
    s = re.sub(r"c(?=[eiy])", "с", s)          # c перед e/i/y → с, иначе → к
    return "".join(_БУКВЫ.get(ch, ch) for ch in s)


def _слово(w: str) -> tuple[str, bool]:
    """(кириллица, точно ли). Точно = взято из выученного/словаря."""
    чист = w.strip(".,-")
    if чист in ВЫУЧЕНО["слова"]:
        return ВЫУЧЕНО["слова"][чист], True
    if чист in СЛОВАРЬ:
        return СЛОВАРЬ[чист], True
    # окончание + побуквенный остаток (это уже догадка → не точно)
    for анг, кир in ОКОНЧАНИЯ:
        if len(чист) > len(анг) and чист.endswith(анг):
            return _побуквенно(чист[: -len(анг)]) + кир, False
    return _побуквенно(чист), False


def транслит(имя: str) -> tuple[str, bool]:
    """Кандидат кириллицей + флаг уверенности (все слова из словаря/выученного)."""
    ядро = _ядро(имя)
    if ядро in ВЫУЧЕНО["фразы"]:
        return ВЫУЧЕНО["фразы"][ядро].upper(), True
    части, уверенно = [], True
    for w in ядро.split():
        кир, точно = _слово(w)
        if not кир:                       # пустое (например, одинокий дефис) — пропускаем
            continue
        части.append(кир)
        уверенно = уверенно and точно
    return " ".join(части).upper(), уверенно


def транслит_адрес(адрес: str) -> str:
    """Черновик адреса: слова через словарь/побуквенно, цифры/разделители сохраняем."""
    out = []
    for кусок in re.split(r"(\W+)", адрес or ""):
        if кусок.strip() and кусок.strip().isalpha():
            кир, _ = _слово(кусок.lower())
            out.append(кир)
        else:
            out.append(кусок)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def запомнить(латиница: str, кириллица: str) -> None:
    """
    Выучить написание из карточки реестра (истина). Копим и фразу целиком, и
    пословно (если число слов совпало). Пополняет translit_bg_выучено.json.
    """
    en = _ядро(латиница)
    cy = _ядро(кириллица)
    if not en or not cy:
        return
    изменилось = False
    if ВЫУЧЕНО["фразы"].get(en) != cy:
        ВЫУЧЕНО["фразы"][en] = cy
        изменилось = True
    ew, cw = en.split(), cy.split()
    if len(ew) == len(cw):
        for e, c in zip(ew, cw):
            if e and c and not e.isdigit() and ВЫУЧЕНО["слова"].get(e) != c:
                ВЫУЧЕНО["слова"][e] = c
                изменилось = True
    if изменилось:
        try:
            _ФАЙЛ.write_text(
                json.dumps(ВЫУЧЕНО, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
