""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://www.ajpes.si'

class Slovenia(GeoDriver):
    code, title = ('SI', 'Словения')
    url = f'{BASE}/prs/default.asp?language=english'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.рег = ''

    @staticmethod
    def _улица(c: Company) -> str:
        """"""
        слова = [w for w in re.split('[\\s,]+', (c.address or '').strip()) if len(w) >= 4 and re.match('^[^\\d]+$', w)]
        return слова[0] if слова else ''

    def _url_выдачи(self, имя: str, улица: str='', стр: int=1) -> str:
        return f'{BASE}/prs/rezultati.asp?podrobno=0&tip=0&naziv={quote(имя)}&maticna=&davcna=&status=1&ulica={quote(улица)}' + (f'&frm_pos={стр}' if стр > 1 else '')

    def search(self, c: Company) -> list[Candidate]:
        """"""
        self.br.goto(self.url)
        self._allow()
        self._имя, self._улица_поиска = (c.name, '')
        улица = self._улица(c)
        выдача = self._url_выдачи(c.name, улица)
        self._перейти(выдача)
        if re.search('not available|please log in', self.page.inner_text('body'), re.I):
            self._аноним(c.name)
            self._перейти(выдача)
        if улица:
            найдено = self.кандидаты_страницы()
            if найдено:
                self.log(f'  · фильтр по улице «{улица}»: {len(найдено)} шт.')
                self._улица_поиска = улица
                return найдено
            self.log(f'  · по улице «{улица}» пусто — ищу по всей Словении')
            self._перейти(self._url_выдачи(c.name))
        self._стр = 1
        return self.кандидаты_страницы()

    def следующая_страница(self) -> bool:
        стр = getattr(self, '_стр', 1) + 1
        тело = self.page.inner_text('body')
        m = re.search('Hits:\\s*(\\d+)\\s*\\(showing\\s*(\\d+)\\s*-\\s*(\\d+)\\)', тело, re.I)
        if not m or int(m.group(3)) >= int(m.group(1)):
            return False
        self._стр = стр
        self._перейти(self._url_выдачи(getattr(self, '_имя', ''), getattr(self, '_улица_поиска', ''), стр))
        return True

    def _перейти(self, url: str) -> None:
        """"""
        for _ in range(3):
            try:
                self.br.goto(url)
                self.page.wait_for_load_state('domcontentloaded')
                self.page.wait_for_timeout(600)
                if 'chrome-error' not in self.page.url:
                    return
            except Exception:
                pass
            self.page.wait_for_timeout(1200)

    def _allow(self) -> None:
        try:
            b = self.page.get_by_role('link', name='ALLOW', exact=True).first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    def _аноним(self, фирма: str) -> None:
        """"""
        try:
            вход = self.page.get_by_role('link', name='LOGIN').first
            if вход.count() and вход.is_visible():
                вход.click()
                self.page.wait_for_load_state('domcontentloaded')
                self.page.wait_for_timeout(600)
            аноним = self.page.get_by_text('Log in as an anonymous user').first
            if аноним.count() and аноним.is_visible():
                аноним.click()
                self.page.wait_for_timeout(600)
                кнопка = self.page.get_by_role('button', name='Continue').first
                if кнопка.count() and кнопка.is_visible():
                    кнопка.click()
                    self.page.wait_for_load_state('domcontentloaded')
                    self.page.wait_for_timeout(800)
                return
        except Exception:
            pass
        self.human.login('AJPES (ajpes.si) — «Log in as an anonymous user»', фирма)

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator('table tr').all():
            ссылка = строка.locator("a[href*='podjetje']").first
            if not ссылка.count():
                continue
            if not (ссылка.inner_text() or '').strip():
                continue
            ячейки = [строка.locator('td').nth(j).inner_text().strip() for j in range(строка.locator('td').count())]
            if len(ячейки) < 4:
                continue
            href = ссылка.get_attribute('href') or ''
            if not href or href in виденные:
                continue
            виденные.add(href)
            коротко = ячейки[1].strip() if len(ячейки) > 1 else ''
            cands.append(Candidate(name=ссылка.inner_text().strip(), address=ячейки[2], ref=href, aliases=(коротко,) if коротко else ()))
        return cands
    ПРИЗНАК_КАРТОЧКИ = '() => /Registration number|Entity status|Business address|Matična številka|Poslovni naslov|Identification number|Contracted name|PRS unit/i.test(document.body.innerText)'

    def _дождаться_карточки(self, фирма: str='') -> bool:
        """"""
        for попытка in (1, 2):
            try:
                self.page.wait_for_function(self.ПРИЗНАК_КАРТОЧКИ, timeout=20000)
                return True
            except Exception:
                pass
            if self.human.исполнить_приказ(self.br, self.log):
                continue
            if попытка == 1:
                self.log('  · SI: карточка ещё не прочиталась — жду')
                self.br.check_captcha(фирма, ждать_мс=4000)
        self.log(f'  ⚠ SI: карточка так и не открылась — {self._что_на_экране()}')
        return False

    def _что_на_экране(self) -> str:
        """"""
        try:
            адрес = self.page.url or '—'
        except Exception:
            адрес = '—'
        try:
            текст = re.sub('\\s+', ' ', self.page.inner_text('body'))[:120]
        except Exception:
            текст = ''
        return f'адрес {адрес} · на странице: «{текст}»'

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            self._дождаться_карточки()
            return
        url = str(cand.ref)
        self._перейти(url if url.startswith('http') else f"{BASE}/prs/{url.lstrip('/')}")
        self._дождаться_карточки(cand.name)

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        статус = self._поле(текст, 'Entity status')
        if статус:
            if 'registered' not in статус.lower():
                return (False, f"статус: {статус or '—'}")
            причина = проверить_статус(статус)
            if причина:
                return (False, причина)
        elif not self._карточка_prs(текст):
            return (False, 'статус: —')
        причина = проверить_форму('SI', self._поле(текст, 'Legal organizational form'))
        if причина:
            return (False, причина)
        self.имя = self._поле(текст, 'Full company name') or self._поле(текст, 'Short company name') or self._поле(текст, 'Full name') or self._поле(текст, 'Contracted name') or c.name
        self.адрес = self._поле(текст, 'Business address') or self._адрес_prs(текст)
        self.рег = re.sub('\\D', '', self._поле(текст, 'Registration number') or self._поле(текст, 'Identification number'))
        return (True, '')

    @staticmethod
    def _карточка_prs(текст: str) -> bool:
        """"""
        return bool(re.search('Registered in Slovenian Business Register', текст, re.I) or re.search('Basic information on the PRS unit', текст, re.I))

    def _адрес_prs(self, текст: str) -> str:
        """"""
        части = [self._поле(текст, 'Address'), self._поле(текст, 'Post office') or self._поле(текст, 'City')]
        return ', '.join((ч for ч in части if ч))

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """"""
        m = re.search(f'\\b{re.escape(подпись)}\\b\\s*:?[ \\t]*\\n[ \\t]*([^\\n]+)', текст, re.I)
        if not m:
            m = re.search(f'\\b{re.escape(подпись)}\\b\\s*:[ \\t]*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.рег

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
