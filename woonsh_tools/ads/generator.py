"""
Google Ads CSV generator — merged X-File engine + ЦСВ Вайт streaming.

ThreadPoolExecutor(4) parallel campaigns, MODEL_CHAIN auto-rotation,
THINK_LADDER, temperature fallback, auto-repair (3 attempts),
policy filtering, negatives in 8 languages, DKI macro handling.
"""

import csv
import http.client
import io
import json
import os
import random
import re
import socket
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, urldefrag, urljoin, unquote

from woonsh_tools.core.gemini import GeminiClient

CSV_COLUMNS = [
    "Row Type", "Action",
    "Campaign status", "Campaign", "Campaign type", "Networks",
    "Budget", "Budget type", "Bid strategy type",
    "Language", "Location", "EU political ads",
    "Ad group status", "Ad group", "Ad group type", "Default max. CPC",
    "Keyword status", "Keyword", "Level", "Negative keyword", "Type",
    "Ad status", "Ad type",
] + [f"Headline {i}" for i in range(1, 16)] + [
    f"Description {i}" for i in range(1, 5)
] + [
    "Path 1", "Path 2", "Final URL",
    "Asset action", "Asset type", "Callout text",
    "Sitelink text", "Sitelink description 1", "Sitelink description 2",
    "Structured snippet header", "Structured snippet values",
]

MATCH_TYPES = {"broad": "Broad match", "phrase": "Phrase match",
               "exact": "Exact match"}

_NEG = {
    "en": "free|freebie|download|torrent|crack|pirated|jobs|job|careers|vacancy|vacancies|salary|hiring|resume|cv|"
          "internship|volunteer|diy|how to|tutorial|wiki|wikipedia|pdf|forum|reddit|youtube|video|meaning|definition|"
          "what is|example|template|sample|essay|homework|lyrics|quotes|images|pictures|wallpaper|for kids|game|games|"
          "movie|movies|porn|xxx|scam|complaint|complaints|lawsuit|phone number|login|sign in|news|memes",
    "ru": "бесплатно|скачать|торрент|взлом|вакансии|работа|зарплата|резюме|стажировка|своими руками|как сделать|"
          "учебник|реферат|курсовая|википедия|форум|ютуб|видео|смотреть онлайн|фото|картинки|обои|игра|игры|фильм|"
          "порно|жалоба|развод|мошенники|что такое|значение|определение|пример|шаблон|образец|вход|личный кабинет|"
          "песня|текст песни|стихи|анекдоты|сочинение|новости|мемы",
    "uk": "безкоштовно|завантажити|торрент|вакансії|робота|зарплата|резюме|стажування|власноруч|як зробити|підручник|"
          "реферат|вікіпедія|форум|відео|дивитися онлайн|фото|картинки|шпалери|гра|ігри|фільм|порно|скарга|шахраї|"
          "що таке|значення|визначення|приклад|шаблон|зразок|вхід|пісня|вірші|анекдоти|новини|меми",
    "de": "kostenlos|gratis|download|herunterladen|torrent|jobs|stellenangebote|gehalt|lebenslauf|praktikum|"
          "selber machen|anleitung|wikipedia|forum|video|bilder|spiel|film|porno|beschwerde|was ist|bedeutung|"
          "definition|beispiel|vorlage|muster|login|nachrichten",
    "es": "gratis|descargar|torrent|empleo|trabajo|salario|curriculum|prácticas|hazlo tú mismo|tutorial|wikipedia|"
          "foro|vídeo|imágenes|juego|película|porno|queja|qué es|significado|definición|ejemplo|plantilla|login|"
          "noticias",
    "fr": "gratuit|télécharger|torrent|emploi|offre d'emploi|salaire|cv|stage|faire soi-même|tutoriel|wikipédia|"
          "forum|vidéo|images|jeu|film|porno|plainte|qu'est-ce que|signification|définition|exemple|modèle|"
          "connexion|actualités",
    "pl": "za darmo|darmowe|pobierz|torrent|praca|oferty pracy|wynagrodzenie|cv|staż|zrób to sam|poradnik|"
          "wikipedia|forum|wideo|zdjęcia|gra|film|porno|skarga|co to jest|znaczenie|definicja|przykład|wzór|"
          "logowanie|wiadomości",
    "lv": "bezmaksas|lejupielādēt|darbs|vakances|alga|cv|prakse|pašam|vikipēdija|forums|video|attēli|spēle|filma|"
          "porno|sūdzība|kas ir|nozīme|piemērs|paraugs|ziņas",
}
BUILTIN_NEG = {k: v.split("|") for k, v in _NEG.items()}

SNIPPET_HEADERS = {
    "Amenities", "Brands", "Courses", "Degree programs", "Destinations",
    "Featured hotels", "Insurance coverage", "Models", "Neighborhoods",
    "Service catalog", "Shows", "Styles", "Types",
}

