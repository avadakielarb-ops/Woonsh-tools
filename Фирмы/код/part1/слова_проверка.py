r"""
ПРОВЕРКА ПЛОХИХ СЛОВ ЧЕРЕЗ GEMINI.

Зачем. Слово, по которому находится две фирмы, стоит столько же, сколько
слово, по которому находится двести: тот же заход на dnb, та же выдача, то же
время. Разница только в результате. Сейчас такие слова просто тихо съедают
прогон, и никто не разбирается, почему они пустые.

Причины у пустого слова разные, и лечатся они по-разному:
  · слова в этом языке нет вовсе (модель выдумала или ошиблась в написании);
  · слово есть, но в названиях фирм не встречается («вторник», «поэтому»);
  · слово редкое, но живое — просто не повезло, пробовать стоит.
Первые два — брак, их надо выбросить навсегда. Третье выбрасывать нельзя.

Отличить их по цифрам невозможно: и «выдуманное» и «редкое» дают ноль. Поэтому
спрашиваем у модели — она знает язык. Проверяем ПАЧКОЙ и только те слова, что
уже показали плохой выхлоп: гонять на проверку весь запас незачем.
"""
from __future__ import annotations

import json

from part1.слова_gemini import (МОДЕЛИ, СТРАНА_НАЗВАНИЕ, ЯЗЫК_НАЗВАНИЕ,
                                _спросить, ключ, модель)

# ПРИМЕРЫ В ПРОМПТЕ — не украшение. Замер 09.09.2026: пачка из двух слов
# («jaspis», «warm») получила «живое» на оба, а та же «warm» в пачке из
# четырёх, где рядом лежали «wtorek» и «ponieważ», — честное «не в именах».
# Модель равняется на соседей по списку: когда явного мусора рядом нет, она
# считает мусором ничего. Примеры дают точку отсчёта независимо от того, что
# попало в пачку.
ПРОМПТ = """\
You are checking SEARCH TOKENS used to find companies by name in the business \
register of {страна}. Each token below produced almost no results.

For every token say WHY, choosing exactly one verdict:
  "нет"      — this is not a real word in {язык} or English, or it is misspelled;
  "не в именах" — it is a real word, but companies there never put it in their names \
(grammar words, verbs, abstract notions, everyday words nobody brands with);
  "живое"    — a real word that companies could plausibly use; it just happens to be rare.

Be strict with "живое": give it only when you would expect at least a handful of \
real companies in {страна} to carry this word in their registered name.

Calibration — the same three verdicts on tokens you already know:
  "qwertzu" -> "нет"          (random letters, no such word in any language)
  "jaspsi"  -> "нет"          (misspelling of a real word)
  "because" -> "не в именах"  (function word, nobody brands with it)
  "tuesday" -> "не в именах"  (everyday word, not a brand)
  "granite" -> "живое"        (material, common in company names)

Tokens:
{слова}

Return JSON only: an array of {{"w": token, "вердикт": one of the three, \
"почему": short reason in Russian, max 8 words}}. No commentary."""

СХЕМА = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"w": {"type": "STRING"},
                       "вердикт": {"type": "STRING"},
                       "почему": {"type": "STRING"}},
        "required": ["w", "вердикт"],
    },
}

БРАК = {"нет", "не в именах"}


def проверить(гео: str, слова: list[str], log=print,
              api_key: str | None = None) -> dict[str, dict]:
    """
    Слово → {'вердикт', 'почему'}. Пустой ответ модели = ничего не решаем.

    Ошибку сети НЕ поднимаем наверх: проверка слов — дело полезное, но не
    настолько, чтобы из-за неё падал прогон. Не ответила — значит в этот раз
    не почистили, попробуем в следующий.
    """
    слова = [с for с in dict.fromkeys(с.strip() for с in слова) if с]
    if not слова:
        return {}
    гео = (гео or "").upper()
    промпт = ПРОМПТ.format(
        страна=СТРАНА_НАЗВАНИЕ.get(гео, гео),
        язык=ЯЗЫК_НАЗВАНИЕ.get(гео, "English"),
        слова="\n".join(f"- {с}" for с in слова))

    сырое = ""
    for имя in (модель(), *МОДЕЛИ):
        try:
            # Схема СВОЯ и температура низкая: здесь нужен точный разбор, а не
            # разнообразие. С общей схемой генератора ответ приходил в чужом
            # формате и разбирался в ноль.
            сырое = _спросить(имя, промпт, api_key or ключ(),
                              схема=СХЕМА, температура=0.2)
            log(f"  · проверку слов сделал {имя}")
            break
        except Exception as e:
            log(f"  · {имя}: {type(e).__name__}: {str(e)[:80]}")
    if not сырое:
        log("  · проверить слова не вышло — оставляю как есть")
        return {}

    try:
        разобрано = json.loads(сырое)
    except Exception:
        log("  · ответ проверки не разобрался")
        return {}

    итог: dict[str, dict] = {}
    for э in разобрано if isinstance(разобрано, list) else []:
        слово = str((э or {}).get("w", "")).strip()
        вердикт = str((э or {}).get("вердикт", "")).strip().lower()
        if слово and вердикт:
            итог[слово] = {"вердикт": вердикт,
                           "почему": str(э.get("почему", "")).strip()}
    плохих = sum(1 for з in итог.values() if з["вердикт"] in БРАК)
    log(f"  · проверено {len(итог)} слов, в брак {плохих}")
    return итог


def отсеять(гео: str, подозрительные: list[str], запас, log=print) -> list[str]:
    """
    Проверить подозрительные слова и выбросить брак из запаса НАВСЕГДА.

    Возвращает выброшенные. «Живое» не трогаем: редкое слово — не плохое,
    и выбрасывать его значит терять фирмы, до которых просто не дошли.
    """
    вердикты = проверить(гео, подозрительные, log=log)
    брак = [с for с, з in вердикты.items() if з["вердикт"] in БРАК]
    if not брак:
        return []
    запас.забраковать(гео, брак)
    for с in брак:
        log(f"  ✘ слово «{с}» — {вердикты[с]['вердикт']}: "
            f"{вердикты[с].get('почему', '')}")
    return брак
