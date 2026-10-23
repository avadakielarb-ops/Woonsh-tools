""""""
from __future__ import annotations
import re
import random
import datetime
import subprocess
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
ФОРМА_РЕ = '(Besloten Vennootschap|Naamloze Vennootschap|Eenmanszaak|Vennootschap onder firma|Commanditaire vennootschap|Maatschap|Coöperatie|Stichting|Vereniging)'

class Netherlands(GeoDriver):
    code, title = ('NL', 'Нидерланды')
    url = 'https://www.kvk.nl/en/search/'
    method = 'pdf'

    def __init__(self, br, human):
        super().__init__(br, human)
        self._блок = ''
        self.имя = ''
        self.адрес = ''
        self.kvk = ''
        self.форма = ''
        self.vestiging = ''
        self.handelsnamen = ''
        self.statutaire = ''
        self.activiteiten = ''
        self.generated = {}

    def search(self, c: Company) -> list[Candidate]:
        self.log('  · открываю kvk.nl/en/search')
        self.br.goto(self.url)
        self.page.wait_for_timeout(1200)
        if self._cookie():
            self.log('  · куки приняты (Accept all)')
        else:
            self.log('  · кнопку куки не нашёл (возможно, уже принято)')
        try:
            поле = self.page.get_by_placeholder('Search in kvk.nl').first
            поле.wait_for(state='visible', timeout=8000)
            поле.click()
            поле.fill(c.name)
            self.log(f'  · вбил «{c.name}», жму Search')
            self.page.get_by_role('button', name='Search').first.click(timeout=6000)
        except Exception as e:
            self.log(f'  · поиск не сработал ({type(e).__name__}) — зову человека')
            self.human.stuck('вбей имя в поиск kvk.nl, нажми Search и «Продолжить».', c.name)
        self.page.wait_for_timeout(2000)
        self._раскрыть()
        cands = self.кандидаты_страницы()
        self.log(f'  · нашёл {len(cands)} фирм в выдаче')
        if not cands:
            self.human.stuck('не вижу результатов на kvk.nl — доведи поиск руками (имя → Search), дождись списка фирм и нажми «Продолжить».', c.name)
            cands = self.кандидаты_страницы()
            self.log(f'  · после человека: {len(cands)} фирм')
        return cands

    def _cookie(self) -> bool:
        for _ in range(3):
            for loc in (self.page.get_by_role('button', name='Accept all'), self.page.get_by_role('button', name='Accepteren'), self.page.get_by_role('button', name='Alles accepteren'), self.page.locator('#onetrust-accept-btn-handler')):
                try:
                    b = loc.first
                    if b.count() and b.is_visible():
                        b.click(timeout=3000)
                        self.page.wait_for_timeout(600)
                        return True
                except Exception:
                    continue
            self.page.wait_for_timeout(700)
        return False

    def _раскрыть(self) -> None:
        try:
            кнопки = self.page.get_by_role('button', name='Show more')
            for i in range(min(кнопки.count(), 10)):
                try:
                    кнопки.nth(i).click(timeout=1500)
                    self.page.wait_for_timeout(150)
                except Exception:
                    continue
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        блоки = self.page.locator("[data-ui-test-class='search-result']")
        тексты: list[str] = []
        if блоки.count():
            for i in range(блоки.count()):
                try:
                    тексты.append(блоки.nth(i).inner_text())
                except Exception:
                    continue
        else:
            ссылки = self.page.locator("[aria-label*='met nummer']")
            for i in range(min(ссылки.count(), 30)):
                a = ссылки.nth(i)
                try:
                    бл = a.locator("xpath=ancestor::*[contains(.,'KVK number')][1]")
                    тексты.append(бл.inner_text() if бл.count() else a.inner_text() or '')
                except Exception:
                    continue
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for текст in тексты:
            kvk = self._поле(текст, 'KVK number:?\\s*(\\d{8})')
            ключ = kvk + '|' + self._поле(текст, 'Branch number:?\\s*(\\d+)')
            if not kvk or ключ in виденные:
                continue
            виденные.add(ключ)
            имя = текст.strip().split('\n')[0].strip()
            cands.append(Candidate(name=имя, address=self._адрес(текст), ref=текст))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            self._блок = self.page.inner_text('body')
        else:
            self._блок = str(cand.ref)
            self.имя = cand.name

    def check(self, c: Company) -> tuple[bool, str]:
        т = self._блок or ''
        self.форма = self._поле(т, ФОРМА_РЕ)
        причина = проверить_форму('NL', self.форма) or проверить_статус(self.форма)
        if причина:
            return (False, причина)
        низ = т.lower()
        for плохо in ('faillissement', 'opgeheven', 'ontbonden', 'surseance', 'uitgeschreven'):
            if плохо in низ:
                return (False, f'статус-стоп: {плохо}')
        self.kvk = self._поле(т, 'KVK number:?\\s*(\\d{8})')
        self.vestiging = self._поле(т, 'Branch number:?\\s*(\\d+)')
        self.адрес = self._адрес(т)
        self.handelsnamen = self._поле(т, 'Trade names?:\\s*([^\\n]+)')
        self.statutaire = self._поле(т, 'Name given in the articles:\\s*([^\\n]+)')
        self.activiteiten = self._деятельность(т)
        if not self.имя:
            self.имя = т.strip().split('\n')[0].strip() or c.name
        return (True, '')

    @staticmethod
    def _поле(текст: str, pattern: str) -> str:
        m = re.search(pattern, текст, re.I)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _адрес(текст: str) -> str:
        for строка in текст.split('\n'):
            if re.search('\\b\\d{4} ?[A-Z]{2}\\b', строка):
                ч = строка.strip()
                if ч and (not re.match('(KVK|Branch|RSIN)', ч, re.I)):
                    return ч
        return ''

    @staticmethod
    def _деятельность(текст: str) -> str:
        m = re.search('\\n(De uitoefening[^\\n]+|[^\\n]*(?:bureau|handel|exploitatie|advies|consultancy|productie|dienstverlening)[^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.kvk

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
