""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
BASE = 'https://datacvr.virk.dk'
ПЛОХОЙ_СТАТУС = ('konkurs', 'tvangsopløs', 'ophørt', 'likvidation', 'opløst', 'reassum', 'tvangsoplos')

class Denmark(GeoDriver):
    code, title = ('DK', 'Дания')
    url = f'{BASE}/'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.cvr = ''
        self.статус = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self._cookie()
        поле = self.page.locator("#forside-soegefelt-id, input[placeholder*='Søg efter']").first
        поле.fill(c.name)
        self._cookie()
        self.page.locator("button[data-cy='forside-soegefelt-btn'], button[aria-label='Søg i CVR'], button.search-btn").first.click()
        try:
            self.page.wait_for_selector('span.bold.value', timeout=12000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _cookie(self) -> None:
        """"""
        for сел in ("a:has-text('Accepter')", "button:has-text('Accepter')"):
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click()
                    self.page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        имена = self.page.locator('span.bold.value')
        for i in range(имена.count()):
            сп = имена.nth(i)
            карточка = сп.locator("xpath=ancestor::*[contains(.,'CVR-nummer') or contains(.,'P-nummer')][1]")
            if not карточка.count():
                continue
            текст = карточка.inner_text()
            mc = re.search('CVR-nummer:?\\s*(\\d{8})', текст)
            if not mc:
                continue
            cvr = mc.group(1)
            if cvr in виденные:
                continue
            виденные.add(cvr)
            имя = сп.inner_text().strip()
            адрес = ''
            ma = re.search(re.escape(имя) + '\\s*(.+?)\\s*CVR-nummer', текст, re.S)
            if ma:
                адрес = re.sub('\\s+', ' ', ma.group(1)).strip()
            статус = ''
            ms = re.search('Status:?\\s*([^\\n]+)', текст, re.I)
            if ms:
                статус = ms.group(1).strip()
            cands.append(Candidate(name=имя, address=адрес, ref={'cvr': cvr, 'статус': статус, 'имя': имя, 'адрес': адрес}))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            текст = self.page.inner_text('body')
            m = re.search('CVR-nummer\\s*\\n?\\s*(\\d{8})', текст)
            self.cvr = m.group(1) if m else ''
            h = self.page.locator('h1, h2').first
            self.имя = h.inner_text().strip() if h.count() else cand.name
            self.статус = self._поле(текст, 'Status')
            адр = self._поле(текст, 'Adresse')
            город = self._поле(текст, 'Postnummer og by')
            self.адрес = ', '.join((x for x in (адр, город) if x))
            return
        d = cand.ref
        self.cvr, self.статус = (d['cvr'], d['статус'])
        self.имя, self.адрес = (d['имя'], d['адрес'])

    def check(self, c: Company) -> tuple[bool, str]:
        статус = self.статус
        if not статус:
            статус = self._поле(self.page.inner_text('body'), 'Status')
        low = статус.lower()
        if not low:
            return (False, 'не нашёл статус фирмы')
        if any((p in low for p in ПЛОХОЙ_СТАТУС)):
            return (False, f'статус: {статус}')
        if 'normal' not in low and 'aktiv' not in low:
            return (False, f'статус не Normal ({статус})')
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'{re.escape(подпись)}\\s*\\n?\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.cvr

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
