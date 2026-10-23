""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://www.zefix.ch'

class Switzerland(GeoDriver):
    code, title = ('CH', 'Швейцария')
    url = f'{BASE}/en/search/entity/list'
    method = 'print'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.uid = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self._agree()
        поле = self.page.get_by_role('combobox', name='business name or UID').first
        поле.click()
        поле.fill(c.name)
        поле.press('Enter')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(1200)
        self._agree()
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _agree(self) -> None:
        """"""
        try:
            b = self.page.get_by_role('button', name='Agree').first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass
    _МУСОР = ('opens in a new tab', 'cantonal excerpt', 'che-')

    def на_карточке(self) -> bool:
        """"""
        return '/firm/' in (self.page.url or '')

    def _имя_карточки(self) -> str:
        for sel in ('h1', 'h2', "[class*='title']"):
            try:
                э = self.page.locator(sel).first
                if э.count():
                    имя = э.inner_text().strip().splitlines()[0].strip()
                    if имя and len(имя) > 2:
                        return имя
            except Exception:
                continue
        return ''

    def _поле_карточки(self, подпись: str) -> str:
        """"""
        try:
            строка = self.page.locator(f"tr:has-text('{подпись}')").first
            if строка.count():
                я = строка.locator('td').first
                if я.count():
                    return я.inner_text().strip()
        except Exception:
            pass
        return ''

    def _карточка_как_кандидат(self) -> Candidate:
        адрес = ' '.join((x for x in (self._поле_карточки('address'), self._поле_карточки('ZIP / Town')) if x))
        return Candidate(name=self._имя_карточки() or '', address=адрес, ref='CARD')

    def кандидаты_страницы(self) -> list[Candidate]:
        if self.на_карточке():
            return [self._карточка_как_кандидат()]
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator('table tr').all():
            ссылка = строка.locator("a[href*='/firm/']").first
            if not ссылка.count():
                continue
            href = ссылка.get_attribute('href') or ''
            имя = ссылка.inner_text().strip()
            if not имя or not href or href in виденные:
                continue
            виденные.add(href)
            ячейки = [строка.locator('td').nth(j).inner_text().strip() for j in range(строка.locator('td').count())]
            место = ''
            for я in reversed(ячейки):
                низ = я.lower()
                if я and я != имя and (not any((м in низ for м in self._МУСОР))):
                    место = я
                    break
            cands.append(Candidate(name=имя, address=место, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref in ('HUMAN', 'CARD'):
            return
        ссылка = str(cand.ref)
        self.br.goto(ссылка if ссылка.startswith('http') else BASE + ссылка)
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(800)
        self._agree()

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        статус = self._поле(текст, 'status')
        if 'activ' not in статус.lower():
            return (False, f"статус: {статус or '—'}")
        причина = проверить_статус(статус)
        if причина:
            return (False, причина)
        форма = self._поле(текст, 'legal form')
        причина = проверить_форму('CH', форма)
        if причина:
            return (False, причина)
        h1 = self.page.locator('h1').first
        self.имя = h1.inner_text().strip() if h1.count() else c.name
        улица = self._поле(текст, 'address')
        индекс_город = self._поле(текст, 'ZIP / Town')
        self.адрес = ', '.join((x for x in (улица, индекс_город) if x))
        mu = re.search('(CHE-\\d{3}\\.\\d{3}\\.\\d{3})', текст)
        self.uid = mu.group(1) if mu else ''
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """"""
        m = re.search(f'\\b{re.escape(подпись)}\\b[ \\t]*\\t[ \\t]*([^\\n]+)', текст, re.I)
        if not m:
            m = re.search(f'\\b{re.escape(подпись)}\\b\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.uid

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
