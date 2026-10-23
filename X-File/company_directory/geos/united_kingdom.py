""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.browser import SkipCompany
from company_directory.core.matching import Candidate, normalize
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://find-and-update.company-information.service.gov.uk'
МЕСЯЦЫ = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
НУЖНЫЕ_ДОКУМЕНТЫ = ('incorporation', 'change of name', 'change company name', 'company name changed')

class UnitedKingdom(GeoDriver):
    code, title = ('UK', 'Британия')
    url = f'{BASE}/search/companies'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.number = ''
        self.имя = ''
        self.адрес = ''
        self.меняли_имя = False
        self._искомое = ''
        self._инкорп_имя = ''
        self._инкорп_док = None
        self._смены = []
        self._цепочка_полная = True
        self._история_прочитана = False

    def search(self, c: Company) -> list[Candidate]:
        self._искомое = c.name
        self.br.goto(f"{self.url}?q={c.name.replace(' ', '+')}")
        self.page.wait_for_load_state('domcontentloaded')
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        for item in self.page.locator('li.type-company').all():
            ссылка = item.locator("a[href^='/company/']").first
            if not ссылка.count():
                continue
            href = ссылка.get_attribute('href') or ''
            текст = item.inner_text()
            if 'dissolved' in текст.lower():
                continue
            имя = ссылка.inner_text().strip()
            m = re.search('Matching previous names:\\s*(.+?)(?:\\n\\d{6,8}\\b|Incorporated|Dissolved|$)', текст, re.I | re.S)
            прежние = tuple((x.strip() for x in m.group(1).split('\n') if x.strip())) if m else ()
            cands.append(Candidate(name=имя, address=текст, url=href, ref=href, aliases=прежние))
        return cands

    def следующая_страница(self) -> bool:
        try:
            nxt = self.page.locator("a:has-text('Next'), a[rel='next']").first
            if nxt.count():
                nxt.scroll_into_view_if_needed(timeout=3000)
                if nxt.is_visible() and nxt.is_enabled():
                    nxt.click()
                    self.page.wait_for_load_state('domcontentloaded')
                    return True
        except Exception:
            pass
        return False

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            m = re.search('/company/([^/?#]+)', self.page.url)
            self.number = m.group(1) if m else ''
            return
        m = re.search('/company/([^/?#]+)', str(cand.ref))
        self.number = m.group(1) if m else ''
        self.br.goto(f'{BASE}/company/{self.number}')
        self.page.wait_for_load_state('domcontentloaded')

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        low = текст.lower()
        статус = self._поле(текст, 'Company status')
        if 'active' not in статус.lower():
            return (False, f"статус не Active ({статус or '—'})")
        if 'overdue' in low:
            return (False, 'есть просрочка (overdue)')
        тип = self._поле(текст, 'Company type')
        причина = проверить_форму('UK', тип) or проверить_статус(тип)
        if причина:
            return (False, причина)
        h1 = self.page.locator('h1').first
        self.имя = h1.inner_text().strip() if h1.count() else ''
        self.адрес = self._поле(текст, 'Registered office address')
        self.меняли_имя = 'previous company names' in low
        self._инкорп_имя = self._старейшее_имя(текст) or self.имя
        self._собрать_документы()
        return (True, '')

    def _старейшее_имя(self, текст: str) -> str:
        """"""
        if 'Previous company names' not in текст:
            return ''
        блок = текст.split('Previous company names', 1)[-1]
        имена = [x.strip() for x in re.findall('([A-Z][^\\n]*?)\\s+\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{4}\\s*[-–]', блок)]
        имена = [x for x in имена if re.search('\\b(limited|ltd|plc)\\b', x, re.I)]
        return имена[-1] if имена else ''
    МАКС_СТРАНИЦ_ИСТОРИИ = 12

    def _собрать_документы(self) -> None:
        """"""
        self._инкорп_док, self._смены = (None, [])
        self._история_прочитана = False
        self.br.goto(f'{BASE}/company/{self.number}/filing-history')
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(800)
        фильтр_встал = self._включить_фильтр()
        страница = 1
        while страница <= self.МАКС_СТРАНИЦ_ИСТОРИИ:
            строки = self.page.locator('table#fhTable tr').all()
            if not строки:
                break
            for строка in строки:
                low = строка.inner_text().lower()
                if not any((k in low for k in НУЖНЫЕ_ДОКУМЕНТЫ)):
                    continue
                pdf = строка.locator("a:has-text('View PDF')").first
                href = pdf.get_attribute('href') or '' if pdf.count() else ''
                дата = self._дата(строка.inner_text())
                if 'incorporation' in low and 'change' not in low:
                    if href and (not self._инкорп_док):
                        self._инкорп_док = (дата, href)
                elif (дата, href) not in self._смены:
                    self._смены.append((дата, href))
            if self._инкорп_док:
                if страница > 1:
                    self.log(f'  · UK: Incorporation нашёлся на странице {страница}')
                break
            if not self._на_следующую():
                self._история_прочитана = фильтр_встал
                break
            страница += 1
        self.меняли_имя = self.меняли_имя or bool(self._смены)
        self._цепочка_полная = all((href for _, href in self._смены))

    def _включить_фильтр(self) -> bool:
        """"""
        try:
            галка = self.page.locator('#filter-category-incorporation')
            if not галка.count():
                return False
            if not галка.is_checked():
                галка.check()
                self.page.wait_for_timeout(1500)
            if 'category=incorporation' not in self.page.url:
                try:
                    self.page.evaluate("document.getElementById('filing-history-filter').submit()")
                    self.page.wait_for_load_state('domcontentloaded')
                    self.page.wait_for_timeout(1200)
                except Exception:
                    pass
            return 'category=incorporation' in self.page.url
        except Exception:
            return False

    def _на_следующую(self) -> bool:
        """"""
        try:
            for sel in ("a[rel='next']", "a:has-text('Next')", ".pager a:has-text('Next')"):
                ссылка = self.page.locator(sel).first
                if ссылка.count() and ссылка.is_visible():
                    ссылка.click()
                    self.page.wait_for_load_state('domcontentloaded')
                    self.page.wait_for_timeout(1000)
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'{re.escape(подпись)}\\s*\\n?\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.number

    def данные_реестра(self) -> dict:
        неполная = self.меняли_имя and (not self._цепочка_полная)
        return {'имя': self._инкорп_имя if неполная else self.имя, 'адрес': self.адрес, 'меняли_имя': self.меняли_имя, 'цепочка_неполная': неполная}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')

    @staticmethod
    def _дата(текст: str) -> tuple:
        """"""
        m = re.search('(\\d{1,2})\\s+([A-Za-z]{3})[a-z]*\\s+(\\d{4})', текст)
        if not m:
            return (9999, 12, 31)
        return (int(m.group(3)), МЕСЯЦЫ.get(m.group(2).lower(), 12), int(m.group(1)))
