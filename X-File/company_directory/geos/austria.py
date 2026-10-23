""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://www.gisa.gv.at'
ФОРМА = f'{BASE}/fshost-gisa-p/user/formular.aspx?lang=en'

class Austria(GeoDriver):
    code, title = ('AT', 'Австрия')
    url = ФОРМА
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.фб = ''
        self._ссылка = None
        self._текст = ''

    def search(self, c: Company) -> list[Candidate]:
        try:
            self.br.goto(self.url)
            self.page.wait_for_load_state('domcontentloaded', timeout=20000)
        except Exception as e:
            self.log(f'  ✘ AT: реестр не открылся ({type(e).__name__})')
            self.human.сайт_не_отвечает('Австрии (GISA)', self.url, c.name)
        self.page.wait_for_timeout(800)
        if not self.page.get_by_text('Search by legal person').count():
            self.log('  ✘ AT: формы поиска на странице нет — похоже, сайт лежит')
            self.human.сайт_не_отвечает('Австрии (GISA)', self.url, c.name)
        try:
            self.page.get_by_text('Search by legal person').first.click()
            self.page.wait_for_timeout(600)
        except Exception:
            pass
        try:
            поле = self.page.get_by_label('Name/designation').first
            поле.click()
            поле.fill(c.name)
            self.page.get_by_role('button', name='Forward').first.click()
            self.page.wait_for_load_state('networkidle')
            self.page.wait_for_timeout(800)
        except Exception:
            self.human.stuck('не нашёл форму GISA — выбери «Search by legal person», впиши имя и нажми «Forward», потом «Продолжить».', c.name)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator('table tr').all():
            ссылка = строка.locator("a:has-text('GISA extract incl')").first
            if not ссылка.count():
                continue
            текст = строка.inner_text()
            m = re.search('Holder of the business licence\\s*\\n?\\s*([^;\\n]+?)\\s*(?:;\\s*([^\\s\\n]+))?\\s*\\n', текст, re.I)
            имя = m.group(1).strip() if m else ''
            фб = (m.group(2) or '').strip() if m else ''
            if not имя:
                continue
            ключ = фб or имя
            if ключ in виденные:
                continue
            виденные.add(ключ)
            ma = re.search('Location\\s*\\n?\\s*([^\\n]+)', текст, re.I)
            cands.append(Candidate(name=имя, address=ma.group(1).strip() if ma else '', ref={'ссылка': ссылка, 'фб': фб, 'имя': имя, 'адрес': ma.group(1).strip() if ma else '', 'текст': текст}))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        d = cand.ref
        self._ссылка, self.фб = (d['ссылка'], d['фб'])
        self.имя, self.адрес, self._текст = (d['имя'], d['адрес'], d['текст'])

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self._текст or self.page.inner_text('body')
        if not re.search('Licence valid', текст, re.I):
            return (False, 'лицензия не действующая')
        причина = проверить_форму('AT', self.имя) or проверить_статус(self.имя) or проверить_статус(текст[:200])
        if причина:
            return (False, причина)
        return (True, '')

    def номер(self) -> str:
        return self.фб

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
