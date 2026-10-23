"""
ГЕНЕРАТОР СЛОВ ДЛЯ ПОИСКА ФИРМ.

Часть 1 ищет на dnb.com по СЛОВУ В НАЗВАНИИ фирмы. Раньше слово вбивал человек
руками — каждый раз, на каждую страну. Здесь оно берётся само.

Три вещи, без которых генератор бесполезен:

1. СЛОВО — ЭТО ЧАСТЬ НАЗВАНИЯ, А НЕ ОТРАСЛЬ. Рабочие слова прошлых прогонов —
   ice, energy, star, lock, crystal: обычные существительные, которые фирмы
   суют себе в имя. «Логистические услуги» или «стоматология» не найдут
   ничего: dnb ищет по имени, а не по виду деятельности.

2. ПОВТОР = ПОТЕРЯННЫЙ ПРОГОН. Одно слово в одной стране выдаёт свой список
   один раз; второй заход по нему даст те же фирмы, а они уже забронированы.
   Поэтому смотрим в историю очереди и НИКОГДА не предлагаем то, что уже
   гонялось по этой стране.

3. ПОЛИТИКА GOOGLE ADS. Фирма со словом health, casino, loan, crypto в имени —
   это отказ или блокировка аккаунта. Отсеиваем на входе, и на английском,
   и на языке гео: «apteka», «kasyno», «kredyt» так же опасны, как «pharmacy».

Порядок выдачи: сперва английский, кончился приличный запас — переходим на
язык страны. Ровно так это делают руками.
"""
from __future__ import annotations

import random
import re
import unicodedata

# ──────────────────────────────────────────────────────────────────────────────
# СТОП-СЛОВА: тематики, из-за которых Google Ads отказывает или блокирует.
# Проверяем ВХОЖДЕНИЕМ, поэтому корней достаточно: «health» ловит и «healthcare».
# Локальные корни не менее важны английских — фирма называется на своём языке.
# ──────────────────────────────────────────────────────────────────────────────
#
# ДВА УРОВНЯ, И ЭТО ВАЖНО.
#
# Длинные однозначные корни ловим ВХОЖДЕНИЕМ: «health» обязан поймать и
# «healthcare», и «healthy». Ложных срабатываний у таких почти не бывает.
#
# А короткие и многозначные — ТОЛЬКО ЦЕЛЫМ СЛОВОМ. Живой замер: Gemini выдал
# «sextant» (навигационный прибор — идеальное имя для фирмы), и подстрочный
# корень «sex» его убил. По той же логике мы бы выбросили bronze («bron» —
# оружие по-польски), ammonite («ammo»), betula — берёзу («bet»), banksia
# («bank»), hackberry («hack»), cashmere («cash»), coincidence («coin»).
# Это не мелочь: такие слова — самое ценное, что может дать генератор.
#
СТОП_КОРНИ = {
    # здоровье, медицина, аптеки, БАДы
    "health", "medic", "medical", "pharma", "apotek", "apteka", "apteek",
    "aptieka", "farmac", "farmak", "klinik", "clinic", "dental", "dentist",
    "hospital", "therap", "psych", "vitamin", "supplement",
    "gesund", "salud", "zdrav", "zdrow", "helse", "sundhed",
    # азартные игры, ставки, лотереи
    "casino", "kasyno", "kasino", "gambl", "betting", "poker", "lotto",
    "lottery", "loteri", "bookmak", "zaklad", "kihlveo",
    # финансы, кредиты, крипта
    "credit", "kredit", "kredyt", "pozyczk", "aizdev",
    "payday", "crypto", "kripto", "bitcoin", "forex",
    "trading", "invest", "broker", "insur",
    # взрослое, знакомства
    "adult", "escort", "erotic", "erotik", "porn", "dating",
    # табак, алкоголь, вейпы, каннабис
    "tobacco", "tabak", "cigar", "vaping", "nikotin", "nicotine",
    "cannab", "konopi", "alcohol", "alkohol", "vodka", "wodka",
    "brewery", "brouwer", "destill",
    # оружие
    "weapon", "firearm", "ammun", "waffen",
    # политика, религия, деликатные темы
    "politic", "polityk", "church", "kirche", "kosciol", "baznic",
    "election", "immigration", "lawyer", "advokat",
    # прочее из ограниченных категорий
    "narko", "steroid", "doping", "surveill",
}

