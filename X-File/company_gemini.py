"""Bounded grounded search requests with redacted per-model diagnostics."""
import json
import re
import time
import urllib.error
import urllib.request


class SearchAPIError(RuntimeError):
    pass


def redact(text, key):
    text = str(text).replace(key, '[скрыто]') if key else str(text)
    return re.sub(r'AIza[\w-]+', '[скрыто]', text)


def explain(error, model, key):
    raw = error.read(65536).decode('utf-8', errors='replace')
    try:
        obj = json.loads(raw).get('error', {})
    except (ValueError, AttributeError):
        obj = {}
    lines = [f'{model}: HTTP {error.code} {obj.get("status", "")}',
             str(obj.get('message') or raw or error.reason)[:2500]]
    for detail in obj.get('details', []):
        if not isinstance(detail, dict):
            continue
        for violation in detail.get('violations', []):
            lines.append('Квота: ' + json.dumps(violation, ensure_ascii=False))
        if detail.get('retryDelay'):
            lines.append('Google рекомендует повтор через: ' + str(detail['retryDelay']))
    if error.code == 429:
        lines.append('Лимит модели, проекта или Google Search. Смена модели не снимает общий лимит проекта.')
    return redact('\n'.join(lines), key)


def grounded_request(engine, key, body, notify=lambda text: None, stop=None):
    history = []
    deadline = time.monotonic() + 180
    models = list(dict.fromkeys(engine.model_order(key)))[:6]
    for model in models:
        if stop is not None and stop.is_set():
            raise SearchAPIError('Поиск остановлен.\n' + '\n\n'.join(history))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            history.append('Общее время поиска превысило 3 минуты.')
            break
        notify('Запрос к модели ' + model + '…')
        req = urllib.request.Request(
            'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent',
            data=json.dumps(body).encode(),
            headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=min(45, remaining)) as response:
                data = json.loads(response.read(4_000_000))
        except urllib.error.HTTPError as exc:
            reason = explain(exc, model, key)
            history.append(reason)
            unsupported_search = exc.code == 400 and any(word in reason.lower() for word in ('not supported', 'unsupported')) and any(word in reason.lower() for word in ('search', 'grounding', 'tool'))
            retryable = exc.code in (404, 429, 500, 502, 503, 504) or unsupported_search
            notify(reason + '\nПроверяю следующую модель…' if retryable else reason)
            if not retryable:
                raise SearchAPIError('\n\n'.join(history)) from None
            continue
        except (OSError, TimeoutError) as exc:
            raise SearchAPIError('\n\n'.join(history + [redact(f'{model}: ошибка соединения: {exc}', key)])) from None
        if stop is not None and stop.is_set():
            raise SearchAPIError('Поиск остановлен.\n' + '\n\n'.join(history))
        candidate = (data.get('candidates') or [{}])[0]
        sources = candidate.get('groundingMetadata', {}).get('groundingChunks', [])
        if not any(c.get('web', {}).get('uri') for c in sources):
            history.append(model + ': ответ без источников Google Search; результат не принят.')
            notify(history[-1] + ' Проверяю следующую модель…')
            continue
        notify('\n\n'.join(history + ['Поиск выполнен: ' + model]))
        return data, model
    raise SearchAPIError('Не удалось выполнить поиск на доступных моделях.\n\n' + '\n\n'.join(history))
