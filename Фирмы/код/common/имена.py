"""
ИМЯ ФИРМЫ: ключ для сравнения, запрос в реестр, имя для бота.

Живёт отдельно от окна, потому что нужно многим: кнопке в интерфейсе, скрипту
проверки из командной строки, драйверам реестров и ядру выбора.

ОДИН СПИСОК ПРАВОВЫХ ФОРМ НА ВЕСЬ ПРОЕКТ. До 20.10.2026 их было шесть (здесь,
в ядре, у Эстонии, «формы впереди» Латвии…) и они спорили: «Osaühing AA Aqua»
искалось как «AA Aqua», а сравнивалось как «osauhing aa aqua» — фирма, которую
реестр показал первой строкой, не совпадала сама с собой.

`normalize` из ядра сюда НЕ переезжает и НЕ меняется: это ключ ХРАНЕНИЯ
(журнал бота, отпечатки реестра фирм, «Ключ» на листе «Реестр»). Поменять его —
значит забыть всё, что уже записано. Для сравнения имён — `ключ_имени`.
"""
from __future__ import annotations

import re
import unicodedata

# Правовая форма, написанная словами целиком. Идёт ПЕРВОЙ: короткий шаблон
# «SPOLKA» не поймает «SPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA».
# Нужна только `без_формы_ascii` — имени для бота, которое трогать нельзя.
ДЛИННЫЕ = (r"SPO[LŁ]KA\s+Z\s+OGRANICZON[AĄ]\s+ODPOWIEDZIALNO[SŚ]CI[AĄ]|"
           r"KORLATOLT\s+FELELOSSEGU\s+TARSASAG|"
           r"GESELLSCHAFT\s+MIT\s+BESCHRANKTER\s+HAFTUNG|"
           r"MITTETULUNDUS[UÜ]HING|OSA[UÜ]HING|AKTSIASELTS|"
           r"SPOLKA\s+AKCYJNA|AKTIENGESELLSCHAFT")

ФОРМЫ = (r"O[UÜ]|MT[UÜ]|AS|SIA|UAB|SP\.?\s*Z\s*O\.?\s*O\.?|"
         r"S\.?R\.?O\.?|A\.?S\.?|D\.?O\.?O\.?|KFT|ZRT|BT|GMBH|AG|BV|NV|"
         r"SARL|SAS|S\.?A\.?|S\.?P\.?|LTD|LIMITED|PLC|LLC|INC|APS|OY|AB|"
         r"EOOD|OOD|PTY")

# ── ЕДИНЫЙ СПИСОК ФОРМ ─────────────────────────────────────────────────────
# Пишем как люди («sp. z o.o.», «a/s»), в слова раскладывает `_слова`: точки,
# слэши и дефисы становятся пробелами, диакритика складывается. Поэтому
# «S.R.O.», «s r o» и «sro» перечислены отдельно — это разные последовательности
# слов.
#
# Срезаем ТОЛЬКО С КРАЁВ имени и только целыми словами: «GAS AS» → «gas», а
# «AS» в середине («BALTIC AS GROUP») остаётся. Спереди — только формы,
# которые там правда стоят (Балтия: SIA "…", AS "…", OÜ …); иначе «AD ASTRA»
# искалось бы как «ASTRA».


def _сложить(s: str) -> str:
    """Диакритику и особые буквы — в простую латиницу, нижний регистр."""
    т = unicodedata.normalize("NFKD", s or "")
    т = "".join(c for c in т if not unicodedata.combining(c)).lower()
    for a, b in (("ł", "l"), ("ø", "o"), ("đ", "d"), ("ð", "d"),
                 ("ħ", "h"), ("ß", "ss"), ("æ", "ae"), ("œ", "oe"), ("þ", "th")):
        т = т.replace(a, b)
    return т


def _слова(s: str) -> list[str]:
    """
    Имя → значимые слова. ВСЕ ЗНАКИ — РАЗДЕЛИТЕЛИ, кроме «&» и «+» (= and).

    Живые случаи: в DnB «MARK`S» с обратным апострофом, в реестре «MARK'S»
    или «Mark’s»; «A&B» против «A & B» против «A and B»; «S.Lindén» против
    «S. Lindén». Раньше каждый такой знак давал другой ключ и фирма «не
    находилась», хотя стояла первой строкой.
    """
    т = _сложить(s)
    т = re.sub(r"[&+]", " and ", т)
    return re.findall(r"[^\W_]+", т)


