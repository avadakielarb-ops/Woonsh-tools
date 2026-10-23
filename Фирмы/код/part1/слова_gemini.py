"""
ПОПОЛНЕНИЕ ЗАПАСА СЛОВ ЧЕРЕЗ GEMINI.

Только stdlib (urllib) — как в проекте «Генератор ЦСВ»: лишняя зависимость
ради одного POST не нужна.

ГЛАВНОЕ ПРО ПРОМПТ. Первая же проба показала, чего просить НЕЛЬЗЯ: на запрос
«существительные, часто встречающиеся в названиях компаний» Gemini выдал
Solutions, Technologies, Systems, Group, Innovations. Искать по ним бессмысленно:
такие слова стоят у сотен тысяч фирм, выдача dnb забита, и все эти фирмы давно
перепаханы другими. Нам нужна ПРОТИВОПОЛОЖНОСТЬ — слова, которые встречаются
у десятков фирм, а не у десятков тысяч. Поэтому промпт запрещает корпоративный
словарь поимённо и требует конкретных предметных существительных.

Модели проверяем на живом ключе: доступны вплоть до gemini-3.7-flash.
Берём новейший флеш, при отказе спускаемся по списку — модель могут снять.

Что бы модель ни вернула, КАЖДОЕ слово проходит наш собственный фильтр
(`слова.запрещено`): за политику Google Ads отвечаем мы, а не подрядчик.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from part1 import слова as словарь

ROOT = "https://generativelanguage.googleapis.com/v1beta"
from common.пути import данные

ФАЙЛ_КЛЮЧЕЙ = данные("ключи.json")

# Порядок по ЗАМЕРУ, а не по номеру версии. На живом ключе 25.08.2026:
# 3.5-flash и 2.5-flash отвечают за 15–30 с, 3.7-flash не уложился в 120 с,
# а 2.5-flash под нагрузкой отдаёт 503 «high demand». Поэтому первым идёт
# проверенный быстрый, дальше запасные — модель могут снять или перегрузить.
# 08.09.2026: gemini-3.8-flash существует, но отдала 503 «Service Unavailable»
# на первом же запросе — в начало списка не ставим, пусть будет запасной.
МОДЕЛИ = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.7-flash",
          "gemini-3.8-flash")
ТАЙМАУТ = 150

# Языки стран — человеческими названиями, для промпта.
ЯЗЫК_НАЗВАНИЕ = {
    "PL": "Polish", "CZ": "Czech", "SK": "Slovak", "SI": "Slovenian",
    "HR": "Croatian", "HU": "Hungarian", "EE": "Estonian", "LV": "Latvian",
    "LT": "Lithuanian", "FI": "Finnish", "NO": "Norwegian", "DK": "Danish",
    "SE": "Swedish", "NL": "Dutch", "BE": "Dutch", "DE": "German",
    "AT": "German", "CH": "German", "FR": "French", "BG": "Bulgarian",
    "IT": "Italian", "ES": "Spanish", "PT": "Portuguese", "RO": "Romanian",
}
СТРАНА_НАЗВАНИЕ = {
    "PL": "Poland", "CZ": "Czechia", "SK": "Slovakia", "SI": "Slovenia",
    "HR": "Croatia", "HU": "Hungary", "EE": "Estonia", "LV": "Latvia",
    "FI": "Finland", "NO": "Norway", "DK": "Denmark", "SE": "Sweden",
    "NL": "Netherlands", "BE": "Belgium", "DE": "Germany", "AT": "Austria",
    "CH": "Switzerland", "FR": "France", "BG": "Bulgaria", "UK": "United Kingdom",
    "IE": "Ireland", "AU": "Australia", "US": "United States",
}

# КАТЕГОРИИ СЛОВ — чтобы наши фирмы не складывались в узор.
#
# Зачем. Если весь запас — камни и металлы, то и найденные фирмы будут
# «Гранит», «Кобальт», «Базальт»: со стороны это выглядит как один почерк, и
# на такой набор смотреть неприятно. Разные поля значений разводят находки.
#
# Второе, не менее важное: категории дают ЧЕСТНОЕ СРАВНЕНИЕ. Слово «ice» дало
# 10 фирм, «pinnacle» — ноль, но по двум словам нельзя судить о полях. Когда у
# каждого слова записана категория, видно уже не «повезло/не повезло», а
# «птицы дают вдвое больше ремёсел» — и следующую сотню можно просить с
# перекосом в то, что работает.
КАТЕГОРИИ = {
    "камни": "stones, minerals, metals and finishes",
    "деревья": "trees, shrubs, herbs and garden plants",
    "звери": "birds, animals, fish and insects",
    "погода": "weather, sky, seasons and light phenomena",
    "ландшафт": "landscape, water, coast and terrain",
    "ремёсла": "crafts, tools, workshop and old trades",
    "цвет": "colours, shades, lamps and fire",
    "навигация": "navigation, instruments, time and measurement",
    "ткани": "fabrics, materials, timber and building stuff",
    "старина": "mythology, heraldry, runes and old lore",
}

ПРОМПТ = """\
You generate SEARCH TOKENS for finding registered companies by NAME in a \
business directory (Dun & Bradstreet). The directory matches the token against \
the company's registered name, not its industry.

