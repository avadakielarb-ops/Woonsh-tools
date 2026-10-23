""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
BASE = 'https://or.justice.cz/ias/ui'

class Czechia(GeoDriver):
    code, title = ('CZ', 'Чехия')
    url = f'{BASE}/rejstrik'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.ico = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        поле = self.page.locator("input[name='nazev'], input[type='text']:visible").first
        поле.fill(c.name)
        self.page.locator("input[type='submit'], button:has-text('Hledat'), input[value='Hledat'], input[value='Vyhledat']").first.click()
        self.page.wait_for_load_state('domcontentloaded')
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        for блок in self.page.locator("div:has(> a:has-text('Úplný výpis'))").all():
            имя = self._поле(блок.inner_text(), 'Název subjektu')
            if not имя or имя == '*':
                continue
            cands.append(Candidate(name=имя, address=self._поле(блок.inner_text(), 'Sídlo'), ref=блок))
        if cands:
            return cands
        текст = self._текст_выдачи()
        имя = self._поле(текст, 'Název subjektu')
        if имя and имя != '*':
            cands.append(Candidate(name=имя, address=self._поле(текст, 'Sídlo'), ref='СТРАНИЦА'))
        return cands

    def _текст_выдачи(self) -> str:
        """"""
        текст = self.page.inner_text('body')
        m = re.search('Počet nalezených subjektů[^\\n]*', текст, re.I)
        return текст[m.end():] if m else текст

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        self.имя, self.адрес = (cand.name, cand.address)
        ссылка = self.page.locator("a:has-text('Úplný výpis')").first if cand.ref == 'СТРАНИЦА' else cand.ref.locator("a:has-text('Úplný výpis')").first
        ссылка.click()
        self.page.wait_for_load_state('domcontentloaded')

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        имя = (self.имя or self._поле(текст, 'Obchodní firma')).lower()
        for плохо, причина in (('v likvidaci', 'в ликвидации'), ('v konkursu', 'в конкурсном производстве'), ('v úpadku', 'в банкротстве')):
            if плохо in имя:
                return (False, причина)
        m = re.search('Identifikační číslo:?\\s*([\\d\\s]{6,})', текст)
        self.ico = re.sub('\\s', '', m.group(1)) if m else ''
        if not self.имя:
            self.имя = self._поле(текст, 'Obchodní firma')
        if not self.адрес:
            self.адрес = self._поле(текст, 'Sídlo')
        return (True, '')

    def номер(self) -> str:
        return self.ico

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """"""
        m = re.search(f'{re.escape(подпись)}\\s*:?[ \\t]*\\n?[ \\t]*([^\\n]*)', текст, re.I)
        if not m:
            return ''
        знач = m.group(1)
        for соседняя in ('IČO', 'Den zápisu', 'Spisová značka', 'Právní forma', 'Identifikační číslo', 'Datum vzniku', 'Sídlo'):
            знач = re.split(f'[\\t ]{re.escape(соседняя)}\\s*:', знач)[0]
        return re.sub('\\s+', ' ', знач).strip()
