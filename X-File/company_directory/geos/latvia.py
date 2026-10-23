""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.names import без_формы
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
BASE = 'https://info.ur.gov.lv'

class Latvia(GeoDriver):
    code, title = ('LV', 'Латвия')
    url = f'{BASE}/#/data-search'
    method = 'download'
    номер_regex = '\\b(\\d{11})\\b'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.regnr = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_timeout(1500)
        self._закрыть()
        поле = self.page.locator("input[placeholder*='nosaukum'], input[placeholder*='Uzņēmuma'], input[type='search']:visible, input[type='text']:visible").first
        поле.click()
        поле.fill(без_формы(c.name) or c.name)
        self.page.wait_for_timeout(700)
        поле.press('Enter')
        try:
            self.page.wait_for_function('() => /Re[gģ]\\.?\\s*Nr/.test(document.body.innerText)', timeout=12000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
        self._закрыть()
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _закрыть(self) -> None:
        """"""
        try:
            b = self.page.locator("button:has-text('Aizvērt')").first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        текст = self.page.inner_text('body')
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for m in re.finditer('Re[gģ]\\.?\\s*Nr\\.?\\s*:?\\s*(\\d{11})', текст):
            regnr = m.group(1)
            if regnr in виденные:
                continue
            виденные.add(regnr)
            хвост = текст[m.end():m.end() + 140]
            if re.search('Izsl[eē]gt', хвост):
                continue
            до = [s.strip() for s in текст[:m.start()].split('\n') if s.strip()]
            имя = до[-2] if len(до) >= 2 else до[-1] if до else ''
            адрес = до[-1] if до else ''
            прежние: tuple = ()
            mp = re.search('Iepriekš:?\\s*([^\\n]+)', хвост, re.I)
            if mp:
                прежние = (mp.group(1).strip(),)
            cands.append(Candidate(name=имя, address=адрес, ref=regnr, aliases=прежние))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            m = re.search('legal-entity/(\\d{11})', self.page.url)
            self.regnr = m.group(1) if m else ''
            self._закрыть()
            return
        self.regnr = str(cand.ref)
        self.имя, self.адрес = (cand.name, cand.address)
        self.br.goto(f'{BASE}/#/legal-entity/{self.regnr}')
        try:
            self.page.wait_for_function('() => /\\d{11}/.test(document.body.innerText)', timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(400)
        self._закрыть()

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        м = re.search('(Izsl[eē]gt\\w*|likvid[āa]cij\\w*|maks[āa]tnesp[eē]j\\w*)', текст, re.I)
        if м and м.start() < len(текст) * 0.5:
            return (False, 'исключена / ликвидация / неплатёжеспособность')
        if not self.адрес:
            ma = re.search('Adres\\w*:?\\s*\\n?\\s*([^\\n]+)', текст, re.I)
            if ma:
                self.адрес = ma.group(1).strip()
        return (True, '')

    def номер(self) -> str:
        return self.regnr

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