_SUPERLATIVES = (
    "best", "#1", "no.1", "no. 1", "number one", "number 1", "cheapest",
    "лучш", "№1", "№ 1", "номер 1", "самый", "самая", "самое", "самые",
    "найкращ", "самий", "beste", "günstigste", "mejor", "meilleur",
    "najlepsz", "najtańsz", "labākais", "lētākais",
)
_CLICK_HERE = (
    "click here", "нажмите здесь", "кликните", "натисніть тут",
    "hier klicken", "haga clic aquí", "cliquez ici", "kliknij tutaj",
    "noklikšķiniet",
)

NETWORK_ERRORS = (urllib.error.URLError, http.client.RemoteDisconnected,
                  http.client.IncompleteRead, ConnectionError,
                  TimeoutError, socket.timeout)

HISTORY_DIR = Path.home() / ".woonsh-tools" / "ads_history"
HISTORY_KEEP = 10000
JOBS = {}

_client = GeminiClient()


def set_client(client):
    global _client
    _client = client


# ---------------------------------------------------------------- policy
def policy_issue(text, brand):
    t = text.lower()
    for w in _SUPERLATIVES:
        if w in t:
            return f"неподтверждённое превосходство («{w}»)"
    if any(w in t for w in _CLICK_HERE):
        return "призыв «нажмите здесь»"
    if re.search(r"([!?.,:;\-])\1|\.\.\.|…", text):
        return "повторяющаяся пунктуация"
    if text.count("!") > 1:
        return "больше одного «!»"
    if re.search(r"[™®©★☆♥♦♠♣✓✔✅❤→►•¡¿@*_=<>|~`☀-➿\U0001F000-\U0001FFFF]", text):
        return "запрещённые символы или эмодзи"
    if re.search(r"https?://|www\.|[\w.-]+@[\w.-]+\.\w+", t):
        return "ссылка или e-mail в тексте"
    if re.search(r"\+?\d[\d\s().-]{7,}\d", text):
        return "телефон в тексте"
    for w in re.findall(r"[^\W\d_]{4,}", text):
        if w.isupper() and w.lower() not in brand:
            return f"слово заглавными («{w}»)"
    if re.match(r"^[^\w\"'«(]", text):
        return "текст начинается со знака пунктуации"
    return None


# ---------------------------------------------------------------- site fetch
class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.headings = []
        self._head_tag = None
        self.text = []
        self.links = []
        self._href = None
        self._anchor = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key in ("description", "og:description", "og:title",
                       "og:site_name", "keywords"):
                self.meta[key] = a.get("content", "")
        elif tag in ("h1", "h2", "h3"):
            self._head_tag = tag
        elif tag == "a" and a.get("href"):
            self._href, self._anchor = a["href"], []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag == self._head_tag:
            self._head_tag = None
        elif tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._anchor)))
            self._href = None

    def handle_data(self, data):
        d = data.strip()
        if not d:
            return
        if self._href:
            self._anchor.append(d)
        if self.in_title:
            self.title += d + " "
        elif not self.skip:
            if self._head_tag:
                self.headings.append(d)
            self.text.append(d)


_FILE_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|zip|rar|docx?|xlsx?|pptx?|mp[34]|"
    r"avi|css|js|xml|ico)$", re.I)
_PAGE_KEYS = (
    "about", "service", "solution", "product", "catalog", "shop", "store",
    "pricing", "price", "company", "o-nas", "onas", "uslug", "produk",
    "katalog", "cenn", "tseny", "leistung", "dienst", "preis", "servicio",
    "producto", "precio", "nosotros", "propos", "produit", "tarif", "oferta",
    "firm", "pakalpoj", "par-mums",
    "о нас", "услуг", "продук", "каталог", "цен", "магазин",
    "про нас", "послуг", "продукц", "ціни", "контакт", "contact",
)


def _host(u):
    return urlparse(u).netloc.lower().replace("www.", "")


def _get(url, limit=1_500_000, timeout=20):
    for attempt in range(2):
        try:
            return _get_once(url, limit, timeout)
        except urllib.error.HTTPError:
            raise
        except NETWORK_ERRORS:
            if attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(
                "Не удалось прочитать сайт: соединение оборвалось. "
                "Повторите позже либо заполните описание бизнеса.")


