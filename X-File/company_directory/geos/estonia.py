""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
ROOT = 'https://ariregister.rik.ee'
BASE = f'{ROOT}/eng'
ФОРМЫ = {'ou', 'oü', 'oy', 'as', 'a/s', 'mtu', 'mtü', 'tuh', 'tüh', 'uu', 'uü', 'fie', 'sa', 'tu', 'tü', 'ky', 'kü', 'osauhing', 'osaühing', 'aktsiaselts', 'tulundusuhistu', 'tulundusühistu', 'sihtasutus', 'mittetulundusuhing', 'mittetulundusühing', 'ltd', 'llc', 'inc', 'corp', 'co', 'gmbh'}

def без_формы(имя: str) -> str:
    """"""
    слова = [с for с in re.split('\\s+', (имя or '').strip()) if с]

    def форма(с: str) -> bool:
        return с.strip('.,«»"\'').lower() in ФОРМЫ
    while слова and форма(слова[0]):
        слова.pop(0)
    while слова and форма(слова[-1]):
        слова.pop()
    return ' '.join(слова).strip() or (имя or '').strip()

class Estonia(GeoDriver):
    code, title = ('EE', 'Эстония')
    url = BASE
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.код = ''

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(BASE)
        поле = self.page.locator("#company_search, input[name='name_or_code']").first
        запрос = без_формы(c.name)
        if запрос != c.name:
            self.log(f'  · EE: ищу без правовой формы — «{запрос}»')
        поле.fill(запрос)
        self.page.locator("button.btn-search, button[aria-label='Search']").first.click()
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(800)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()
    НЕ_ВЫДАЧА = '.ar__subheader, .ar__subheader__recent_search, header, footer, nav'

    def кандидаты_страницы(self) -> list[Candidate]:
        """"""
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("a[href*='/company/']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            try:
                if ссылка.evaluate(f'e => !!e.closest({self.НЕ_ВЫДАЧА!r})'):
                    continue
            except Exception:
                pass
            href = ссылка.get_attribute('href') or ''
            m = re.search('/company/(\\d+)', href)
            if not m or m.group(1) in виденные:
                continue
            имя = ссылка.inner_text().strip()
            if not имя or имя.lower() in ('in english', 'eesti keel'):
                continue
            текст, адрес = (имя, '')
            узел = ссылка
            for _ in range(6):
                узел = узел.locator('xpath=..')
                try:
                    текст = узел.inner_text()
                except Exception:
                    break
                ma = re.search('([^\\n]*(?:maakond|linn|vald)[^\\n]*)', текст)
                if ma:
                    адрес = re.sub('\\s*Open map\\s*$', '', ma.group(1)).strip()
                    break
                if len(текст) > 400:
                    break
            if re.search('\\bDeleted\\b', текст, re.I):
                self.log(f'  · EE: «{имя}» удалена из реестра — пропускаю')
                continue
            if re.search('\\bDeletion warning\\b', текст, re.I):
                self.log(f'  · EE: «{имя}» — стоит Deletion warning, беру и проверю на карточке')
            виденные.add(m.group(1))
            cands.append(Candidate(name=имя, address=адрес, url=href, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        """"""
        if cand.ref == 'HUMAN':
            self.код = self._код_из_url(self.page.url) or self.код
            return
        url = str(cand.ref)
        self.код = self._код_из_url(url) or self.код
        self.br.goto(url if url.startswith('http') else ROOT + url)
        self.page.wait_for_load_state('networkidle')
        self.код = self._код_из_url(self.page.url) or self.код

    @staticmethod
    def _код_из_url(url: str) -> str:
        m = re.search('/company/(\\d{6,9})', url or '')
        return m.group(1) if m else ''

    def check(self, c: Company) -> tuple[bool, str]:
        text = self.page.inner_text('body')
        low = text.lower()
        статус = self._поле(text, 'Status').lower()
        if 'entered into the register' not in статус:
            return (False, f"статус: {статус or '—'}")
        if any((w in статус for w in ('liquidation', 'bankrupt', 'deleted'))):
            return (False, f'статус: {статус}')
        for флаг, причина in (('non-submitted annual report', 'не сданы годовые отчёты'), ('unpaid fine', 'неоплаченные штрафы')):
            if флаг in low:
                self.log(f'  · {c.name}: {причина} — беру всё равно, фирма активна')
                break
        for флаг, причина in (('deletion warning', 'предупреждение об удалении'), ('a deletion notice concerning', 'уведомление об удалении')):
            if флаг in low:
                self.log(f'  · {c.name}: {причина} — беру, фирма ещё в реестре')
                break
        h = self.page.locator('.header-name-print').first
        имя = h.inner_text().strip() if h.count() else c.name
        self.имя = re.sub('\\s*\\(\\d+\\)\\s*$', '', имя).strip()
        self.код = self._код_из_url(self.page.url) or re.sub('\\D', '', self._поле(text, 'Registry code')) or self.код
        ma = re.search('([^\\n]*(?:maakond|linn|vald)[^\\n]*\\d{4,5})', text)
        self.адрес = ma.group(1).strip() if ma else ''
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'{re.escape(подпись)}\\s*\\n\\s*([^\\n]+)', текст, re.I)
        return m.group(1).strip() if m else ''

    def номер(self) -> str:
        return self.код

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
