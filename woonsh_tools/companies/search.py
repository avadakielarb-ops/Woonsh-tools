"""
Поиск фирм — единый движок.

Объединяет:
- X-File company_search: discover() через Gemini grounded search,
  DnB → реестр (company_directory), Telegram-бот проверки
- X-File company_gemini: grounded_request() с ротацией до 6 моделей, 180с
- X-File company_keywords: translate_keyword() через MyMemory API
- Фирмы: очередь заданий, мультигео, человек-в-цикле

Зависимости: company_directory (подпакет с гео-драйверами) копируется as-is.
"""

import asyncio
import csv
import datetime
import hashlib
import json
import re
import threading
import urllib.error
import urllib.request
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

# ---------------------------------------------------------------------------
#  Константы
# ---------------------------------------------------------------------------

BOT = "usedcompaniesarb_bot"

LANGUAGES = {
    "Australia": ("en",), "Austria": ("de",), "Belgium": ("nl", "fr", "de"),
    "Bulgaria": ("bg",), "Croatia": ("hr",), "Czech Republic": ("cs",),
    "Denmark": ("da",), "Estonia": ("et",), "Finland": ("fi", "sv"),
    "France": ("fr",), "Germany": ("de",), "Hungary": ("hu",),
    "Iceland": ("is",), "Latvia": ("lv",), "Netherlands": ("nl",),
    "Norway": ("nb",), "Poland": ("pl",), "Slovenia": ("sl",),
    "Sweden": ("sv",), "Switzerland": ("de", "fr", "it"),
    "United Kingdom": ("en",), "USA": ("en",),
}

PROVIDERS = ("DnB → реестр", "Только реестр", "Gemini + Google Search")

# ---------------------------------------------------------------------------
#  Утилиты
# ---------------------------------------------------------------------------

def now():
    return datetime.datetime.now().astimezone().isoformat()


def http_url(value):
    value = str(value or "").strip()
    u = urlparse(value)
    return value if u.scheme in ("http", "https") and u.hostname and not u.username else ""


def bot_status(text):
    text = text.casefold().replace("ё", "е")
    if any(s in text for s in ("компания уже есть", "уже добавлена", "already exists")):
        return "Уже есть"
    if any(s in text for s in ("компания добавлена", "company added")):
        return "Добавлена"
    return "Ответ не распознан"


# ---------------------------------------------------------------------------
#  Перевод ключевых слов (MyMemory API)
# ---------------------------------------------------------------------------

def country_languages(country):
    if country not in LANGUAGES:
        return ("en",)
    return LANGUAGES[country]