def _get_once(url, limit=1_500_000, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = urldefrag(r.geturl())[0]
        raw = r.read(limit)
        charset = r.headers.get_content_charset() or "utf-8"
    return final, raw.decode(charset, errors="replace")


def _rank_urls(cands, base):
    seen, scored = {base.rstrip("/")}, []
    for u, anchor in cands:
        u = urldefrag(u)[0]
        p = urlparse(u)
        if (p.scheme not in ("http", "https") or _host(u) != _host(base)
                or _FILE_EXT.search(p.path) or u.rstrip("/") in seen):
            continue
        seen.add(u.rstrip("/"))
        key = (unquote(p.path) + " " + anchor).lower()
        scored.append((sum(k in key for k in _PAGE_KEYS), u))
    scored.sort(key=lambda x: -x[0])
    return scored


def fetch_site(url, extra_pages=0):
    final_url, html = _get(url)
    p = _TextExtractor()
    p.feed(html)
    lang = re.search(r"<html[^>]*\blang=[\"']?([a-zA-Z-]+)", html)
    scored = _rank_urls(
        [(urljoin(final_url, h), a) for h, a in p.links], final_url)
    main_text = " ".join(p.text)[:6000]

    if extra_pages and (len(main_text) < 800 or not scored
                        or scored[0][0] == 0):
        try:
            parsed = urlparse(final_url)
            _, xml = _get(
                f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
                limit=400_000, timeout=10)
            scored += _rank_urls(
                [(m, "") for m in re.findall(
                    r"<loc>\s*(.*?)\s*</loc>", xml)[:300]],
                final_url)
            scored.sort(key=lambda x: -x[0])
        except Exception:
            pass

    chosen = ([u for s, u in scored if s > 0][:extra_pages]
              or [u for _, u in scored][:extra_pages])

    def load(u):
        try:
            fu, h = _get(u, limit=600_000, timeout=12)
            e = _TextExtractor()
            e.feed(h)
            return {"url": fu, "title": e.title.strip(),
                    "text": " ".join(e.text)[:2000]}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        extra = [x for x in ex.map(load, chosen) if x and x["text"]]

    return {
        "url": url, "final_url": final_url,
        "title": p.title.strip(), "meta": p.meta,
        "headings": p.headings[:40], "text": main_text,
        "html_lang": lang.group(1) if lang else "",
        "extra": extra,
        "links": ([final_url] + [e["url"] for e in extra]
                  + [u for _, u in scored if u not in chosen][:12]),
    }


# ---------------------------------------------------------------- text utils
def clean_keyword(k):
    k = re.sub(r"[!@%,*()\[\]{}<>=+?;:\"""^~|\\/_]", " ", str(k)).lower()
    k = re.sub(r"\s+", " ", k).strip(" .-'")
    return k if k and len(k) <= 80 and len(k.split()) <= 10 else ""


def clean_text(t, limit, no_excl=False):
    t = re.sub(r"\s+", " ", str(t)).strip()
    if no_excl:
        t = t.replace("!", "").strip()
    return t if t and len(t) <= limit else ""


def plain(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']|_", " ", str(t or ""))).strip(" '")


def clean_path(p):
    p = re.sub(r"[^\w-]", "", str(p or ""), flags=re.U)
    return p[:15]


def sentence_case(h, brand, lang):
    words = h.split()
    long_words = [w for w in words if len(w) > 3 and w[0].isalpha()]
    caps = [w for w in long_words if w[0].isupper() and not w.isupper()]
    if (lang.startswith("de") or len(long_words) < 3
            or len(caps) < 0.7 * len(long_words)):
        return h
    out = [w if (w.isupper() and len(w) > 1)
           or w.lower().strip(".,") in brand else w.lower() for w in words]
    out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def uniq(items):
    seen, out = set(), []
    for i in items:
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


def money(x):
    return f"{x:.2f}"


def policy_filter(texts, need, brand, enabled, warnings, label, kind):
    if not enabled:
        return texts
    good, bad = [], []
    for t in texts:
        r = policy_issue(t, brand)
        (bad if r else good).append((t, r))
    for t, r in bad:
        warnings.append(f"{label}: убран {kind} «{t}» — {r}")
    return [t for t, _ in good]


# ---------------------------------------------------------------- prompts
def site_brief(site, about=""):
    parts = []
    if about:
        parts.append(
            f"ADVERTISER'S OWN DESCRIPTION (highest priority): {about}")
    parts.append(
        f"URL: {site['final_url']}\nTitle: {site['title']}\n"
        f"Meta: {json.dumps(site['meta'], ensure_ascii=False)}\n"
        f"Headings: {' | '.join(site['headings'])}\n"
        f"Page text: {site['text']}")
    for e in site.get("extra", []):
        parts.append(f"Additional page {e['url']} — {e['title']}\n{e['text']}")
    return "\n\n".join(parts)


def plan_site(api_key, site, s):
    prompt = (
        "You are a Google Ads Search specialist. Analyse this website "
        "and plan a Search campaign structure.\n\n"
        f"{site_brief(site, s['about'])}\n\n"
        'Return ONLY JSON:\n'
        '{"topic": "<2-8 words>",\n'
        ' "summary": "<1-2 sentences>",\n'
        ' "language_code": "<e.g. en, ru, de>",\n'
        ' "campaigns": [{"theme": "<short>", "ad_groups": ["<name>", ...]}]}\n\n'
        f"Exactly {s['campaigns']} campaigns, each with exactly "
        f"{s['ad_groups']} ad groups.\n"
        "Themes/ad groups must be distinct, relevant, in the site's language, "
        "max 40 chars, no special characters.\n"
        + (f"Extra instructions: {s['notes']}" if s.get("notes") else "")
    )
    return _client.generate_json(prompt, api_key=api_key, max_tokens=3000)


def write_campaign(api_key, site, plan, camp, s, lang):
    neg_part = neg_json = ext_part = ext_json = ""
    if s["neg"]["ai"]:
        neg_part = (
            f"\nAlso write exactly {s['neg']['ai']} negative keywords: "
            "searches that would NOT buy. Single words or 2-3 word phrases, "
            "lowercase, in the site's language.")
        neg_json = '"negative_keywords": ["..."], '
    if s["ext"]["sitelinks"]:
        ext_part += (
            f"\nAlso write {s['ext']['sitelinks'] + 2} sitelinks: "
            "text <= 25 chars, d1 <= 35 chars, d2 <= 35 chars, "
            "url from: " + json.dumps(site["links"], ensure_ascii=False)
            + "; every sitelink must use a DIFFERENT url.")
        ext_json += '"sitelinks": [{"text":"","d1":"","d2":"","url":""}], '
    if s["ext"]["callouts"]:
        ext_part += (
            f"\nAlso write {s['ext']['callouts'] + 6} callouts: "
            "STRICTLY <= 25 characters each, all different, real benefits.")
        ext_json += '"callouts": ["..."], '
    if s["ext"].get("snippets"):
        ext_part += (
            "\nWrite one structured snippet with an English Google header "
            "(Types, Brands or Service catalog) and 3-6 distinct values "
            "<=25 chars.")
        ext_json += '"snippets": [{"type":"Types","values":["..."]}], '
    if ext_part:
        ext_part += ("\nSitelink and callout texts: letters, digits and "
                     "spaces only. No superlatives.")

    prompt = (
        f'You are a Google Ads Search specialist writing in "{lang}".\n\n'
        f"Website:\n{site_brief(site, s['about'])}\n\n"
        f"Site topic: {plan.get('topic')}\n"
        f"Campaign theme: {camp['theme']}\n"
        f"Ad groups: {json.dumps(camp['ad_groups'], ensure_ascii=False)}\n\n"
        f"For EACH ad group write:\n"
        f"- exactly {s['keywords']} distinct keywords (2-4 words, "
        "commercial intent, lowercase),\n"
        f"- exactly {s['ads']} responsive search ad(s); every ad has "
        f"exactly {min(15, s['headlines'] + 3)} headlines and "
        f"{s['descriptions'] + 2} descriptions,\n"
        "- path1 and path2 (each max 15 chars).\n"
        "STRICT LIMITS: headline <= 30 chars, description <= 90 chars, "
        "no exclamation marks in headlines, no phone numbers, no false "
        "claims. Headlines within one ad must differ.\n"
        "GOOGLE ADS POLICY: no superlatives, no ALL-CAPS words, no "
        "repeated punctuation, no symbols/emoji, no \"click here\".\n"
        "CASE: write like normal sentences."
        f"{neg_part}{ext_part}\n"
        + (f"Extra instructions: {s['notes']}\n" if s.get("notes") else "")
        + f"\nReturn ONLY JSON:\n{{{neg_json}{ext_json}"
        '"ad_groups": [{"name":"<same>","keywords":["..."],'
        '"ads":[{"headlines":["..."],"descriptions":["..."],'
        '"path1":"","path2":""}]}]}'
    )
    return _client.generate_json(prompt, api_key=api_key, max_tokens=16000)


# ---------------------------------------------------------------- rows
def negatives_for(s, lang, ai_list, keywords, warnings, label):
    base = lang[:2].lower()
    words = ((BUILTIN_NEG.get(base, BUILTIN_NEG["en"])
              if s["neg"]["builtin"] else [])
             + s["neg"]["custom"] + ai_list)
    words = uniq([clean_keyword(w) for w in words])
    kw_tokens = [set(k.split()) for k in keywords]
    kept = [w for w in words
            if not any(set(w.split()) <= t for t in kw_tokens)]
    if len(kept) < len(words):
        warnings.append(
            f"{label}: убрано минус-слов, совпадающих с ключами: "
            f"{len(words) - len(kept)}")
    return kept


def campaign_rows(s, st, camp, res, budget, warnings):
    host, url, lang = st["host"], st["final_url"], st["lang"]
    brand = set(st["brand"])
    name = camp["name"]
    child = "Enabled"
    rows = [{
        "Row Type": "Campaign", "Action": "Add",
        "Campaign": name, "Campaign type": "Search",
        "Campaign status": s["status"],
        "Budget": money(budget), "Budget type": "Daily",
        "Bid strategy type": "Manual CPC",
        "Networks": "Google search",
        "Language": lang, "Location": "; ".join(s["locations"]),
        "EU political ads": "No",
    }]
    stats = {"ad_groups": 0, "keywords": 0, "ads": 0,
             "negatives": 0, "sitelinks": 0, "callouts": 0}
    all_kws, first_group = [], None

    for g in res.get("ad_groups", [])[:s["ad_groups"]]:
        gname = clean_text(g.get("name"), 60)
        if not gname:
            continue
        rows.append({
            "Row Type": "Ad group", "Action": "Add",
            "Campaign": name, "Ad group": gname,
            "Ad group status": child, "Ad group type": "Standard",
            "Default max. CPC": money(s["max_cpc"]),
        })
        stats["ad_groups"] += 1
        first_group = first_group or gname

        kws = uniq([clean_keyword(k)
                     for k in g.get("keywords", [])])[:s["keywords"]]
        if len(kws) < s["keywords"]:
            warnings.append(
                f"{host} / {gname}: ключей {len(kws)} из {s['keywords']}")
        all_kws += kws
        for kw in kws:
            for m in s["match_types"]:
                rows.append({
                    "Row Type": "Keyword", "Action": "Add",
                    "Campaign": name, "Ad group": gname,
                    "Keyword": kw, "Type": MATCH_TYPES[m],
                    "Keyword status": child,
                })
            stats["keywords"] += 1

        for ad in g.get("ads", [])[:s["ads"]]:
            hs = uniq([sentence_case(clean_text(h, 30, True), brand, lang)
                       for h in ad.get("headlines", [])])
            hs = policy_filter(
                [h for h in hs if h], 3, brand, s["policy"],
                warnings, f"{host} / {gname}", "заголовок")
            hs = hs[:s["headlines"]]
            ds = uniq([clean_text(d, 90)
                       for d in ad.get("descriptions", [])])
            ds = policy_filter(
                [d for d in ds if d], 2, brand, s["policy"],
                warnings, f"{host} / {gname}", "текст")
            ds = ds[:s["descriptions"]]
            if len(hs) < 3 or len(ds) < 2:
                warnings.append(
                    f"{host} / {gname}: объявление пропущено "
                    f"(заголовков {len(hs)}, описаний {len(ds)})")
                continue
            row = {
                "Row Type": "Ad", "Action": "Add",
                "Campaign": name, "Ad group": gname,
                "Ad status": child, "Ad type": "Responsive search ad",
                "Final URL": url,
                "Path 1": clean_path(ad.get("path1")),
                "Path 2": clean_path(ad.get("path2")),
            }
            for i, h in enumerate(hs, 1):
                row[f"Headline {i}"] = h
            for i, d in enumerate(ds, 1):
                row[f"Description {i}"] = d
            rows.append(row)
            stats["ads"] += 1

    if s["neg"]["on"]:
        for w in negatives_for(s, lang, res.get("negative_keywords", []),
                               all_kws, warnings, f"{host} / {name}"):
            rows.append({
                "Row Type": "Negative keyword", "Action": "Add",
                "Campaign": name, "Level": "Campaign",
                "Negative keyword": w,
                "Type": MATCH_TYPES[s["neg"]["match"]],
                "Keyword status": "Enabled",
            })
            stats["negatives"] += 1

    ext = {"sitelinks": [], "callouts": []}
    if s["ext"]["sitelinks"] or s["ext"]["callouts"]:
        allowed = set(st["site"]["links"])
        used_urls = set()
        for sl in (res.get("sitelinks", [])
                   if s["ext"]["sitelinks"] else []):
            if len(ext["sitelinks"]) >= s["ext"]["sitelinks"]:
                break
            text, d1, d2 = (
                clean_text(plain(sl.get(k)), n)
                for k, n in (("text", 25), ("d1", 35), ("d2", 35)))
            link = sl.get("url") if sl.get("url") in allowed else None
            if not (text and d1 and d2 and link) or link in used_urls:
                continue
            if s["policy"] and any(
                    policy_issue(x, brand) for x in (text, d1, d2)):
                continue
            used_urls.add(link)
            ext["sitelinks"].append({
                "Row Type": "Sitelink", "Action": "Add",
                "Asset action": "Create new", "Level": "Campaign",
                "Campaign": name, "Final URL": link,
                "Sitelink text": text,
                "Sitelink description 1": d1,
                "Sitelink description 2": d2,
            })
        callouts = (uniq([clean_text(plain(c), 25)
                          for c in res.get("callouts", [])])
                    if s["ext"]["callouts"] else [])
        for c in callouts:
            if len(ext["callouts"]) >= s["ext"]["callouts"] or not first_group:
                break
            if not (s["policy"] and policy_issue(c, brand)):
                ext["callouts"].append({
                    "Action": "Add", "Campaign": name,
                    "Ad group": first_group,
                    "Asset type": "Callout", "Callout text": c,
                })
        stats["sitelinks"] = len(ext["sitelinks"])
        stats["callouts"] = len(ext["callouts"])
        rows += ext["callouts"] + ext["sitelinks"]

    if s["ext"].get("snippets"):
        for sn in res.get("snippets", [])[:2]:
            values = uniq([clean_text(v, 25) for v in sn.get("values", [])])
            values = [v for v in values if v]
            if sn.get("type") in SNIPPET_HEADERS and len(values) >= 3:
                rows.append({
                    "Action": "Add", "Campaign": name,
                    "Level": "Campaign",
                    "Asset type": "Structured snippet",
                    "Structured snippet header": sn["type"],
                    "Structured snippet values": ";".join(values[:10]),
                })

    return rows, stats


# ---------------------------------------------------------------- build
class Progress:
    def __init__(self):
        self.lock = threading.Lock()
        self.total, self.done, self.msg, self.log = 1, 0, "Запуск…", []
        self.result = self.error = self.state = self.hist_path = None
        self.finished = False
        self.t0 = time.time()

    def say(self, msg):
        with self.lock:
            self.msg = msg
            self.log.append(msg)

    def step(self, msg=None, n=1):
        with self.lock:
            self.done = min(self.total, self.done + n)
        if msg:
            self.say(msg)

    def snapshot(self):
        with self.lock:
            elapsed = time.time() - self.t0
            eta = (elapsed / self.done * (self.total - self.done)
                   if self.done and not self.finished else None)
            return {
                "done": self.done, "total": self.total,
                "msg": self.msg, "log": self.log[-30:],
                "elapsed": int(elapsed),
                "eta": None if eta is None else int(eta),
                "finished": self.finished, "error": self.error,
            }


def build_site(api_key, url, s, prog):
    host = urlparse(url).netloc.replace("www.", "")
    prog.say(f"[{host}] Загружаю сайт…")
    pre_warn = []
    try:
        site = fetch_site(url, s["pages"])
    except Exception as e:
        if not s["about"]:
            if (isinstance(e, urllib.error.HTTPError)
                    and e.code in (401, 403, 429, 503)):
                raise RuntimeError(
                    f"Сайт закрыт (HTTP {e.code}). Заполните «О чём реклама».")
            raise
        site = {"url": url, "final_url": url, "title": "", "meta": {},
                "headings": [], "text": "", "html_lang": "",
                "extra": [], "links": [url]}
        pre_warn.append(
            f"{host}: сайт не открылся, использовано описание бизнеса")

    prog.step(f"[{host}] Сайт прочитан. Gemini планирует кампании…")
    if (len(site["text"]) + sum(len(e["text"]) for e in site["extra"]) < 500
            and not s["about"]):
        pre_warn.append(f"{host}: мало текста на сайте — дополните описание")

    plan = plan_site(api_key, site, s)
    lang = (s.get("language") or plan.get("language_code")
            or site["html_lang"][:2] or "en")
    camps_plan = plan.get("campaigns", [])[:s["campaigns"]]
    if not camps_plan:
        raise ValueError("Gemini вернул пустой план. Повторите генерацию.")

    prog.step(
        f"[{host}] Тематика: {plan.get('topic')}. "
        f"Пишу объявления ({len(camps_plan)} кампаний)…")
    prog.step(n=s["campaigns"] - len(camps_plan))

    corpus = " ".join([site["text"]] + [e["text"] for e in site["extra"]])
    proper = re.findall(
        r"(?<=[a-zа-яёіїє,]\s)([A-ZА-ЯЁІЇЄ][\w-]{2,})", corpus)
    brand_words = {
        t.lower() for t in re.split(
            r"\W+", site["meta"].get("og:site_name", "")
            + " " + host.split(".")[0]) if t}
    st = {
        "url": url, "host": host, "site": site, "plan": plan,
        "lang": lang, "final_url": site["final_url"],
        "brand": sorted(brand_words | {w.lower() for w in proper}),
        "warnings": pre_warn, "camps": [],
    }

    finished = [0]

    def work(c):
        res = write_campaign(api_key, site, plan, c, s, lang)
        for attempt in range(3):
            probe = {"name": c["theme"]}
            probe_rows, _ = campaign_rows(s, st, probe, res,
                                          s["budget_fixed"], [])
            errors, _ = check(probe_rows, s, policy_issue)
            if not errors:
                break
            prog.say(f"[{host}] Исправляю ошибки, попытка {attempt + 1}/3")
            prompt = (
                "Correct this Google Ads draft JSON. Return only corrected "
                "JSON. Settings: " + json.dumps(s, ensure_ascii=False)
                + "\nWebsite: " + site_brief(site, s["about"])
                + "\nDraft: " + json.dumps(res, ensure_ascii=False)
                + "\nErrors: " + json.dumps(errors, ensure_ascii=False))
            res = _client.generate_json(
                prompt, api_key=api_key, max_tokens=16000)
        finished[0] += 1
        prog.step(
            f"[{host}] Готово кампаний: {finished[0]}/{len(camps_plan)}")
        return res

    with ThreadPoolExecutor(max_workers=min(4, len(camps_plan))) as ex:
        results = list(ex.map(work, camps_plan))

    for c, res in zip(camps_plan, results):
        path = urlparse(url).path.strip("/")
        label = f"{host}/{path}"[:40] if path else host
        camp = {
            "theme": c["theme"], "adnames": c["ad_groups"],
            "name": f"{label} | {c['theme']}"[:80],
            "budget": (s["budget_fixed"] if s["budget_mode"] == "fixed"
                       else random.uniform(s["budget_min"], s["budget_max"])),
        }
        camp["warnings"] = []
        camp["rows"], camp["stats"] = campaign_rows(
            s, st, camp, res, camp["budget"], camp["warnings"])
        st["camps"].append(camp)
    return st


def _csv_text(columns, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def assemble(state):
    rows, sites, warnings = [], [], []
    for st in state["sites"]:
        if st.get("error"):
            sites.append({"url": st["url"], "error": st["error"]})
            continue
        warnings += st["warnings"]
        infos, site_rows = [], []
        tot = {"campaigns": 0, "ad_groups": 0, "keywords": 0, "ads": 0,
               "negatives": 0, "sitelinks": 0, "callouts": 0}
        for i, c in enumerate(st["camps"]):
            site_rows += c["rows"]
            rows += c["rows"]
            warnings += c["warnings"]
            tot["campaigns"] += 1
            for k in tot:
                if k != "campaigns":
                    tot[k] += c["stats"].get(k, 0)
            infos.append({"idx": i, "name": c["name"],
                          "theme": c["theme"], **c["stats"]})
        sites.append({
            "url": st["url"], "topic": st["plan"].get("topic"),
            "summary": st["plan"].get("summary"),
            "language": st["lang"], "stats": tot,
            "campaigns": infos, "pages": len(st["site"]["extra"]),
            "host": st["host"],
            "csv": _csv_text(CSV_COLUMNS, site_rows),
        })
    errors, checks = check(rows, state["s"], policy_issue)
    for st in state["sites"]:
        if st.get("error"):
            errors.append("Не удалось создать кампанию: " + st["url"])
    return {
        "manual_approved": manually_approved(state),
        "errors": errors, "sites": sites,
        "warnings": warnings + checks,
        "columns": CSV_COLUMNS, "rows": rows,
        "csv": _csv_text(CSV_COLUMNS, rows),
    }


def sites_zip(result):
    buf, used = io.BytesIO(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for s in result["sites"]:
            if s.get("error"):
                continue
            name = f"google_ads_{re.sub(r'[^A-Za-z0-9.-]', '_', s['host'])}"
            base, n = name, 2
            while name in used:
                name, n = f"{base}_{n}", n + 1
            used.add(name)
            z.writestr(name + ".csv", "﻿" + s["csv"])
    return buf.getvalue()


# ---------------------------------------------------------------- settings
def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def parse_settings(p):
    s = {
        "campaigns": _clamp(p["campaigns"], 1, 10, 1),
        "ad_groups": _clamp(p["ad_groups"], 1, 10, 1),
        "keywords": _clamp(p["keywords"], 1, 50, 10),
        "ads": _clamp(p["ads"], 1, 3, 1),
        "headlines": _clamp(p["headlines"], 3, 15, 10),
        "descriptions": _clamp(p["descriptions"], 2, 4, 4),
        "max_cpc": 0.01,
        "budget_mode": p["budget_mode"],
        "budget_fixed": float(p["budget_fixed"]),
        "budget_min": float(p["budget_min"]),
        "budget_max": float(p["budget_max"]),
        "status": "Enabled" if p["status"] == "Enabled" else "Paused",
        "match_types": ([m for m in p["match_types"] if m in MATCH_TYPES]
                        or ["phrase"]),
        "language": (p.get("language") or "").strip(),
        "notes": (p.get("notes") or "").strip()[:500],
        "about": (p.get("about") or "").strip()[:3000],
        "pages": _clamp(p.get("pages", 3), 0, 6, 3),
        "policy": bool(p.get("policy", True)),
        "locations": [x.strip()
                      for x in p.get("locations", []) if x.strip()][:30],
        "neg": {
            "on": bool(p.get("neg_on")),
            "builtin": bool(p.get("neg_builtin")),
            "ai": (_clamp(p.get("neg_ai"), 0, 100, 0)
                   if p.get("neg_on") else 0),
            "match": (p.get("neg_match")
                      if p.get("neg_match") in MATCH_TYPES else "phrase"),
            "custom": [clean_keyword(x) for x in re.split(
                r"[\n,;]", p.get("neg_custom") or "") if clean_keyword(x)],
        },
        "ext": {
            "sitelinks": (_clamp(p.get("ext_sitelinks"), 2, 6, 6)
                          if p.get("ext_sitelinks_on") else 0),
            "snippets": bool(p.get("ext_snippets_on", False)),
            "callouts": (_clamp(p.get("ext_callouts"), 2, 10, 8)
                         if p.get("ext_callouts_on") else 0),
        },
    }
    if s["budget_min"] > s["budget_max"]:
        s["budget_min"], s["budget_max"] = s["budget_max"], s["budget_min"]
    return s


# ---------------------------------------------------------------- generate
def generate(payload, prog=None):
    prog = prog or Progress()
    api_key = payload.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Нужен Gemini API key")
    s = parse_settings(payload["settings"])
    urls = []
    for u in payload["urls"]:
        u = u.strip()
        if u:
            urls.append(u if re.match(r"https?://", u) else "https://" + u)
    if not urls:
        raise ValueError("Укажите хотя бы одну ссылку")

    per_site = 2 + s["campaigns"]
    prog.total = len(urls) * per_site + 1
    state = {"api_key": api_key, "s": s, "sites": []}
    for i, u in enumerate(urls, 1):
        try:
            state["sites"].append(build_site(api_key, u, s, prog))
        except Exception as e:
            state["sites"].append({"url": u, "error": str(e)})
            prog.say(f"Ошибка на {u}: {str(e)[:120]}")
        prog.step(n=max(0, i * per_site - prog.done))
    prog.say("Собираю CSV…")
    prog.step()
    prog.state = state
    return assemble(state)


def regenerate(job_id, site_idx, camp_idx, api_key=None):
    prog = JOBS.get(job_id)
    if not prog or not prog.state:
        raise ValueError("Сессия устарела — запустите генерацию заново")
    state = prog.state
    key = api_key or state.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("Для перегенерации нужен Gemini API key")
    st = state["sites"][site_idx]
    camp = st["camps"][camp_idx]
    res = write_campaign(
        key, st["site"], st["plan"],
        {"theme": camp["theme"], "ad_groups": camp["adnames"]},
        state["s"], st["lang"])
    camp["warnings"] = []
    camp["rows"], camp["stats"] = campaign_rows(
        state["s"], st, camp, res, camp["budget"], camp["warnings"])
    prog.result = assemble(state)
    save_history(job_id, prog, [x["url"] for x in state["sites"]])
    return prog.result


# ---------------------------------------------------------------- history
def save_history(job_id, prog, urls):
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        if not prog.hist_path:
            prog.hist_path = (
                HISTORY_DIR
                / f"{time.strftime('%Y%m%d-%H%M%S')}_{job_id}.json")
        state = {k: v for k, v in prog.state.items() if k != "api_key"}
        data = {"profile": getattr(prog, "profile", {}),
                "id": job_id, "ts": int(time.time()),
                "urls": urls, "state": state}
        tmp = Path(str(prog.hist_path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(prog.hist_path)
        for old in sorted(HISTORY_DIR.glob("*.json"))[:-HISTORY_KEEP]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def _history_files():
    return (sorted(HISTORY_DIR.glob("*.json"), reverse=True)
            if HISTORY_DIR.exists() else [])


def history_list():
    out = []
    for f in _history_files():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            sites = [x for x in d["state"]["sites"] if not x.get("error")]
            result = assemble(d["state"])
            out.append({
                "profile": d.get("profile", {}),
                "id": d["id"], "ts": d["ts"], "urls": d["urls"],
                "campaigns": sum(len(x["camps"]) for x in sites),
                "rows": sum(len(c["rows"]) for x in sites for c in x["camps"]),
                "errors": result.get("errors", []),
                "manual_approved": result.get("manual_approved", False),
                "topics": [x["plan"].get("topic") for x in sites],
            })
        except Exception:
            continue
    return out


def history_load(hid):
    for f in _history_files():
        if f"_{hid}.json" in f.name:
            d = json.loads(f.read_text(encoding="utf-8"))
            state = d["state"]
            prog = Progress()
            prog.profile = d.get("profile", {})
            prog.state, prog.hist_path, prog.finished = state, f, True
            prog.result = assemble(state)
            JOBS[hid] = prog
            return {"id": hid, "result": prog.result, "urls": d["urls"]}
    raise ValueError("Запись истории не найдена")


def history_delete(hid):
    for f in _history_files():
        if f"_{hid}.json" in f.name:
            f.unlink(missing_ok=True)
    JOBS.pop(hid, None)
    return {"ok": True}