# Одна форма — один элемент. Многословные идут как есть.
ФОРМЫ_ВСЕ: tuple[str, ...] = (
    "ltd", "limited", "plc", "llc", "inc", "corp", "co", "and co", "pty",
    "gmbh", "ag", "kg", "ohg", "ug", "e.k.",
    "gesellschaft mit beschrankter haftung", "aktiengesellschaft",
    "sarl", "sas", "sasu", "sa", "s.a.", "eurl", "snc", "sci",
    "bv", "b.v.", "nv", "n.v.", "vof",
    "ab", "as", "a/s", "aps", "oy", "oyj", "ky", "tmi",
    "sp. z o.o.", "spzoo", "sp.k.", "s.k.a.", "s.j.", "s.c.",
    "spolka z ograniczona odpowiedzialnoscia", "spolka komandytowo akcyjna",
    "spolka komandytowa", "spolka akcyjna", "spolka jawna", "spolka cywilna",
    "spolka partnerska", "spolka",
    "s.r.o.", "sro", "spol. s r.o.", "a.s.", "v.o.s.", "k.s.",
    "kft", "zrt", "nyrt", "bt", "korlatolt felelossegu tarsasag",
    "d.o.o.", "doo", "j.d.o.o.", "jdoo", "d.d.", "s.p.", "k.d.", "d.n.o.",
    "eood", "ood", "ad",
    # Болгарский реестр пишет кириллицей: «"АББЕКС" ЕООД», «ЕТ "АИТИШ - 14"».
    "еоод", "оод", "ад", "еад", "ет",
    "sia", "akciju sabiedriba", "sabiedriba ar ierobezotu atbildibu", "ik",
    # Латвия пишет форму СЛОВАМИ и впереди, DnB — сокращением сзади:
    # «Individuālais komersants "ANDREJA DARBNĪCA"» = «ANDREJA DARBNICA IK»
    # (живой прогон 20.10.2026).
    "individualais komersants", "individualais uznemums", "ind",
    "zemnieku saimnieciba", "zs", "biedriba", "bdr",
    "uab", "mb", "kb", "ps", "ks",
    "ou", "mtu", "fie", "tuh", "uu", "tu", "osauhing", "aktsiaselts",
    "tulundusuhistu", "sihtasutus", "mittetulundusuhing",
    "srl", "s.r.l.", "spa", "s.p.a.",
    "zao", "ooo",
)

# Какие из них бывают ВПЕРЕДИ имени.
ФОРМЫ_ВПЕРЕДИ: tuple[str, ...] = (
    "sia", "as", "ou", "uab", "ab", "ik", "mb", "kb", "ps", "ks", "zao", "ooo",
    "mtu", "fie", "osauhing", "aktsiaselts", "mittetulundusuhing",
    "akciju sabiedriba", "sabiedriba ar ierobezotu atbildibu",
    "individualais komersants", "individualais uznemums",
    "zemnieku saimnieciba", "zs", "biedriba", "ет", "et",
)

# Формы словами, длинные первыми: «spolka z ograniczona …» раньше «spolka».
_ФОРМЫ_СЛОВАМИ: list[tuple[str, ...]] = sorted(
    {tuple(_слова(ф)) for ф in ФОРМЫ_ВСЕ if _слова(ф)},
    key=len, reverse=True)
_ВПЕРЕДИ_СЛОВАМИ = {tuple(_слова(ф)) for ф in ФОРМЫ_ВПЕРЕДИ}


def _срезать_формы(слова: list[str], ключи: list[str]) -> list[str]:
    """
    Срезать формы с обоих краёв. `ключи` — сложенные слова, по которым
    сверяем; режем параллельно `слова` (что возвращаем). Пустым не оставляем:
    имя из одной формы («OU») лучше искать как есть.
    """
    с, к = list(слова), list(ключи)
    менялось = True
    while менялось and len(к) > 1:
        менялось = False
        for ф in _ФОРМЫ_СЛОВАМИ:
            n = len(ф)
            if n < len(к) and tuple(к[-n:]) == ф:
                с, к = с[:-n], к[:-n]
                менялось = True
                break
            if n < len(к) and ф in _ВПЕРЕДИ_СЛОВАМИ and tuple(к[:n]) == ф:
                с, к = с[n:], к[n:]
                менялось = True
                break
    return с