@lru_cache(maxsize=256)
def _translate(text, source, target):
    query = urlencode({"q": text, "langpair": source + "|" + target})
    request = urllib.request.Request(
        "https://api.mymemory.translated.net/get?" + query,
        headers={"User-Agent": "WoonshTools/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        if int(result.get("responseStatus", 0)) != 200:
            raise ValueError(str(result.get("responseDetails", "Нет перевода"))[:200])
        translated = unescape(str(result["responseData"]["translatedText"])).strip()
        if not translated or (target != "bg" and re.search("[А-Яа-яЁёІіЇїЄєҐґ]", translated)):
            raise ValueError("Сервис не перевёл ключевые слова на выбранный язык.")
        return translated
    except Exception as exc:
        raise ValueError(
            "Не удалось перевести запрос. Повторите позже или введите "
            "ключевые слова на языке страны. " + str(exc)[:200]) from exc


def translate_keyword(text, target, stop=None, source=None):
    text = text.strip()
    if not text or len(text.encode("utf-8")) > 500:
        raise ValueError("Введите ключевые слова длиной до 500 байт.")
    all_codes = {code for codes in LANGUAGES.values() for code in codes}
    if target not in all_codes:
        raise ValueError("Неизвестный язык поиска.")
    if stop is not None and stop.is_set():
        return ""
    if not re.search("[А-Яа-яЁёІіЇїЄєҐґ]", text):
        return text
    source = source or ("uk" if re.search("[ІіЇїЄєҐґ]", text) else "ru")
    return _translate(text, source, target)


# ---------------------------------------------------------------------------
#  Gemini grounded search (из company_gemini)
# ---------------------------------------------------------------------------

class SearchAPIError(RuntimeError):
    pass


def _redact(text, key):
    text = str(text).replace(key, "[скрыто]") if key else str(text)
    return re.sub(r"AIza[\w-]+", "[скрыто]", text)


def _explain_error(error, model, key):
    raw = error.read(65536).decode("utf-8", errors="replace")
    try:
        obj = json.loads(raw).get("error", {})
    except (ValueError, AttributeError):
        obj = {}
    lines = [
        f"{model}: HTTP {error.code} {obj.get('status', '')}",
        str(obj.get("message") or raw or error.reason)[:2500],
    ]
    for detail in obj.get("details", []):
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations", []):
            lines.append("Квота: " + json.dumps(violation, ensure_ascii=False))
        if detail.get("retryDelay"):
            lines.append("Google рекомендует повтор через: " + str(detail["retryDelay"]))
    if error.code == 429:
        lines.append("Лимит модели, проекта или Google Search.")
    return _redact("\n".join(lines), key)


def grounded_request(api_key, models, body, notify=None, stop=None):
    """Запрос с Google Search grounding, ротация до 6 моделей, 180с."""
    import time
    notify = notify or (lambda text: None)
    history = []
    deadline = time.monotonic() + 180

    for model in models[:6]:
        if stop is not None and stop.is_set():
            raise SearchAPIError("Поиск остановлен.\n" + "\n\n".join(history))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            history.append("Общее время поиска превысило 3 минуты.")
            break
        notify("Запрос к модели " + model + "…")
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + model + ":generateContent",
            data=json.dumps(body).encode(),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=min(45, remaining)) as response:
                data = json.loads(response.read(4_000_000))
        except urllib.error.HTTPError as exc:
            reason = _explain_error(exc, model, api_key)
            history.append(reason)
            unsupported = exc.code == 400 and any(
                w in reason.lower() for w in ("not supported", "unsupported")
            ) and any(w in reason.lower() for w in ("search", "grounding", "tool"))
            retryable = exc.code in (404, 429, 500, 502, 503, 504) or unsupported
            notify(reason + ("\nПроверяю следующую модель…" if retryable else ""))
            if not retryable:
                raise SearchAPIError("\n\n".join(history)) from None
            continue
        except (OSError, TimeoutError) as exc:
            raise SearchAPIError(
                "\n\n".join(history + [
                    _redact(f"{model}: ошибка соединения: {exc}", api_key)
                ])
            ) from None

        if stop is not None and stop.is_set():
            raise SearchAPIError("Поиск остановлен.\n" + "\n\n".join(history))
        candidate = (data.get("candidates") or [{}])[0]
        sources = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
        if not any(c.get("web", {}).get("uri") for c in sources):
            history.append(model + ": ответ без источников Google Search.")
            notify(history[-1] + " Проверяю следующую модель…")
            continue
        notify("\n\n".join(history + ["Поиск выполнен: " + model]))
        return data, model

    raise SearchAPIError(
        "Не удалось выполнить поиск на доступных моделях.\n\n"
        + "\n\n".join(history))


def discover_gemini(api_key, models, country, topic, count,
                    notify=None, stop=None):
    """Gemini + Google Search: поиск фирм через grounded request."""
    prompt = (
        f"Use Google Search to find up to {count} real active companies "
        f"in {country}, sector: {topic}. "
        "Each must have a full street address and its own official website. "
        "Exclude parked domains. Do not invent facts. Return JSON only: "
        '{"companies":[{"name":"legal name","address":"full address",'
        '"site":"https://...","source":"source URL",'
        '"registry":"official registry URL if found, otherwise empty"}]}.'
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8000},
    }
    data, model = grounded_request(api_key, models, body, notify, stop)
    candidate = (data.get("candidates") or [{}])[0]
    chunks = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
    sources = [c["web"] for c in chunks if c.get("web", {}).get("uri")]
    text = "".join(
        p.get("text", "")
        for p in candidate.get("content", {}).get("parts", []))

    # parse JSON из текста модели
    rows = []
    try:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            result = json.loads(match.group())
        else:
            result = {"companies": []}
    except (json.JSONDecodeError, ValueError):
        result = {"companies": []}

    for item in result.get("companies", [])[:count]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        address = str(item.get("address", "")).strip()
        site = http_url(item.get("site"))
        source = http_url(item.get("source"))
        if not (name and address and site and source):
            continue
        rows.append({
            "name": name, "address": address, "site": site,
            "source": source, "country": country,
            "registry": http_url(item.get("registry")),
            "website": "Не проверен", "bot": "Не проверена",
            "pdf": "Не получена", "created": now(),
            "sources": sources, "provider": "Gemini",
        })
    if not rows:
        raise ValueError("Не найдено полных записей с адресом, сайтом и источником.")
    return rows


