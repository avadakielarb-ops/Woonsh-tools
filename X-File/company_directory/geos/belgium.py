""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver

class Belgium(GeoDriver):
    code, title = ('BE', 'Бельгия')
    url = 'https://kbopub.economie.fgov.be/kbopub/zoeknaamfonetischform.html'
    method = 'print'
    номер_regex = '\\b(\\d{4}\\.\\d{3}\\.\\d{3})\\b'

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.locator("input[name='searchWord'], input#searchWord, input[type='text']").first.fill(c.name)
        self.page.locator("input[value='Zoek'], button:has-text('Zoek'), input[type='submit']").first.click()
        self.page.wait_for_load_state('networkidle')
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        строки = self.page.locator("tr:has(a[href*='ondernemingsnummer'])")
        for i in range(строки.count()):
            строка = строки.nth(i)
            ячейки = [строка.locator('td').nth(j).inner_text().strip() for j in range(строка.locator('td').count())]
            if not ячейки:
                continue
            if not any(('ENT RP' in re.sub('\\s+', ' ', т.upper()) for т in ячейки)):
                continue
            ссылка = строка.locator("a[href*='ondernemingsnummer']").first
            имя = ячейки[-2] if len(ячейки) >= 2 else ссылка.inner_text().strip()
            адрес = ячейки[-1] if ячейки else ''
            cands.append(Candidate(name=имя, address=адрес, ref=ссылка))
        return cands

    def следующая_страница(self) -> bool:
        try:
            ссылка = self.page.locator("a:has-text('Volgende'), a:has-text('volgende')").first
            if ссылка.count() and ссылка.is_visible():
                ссылка.click()
                self.page.wait_for_load_state('networkidle')
                return True
        except Exception:
            pass
        return False

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        cand.ref.click()
        self.page.wait_for_load_state('networkidle')

    def check(self, c: Company) -> tuple[bool, str]:
        text = self.page.inner_text('body')
        m = re.search('Status:\\s*([^\\n]+)', text, re.I)
        статус = (m.group(1) if m else '').strip().lower()
        m2 = re.search('Rechtstoestand:\\s*([^\\n]+)', text, re.I)
        состояние = (m2.group(1) if m2 else '').strip().lower()
        if 'actief' not in статус:
            return (False, f"статус не Actief ({статус or '—'})")
        if состояние and 'normale toestand' not in состояние:
            return (False, f'Rechtstoestand: {состояние}')
        return (True, '')

    def данные_реестра(self) -> dict:
        """"""
        text = self.page.inner_text('body')
        m = re.search('Adres van de zetel:\\s*(.+?)(?:Sinds |Telefoonnummer|Type entiteit|\\n\\s*\\n)', text, re.I | re.S)
        адрес = re.sub('\\s+', ' ', m.group(1)).strip() if m else ''
        n = re.search('Naam:\\s*([^\\n]+)', text, re.I)
        return {'имя': n.group(1).strip() if n else '', 'адрес': адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
