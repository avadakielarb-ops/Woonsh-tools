""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://virksomhet.brreg.no/en/oppslag/enheter'
ПЛОХОЙ_СТАТУС = ('konkurs', 'avvikling', 'slettet', 'tvangs', 'oppløst', 'opplost')

class Norway(GeoDriver):
    code, title = ('NO', 'Норвегия')
    url = BASE
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.orgnr = ''
        self.сайт = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(f'{BASE}?navn={quote(c.name)}')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(900)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("[data-testid^='card-link-']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            orgnr = re.sub('\\D', '', ссылка.get_attribute('data-testid') or '')
            if not orgnr or orgnr in виденные:
                continue
            виденные.add(orgnr)
            текст = ссылка.inner_text()
            загол = ссылка.locator('h3, h2').first
            имя = загол.inner_text().strip() if загол.count() else текст.split('\n')[0].strip()
            cands.append(Candidate(name=имя, address=self._адрес(текст), ref=orgnr))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            m = re.search('/enheter/(\\d{9})', self.page.url)
            self.orgnr = m.group(1) if m else ''
            return
        self.orgnr = str(cand.ref)
        self.имя = cand.name
        self.br.goto(f'{BASE}/{self.orgnr}')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(700)

    def check(self, c: Company) -> tuple[bool, str]:
        текст = ''
        try:
            секция = self.page.get_by_test_id('basisopplysninger')
            if секция.count():
                текст = секция.inner_text()
        except Exception:
            текст = ''
        if not текст:
            текст = self.page.inner_text('body')
        низ = текст.lower()
        for плохо in ПЛОХОЙ_СТАТУС:
            if плохо in низ:
                return (False, f'статус-стоп: {плохо}')
        тип = self._поле(текст, 'Type of organisation')
        причина = проверить_форму('NO', тип) or проверить_статус(тип)
        if причина:
            return (False, причина)
        h1 = self.page.locator('h1').first
        if h1.count() and h1.inner_text().strip():
            self.имя = h1.inner_text().strip()
        адрес = self._адрес(текст)
        if адрес:
            self.адрес = адрес
        self.сайт = self._поле(текст, 'Web address')
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'\\b{re.escape(подпись)}\\b:?\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _адрес(текст: str) -> str:
        """"""
        m = re.search('Business address:?\\s*\\n\\s*([^\\n]+)\\n\\s*([^\\n]+)', текст, re.I)
        if m and (not re.match('(Country|Type of|Web|E-?mail|Phone|Organisation)', m.group(2).strip(), re.I)):
            return f'{m.group(1).strip()}, {m.group(2).strip()}'
        m = re.search('Business address:?\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.orgnr

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес, 'сайт': self.сайт}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