СТОП_СЛОВА = {
    # короткие и многозначные — только целиком
    "med", "diet", "slim", "sante", "terve",
    "bet", "wett", "loan", "laen", "cash", "coin", "token", "bank",
    "sex", "randk", "vape", "hemp", "cbd", "wine", "wein", "beer", "bier",
    "piwo", "ammo", "gun", "bron", "relv", "party", "abort", "visa",
    "drug", "hack", "spy", "kirik",
}

# ──────────────────────────────────────────────────────────────────────────────
# СЛОВАРЬ ИМЁН-ТОКЕНОВ по языкам.
#
# Подбор не случайный: это существительные и прилагательные, которые реально
# встречаются в названиях фирм — природа, металлы, камни, цвета, животные,
# геометрия, качества. Нейтральные по тематике: ни одна категория не пересекается
# со стоп-листом, поэтому в Ads такие имена не вызывают вопросов.
#
# Намеренно НЕ берём слишком частые (group, service, trade, company): по ним
# выдача забита, и такие фирмы уже перепаханы другими.
# ──────────────────────────────────────────────────────────────────────────────
СЛОВАРЬ: dict[str, list[str]] = {
    "EN": [
        "amber", "anchor", "arrow", "aurora", "basalt", "beacon", "birch",
        "bison", "bridge", "cedar", "cobalt", "compass", "coral", "crane",
        "crystal", "dune", "eagle", "ember", "falcon", "fern", "flint",
        "forge", "garnet", "granite", "harbor", "harvest", "heron", "ivory",
        "jade", "juniper", "kestrel", "lantern", "lark", "lattice", "linden",
        "lumen", "maple", "meridian", "mosaic", "nimbus", "obsidian", "onyx",
        "orchid", "osprey", "pebble", "pinnacle", "quartz", "quill", "raven",
        "ridge", "saffron", "sapphire", "sequoia", "solstice", "spruce",
        "summit", "thistle", "topaz", "vertex", "willow", "zenith", "zephyr",
    ],
    "PL": [
        "bursztyn", "brzoza", "dąb", "granit", "jodła", "jarzębina", "kotwica",
        "kryształ", "lipa", "modrzew", "mozaika", "orzeł", "perła", "promień",
        "sokół", "sosna", "srebro", "strzała", "szafir", "topaz", "wierzba",
        "wrzos", "żagiel", "źródło",
    ],
    "CS": [
        "bříza", "dub", "jantar", "javor", "jedle", "kotva", "křišťál",
        "lípa", "mozaika", "orel", "perla", "pramen", "sokol", "smrk",
        "stříbro", "šafrán", "šípek", "topol", "vrba", "zenit",
    ],
    "SK": [
        "breza", "dub", "jantár", "javor", "jedľa", "kotva", "krištáľ",
        "lipa", "orol", "perla", "prameň", "sokol", "smrek", "striebro",
        "vŕba", "zenit",
    ],
    "SL": [
        "bor", "breza", "hrast", "jantar", "javor", "jelka", "kristal",
        "lipa", "mozaik", "orel", "biser", "izvir", "sokol", "srebro",
        "vrba", "zenit",
    ],
    "HR": [
        "bor", "breza", "hrast", "jantar", "javor", "jela", "kristal",
        "lipa", "mozaik", "orao", "biser", "izvor", "sokol", "srebro",
        "vrba", "zenit",
    ],
    "HU": [
        "borostyán", "bükk", "cédrus", "fenyő", "gránit", "hárs", "horgony",
        "juhar", "kristály", "mozaik", "nyír", "opál", "sas", "solymos",
        "sólyom", "ezüst", "forrás", "zenit",
    ],
    "ET": [
        "merevaik", "kask", "tamm", "kuusk", "vaher", "pärn", "ankur",
        "kristall", "mosaiik", "kotkas", "pärl", "allikas", "hõbe", "paju",
        "graniit", "põhjatäht",
    ],
    "LV": [
        "dzintars", "bērzs", "ozols", "egle", "kļava", "liepa", "enkurs",
        "kristāls", "mozaīka", "ērglis", "pērle", "avots", "sudrabs", "vītols",
        "granīts", "zenīts",
    ],
    "FI": [
        "meripihka", "koivu", "tammi", "kuusi", "vaahtera", "lehmus", "ankkuri",
        "kristalli", "mosaiikki", "kotka", "helmi", "lähde", "hopea", "paju",
        "graniitti", "zeniitti",
    ],
    "NO": [
        "rav", "bjørk", "eik", "gran", "lønn", "lind", "anker", "krystall",
        "mosaikk", "ørn", "perle", "kilde", "sølv", "selje", "granitt",
        "nordlys",
    ],
    # «eg» (дуб) и «ek» — настоящие слова, но искать по двум буквам бессмысленно:
    # dnb вернёт мусор из любых названий, где эти буквы встретились.
    "DA": [
        "rav", "birk", "gran", "ahorn", "lind", "anker", "krystal",
        "mosaik", "ørn", "perle", "kilde", "sølv", "granit", "nordlys",
        "tjørn", "ravn",
    ],
    "SV": [
        "bärnsten", "björk", "gran", "lönn", "lind", "ankare",
        "kristall", "mosaik", "örn", "pärla", "källa", "silver", "vide",
        "granit", "norrsken", "korp",
    ],
    # «bron» (нидерл. «источник») выброшено намеренно: без диакритики оно
    # совпадает с польским «broń» — оружие, а это стоп-тема Google Ads.
    "NL": [
        "amber", "berk", "eik", "spar", "esdoorn", "linde", "anker",
        "kristal", "mozaïek", "arend", "parel", "zilver", "wilg",
        "graniet", "zenit", "havik",
    ],
    "DE": [
        "bernstein", "birke", "eiche", "tanne", "ahorn", "linde", "anker",
        "kristall", "mosaik", "adler", "perle", "quelle", "silber", "weide",
        "granit", "zenit", "falke", "distel", "lärche", "flieder",
    ],
    "FR": [
        "ambre", "bouleau", "chêne", "sapin", "érable", "tilleul", "ancre",
        "cristal", "mosaïque", "aigle", "perle", "source", "argent", "saule",
        "granit", "zénith", "faucon", "chardon", "mélèze", "lilas",
    ],
    "BG": [
        "кехлибар", "бреза", "дъб", "ела", "явор", "липа", "котва",
        "кристал", "мозайка", "орел", "перла", "извор", "сребро", "върба",
        "гранит", "зенит",
    ],
}

