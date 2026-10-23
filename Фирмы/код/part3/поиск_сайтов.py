# -*- coding: utf-8 -*-
"""
ЧАСТЬ 3 — «Найти сайты». Берёт фирмы БЕЗ сайта (лист «Без сайта» из Части 1),
ищет их официальный сайт и пишет подтверждённые в лист «Нашли сайт»:
Организация | Адрес | Website.

ЛОГИКА (согласована с пользователем):

  У каждой ссылки из выдачи — ДВЕ роли:
    • РЕЕСТР/КАТАЛОГ (societe, pappers, annuaire, infonet, lefigaro…) — это ИСТОЧНИК,
      а НЕ ответ. Мы его НЕ сохраняем, но ВЫЧИТЫВАЕМ из него:
         – поле «Site web / Website» → готовый кандидат (сайт фирмы);
         – адрес фирмы по реестру → запоминаем как ВТОРОЙ адрес.
    • САЙТ-КАНДИДАТ (любой другой домен) — это возможный ОТВЕТ, его надо
      подтвердить адресом.

  Держим ДВА адреса: из DNB (Excel) и из реестра — они могут отличаться, сверяем
  кандидата по ОБОИМ.

  Подтверждение кандидата: открываем сайт И его страницы «Контакты / О нас /
  Mentions légales / Impressum» (там по закону адрес) и ищем город/индекс любого
  из двух адресов. Бонус к уверенности, если имя фирмы есть в домене (но это НЕ
  обязательно — домены бывают любые).

  Если реестр отдал поле «сайт» — доверяем ему как готовому ответу, но адрес всё
  равно сверяем (реестр иногда устаревает).

  Ничего не подтвердилось → человек, но ВИДИТ страницы по одной: открываю
  кандидата → «✔ Да / → Следующий / ✖ Ни один». Каталог как ответ НЕ сохраняю.

Поиск идёт в DuckDuckGo HTML (html.duckduckgo.com/html) — почти не капчит и
парсится без JS (в отличие от Bing/Google). Ссылки там завёрнуты в /l/?uddg=<url>.

Вход:  лист «Без сайта»  (Организация | Адрес | Город | Индекс | E-пометка)
Выход: лист «Нашли сайт» (Организация | Адрес | Website); в «Без сайта» — пометка.
"""
from __future__ import annotations

import re
from pathlib import Path
from threading import Event
from urllib.parse import quote, urljoin

from openpyxl import load_workbook
from openpyxl.styles import Font

from common.browser import Browser
from common.human import (HumanGate, AbortRun, SkipCompany, подождать_паузу,
                          сохранить_excel)
from part1.dnb import это_сайт_фирмы          # доп. фильтр «сайт фирмы, не каталог»

DUCK = "https://html.duckduckgo.com/html/?q="

# ── МУСОР: поисковики, соцсети, энциклопедии, маркетплейсы — выкидываем совсем ──
_МУСОР = (
    "duckduckgo.com", "google.", "bing.com", "microsoft.com", "yahoo.", "yandex.",
    "wikipedia.org", "wikimedia.org", "imdb.com", "youtube.com", "youtu.be",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "pinterest.", "tiktok.com", "amazon.", "ebay.", "aliexpress.", "tripadvisor.",
    "yelp.",
)

# ── РЕЕСТРЫ/КАТАЛОГИ: НЕ ответ, но ИСТОЧНИК (сайт-поле + адрес фирмы) ──
# Полностью их не перечислить — основную работу делает детектор по СОДЕРЖИМОМУ
# (похоже_на_каталог). Здесь — известные, чтобы отсеять сразу по домену.
_РЕЕСТРЫ = (
    "annuaire-entreprises.data.gouv.fr", "data.inpi.fr", "societe.com", "pappers.fr",
    "pappers.", "infonet.fr", "verif.com", "manageo.fr", "b-reputation.com",
    "lefigaro.fr", "score3.fr", "infogreffe.fr", "bodacc", "kompass.com",
    "europages.", "dnb.com", "dnbcountryrisk", "northdata.", "companieshouse",
    "handelsregister", "kvk.nl", "opencorporates.com", "pagesjaunes.fr",
    "creditsafe", "ellisphere", "societeinfo", "corporama", "usinenouvelle",
    "bilansgratuits", "l-expert-comptable", "leadar.", "firmania.", "cylex",
    "trouverunemploi",
    # каталоги-агрегаторы (из живого прогона по France)
    "hoodspot.fr", "petitesaffiches.fr", "e-pro.fr", "e-pro.", "annuaire-",
    "-annuaire", "chercher.pro", "trouver.pro", "verif-siren", "avis-verifies",
    "yellowpages", "yelp.", "119.fr", "118000.fr", "local.fr", "justacote.com",
    "starofservice", "wanteeed", "entreprises.lefigaro", "figaro.fr",
)