Country: {страна}
Languages required: English AND {язык}.

Produce exactly {сколько} single-word tokens.

WHAT A GOOD TOKEN IS
A concrete, picturable noun or adjective that real companies put INSIDE their \
names — nature, materials, stones, metals, colours, birds, trees, weather, \
landscape, geometry, crafts, old trades, mythology, navigation.
Examples of the RIGHT KIND (English): amber, kestrel, basalt, juniper, lantern, \
meridian, obsidian, thistle, zephyr. These nine are illustrations only — never \
output them or their {язык} translations; give different words of that kind.
Give the {язык} tokens as words a native speaker would actually see on a \
company sign in {страна} — real {язык} words, correctly spelled with proper \
diacritics, NOT English words transliterated.

FREQUENCY IS THE POINT
Aim for tokens carried by roughly 30 to 200 companies in {страна}.
Below that band a token yields one or two firms and the run stalls; above it \
the companies were found and used by everyone else long ago. When unsure, lean \
towards the COMMONER side: a word nobody uses is worse than useless, because \
it costs a full search to discover it is empty.

THE COMPANIES MUST HAVE WEBSITES
This is as important as the frequency band. We need tokens that ACTIVE TRADING \
companies put in their names — firms that sell something, run a shop, a studio, \
a workshop, a service, and therefore keep a website. Avoid words that mostly \
attach to entities with no web presence: village cooperatives, hunting and \
fishing societies, allotment associations, parish bodies, sports clubs, \
volunteer brigades, folk ensembles, tiny one-person craft trades, and purely \
archaic or dialect words that only old rural entities use.
Prefer words that sound at home on a modern company sign or a brand: materials \
and finishes, tools and workshop words, navigation and weather, light and \
colour, precision and speed, birds and predators. A good test: could a design \
studio, a logistics firm or a machine shop plausibly be named after it?

HARD BANS — never output any of these
- Generic corporate vocabulary in ANY language: solutions, technologies, \
systems, group, holding, services, consulting, partners, international, global, \
industries, enterprises, management, development, logistics, capital, invest, \
projects, trade, company, and their {язык} equivalents.
- Anything restricted by Google Ads policy, in either language: healthcare, \
medicine, pharmacy, clinics, supplements; gambling, betting, lotteries; loans, \
credit, payday, crypto, forex, banking, insurance; adult content, dating; \
tobacco, vaping, cannabis, alcohol; weapons, ammunition; politics, religion; \
drugs, surveillance.
- Personal names, brand names, city names, country names.
- Legal forms (Ltd, GmbH, {язык} equivalents).
- Anything shorter than 4 letters or longer than 14 letters.
- Multi-word phrases, hyphens, digits, punctuation.

SPREAD ACROSS CATEGORIES
Every token belongs to exactly one of these categories, and you must spread the \
tokens EVENLY across all of them — roughly the same count in each:
{категории}
Do not fill the list from one or two categories: a directory full of companies \
named after stones looks like one hand made it.

ALREADY USED — do not repeat any of these:
{исключить}

