""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://sudreg.pravosudje.hr/ords/r/esudreg/public'
ПЛОХОЙ_СТАТУС = ('stečaj', 'stecaj', 'likvidacij', 'brisan', 'predsteč', 'predstec')

class Croatia(GeoDriver):
    code, title = ('HR', 'Хорватия')
    url = f'{BASE}/pretraga-subjekata'
    method = 'print'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.mbs = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(1200)
        поле = self.page.get_by_label('Ime/Naziv pravnog subjekta').first
        поле.click()
        поле.fill(c.name)
        self.page.get_by_role('button', name='Pretraži').first.click()
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(1200)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator('table tr').all():
            ячейки = [строка.locator('td').nth(j).inner_text().strip() for j in range(строка.locator('td').count())]
            if len(ячейки) < 7:
                continue
            mbs = re.sub('\\D', '', ячейки[0])
            if not mbs or mbs in виденные:
                continue
            if 'aktiv' not in ячейки[3].lower():
                continue
            виденные.add(mbs)
            cands.append(Candidate(name=ячейки[4], address=ячейки[6], ref=mbs))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            m = re.search('p28_sbt_mbs=(\\d+)', self.page.url)
            self.mbs = m.group(1) if m else ''
            return
        self.mbs = str(cand.ref)
        self.имя, self.адрес = (cand.name, cand.address)
        self.br.goto(f'{BASE}/podaci-o-poslovnom-subjektu?p28_sbt_mbs={self.mbs}')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(1000)

    @staticmethod
    def _данные(текст: str) -> str:
        """"""
        for якорь in ('Prikaži verziju za ispis', 'Podaci o subjektu'):
            поз = текст.rfind(якорь)
            if поз >= 0:
                return текст[поз + len(якорь):]
        поз = текст.rfind('Nadležni sud')
        return текст[поз:] if поз >= 0 else текст

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self._данные(self.page.inner_text('body'))
        статус = self._поле(текст, 'Status')
        низ = статус.lower()
        if any((w in низ for w in ПЛОХОЙ_СТАТУС)):
            return (False, f'статус: {статус}')
        причина = проверить_статус(статус)
        if причина:
            return (False, причина)
        причина = проверить_форму('HR', self._поле(текст, 'Pravni oblik'))
        if причина:
            return (False, причина)
        self.имя = self._поле(текст, 'Tvrtka') or self.имя
        адрес_карточки = self._адрес(текст)
        if адрес_карточки:
            self.адрес = адрес_карточки
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'\\b{re.escape(подпись)}\\b\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _адрес(текст: str) -> str:
        """"""
        m = re.search('Sjedište/adresa\\s*\\n\\s*([^\\n]+)\\n\\s*([^\\n]+)', текст, re.I)
        if m:
            return f'{m.group(1).strip()}, {m.group(2).strip()}'
        m = re.search('Sjedište/adresa\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.mbs

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
