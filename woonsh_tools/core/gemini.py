"""
Unified Gemini client — merged from ЦСВ Вайт MODEL_CHAIN + X-File THINK_LADDER
+ woonsh key rotation + Retry-After handling.

Thread-safe. One instance per app; modules call client.generate_json(...).
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

MODEL_CHAIN = (
    "gemini-3.8-flash", "gemini-3.6-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
)
FALLBACK_MODELS = list(MODEL_CHAIN)

RETRY_CODES = {429, 500, 502, 503, 504}
API_TRIES = 5
API_WAITS = (10, 30, 60, 90)

THINK_LADDER = [{"thinkingBudget": 0}, {"thinkingLevel": "minimal"}, None]


class RateLimited(RuntimeError):
    def __init__(self, msg, daily=False, wait=60):
        super().__init__(msg)
        self.daily = daily
        self.wait = wait


class ModelMissing(RuntimeError):
    pass


def _retry_delay(err_body, headers, attempt):
    try:
        ra = (headers or {}).get("Retry-After")
        if ra:
            return max(5, min(120, int(float(ra))))
    except Exception:
        pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', err_body or "")
    if m:
        return max(5, min(120, int(float(m.group(1))) + 1))
    return API_WAITS[min(attempt - 1, len(API_WAITS) - 1)]


def _version_key(name):
    m = re.search(r"(\d+(?:\.\d+)?)", name)
    v = float(m.group(1)) if m else 0.0
    return (v, "lite" not in name, "preview" not in name and "exp" not in name)


class GeminiClient:
    """Thread-safe Gemini API client with model chain and key rotation."""

    def __init__(self, keys=None, models=None):
        self._keys = [k for k in (keys or []) if k]
        self._models = models or list(MODEL_CHAIN)
        self._lock = threading.Lock()
        self._chain = None
        self._chain_key = ""
        self._cool = {}
        self._model_cache = {"t": 0.0, "names": []}
        self._good_model = None
        self._think_ok = {}

    def set_key(self, key):
        with self._lock:
            if key and key not in self._keys:
                self._keys.insert(0, key)
            elif key and key in self._keys:
                self._keys.remove(key)
                self._keys.insert(0, key)
            self._chain = None

    @property
    def api_key(self):
        return self._keys[0] if self._keys else ""

    def available(self):
        return bool(self._keys)

    def list_models(self, api_key=None):
        key = api_key or self.api_key
        if not key:
            return FALLBACK_MODELS
        if self._model_cache["names"] and time.time() - self._model_cache["t"] < 3600:
            return self._model_cache["names"]
        names = []
        try:
            req = urllib.request.Request(
                f"{API_ROOT}/models?pageSize=200",
                headers={"x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=20) as r:
                found = []
                for m in json.loads(r.read()).get("models", []):
                    name = m["name"].split("/")[-1]
                    mm = re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash(-lite)?", name)
                    if mm and "generateContent" in m.get("supportedGenerationMethods", []):
                        found.append((
                            tuple(int(x) for x in mm.group(1).split(".")),
                            bool(mm.group(2)), name))
            found.sort(key=lambda f: f[0], reverse=True)
            found.sort(key=lambda f: not f[1])
            names = [f[2] for f in found]
        except Exception:
            pass
        self._model_cache.update(t=time.time(), names=names)
        return names or FALLBACK_MODELS

    def _auto_chain(self, api_key):
        with self._lock:
            if self._chain is not None and self._chain_key == api_key:
                return self._chain
        try:
            have = set(self.list_models(api_key))
        except Exception:
            have = set()
        chain = [m for m in MODEL_CHAIN if m in have] if have else list(MODEL_CHAIN)
        if not chain:
            flash = [m for m in have if "flash" in m and not any(
                w in m for w in ("image", "tts", "audio", "embedding", "live"))]
            chain = sorted(flash, key=_version_key, reverse=True)[:6]
        with self._lock:
            self._chain = chain or list(MODEL_CHAIN)
            self._chain_key = api_key
            self._cool = {}
            return self._chain

    def _request(self, url, payload=None, api_key="", timeout=120,
                 on_wait=None, retry_429=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        last = ""
        for attempt in range(1, API_TRIES + 1):
            req = urllib.request.Request(url, data=data,
                                         method="POST" if data else "GET")
            req.add_header("x-goog-api-key", api_key)
            if data:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                try:
                    msg = json.loads(body)["error"]["message"]
                except Exception:
                    msg = body[:400]
                if e.code in (401, 403):
                    raise RuntimeError(
                        f"Gemini API {e.code}: ключ не подходит. {msg}")
                if e.code == 404:
                    raise ModelMissing(
                        f"Gemini API 404: модель недоступна. {msg}")
                if e.code == 429 and not retry_429:
                    raise RateLimited(
                        f"Gemini API 429: {msg}",
                        daily="PerDay" in body,
                        wait=_retry_delay(body, e.headers, 1))
                if e.code not in RETRY_CODES:
                    raise RuntimeError(f"Gemini API {e.code}: {msg}")
                why = "лимит Google" if e.code == 429 else f"сервер {e.code}"
                last = f"Gemini API {e.code}: {msg}"
                wait = _retry_delay(body, e.headers, attempt)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                reason = getattr(e, "reason", e)
                why = "нет связи"
                last = f"Нет связи с Gemini API: {reason}"
                wait = API_WAITS[min(attempt - 1, len(API_WAITS) - 1)]
            if attempt == API_TRIES:
                break
            if on_wait:
                on_wait(f"жду {wait}с · {attempt + 1}/{API_TRIES}",
                        f"{why}: жду {wait} с, попытка {attempt + 1}/{API_TRIES}.")
            time.sleep(wait)
        raise RuntimeError(
            f"{last}\n\nПовторено {API_TRIES} раз — не помогло.")

    def _next_daily_reset(self):
        now = time.time()
        reset = (now // 86400) * 86400 + 8 * 3600
        return reset if reset > now else reset + 86400

    def _call_auto(self, api_key, payload, on_wait=None):
        chain = self._auto_chain(api_key)
        while True:
            now = time.time()
            with self._lock:
                ready = [m for m in chain if self._cool.get(m, 0) <= now]
                soonest = min(
                    (self._cool.get(m, now) for m in chain), default=now)
            if not chain:
                raise RuntimeError("Ни одна модель из цепочки недоступна.")
            if not ready:
                wait = int(soonest - now) + 1
                if wait > 180:
                    raise RuntimeError(
                        "Дневные лимиты исчерпаны на всех моделях: "
                        + ", ".join(chain) + ".")
                if on_wait:
                    on_wait(f"жду {wait}с · лимиты",
                            f"Лимиты исчерпаны — жду {wait} с.")
                time.sleep(wait)
                continue
            m = ready[0]
            try:
                url = f"{API_ROOT}/models/{m}:generateContent"
                return self._request(url, payload, api_key,
                                     on_wait=on_wait, retry_429=False), m
            except RateLimited as e:
                until = (self._next_daily_reset() if e.daily
                         else time.time() + max(e.wait, 60))
                with self._lock:
                    self._cool[m] = until
                    nxt = next((x for x in chain if x != m
                                and self._cool.get(x, 0) <= time.time()), "")
                if on_wait:
                    on_wait(
                        f"лимит → {m.replace('gemini-', '')}" if nxt
                        else "лимиты исчерпаны",
                        f"{m}: лимит исчерпан"
                        + (f" — переключаюсь на {nxt}." if nxt else "."))
            except ModelMissing:
                with self._lock:
                    if m in chain:
                        chain.remove(m)

    def _call_model(self, api_key, model, payload, on_wait=None):
        if not model or model.lower().startswith("авто"):
            return self._call_auto(api_key, payload, on_wait)
        url = f"{API_ROOT}/models/{model}:generateContent"
        return self._request(url, payload, api_key, on_wait=on_wait), model

    def _gemini_text(self, api_key, prompt, max_tokens, temperature, model=None):
        base = {
            "responseMimeType": "application/json",
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }
        data, last_err = None, ""
        deadline = time.monotonic() + 180
        models = [model] if model else self._model_order(api_key)
        for m in models:
            ladder = ([self._think_ok[m]] if m in self._think_ok
                      else THINK_LADDER)
            for think in ladder:
                cfg = dict(base, **({"thinkingConfig": think} if think else {}))
                code = 0
                for attempt in range(2):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Превышено время ожидания Gemini (3 мин)")
                    body = json.dumps({
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": cfg,
                    }).encode()
                    req = urllib.request.Request(
                        f"{API_ROOT}/models/{m}:generateContent",
                        data=body,
                        headers={"x-goog-api-key": api_key,
                                 "content-type": "application/json"})
                    try:
                        with urllib.request.urlopen(
                                req, timeout=max(1, min(60, deadline - time.monotonic()))
                        ) as r:
                            data = json.loads(r.read())
                        self._good_model = m
                        self._think_ok[m] = think
                        break
                    except urllib.error.HTTPError as e:
                        code = e.code
                        last_err = (f"Gemini API {e.code} ({m}): "
                                    f"{e.read().decode(errors='replace')[:300]}")
                        if code in (429, 503) and attempt < 1:
                            time.sleep(3)
                            continue
                        if code in (401, 403):
                            raise RuntimeError(last_err)
                        break
                    except (urllib.error.URLError, TimeoutError, OSError):
                        last_err = "Gemini: соединение оборвалось."
                        if attempt < 1 and time.monotonic() + 2 < deadline:
                            time.sleep(2)
                            continue
                        break
                if data or code != 400:
                    break
            if data:
                break
        if not data:
            raise RuntimeError(last_err or "Gemini unavailable")
        try:
            text = "".join(
                p.get("text", "")
                for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise RuntimeError(
                f"Gemini не вернул контент: {json.dumps(data)[:300]}")
        return text

    def model_order(self, api_key):
        return self._model_order(api_key)

    def _model_order(self, api_key):
        first = [os.environ.get("GEMINI_MODEL"), self._good_model]
        order = []
        for m in first + self.list_models(api_key) + FALLBACK_MODELS:
            if m and m not in order:
                order.append(m)
        return order[:6]

    def generate_json(self, prompt, api_key=None, max_tokens=8000,
                      model=None, schema=None, on_wait=None):
        key = api_key or self.api_key
        if not key:
            raise ValueError("Нужен Gemini API key")

        if schema:
            payload = {
                "contents": [{"role": "user",
                              "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 1.0,
                },
            }
            data, used = self._call_model(key, model, payload, on_wait)
            candidates = data.get("candidates") or []
            if not candidates:
                reason = data.get("promptFeedback", {}).get(
                    "blockReason", "unknown")
                raise RuntimeError(f"Модель не вернула ответ ({reason}).")
            text = "".join(
                p.get("text", "")
                for p in candidates[0].get("content", {}).get("parts", []))
            return parse_json_loose(text)

        last = None
        for temperature in (0.7, 0.4, 0.2):
            text = self._gemini_text(key, prompt, max_tokens, temperature, model)
            try:
                return parse_json_loose(text)
            except ValueError as e:
                last = e
        raise RuntimeError(
            f"Gemini трижды вернул некорректный JSON ({last}).")

    def generate_text(self, prompt, api_key=None, max_tokens=900,
                      system=None, model=None):
        key = api_key or self.api_key
        if not key:
            raise ValueError("Нужен Gemini API key")
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens,
                                 "temperature": 0.7},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data, used = self._call_model(key, model, payload)
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        return "".join(
            p.get("text", "")
            for p in candidates[0].get("content", {}).get("parts", []))


def parse_json_loose(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    m2 = re.search(r"\{.*\}", text, re.S)
    if not m2:
        raise ValueError("в ответе нет JSON")
    raw = m2.group(0)
    fixes = [
        lambda t: t,
        lambda t: re.sub(r",\s*([}\]])", r"\1", t),
        lambda t: re.sub(
            r'([{,]\s*)([A-Za-z_]\w*)\s*:',
            r'\1"\2":',
            re.sub(r",\s*([}\]])", r"\1", t)),
        lambda t: re.sub(r",\s*([}\]])", r"\1",
                          t.replace("“", '"').replace("”", '"')),
    ]
    err = None
    for fix in fixes:
        try:
            return json.loads(fix(raw), strict=False)
        except ValueError as e:
            err = err or e
    raise err