Return JSON only: an array of objects \
{{"w": token, "lang": "en" or "local", "cat": one of the category keys}}.
About half English, half {язык}. No commentary."""

СХЕМА = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"w": {"type": "STRING"},
                       "lang": {"type": "STRING"},
                       "cat": {"type": "STRING"}},
        "required": ["w", "lang"],
    },
}


class НетКлюча(RuntimeError):
    """Файл с ключом отсутствует или пуст."""


def ключ(path: Path = ФАЙЛ_КЛЮЧЕЙ) -> str:
    """
    Ключ из «ключи.json». Файл в .gitignore — в репозиторий не попадёт.

    encoding='utf-8-sig': PowerShell пишет файлы с BOM, и обычный json.load
    на нём падает с «Unexpected UTF-8 BOM».
    """
    p = Path(path)
    if not p.exists():
        raise НетКлюча(
            f"нет файла {p} — положи рядом с app.py:\n"
            '{"gemini_api_key": "AIza…", "gemini_model": "gemini-3.7-flash"}')
    try:
        д = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        raise НетКлюча(f"{p} не читается: {e}") from e
    к = (д.get("gemini_api_key") or "").strip()
    if not к:
        raise НетКлюча(f"в {p} пустой gemini_api_key")
    return к


def модель(path: Path = ФАЙЛ_КЛЮЧЕЙ) -> str:
    try:
        д = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return (д.get("gemini_model") or "").strip() or МОДЕЛИ[0]
    except Exception:
        return МОДЕЛИ[0]


def спросить_любой(промпт: str, api_key: str | None = None,
                   схема: dict | None = None, температура: float = 1.3,
                   log=print) -> str:
    """
    Спросить модель, перебирая список, пока одна не ответит.

    ЗАЧЕМ. Модель из настроек живёт своей жизнью: 22.09.2026 «gemini-3.5-flash»
    начала отдавать 503 на любой запрос, и вместе с ней встало всё, что через
    неё ходит, — и генератор слов, и подсказка местных написаний. При этом
    «gemini-2.5-flash» отвечала как ни в чём не бывало.

    Перебираем с настроенной, дальше по списку МОДЕЛИ. Отвечает первая живая.
    Молчат все — бросаем последнюю ошибку: это честнее пустого ответа.
    """
    api_key = api_key or ключ()
    порядок = [модель()] + [м for м in МОДЕЛИ if м != модель()]
    беда: Exception | None = None
    for имя in порядок:
        try:
            ответ = _спросить(имя, промпт, api_key, схема=схема,
                              температура=температура)
            if имя != порядок[0]:
                log(f"  · модель «{порядок[0]}» молчит — ответила «{имя}»")
            return ответ
        except Exception as e:
            беда = e
            continue
    raise беда or RuntimeError("ни одна модель не ответила")


def _спросить(имя_модели: str, промпт: str, api_key: str,
              timeout: int = ТАЙМАУТ, схема: dict | None = None,
              температура: float = 1.3) -> str:
    """
    Один запрос к модели.

    схема и температура — параметры, потому что этот же вызов использует
    проверка слов, а ей нужен ДРУГОЙ формат ответа и НИЗКАЯ температура.
    Раньше схема была зашита: проверка получала ответ в формате генератора
    ({w, lang} вместо вердикта) и молча возвращала ноль разобранных слов.
    Разнообразие нужно при выдумывании слов, а при оценке — наоборот, вредно.
    """
    payload = {
        "contents": [{"role": "user", "parts": [{"text": промпт}]}],
        "generationConfig": {
            # температура высокая намеренно: нам нужно РАЗНООБРАЗИЕ, а не
            # самый вероятный ответ. Самый вероятный — это и есть «solutions».
            "temperature": температура,
            "responseMimeType": "application/json",
            "responseSchema": схема or СХЕМА,
        },
    }
    req = urllib.request.Request(
        f"{ROOT}/models/{имя_модели}:generateContent",
        data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("x-goog-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ответ = json.loads(r.read().decode("utf-8"))
    части = (ответ.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(ч.get("text", "") for ч in части)


def сгенерировать(гео: str, сколько: int = 100,
                  исключить: set[str] | None = None,
                  log=print, api_key: str | None = None,
                  категории: dict | None = None) -> list[str]:
    """
    Слова для одной страны. Возвращает ТОЛЬКО прошедшие наш фильтр.

    Порядок — чередование категорий и языков: он же станет порядком прогонов.

    категории — необязательный словарь, который ЗАПОЛНИТ функция: {слово:
    «камни»}. Отдельным параметром, а не вторым возвращаемым значением, чтобы
    не переделывать три места вызова ради поля, которое нужно одному.
    """
    гео = (гео or "").upper()
    api_key = api_key or ключ()
    исключить = {с.lower() for с in (исключить or set())}

    промпт = ПРОМПТ.format(
        страна=СТРАНА_НАЗВАНИЕ.get(гео, гео),
        язык=ЯЗЫК_НАЗВАНИЕ.get(гео, "English"),
        сколько=сколько,
        категории="\n".join(f"  {к} — {о}" for к, о in КАТЕГОРИИ.items()),
        # длинный список исключений раздувает запрос и путает модель;
        # свои же повторы всё равно отсеет фильтр ниже
        исключить=", ".join(sorted(исключить)[:150]) or "(nothing yet)")

    последняя = None
    for имя in (модель(), *МОДЕЛИ):
        try:
            сырое = _спросить(имя, промпт, api_key)
            log(f"  · Gemini ({имя}) ответил")
            break
        except urllib.error.HTTPError as e:
            тело = e.read().decode("utf-8", "replace")[:200]
            последняя = f"HTTP {e.code}: {тело}"
            log(f"  · {имя}: {последняя}")
        except Exception as e:
            последняя = f"{type(e).__name__}: {e}"
            log(f"  · {имя}: {последняя}")
    else:
        raise RuntimeError(f"Gemini не ответил ни одной моделью. {последняя}")

    try:
        разобрано = json.loads(сырое)
    except Exception as e:
        raise RuntimeError(f"Gemini вернул не JSON: {e}; начало ответа: "
                           f"{(сырое or '')[:160]}") from e

    принятые, брак = [], []
    видели = set(исключить)
    for э in разобрано if isinstance(разобрано, list) else []:
        слово = (э.get("w") if isinstance(э, dict) else str(э) or "").strip()
        язык = (э.get("lang") if isinstance(э, dict) else "en") or "en"
        катег = (э.get("cat") if isinstance(э, dict) else "") or ""
        if not слово or слово.lower() in видели:
            continue
        причина = словарь.запрещено(слово)
        if причина:
            брак.append(f"{слово} ({причина})")
            continue
        видели.add(слово.lower())
        принятые.append({
            "w": слово,
            "англ": язык.lower().startswith("en"),
            # категорию модель может назвать своими словами или пропустить —
            # чужую не выдумываем, кладём «разное». Пустая категория честнее
            # приписанной наугад: по ней потом считают статистику.
            "cat": катег if катег in КАТЕГОРИИ else "разное",
        })

    if брак:
        log(f"  · отсеял {len(брак)}: " + ", ".join(брак[:5])
            + ("…" if len(брак) > 5 else ""))
    итог = разложить(принятые)
    по_кат = Counter(з["cat"] for з in принятые)
    местных = sum(1 for з in принятые if not з["англ"])
    log(f"  · принято {len(итог)} слов ({местных} местных + "
        f"{len(принятые) - местных} англ.), категорий {len(по_кат)}: "
        + ", ".join(f"{к}:{n}" for к, n in по_кат.most_common(6)))
    if категории is not None:
        категории.update({з["w"].lower(): з["cat"] for з in принятые})
    return итог


def разложить(слова: list[dict]) -> list[str]:
    """
    Разложить слова так, чтобы соседи различались и языком, и категорией.

    Запас выдаётся строго по порядку, поэтому порядок здесь — это и есть
    порядок будущих прогонов. Если сложить подряд, первые десять прогонов
    уйдут в один смысловой куст: сначала все камни, потом все птицы. Идём по
    категориям по кругу, а внутри круга чередуем язык.
    """
    по_кат: dict[str, dict[str, list]] = {}
    for з in слова:
        гнездо = по_кат.setdefault(з["cat"], {"англ": [], "мест": []})
        гнездо["англ" if з["англ"] else "мест"].append(з["w"])

    итог: list[str] = []
    брать_англ = False
    while any(г["англ"] or г["мест"] for г in по_кат.values()):
        for кат in sorted(по_кат):
            г = по_кат[кат]
            # берём из нужной половины; если она пуста — из другой
            первый = "англ" if брать_англ else "мест"
            второй = "мест" if брать_англ else "англ"
            если = г[первый] or г[второй]
            if если:
                итог.append(если.pop(0))
        брать_англ = not брать_англ
    return итог


def вперемешку(местные: list[str], англ: list[str]) -> list[str]:
    """
    Чередовать местные и английские слова: местное, английское, местное…

    ПОЧЕМУ НЕ ПОДРЯД. Сначала было «англ + местные», и до эстонских слов
    очередь не доходила НИКОГДА: запас выдаётся строго по порядку, а
    английских сто штук. Замер 08.09.2026 это подтвердил — «teras, vask,
    pronks» лежали в хвосте нетронутыми, отсюда и «2–3 фирмы на слово».

    Потом я поставил местные вперёд — и получил ту же беду зеркально:
    английские не попробуются, пока не кончатся местные, а на них в EE и HU
    выхлоп бывает выше. Чередование убирает обе крайности: обе половины
    проверяются с самого начала, и статистика выхлопа набирается по ним
    одновременно, а не по очереди через неделю.

    Кончилось одно — остаток второго идёт как есть. Для англоязычных стран
    местных нет вовсе, и список просто остаётся английским.
    """
    итог: list[str] = []
    for м, а in zip(местные, англ):
        итог += [м, а]
    хвост = местные[len(англ):] if len(местные) > len(англ) else англ[len(местные):]
    return итог + list(хвост)