def ключ_имени(имя: str) -> str:
    """
    КЛЮЧ ДЛЯ СРАВНЕНИЯ имён фирм — один на весь проект.

    Складывает диакритику, «&»/«+» читает как «and», все прочие знаки
    (кавычки, апострофы, обратные кавычки, точки, дефисы, скобки) считает
    пробелом, срезает правовые формы с краёв, схлопывает «NAME (NAME)».

        «SIA "AQUA-360"», «Aqua-360 SIA», «AQUA 360»  → «aqua 360»
        «Osaühing AA Aqua», «AA AQUA OU»              → «aa aqua»
        «MARK`S PLUMBING LTD», «Mark’s Plumbing Ltd»  → «mark s plumbing»

    Только для сравнения. Хранить по нему ничего нельзя — см. шапку модуля.
    """
    сл = _слова(имя)
    сл = _срезать_формы(сл, сл)
    полов = len(сл) // 2
    if полов and len(сл) % 2 == 0 and сл[:полов] == сл[полов:]:
        сл = сл[:полов]
    return " ".join(сл)


_ОБРЕЗ = re.compile(r"\s*(\.\.\.|…)\s*$")


def обрезано(имя: str) -> bool:
    """DnB обрезал длинное имя многоточием: «… JANISZEWSKI DA...»."""
    return bool(_ОБРЕЗ.search(имя or ""))


def без_обреза(имя: str) -> str:
    """
    Обрезанное имя — без многоточия и без недописанного последнего слова.

    Живой прогон 20.10.2026, Польша: «A D T MARMUR I GRANIT S C JANISZEWSKI
    DA...» уходило в реестр как есть, с «...», — и находить было нечем.
    «DA» — огрызок фамилии, его тоже долой: по огрызку реестр не найдёт.
    """
    if not обрезано(имя):
        return (имя or "").strip()
    т = _ОБРЕЗ.sub("", имя or "")
    слова = т.split()
    if len(слова) > 2:
        слова = слова[:-1]
    return " ".join(слова).strip(" ,.[(\"'")


def полное_имя(имя: str) -> str:
    """
    Ключ ВМЕСТЕ с правовой формой: «ANVIL ELECTRONICS PTY. LTD.» →
    «anvil electronics pty ltd». Различает тёзок, когда ключи без формы
    совпали: в ABR рядом с нашей «ANVIL ADVISORY PTY LTD» стоит чужое торговое
    имя «Anvil Advisory» с другим ABN (живая проверка 20.10.2026).
    """
    т = " " + " ".join(_слова(имя)) + " "
    # ФОРМА СЛОВАМИ = ФОРМА СОКРАЩЕНИЕМ. «ARBOR BG SP Z O O SPÓŁKA
    # KOMANDYTOWA» и «ARBOR BG SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ SPÓŁKA
    # KOMANDYTOWA» — одна фирма (живой прогон PL 20.10.2026).
    for длинно, коротко in _СОКРАЩЕНИЯ:
        т = т.replace(f" {длинно} ", f" {коротко} ")
    return т.strip()


_СОКРАЩЕНИЯ = [(" ".join(_слова(а)), " ".join(_слова(б))) for а, б in (
    ("spolka z ograniczona odpowiedzialnoscia", "sp z o o"),
    ("spolka komandytowa", "sp k"),
    ("spolka komandytowo akcyjna", "s k a"),
    ("spolka akcyjna", "s a"),
    ("spolka jawna", "sp j"),
    ("limited", "ltd"),
    ("proprietary", "pty"),
    ("osauhing", "ou"),
    ("aktsiaselts", "as"),
    ("sabiedriba ar ierobezotu atbildibu", "sia"),
    ("individualais komersants", "ik"),
    ("gesellschaft mit beschrankter haftung", "gmbh"),
    ("korlatolt felelossegu tarsasag", "kft"),
    ("spolecnost s rucenim omezenym", "s r o"),
    ("druzba z omejeno odgovornostjo", "d o o"),
    ("drustvo s ogranicenom odgovornoscu", "d o o"),
)]
_СОКРАЩЕНИЯ.sort(key=lambda п: -len(п[0]))


