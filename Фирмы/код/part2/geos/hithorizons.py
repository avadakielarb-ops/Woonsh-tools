"""
HITHORIZONS — источник ЕИК (National ID) болгарских фирм по АНГЛИЙСКОМУ имени.

Зачем. Болгарский реестр ищет только КИРИЛЛИЦЕЙ, а DnB даёт латиницу. Раньше имя
переводили транслитерацией — и она врала: «ICE» превращалось в «ИСЕ», хотя
по-болгарски это «АЙС». Побуквенные правила в принципе не могут угадать, как
по-болгарски записано английское слово, а словарь всех слов не вместит.

Решение: не угадывать имя, а взять НОМЕР. hithorizons знает и английское имя, и
ЕИК; а болгарский реестр по ЕИК отдаёт выписку прямым адресом. Номер не переврать.

ВАЖНО про Cloudflare. Сайт за Cloudflare и банит за подозрительные шаблоны:
самодельный адрес поиска («/eu/companies?q=…») получил жёсткий блок сразу.
Поэтому ходим ТОЛЬКО через интерфейс — как человек: открыть главную, вбить в
поле, нажать Enter. И держим паузу между фирмами.

Разметка выдачи (снята с живой страницы 23.08.2026):
    a.search-result                       — одна фирма
      h3.truncate[title]                  — ПОЛНОЕ имя (в тексте оно обрезано)
      .search-result-address              — «Plovdiv, BULGARIA»
      tr.search-result-item  td:National ID | td:115504021
ЕИК есть ПРЯМО В ВЫДАЧЕ — карточку открывать не нужно, это лишний запрос.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass

ГЛАВНАЯ = "https://www.hithorizons.com/"
ПОЛЕ = "input[placeholder*='Company Name' i]"
РЕЗУЛЬТАТ = "a.search-result"

# Между фирмами держим паузу: сайт за Cloudflare, ровный пулемётный ритм —
# первый признак робота. Разброс, а не фиксированное число.
ПАУЗА = (2.5, 5.0)


@dataclass
class Находка:
    имя: str
    еик: str
    адрес: str
    hh_id: str


def _норм(s: str) -> str:
    """Имя к сравнимому виду: без формы, знаков и лишних пробелов."""
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    формы = {"EOOD", "OOD", "EAD", "AD", "ET", "DZZD", "KD", "KDA", "SD",
             "LTD", "LIMITED", "LLC", "INC", "CORP", "PLC", "JSC", "CO"}
    слова = [w for w in s.split() if w not in формы]
    return " ".join(слова)


def искать(br, имя: str, log=print) -> list[Находка]:
    """
    Найти фирму по английскому имени. Возвращает находки в порядке выдачи.

    Ходим через интерфейс, а не по склеенному адресу (см. шапку модуля).
    """
    page = br.page
    try:
        if not page.url.startswith(ГЛАВНАЯ):
            br.goto(ГЛАВНАЯ)
            page.wait_for_timeout(1200)
        поле = page.locator(ПОЛЕ).first
        if not поле.count():
            br.goto(ГЛАВНАЯ)
            page.wait_for_timeout(1500)
            поле = page.locator(ПОЛЕ).first
        поле.click(timeout=8000)
        поле.fill(имя, timeout=8000)
        page.wait_for_timeout(600)
        поле.press("Enter")
        page.wait_for_timeout(3500)
    except Exception as e:
        log(f"    hithorizons: поиск не отправился ({type(e).__name__})")
        return []

    br.check_captcha(имя)

    находки: list[Находка] = []
    блоки = page.locator(РЕЗУЛЬТАТ)
    for i in range(min(блоки.count(), 12)):
        б = блоки.nth(i)
        try:
            заголовок = б.locator("h3").first
            полное = (заголовок.get_attribute("title") or
                      заголовок.inner_text()).strip()
            строка = б.inner_text()
            m = re.search(r"National ID\s*\n?\s*(\d{9,13})", строка)
            if not m:
                continue
            адрес = ""
            а = б.locator(".search-result-address").first
            if а.count():
                адрес = а.inner_text().strip().splitlines()[0]
            href = б.get_attribute("href") or ""
            hh = re.search(r"/companies/(H-[A-Z0-9]+)/", href)
            находки.append(Находка(полное, m.group(1), адрес,
                                   hh.group(1) if hh else ""))
        except Exception:
            continue
    return находки


def подобрать(имя: str, находки: list[Находка]) -> Находка | None:
    """
    Однозначная находка или None.

    Сначала точное совпадение имени без правовой формы, потом единственный
    результат. Неоднозначность НЕ разрешаем сами — пусть решает человек:
    взять чужой ЕИК хуже, чем спросить.
    """
    цель = _норм(имя)
    точные = [н for н in находки if _норм(н.имя) == цель]
    if len(точные) == 1:
        return точные[0]
    if not точные and len(находки) == 1:
        return находки[0]
    return None


def пауза() -> None:
    """Человеческий разброс между фирмами — против бана."""
    time.sleep(random.uniform(*ПАУЗА))
