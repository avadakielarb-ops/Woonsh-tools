""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.names import без_формы
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://virre.prh.fi'

class Finland(GeoDriver):
    code, title = ('FI', 'Финляндия')
    url = f'{BASE}/'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.bid = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(1200)
        self._закрыть()
        поле = self.page.get_by_role('textbox', name='Y-tunnus tai diaarinumero tai').first
        if not поле.count():
            поле = self.page.locator("input[type='text']:visible, input[type='search']:visible").first
        поле.click()
        поле.fill(без_формы(c.name) or c.name)
        self.page.wait_for_timeout(400)
        кнопка = self.page.get_by_test_id('button_search').first
        if кнопка.count():
            кнопка.click()
        else:
            поле.press('Enter')
        self._дождаться('document.querySelector("[data-testid^=\'tableRow-\']") !== null || /ei (haku)?tuloksia|no results|ei löytynyt/i.test(document.body.innerText)')
        self.page.wait_for_timeout(400)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _закрыть(self) -> None:
        """"""
        try:
            b = self.page.get_by_role('button', name='Close').first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass
    ЖИВЫЕ_СТАТУСЫ = ('rekisteriss', 'in the register')

    def кандидаты_страницы(self) -> list[Candidate]:
        """"""
        cands: list[Candidate] = []
        виденные: set[str] = set()
        строки = self.page.locator("[data-testid^='tableRow-']")
        всего = строки.count()
        if not всего:
            строки = self.page.locator('table tbody tr')
            всего = строки.count()
        for i in range(всего):
            строка = строки.nth(i)
            try:
                текст = строка.inner_text()
            except Exception:
                continue
            низ = текст.lower()
            if not any((с in низ for с in self.ЖИВЫЕ_СТАТУСЫ)):
                continue
            mb = re.search('\\b(\\d{7}-\\d)\\b', текст)
            ключ = mb.group(1) if mb else re.sub('\\s+', ' ', текст)[:60]
            if ключ in виденные:
                continue
            виденные.add(ключ)
            ссылка = строка.locator('a').first
            имя = ссылка.inner_text().strip() if ссылка.count() else self._ячейка(строка, 'companyName')
            офис = self._ячейка(строка, 'registeredOffice')
            адрес = офис or re.sub('\\s+', ' ', текст).strip()
            if not имя:
                continue
            cands.append(Candidate(name=имя, address=адрес, ref={'строка': i, 'bid': ключ, 'имя': имя}))
        return cands

    def _ячейка(self, строка, поле: str) -> str:
        """"""
        try:
            я = строка.locator(f"[data-testid='tableCell-{поле}']").first
            return я.inner_text().strip() if я.count() else ''
        except Exception:
            return ''

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        self.bid = cand.ref.get('bid', '')
        строка = self.page.locator("[data-testid^='tableRow-']").nth(cand.ref.get('строка', 0))
        имя = cand.ref.get('имя', '')
        ссылка = строка.get_by_test_id(имя).first if имя else None
        if ссылка is None or not ссылка.count():
            ссылка = строка.locator('a').first
        if not ссылка.count():
            ссылка = self.page.get_by_test_id(имя).first
        ссылка.click()
        self._дождаться('/Y-tunnus|Perustiedot|Business ID|Yritysmuoto/i.test(document.body.innerText)')
        self.page.wait_for_timeout(400)

    def _дождаться(self, условие: str, мс: int=20000) -> bool:
        """"""
        try:
            self.page.wait_for_function(f'() => {условие}', timeout=мс)
            return True
        except Exception:
            return False

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        статус = self._поле(текст, 'Status of company') or self._поле(текст, 'Yrityksen tila') or self._поле(текст, 'Tila')
        if not any((с in статус.lower() for с in self.ЖИВЫЕ_СТАТУСЫ)):
            return (False, f"статус: {статус or '—'}")
        причина = проверить_статус(статус)
        if причина:
            return (False, причина)
        тип = self._поле(текст, 'Company type') or self._поле(текст, 'Yritysmuoto')
        причина = проверить_форму('FI', тип)
        if причина:
            return (False, причина)
        self.имя = self._поле(текст, 'Name') or self._поле(текст, 'Nimi') or c.name
        self.адрес = self._поле(текст, 'Postal address') or self._поле(текст, 'Registered office') or self._поле(текст, 'Kotipaikka')
        if not self.bid:
            mb = re.search('\\b(\\d{7}-\\d)\\b', текст)
            self.bid = mb.group(1) if mb else ''
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """"""
        m = re.search(f'\\b{re.escape(подпись)}\\b[ \\t]*\\t[ \\t]*([^\\n]+)', текст, re.I)
        if not m:
            m = re.search(f'\\b{re.escape(подпись)}\\b\\s*\\n\\s*([^\\n]+)', текст, re.I)
        if not m:
            return ''
        знач = m.group(1).strip()
        знач = re.sub('(\\s*\\d{2}\\.\\d{2}\\.\\d{4})+\\s*$', '', знач).strip()
        знач = re.split('\\t', знач)[0].strip()
        return знач

    def номер(self) -> str:
        return self.bid

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