# ---------------------------------------------------------------------------
#  Telegram-бот проверки (Telethon)
# ---------------------------------------------------------------------------

async def telegram_check(config, rows, stop, on_status=None):
    """Проверить список фирм через Used Companies бот."""
    try:
        from telethon import TelegramClient, errors
        from telethon.sessions import StringSession
    except ImportError:
        raise RuntimeError(
            'Установите Telethon: pip install "Telethon<2"')

    on_status = on_status or (lambda text: None)
    client = TelegramClient(
        StringSession(config.get("session", "")),
        config["api_id"], config["api_hash"],
        request_retries=0, connection_retries=1,
        flood_sleep_threshold=0, timeout=15,
        device_model="Woonsh Tools", app_version="0.1")
    try:
        await asyncio.wait_for(client.connect(), 30)
        if not await asyncio.wait_for(client.is_user_authorized(), 20):
            raise ValueError("Сначала войдите в Telegram.")
        bot = await asyncio.wait_for(client.get_entity(BOT), 20)
        if not getattr(bot, "bot", False):
            raise ValueError("Адрес Used Companies не является ботом.")

        checks = {}
        for row in rows:
            if stop.is_set():
                break
            key = BOT + "|" + re.sub(r"\s+", " ", row["name"]).strip().casefold()
            try:
                async with client.conversation(bot, timeout=45, exclusive=True) as conv:
                    await conv.send_message(row["name"])
                    reply = await conv.get_response()
                    status = bot_status(reply.raw_text)
                    checks[key] = {"status": status, "reply": reply.raw_text, "at": now()}
                    row["bot"] = status
                    on_status(f"{row['name']}: {status}")
            except asyncio.TimeoutError:
                row["bot"] = "Нет ответа"
                on_status(f"{row['name']}: нет ответа от бота")
                break
            await asyncio.sleep(3)
        return checks
    finally:
        await client.disconnect()


# ---------------------------------------------------------------------------
#  Статистика (из company_directory/statistics)
# ---------------------------------------------------------------------------

def summarize(rows, countries=None):
    """Сводка по странам: всего, с сайтом, PDF, бот и т.д."""
    if countries is None:
        countries = sorted(set(r.get("country", "") for r in rows))

    result = {c: [0] * 8 for c in countries}
    for row in rows:
        country = row.get("country", "")
        if country not in result:
            continue
        values = result[country]
        site = bool(row.get("site", "").strip())
        pdf = bool(row.get("pdf_path") and Path(row["pdf_path"]).is_file())
        checked = row.get("bot") in ("Уже есть", "Добавлена")
        accepted = row.get("bot") == "Добавлена"
        for index, flag in enumerate(
            (True, site, site and pdf, not site, not site and pdf,
             site and pdf and accepted, checked, not checked)):
            values[index] += int(flag)

    return [(c, *v) for c, v in result.items()]


# ---------------------------------------------------------------------------
#  Проверка сайта (DuckDuckGo → AI)
# ---------------------------------------------------------------------------

def verify_website(row, timeout=20):
    """Простая проверка доступности сайта."""
    site = row.get("site", "")
    if not site:
        row["website"] = "Нет сайта"
        return
    try:
        req = urllib.request.Request(site, headers={"User-Agent": "WoonshTools/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(2048)
        row["website"] = "Доступен; принадлежность не подтверждена"
    except Exception:
        row["website"] = "Не удалось открыть"


# ---------------------------------------------------------------------------
#  Экспорт CSV
# ---------------------------------------------------------------------------

def export_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "Название | Адрес | Сайт", "Страна",
            "Used Companies", "Выписка", "Источник"])
        for r in rows:
            writer.writerow([
                f"{r['name']} | {r['address']} | {r['site']}",
                r["country"], r["bot"], r["pdf"], r["source"],
            ])