def без_формы(имя: str) -> str:
    """
    Имя БЕЗ правовой формы, но со своими буквами: «AQUA-360 SIA» → «AQUA-360».

    Для ЗАПРОСА В РЕЕСТР, а не для сверки. Диакритику тут трогать нельзя:
    латышское «Ķieģelis» без своих букв реестр не найдёт. А вот форму убрать
    обязательно — реестры пишут её по-своему и на своём месте.

    Живой случай 17.09.2026, Латвия. Наша фирма «AQUA-360 SIA», в реестре она
    записана как SIA "AQUA-360" — форма ВПЕРЕДИ, имя В КАВЫЧКАХ. По запросу
    «AQUA-360 SIA» поиск отдал двух чужих («Aqua Unitā», «SIA AQUA»), по
    запросу «aqua-360» — нашу первой строкой.

    Формы — из того же единого списка, что и у `ключ_имени`: искать и
    сравнивать по разным правилам значит не узнать найденное.
    """
    исходные = (имя or "").split()
    # Каждое слово имени может дать несколько сложенных («S.R.O.» → s r o):
    # разворачиваем, помня, какому исходному слову принадлежит каждый кусок.
    куски, чьё = [], []
    for i, с in enumerate(исходные):
        for к in _слова(с):
            куски.append(к)
            чьё.append(i)
    if not куски:
        return (имя or "").strip(" .,«»\"'")
    оставшиеся = _срезать_формы(list(range(len(куски))), куски)
    if not оставшиеся:
        return (имя or "").strip(" .,«»\"'")
    первое, последнее = чьё[оставшиеся[0]], чьё[оставшиеся[-1]]
    т = " ".join(исходные[первое:последнее + 1])
    # ДВОЙНЫЕ КАВЫЧКИ — НЕ ЧАСТЬ ИМЕНИ, где бы они ни стояли. Срезать их
    # только по краям мало: «"Maple Leaf" Rockenbauer …» уходило в реестр как
    # «Maple Leaf" Rockenbauer …» и не находилось (живой прогон AT 20.10.2026).
    # Апостроф не трогаем: «RUNE'S BYGG» — это имя.
    т = re.sub(r"[\"«»„“”]", " ", т)
    # Кавычки вокруг имени — часть записи реестра, а не имени: «SIA "AQUA-360"».
    return re.sub(r"\s+", " ", т).strip(" .,«»\"'„“”")


def без_формы_ascii(имя: str) -> str:
    """
    Имя для бота: без правовой формы и латиницей.

    НЕ ПЕРЕВОДИТЬ НА ЕДИНЫЙ СПИСОК ФОРМ. Бот сверяет с базой команды, куда за
    месяцы ушли тысячи имён ровно в этом виде; другое написание той же фирмы
    бот примет за новую — и фирма уйдёт в работу второй раз.

    Бот сверяет с базой команды, где эстонская «OÜ» записана как «OU», а
    польские хвосты не пишут вовсе. Диакритику складываем, форму срезаем —
    иначе одна и та же фирма не сойдётся сама с собой.

    ХВОСТ ИЗ ДВУХ ФОРМ ПОДРЯД — «PTY LTD» — РАНЬШЕ СРЕЗАЛСЯ НАПОЛОВИНУ.
    Шаблон СЪЕДАЛ пробел после формы, и следующее слово оставалось без
    разделителя слева: «ADELAIDE MARBLE SPECIALISTS PTY LTD» уходило боту как
    «… SPECIALISTS LTD». Точка мешала так же: «PTY. LTD.» не срезалось вовсе.
    Цена: бот сверяет с базой, где форм нет, и такой дубль выглядел как новая
    фирма. Замер 17.09.2026: из 416 имён «с сайтом» испорчено было 213.

    Лечение: не съедать разделитель (смотрим вперёд) и допускать точку.
    Повторяем, пока строка меняется: форм в хвосте бывает и три.
    """
    т = unicodedata.normalize("NFKD", имя or "")
    т = "".join(c for c in т if not unicodedata.combining(c))
    for a, b in (("ł", "l"), ("Ł", "L"), ("ø", "o"), ("đ", "d"), ("ß", "ss")):
        т = т.replace(a, b)
    т = re.sub(rf"(?i)(^|\s){ДЛИННЫЕ}(\s|$)", " ", т)
    было = None
    while было != т:
        было = т
        т = re.sub(rf"(?i)(^|\s)(?:{ФОРМЫ})\.?(?=\s|$)", " ", т)
    return re.sub(r"\s+", " ", т).strip(" .,")
