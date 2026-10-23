""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://search.sunbiz.org'

class USAFlorida(GeoDriver):
    code, title = ('US', 'США (Флорида)')
    url = f'{BASE}/Inquiry/CorporationSearch/ByName'
    method = 'print'
    номер_regex = 'Document Number\\s+([A-Z]?\\d{6,12})'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.locator("input#SearchTerm, input[name='SearchTerm'], input[type='text']").first.fill(c.name)
        self.page.locator("input[type='submit'], button:has-text('Search')").first.click()
        self.page.wait_for_load_state('networkidle')
        cands: list[Candidate] = []
        строки = self.page.locator('table tbody tr')
        for i in range(строки.count()):
            строка = строки.nth(i)
            ссылка = строка.locator('a').first
            if not ссылка.count():
                continue
            текст = строка.inner_text().strip()
            if 'active' not in текст.lower():
                continue
            cands.append(Candidate(name=ссылка.inner_text().strip(), address=текст, ref=ссылка))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        cand.ref.click()
        self.page.wait_for_load_state('networkidle')

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        статус = self._поле(текст, 'Status')
        if not re.match('\\s*active\\b', статус, re.I):
            return (False, f"статус: {статус or '—'}")
        причина = проверить_статус(статус) or проверить_форму('US', статус)
        if причина:
            return (False, причина)
        m = re.search('Corporation Name\\s*\\n\\s*([^\\n]+)', текст, re.I)
        if not m:
            m = re.search('Detail by Entity Name\\s*\\n\\s*([^\\n]+)\\s*\\n\\s*([^\\n]+)', текст, re.I)
            self.имя = m.group(2).strip() if m else c.name
        else:
            self.имя = m.group(1).strip()
        адр = self._поле(текст, 'Principal Address') or self._поле(текст, 'Mailing Address')
        self.адрес = адр
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'\\b{re.escape(подпись)}\\b:?\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