# ---------- чистые функции (тестируются офлайн) ----------

def _домен(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    return re.sub(r"^www\.", "", m.group(1).lower()) if m else (url or "")


def _раскрыть_ddg(href: str) -> str:
    """DuckDuckGo оборачивает ссылку в /l/?uddg=<реальный_url> — раскрываем."""
    from urllib.parse import urlparse, parse_qs, unquote
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "/l/?" in href or "duckduckgo.com/l/" in href:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            return unquote(q["uddg"][0])
    return href


def _мусор(url: str) -> bool:
    return any(x in (url or "").lower() for x in _МУСОР)


def это_реестр(url: str) -> bool:
    return any(x in (url or "").lower() for x in _РЕЕСТРЫ)


def _исключён(url: str) -> bool:
    """Совсем не годится как ответ (мусор ИЛИ реестр)."""
    return _мусор(url) or это_реестр(url)


def годится_как_ответ(url: str) -> bool:
    """Можно сохранить как сайт фирмы? (не мусор, не реестр, проходит фильтр Ч.1)"""
    u = (url or "")
    return u.startswith("http") and not _исключён(u) and это_сайт_фирмы(u)


def классифицировать(ссылки: list[str], лимит: int = 8) -> tuple[list[str], list[str]]:
    """
    Разложить ссылки выдачи на (кандидаты-сайты, реестры-источники).
    Мусор выкидываем. Дедуп по домену.
    """
    канд: list[str] = []
    реестры: list[str] = []
    виденные: set[str] = set()
    for h in ссылки:
        h = _раскрыть_ddg(h)
        if not h.startswith("http") or _мусор(h):
            continue
        d = _домен(h)
        if not d or d in виденные:
            continue
        виденные.add(d)
        if это_реестр(h):
            реестры.append(h)
        elif это_сайт_фирмы(h):
            канд.append(h)
        if len(канд) >= лимит:
            break
    return канд, реестры


# для обратной совместимости со старыми вызовами/тестами
def кандидаты_из_выдачи(ссылки: list[str], лимит: int = 6) -> list[str]:
    return классифицировать(ссылки, лимит)[0]


def извлечь_сайт_из_текста(текст: str, свой: str = "") -> str:
    """
    Достать официальный сайт из текста страницы реестра: URL рядом с меткой
    «Site web / Site internet / Website». «NC»/пусто → ''. Свой/мусор/реестр — мимо.
    """
    for m in re.finditer(
            r"(?:site\s*web|site\s*internet|website|site\s*officiel)"
            r"[\s:.\-–]*((?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?)",
            текст or "", re.I):
        url = m.group(1)
        if not url.lower().startswith("http"):
            url = "http://" + url
        d = _домен(url)
        if not d or (свой and свой in d):
            continue
        if _исключён(url):
            continue
        return url
    return ""


# фразы-маркеры каталога/агрегатора (их нет на нормальном сайте фирмы)
_КАТАЛОГ_СИЛЬНЫЕ = (          # достаточно ОДНОЙ такой фразы
    "revendiquez cette fiche", "c'est votre entreprise", "c’est votre entreprise",
    "annuaire des entreprises", "annuaire qui référence", "réference les tpe",
    "référence les tpe", "ajouter gratuitement votre", "claim this listing",
    "claim this business", "is this your business", "add your business",
    "à qui appartient ce numéro", "signaler une anomalie",
)
_КАТАЛОГ_СЛАБЫЕ = (           # нужно ДВЕ и более
    "afficher le numéro", "afficher le téléphone", "ajouter à une liste",
    "laisser le 1er avis", "laisser un avis", "trier par pertinence",
    "voir toutes les adresses", "bouche à oreille", "créer un compte",
    "qui / quoi", "qui/quoi", "où ? (ex", "mettre à jour", "afficher l'itinéraire",
    "toutes les sociétés", "entreprises et", "adresses", "horaires d'ouverture",
    "business directory", "company directory",
)
_КАТАЛОГ_URL = ("annuaire", "/adresse/", "/adresses/", "yellowpages", "pagesjaunes")


def похоже_на_каталог(текст: str, url: str = "") -> bool:
    """
    Это каталог/агрегатор, а не сайт фирмы? Определяем по СОДЕРЖИМОМУ (домены не
    перечислить). Каталог → в ответ не идёт, только вычитываем сайт-поле/адрес.
    """
    u = (url or "").lower()
    if это_реестр(u):
        return True
    if any(k in u for k in _КАТАЛОГ_URL):
        return True
    if re.search(r"\d{14}", u):            # SIREN/SIRET в URL → карточка каталога
        return True
    низ = (текст or "").lower()
    if any(ф in низ for ф in _КАТАЛОГ_СИЛЬНЫЕ):
        return True
    return sum(1 for ф in _КАТАЛОГ_СЛАБЫЕ if ф in низ) >= 2


def адрес_из_реестра(текст: str) -> tuple[str, str]:
    """
    Вытащить (город, индекс) со страницы реестра: ищем «<индекс 4-5 цифр> <Город>».
    Ничего не нашли → ('', '').
    """
    m = re.search(r"\b(\d{4,5})\s+([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ'’.\- ]{1,28})", текст or "")
    if not m:
        return ("", "")
    город = re.split(r"[\n,.;/(]", m.group(2))[0].strip(" -–")
    return (город, m.group(1))


def адрес_совпал(текст_страницы: str, город: str, индекс: str) -> bool:
    """Адрес фирмы есть на странице? Достаточно ГОРОДА или ИНДЕКСА (без пробелов)."""
    низ = (текст_страницы or "").lower()
    без_проб = re.sub(r"\s", "", низ)
    if индекс and re.sub(r"\s", "", индекс).lower() in без_проб:
        return True
    if город and len(город) >= 3 and город.lower() in низ:
        return True
    return False


def любой_адрес_совпал(текст: str, адреса: list[tuple[str, str]]) -> bool:
    return any(адрес_совпал(текст, г, и) for г, и in адреса)


def имя_в_домене(орг: str, url: str) -> bool:
    """Бонус-сигнал: отличительное слово названия есть в домене (heat → heatlog.fr)."""
    d = _домен(url).split(".")[0]
    стоп = {"the", "and", "group", "groupe", "sarl", "sas", "eurl", "ooo", "ood",
            "eood", "ead", "kft", "bv", "ltd", "gmbh", "srl", "spa", "company",
            "societe", "société", "entreprise"}
    for сл in re.findall(r"[a-zа-яё]{4,}", (орг or "").lower()):
        if сл in стоп:
            continue
        if сл in d:
            return True
    return False


def построить_запрос(орг: str, адрес: str, город: str, страна: str) -> str:
    """Запрос = ИМЯ + АДРЕС + ГОРОД + СТРАНА (гео) — чтобы не ловить «HOME» со всего мира."""
    части = [p.strip() for p in (орг, адрес, город, страна) if p and p.strip()]
    return " ".join(части).strip()


# ---------- работа с браузером ----------

def _ссылки_выдачи(page) -> list[str]:
    """Органические ссылки DuckDuckGo HTML (a.result__a), раскрытые из /l/?uddg=."""
    href: list[str] = []
    for сел in ("a.result__a", "#links a.result__a", ".results a.result__a",
                ".web-result a[href]"):
        try:
            loc = page.locator(сел)
            for i in range(min(loc.count(), 25)):
                h = _раскрыть_ddg(loc.nth(i).get_attribute("href") or "")
                if h.startswith("http"):
                    href.append(h)
            if href:
                break
        except Exception:
            continue
    return href


_РАЗДЕЛЫ = ("contact", "kontakt", "mentions", "mentions-legales", "legal", "légal",
            "about", "propos", "a-propos", "impressum", "over-ons", "overons",
            "o-nas", "onas", "о-нас", "kontakty")


def _разделы_сайта(page, url: str, лимит: int = 3) -> list[str]:
    """Ссылки «Контакты/О нас/Mentions légales/Impressum» ВНУТРИ того же домена."""
    свой = _домен(url)
    out: list[str] = []
    try:
        loc = page.locator("a[href]")
        for i in range(min(loc.count(), 80)):
            h = (loc.nth(i).get_attribute("href") or "").strip()
            if not h or h.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            if any(k in h.lower() for k in _РАЗДЕЛЫ):
                full = urljoin(url, h)
                if _домен(full) == свой and full not in out and full != url:
                    out.append(full)
            if len(out) >= лимит:
                break
    except Exception:
        pass
    return out


def _текст_сайта(br: Browser, url: str) -> str:
    """Текст главной + страниц «Контакты/О нас/Mentions/Impressum» (там адрес)."""
    page = br.page
    куски: list[str] = []
    try:
        br.goto(url)
        page.wait_for_timeout(600)
        куски.append(page.inner_text("body"))
    except Exception:
        return ""
    for r in _разделы_сайта(page, url):
        try:
            br.goto(r)
            page.wait_for_timeout(500)
            куски.append(page.inner_text("body"))
        except Exception:
            continue
    return "\n".join(куски)


def найти_сайт(br: Browser, human: HumanGate, орг: str, адрес: str, город: str,
               индекс: str, страна: str, log=print) -> tuple[str, bool]:
    """
    Найти и подтвердить сайт фирмы. Возвращает (url, подтверждён_адресом).
    Пусто ('', False) — не нашли/пропустили.
    """
    page = br.page
    запрос = построить_запрос(орг, адрес, город, страна)
    br.goto(f"{DUCK}{quote(запрос)}")
    page.wait_for_timeout(700)
    br.check_captcha(орг)                          # DDG почти не капчит, но на всякий

    кандидаты, реестры = классифицировать(_ссылки_выдачи(page))
    адреса: list[tuple[str, str]] = [(город, индекс)]        # первый — из DNB
    log(f"  · кандидатов {len(кандидаты)}, реестров {len(реестры)}")

    очередь: list[str] = list(кандидаты) + list(реестры)     # реестры вычитаем в конце
    проверенные: set[str] = set()
    настоящие: list[str] = []           # реальные сайты фирм (не каталоги) — для человека

    while очередь:
        url = очередь.pop(0)
        d = _домен(url)
        if not d or d in проверенные:
            continue
        проверенные.add(d)

        текст = _текст_сайта(br, url)
        if not текст:
            continue

        # ── каталог/реестр → НЕ ответ, только ИСТОЧНИК (сайт-поле + адрес) ──
        if похоже_на_каталог(текст, url):
            сайт = извлечь_сайт_из_текста(текст, свой=d)
            if сайт and годится_как_ответ(сайт) and _домен(сайт) not in проверенные:
                очередь.insert(0, сайт)                 # реестр указал сайт — проверим первым
                log(f"  · каталог {d} → указал сайт: {сайт}")
            г2, и2 = адрес_из_реестра(текст)
            if г2 and (г2, и2) not in адреса:
                адреса.append((г2, и2))
                log(f"  · каталог {d} → адрес: {и2} {г2}")
            else:
                log(f"  · каталог {d} — пропускаю как ответ")
            continue

        # ── настоящий сайт-кандидат ──
        настоящие.append(url)
        if любой_адрес_совпал(текст, адреса):
            log(f"  · адрес совпал на {d}")
            return url, True
        if имя_в_домене(орг, url):
            log(f"  · имя фирмы в домене {d} (адрес на странице не нашёл)")

    # ── адрес нигде не совпал ──
    if not настоящие:
        # были одни каталоги — честно «не нашли», человека не дёргаем
        log("  · только каталоги, своего сайта не видно")
        return "", False

    # есть реальные сайты, но адрес не подтвердился → человек смотрит ПО ОДНОМУ
    for url in настоящие[:6]:
        try:
            br.goto(url)
            page.wait_for_timeout(400)
        except Exception:
            pass
        выбор = human.меню(
            "Это сайт фирмы?",
            f"«{орг}» ({город} {индекс} {страна}).\n"
            f"Открыл: {_домен(url)}. Это ИХ официальный сайт?",
            [(url, f"✔ Да, это сайт «{орг}»"),
             ("след", "→ Следующий кандидат"),
             ("нет", "✖ Ни один / нет сайта")],
            company=орг,
            # Без человека сайт НЕ подтверждаем. Замер 09.09.2026: домен,
            # который угадался и даже откликнулся, оказывается сайтом ЭТОЙ
            # фирмы лишь в трети случаев — записать чужой хуже, чем никакой.
            авто="нет")
        if выбор == url:
            return url, False
        if выбор == "нет":
            break
        # «след» → следующий кандидат
    return "", False


# ---------- оркестратор ----------

def run(excel: Path, human: HumanGate, страна: str = "", log=print,
        stop: Event | None = None, pause: Event | None = None) -> dict:
    wb = load_workbook(excel)
    if "Без сайта" not in wb.sheetnames:
        log("В файле нет листа «Без сайта» — Часть 3 нечего искать.")
        return {"нашли": 0, "всего": 0}
    ws = wb["Без сайта"]                        # Организация | Адрес | Город | Индекс | (E пометка)

    фирмы = []
    for r in ws.iter_rows(min_row=2, min_col=1, max_col=5):
        орг = str(r[0].value).strip() if r[0].value else ""
        if not орг:
            continue
        пометка = str(r[4].value or "")
        if пометка.startswith("нашли"):        # уже нашли ранее — пропускаем
            continue
        фирмы.append((r[0].row, орг, str(r[1].value or ""),
                      str(r[2].value or ""), str(r[3].value or "")))

    if not фирмы:
        log("В листе «Без сайта» нет фирм для поиска (все уже обработаны).")
        return {"нашли": 0, "всего": 0}

    вых = wb["Нашли сайт"] if "Нашли сайт" in wb.sheetnames else wb.create_sheet("Нашли сайт")
    if вых.max_row == 1 and вых["A1"].value is None:
        вых.append(["Организация", "Адрес", "Website"])
        for c in вых[1]:
            c.font = Font(bold=True)
        for col, w in zip("ABC", [44, 44, 34]):
            вых.column_dimensions[col].width = w

    log(f"Часть 3: ищу сайты для {len(фирмы)} фирм из листа «Без сайта»"
        + (f" (страна: {страна})." if страна else "."))
    нашли = 0
    with Browser(profile="websearch", human=human, log=log) as br:
        for i, (row, орг, адрес, город, индекс) in enumerate(фирмы, 1):
            if stop and stop.is_set():
                break
            подождать_паузу(pause, stop)
            log(f"[{i}/{len(фирмы)}] {орг}")
            try:
                url, подтв = найти_сайт(br, human, орг, адрес, город, индекс, страна, log)
            except SkipCompany:
                ws.cell(row=row, column=5, value="пропущено человеком")
                сохранить_excel(wb, excel, human, log)
                continue
            except AbortRun:
                log("Остановлено человеком.")
                break
            except Exception as e:
                log(f"  ✘ ошибка: {e}")
                url, подтв = "", False
            if url:
                нашли += 1
                вых.append([орг, адрес, url])
                ws.cell(row=row, column=5,
                        value=f"нашли: {url}" + ("" if подтв else " (по выбору человека)"))
                log(f"  ✔ {url}" + ("  (адрес совпал)" if подтв else "  (выбор человека)"))
            else:
                ws.cell(row=row, column=5, value="искали, не нашли")
                log("  ✘ сайт не найден")
            сохранить_excel(wb, excel, human, log)

    сохранить_excel(wb, excel, human, log)
    log(f"\nНашли сайты: {нашли} из {len(фирмы)}. Записаны в лист «Нашли сайт».")
    return {"нашли": нашли, "всего": len(фирмы)}
