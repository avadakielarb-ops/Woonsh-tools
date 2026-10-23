""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
BASE = 'https://abr.business.gov.au'

class Australia(GeoDriver):
    code, title = ('AU', 'Австралия')
    url = f'{BASE}/'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.abn = ''
        self.имя = ''
        self.адрес_dnb = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(f'{BASE}/Search/ResultsActive?SearchText={quote(c.name)}')
        self.page.wait_for_load_state('domcontentloaded')
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        строки = self.page.locator('table tbody tr')
        for i in range(строки.count()):
            строка = строки.nth(i)
            ссылка = строка.locator('a').first
            if not ссылка.count():
                continue
            abn = re.sub('\\D', '', ссылка.inner_text())
            if not abn or abn in виденные:
                continue
            виденные.add(abn)
            ячейки = [строка.locator('td').nth(j).inner_text().strip() for j in range(строка.locator('td').count())]
            имя = ячейки[1] if len(ячейки) > 1 else ссылка.inner_text().strip()
            локация = re.sub('\\s+', ' ', строка.inner_text()).strip()
            cands.append(Candidate(name=имя, address=локация, ref=abn))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            m = re.search('abn=(\\d{11})', self.page.url)
            self.abn = m.group(1) if m else ''
            return
        self.abn = str(cand.ref)
        self.имя = cand.name
        self.br.goto(f'{BASE}/ABN/View?abn={self.abn}')
        self.page.wait_for_load_state('domcontentloaded')

    def check(self, c: Company) -> tuple[bool, str]:
        self.адрес_dnb = ', '.join((x for x in (c.address, c.zip_code, c.city) if x)) if c else ''
        текст = self.page.inner_text('body')
        m = re.search('ABN status:?\\s*\\n?\\s*([^\\n]+)', текст, re.I)
        статус = (m.group(1) if m else '').strip()
        low = статус.lower()
        if 'cancelled' in low:
            return (False, f'ABN отменён ({статус})')
        if 'active' not in low:
            return (False, f"ABN status не Active ({статус or '—'})")
        return (True, '')

    def номер(self) -> str:
        if self.abn:
            return self.abn
        try:
            m = re.search('\\b(\\d{2}\\s\\d{3}\\s\\d{3}\\s\\d{3})\\b', self.page.inner_text('body'))
            return re.sub('\\s', '', m.group(1)) if m else ''
        except Exception:
            return ''

    def данные_реестра(self) -> dict:
        try:
            m = re.search('Entity name:?\\s*\\n?\\s*([^\\n]+)', self.page.inner_text('body'), re.I)
            if m:
                self.имя = m.group(1).strip()
        except Exception:
            pass
        return {'имя': self.имя, 'адрес': self.адрес_dnb}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
