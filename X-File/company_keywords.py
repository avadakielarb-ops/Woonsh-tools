"""Translate public sector keywords before opening company search sources."""
import html
import json
import re
import urllib.request
from urllib.parse import urlencode
from functools import lru_cache

LANGUAGES = {
    'Australia': ('en',), 'Austria': ('de',), 'Belgium': ('nl','fr','de'),
    'Bulgaria': ('bg',), 'Croatia': ('hr',), 'Czech Republic': ('cs',),
    'Denmark': ('da',), 'Estonia': ('et',), 'Finland': ('fi','sv'),
    'France': ('fr',), 'Germany': ('de',), 'Hungary': ('hu',),
    'Iceland': ('is',), 'Latvia': ('lv',), 'Netherlands': ('nl',),
    'Norway': ('nb',), 'Poland': ('pl',), 'Slovenia': ('sl',),
    'Sweden': ('sv',), 'Switzerland': ('de','fr','it'),
    'United Kingdom': ('en',), 'USA': ('en',),
}

def country_languages(country):
    if country not in LANGUAGES:
        raise ValueError('Выберите страну из списка.')
    return LANGUAGES[country]

@lru_cache(maxsize=256)
def _translate(text, source, target):
    query=urlencode({'q':text,'langpair':source+'|'+target})
    request=urllib.request.Request('https://api.mymemory.translated.net/get?'+query,
                                   headers={'User-Agent':'MultiToolFarmer/2.9.7'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            result=json.load(response)
        if int(result.get('responseStatus',0))!=200:
            raise ValueError(str(result.get('responseDetails','Нет перевода'))[:200])
        translated=html.unescape(str(result['responseData']['translatedText'])).strip()
        if not translated or (target!='bg' and re.search('[А-Яа-яЁёІіЇїЄєҐґ]',translated)):
            raise ValueError('Сервис не перевёл ключевые слова на выбранный язык.')
        return translated
    except Exception as exc:
        raise ValueError('Не удалось перевести запрос. Поиск не запущен. '
                         'Повторите позже или введите ключевые слова на языке страны. '+str(exc)[:200]) from exc

def translate_keyword(text, target, stop=None, source=None):
    text=text.strip()
    if not text or len(text.encode('utf-8'))>500:
        raise ValueError('Введите ключевые слова длиной до 500 байт (около 250 букв).')
    if target not in {code for codes in LANGUAGES.values() for code in codes}:
        raise ValueError('Неизвестный язык поиска.')
    if stop is not None and stop.is_set():
        return ''
    if not re.search('[А-Яа-яЁёІіЇїЄєҐґ]',text):
        return text
    source=source or ('uk' if re.search('[ІіЇїЄєҐґ]',text) else 'ru')
    return _translate(text,source,target)