# Какой язык у страны, кроме английского. Код гео → ключ СЛОВАРЯ.
ЯЗЫК_ГЕО: dict[str, str] = {
    "PL": "PL", "CZ": "CS", "SK": "SK", "SI": "SL", "HR": "HR", "HU": "HU",
    "EE": "ET", "LV": "LV", "FI": "FI", "NO": "NO", "DK": "DA", "SE": "SV",
    "NL": "NL", "BE": "NL", "DE": "DE", "AT": "DE", "CH": "DE", "FR": "FR",
    "BG": "BG",
    # англоязычные — второго языка нет, работаем на английском
    "UK": "EN", "IE": "EN", "AU": "EN", "US": "EN",
}


def _без_диакритики(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ł", "l"), ("ø", "o"), ("đ", "d"), ("ß", "ss"), ("ħ", "h")):
        s = s.replace(a, b)
    return s.lower()


def запрещено(слово: str) -> str:
    """
    Почему слово нельзя брать. Пустая строка — можно.

    Сравниваем БЕЗ ДИАКРИТИКИ: «krédyt» и «kredyt» одинаково опасны, а
    реестры и dnb пишут диакритику как попало.
    """
    ч = _без_диакритики(слово).strip()
    if len(ч) < 3:
        return "слишком короткое"
    if len(ч) > 20:
        return "слишком длинное"
    if not re.fullmatch(r"[a-zа-я\- ]+", ч):
        return "посторонние символы"
    for корень in СТОП_КОРНИ:
        if корень in ч:
            return f"тематика под ограничением Google Ads («{корень}»)"
    слова_в = set(re.split(r"[\s\-]+", ч))
    попало = слова_в & СТОП_СЛОВА
    if попало:
        return (f"тематика под ограничением Google Ads "
                f"(«{sorted(попало)[0]}»)")
    return ""


def код_страны(что: str) -> str:
    """
    «Poland» и «PL» — одна и та же страна.

    Очередь хранит ПОЛНОЕ НАЗВАНИЕ («Poland»), а сюда приходит КОД («PL»).
    Пока сравнивали как есть, история не находилась вовсе: генератор honestly
    считал, что по стране ничего не гонялось, и выдавал уже отработанные слова.
    """
    из = (что or "").strip()
    if not из:
        return ""
    try:
        from part1.data.countries import to_code
        код = to_code(из)
        if код:
            return код.upper()
    except Exception:
        pass
    return из.upper()[:2]


def уже_гонялось(история: list[dict], гео: str) -> set[str]:
    """Слова, которые по этой стране УЖЕ отрабатывали (из истории очереди)."""
    г = код_страны(гео)
    было = set()
    for и in история or ():
        if код_страны(и.get("страна", "")) == г:
            было.add(_без_диакритики(и.get("слово", "")))
    return было


def слабое(история: list[dict], гео: str, порог: int = 3) -> set[str]:
    """
    Слова, которые по этой стране дали почти ничего.

    Не просто «уже было»: такое слово не стоит пробовать и в СОСЕДНИХ странах
    того же языка — если по нему в Польше нашлось две фирмы, в Чехии чуда не
    будет. Порог низкий: три фирмы — это уже рабочее слово.
    """
    г = код_страны(гео)
    плохие = set()
    for и in история or ():
        if код_страны(и.get("страна", "")) != г:
            continue
        if int(и.get("взято") or 0) < порог:
            плохие.add(_без_диакритики(и.get("слово", "")))
    return плохие


def запас(гео: str) -> dict[str, list[str]]:
    """Словари, доступные этой стране: английский и язык гео."""
    язык = ЯЗЫК_ГЕО.get((гео or "").upper(), "EN")
    итог = {"EN": list(СЛОВАРЬ["EN"])}
    if язык != "EN":
        итог[язык] = list(СЛОВАРЬ.get(язык, []))
    return итог


def предложить(гео: str, сколько: int, история: list[dict] | None = None,
               занятые: set[str] | None = None,
               семя: int | None = None, буфер=None,
               линия: str = "") -> list[str]:
    """
    Слова для одной страны: сперва английские, потом на языке гео.

    ПОРЯДОК ИСТОЧНИКОВ: сначала буфер (что нагенерил Gemini), потом встроенный
    словарь. Буфер свежее и больше — встроенный остаётся страховкой на случай,
    когда ключа нет, интернета нет или запас кончился посреди работы.

    занятые — слова, уже поставленные в очередь В ЭТОМ ЖЕ заходе (иначе
    сгенерируем одно и то же на две строки).
    буфер — объект part1.запас.Запас; None = не трогать буфер (так гоняются
    офлайн-проверки, чтобы не зависеть от файла состояния).
    линия — «сайт» или «бс»: отбракованное для этой линии буфер не выдаст.
    """
    рнд = random.Random(семя)
    исключить = set(занятые or ())
    исключить |= уже_гонялось(история or [], гео)
    исключить |= слабое(история or [], гео)

    итог: list[str] = []
    if буфер is not None:
        # Буфер выдаёт СРАЗУ ПОМЕЧАЯ выданным: между заполнением очереди и
        # запуском может пройти час, и второй заход обязан получить другое.
        из_буфера = буфер.взять(гео, сколько, кроме=исключить, линия=линия)
        for с in из_буфера:
            итог.append(с)
            исключить.add(_без_диакритики(с))
        if len(итог) >= сколько:
            return итог

    for язык, слова in запас(гео).items():
        свободные = [с for с in слова
                     if _без_диакритики(с) not in исключить and not запрещено(с)]
        рнд.shuffle(свободные)
        for с in свободные:
            if len(итог) >= сколько:
                return итог
            итог.append(с)
            исключить.add(_без_диакритики(с))
    return итог


def сколько_осталось(гео: str, история: list[dict] | None = None) -> int:
    """Сколько неиспользованных слов ещё есть для страны — для честного отчёта."""
    return len(предложить(гео, 10_000, история))
