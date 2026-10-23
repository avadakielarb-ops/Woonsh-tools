""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
BASE = 'https://krs-pobierz.pl'

class Poland(GeoDriver):
    code, title = ('PL', 'Польша')
    url = f'{BASE}/'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.krs = ''

    def search(self, c: Company) -> list[Candidate]:
        for q in self._варианты_запроса(c.name):
            self.br.goto(f'{BASE}/szukaj?q={quote(q)}')
            self.page.wait_for_load_state('domcontentloaded')
            self._cookie()
            self.br.check_captcha(c.name)
            if self._на_карточке():
                return [self._карточка_как_кандидат()]
            cands = self.кандидаты_страницы()
            if cands:
                return cands
        return []

    def _на_карточке(self) -> bool:
        """"""
        try:
            return bool(self.page.locator('#basicDataTable').count()) and bool(self.page.locator("a:has-text('Pobierz odpis KRS')").count())
        except Exception:
            return False

    def _карточка_как_кандидат(self) -> Candidate:
        h1 = self.page.locator('h1').first
        имя = h1.inner_text().strip() if h1.count() else ''
        адрес = re.sub('\\s+', ' ', self._ячейка('Adres')).strip()
        url = self.page.url
        return Candidate(name=имя, address=адрес, url=url, ref=url)
    _ФОРМА = re.compile('\\s+(sp[oó]?[łl]ka\\s+z\\s+ograniczon[ąa]\\s+odpowiedzialno[śs]ci[ąa](\\s+sp[oó][łl]ka\\s+komandytowa)?|sp[oó][łl]ka\\s+komandytowo[-\\s]akcyjna|sp[oó][łl]ka\\s+komandytowa|sp[oó][łl]ka\\s+akcyjna|sp[oó][łl]ka\\s+jawna|sp[oó][łl]ka\\s+cywilna|sp[oó][łl]ka\\s+partnerska|sp\\.?\\s*z\\s*o\\.?\\s*o\\.?|sp\\.?\\s*z\\s*o\\s*o|s\\.?\\s*k\\.?\\s*a\\.?|sp\\.?\\s*k\\.?|sp\\.?\\s*j\\.?|sp\\.?\\s*p\\.?|s\\.?\\s*a\\.?|s\\.?\\s*c\\.?)\\s*$', re.I)

    def _без_формы(self, имя: str) -> str:
        s = (имя or '').strip()
        for _ in range(2):
            s2 = self._ФОРМА.sub('', s).strip()
            if s2 == s:
                break
            s = s2
        return s

    def _варианты_запроса(self, имя: str) -> list[str]:
        имя = (имя or '').strip()
        без_формы = self._без_формы(имя) or имя
        слова = без_формы.split()
        кандидаты = [без_формы]
        if len(слова) >= 3:
            кандидаты.append(' '.join(слова[:2]))
        if слова:
            кандидаты.append(слова[0])
        итог: list[str] = []
        for q in кандидаты:
            q = q.strip()
            if len(q) >= 2 and q not in итог:
                итог.append(q)
        return итог
    СЕЛЕКТОРЫ_COOKIE = ("button:has-text('Akceptuj wszystkie')", "button:has-text('Zaakceptuj wszystkie')", "button:has-text('Akceptuj')", "button:has-text('Zgadzam się')", "button:has-text('Zezwól na wszystkie')", '#onetrust-accept-btn-handler', '#truste-consent-button', "[id*='cookie'] button:has-text('Akcept')", "[class*='cookie'] button:has-text('Akcept')")

    def _cookie(self) -> None:
        """"""
        try:
            self.page.wait_for_selector(', '.join(self.СЕЛЕКТОРЫ_COOKIE), state='visible', timeout=6000)
        except Exception:
            pass
        for сел in self.СЕЛЕКТОРЫ_COOKIE:
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click(timeout=4000)
                    self.page.wait_for_timeout(600)
                    return
            except Exception:
                continue
        try:
            self.br.dismiss_popups()
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("a[href*='-i0']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            href = ссылка.get_attribute('href') or ''
            m = re.search('-i(\\d{6,})', href)
            if not m or m.group(1) in виденные:
                continue
            try:
                if ссылка.locator("xpath=ancestor::*[contains(., 'Polecane')]").count():
                    continue
            except Exception:
                pass
            имя = ссылка.inner_text().strip()
            if not имя:
                continue
            виденные.add(m.group(1))
            адрес = ''
            блок = ссылка.locator("xpath=ancestor::*[contains(.,'Adres')][1]")
            if блок.count():
                ma = re.search('Adres:\\s*([^\\n]+)', блок.inner_text())
                if ma:
                    адрес = ma.group(1).strip()
            cands.append(Candidate(name=имя, address=адрес, url=href, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        url = str(cand.ref)
        self.br.goto(url if url.startswith('http') else BASE + url)
        self.page.wait_for_load_state('domcontentloaded')
        self._cookie()

    def check(self, c: Company) -> tuple[bool, str]:
        статус = self._ячейка('Status').lower()
        if 'aktywna' not in статус:
            return (False, f"статус не aktywna ({статус or '—'})")
        h1 = self.page.locator('h1').first
        имя = h1.inner_text().strip() if h1.count() else ''
        if re.search('w likwidacji|w upad|wykreślon', имя, re.I):
            return (False, 'ликвидация / банкротство / вычеркнута')
        self.имя = имя
        self.krs = re.sub('\\D', '', self._ячейка('KRS'))
        self.адрес = re.sub('\\s+', ' ', self._ячейка('Adres')).strip()
        return (True, '')

    def _ячейка(self, подпись: str) -> str:
        """"""
        try:
            яч = self.page.locator(f"#basicDataTable tr:has(th:text-is('{подпись}')) td").first
            return яч.inner_text().strip() if яч.count() else ''
        except Exception:
            return ''

    def номер(self) -> str:
        return self.krs

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
