""""""
from __future__ import annotations
import random
import re
import time
from dataclasses import dataclass
ГЛАВНАЯ = 'https://www.hithorizons.com/'
ПОЛЕ = "input[placeholder*='Company Name' i]"
РЕЗУЛЬТАТ = 'a.search-result'
ПАУЗА = (2.5, 5.0)

@dataclass
class Находка:
    имя: str
    еик: str
    адрес: str
    hh_id: str

def _норм(s: str) -> str:
    """"""
    s = (s or '').upper()
    s = re.sub('[^A-Z0-9 ]+', ' ', s)
    s = re.sub('\\s+', ' ', s).strip()
    формы = {'EOOD', 'OOD', 'EAD', 'AD', 'ET', 'DZZD', 'KD', 'KDA', 'SD', 'LTD', 'LIMITED', 'LLC', 'INC', 'CORP', 'PLC', 'JSC', 'CO'}
    слова = [w for w in s.split() if w not in формы]
    return ' '.join(слова)

def искать(br, имя: str, log=print) -> list[Находка]:
    """"""
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
        поле.press('Enter')
        page.wait_for_timeout(3500)
    except Exception as e:
        log(f'    hithorizons: поиск не отправился ({type(e).__name__})')
        return []
    br.check_captcha(имя)
    находки: list[Находка] = []
    блоки = page.locator(РЕЗУЛЬТАТ)
    for i in range(min(блоки.count(), 12)):
        б = блоки.nth(i)
        try:
            заголовок = б.locator('h3').first
            полное = (заголовок.get_attribute('title') or заголовок.inner_text()).strip()
            строка = б.inner_text()
            m = re.search('National ID\\s*\\n?\\s*(\\d{9,13})', строка)
            if not m:
                continue
            адрес = ''
            а = б.locator('.search-result-address').first
            if а.count():
                адрес = а.inner_text().strip().splitlines()[0]
            href = б.get_attribute('href') or ''
            hh = re.search('/companies/(H-[A-Z0-9]+)/', href)
            находки.append(Находка(полное, m.group(1), адрес, hh.group(1) if hh else ''))
        except Exception:
            continue
    return находки

def подобрать(имя: str, находки: list[Находка]) -> Находка | None:
    """"""
    цель = _норм(имя)
    точные = [н for н in находки if _норм(н.имя) == цель]
    if len(точные) == 1:
        return точные[0]
    if not точные and len(находки) == 1:
        return находки[0]
    return None

def пауза() -> None:
    """"""
    time.sleep(random.uniform(*ПАУЗА))
