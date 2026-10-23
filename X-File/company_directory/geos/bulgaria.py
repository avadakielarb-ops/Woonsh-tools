""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate, адрес_похож
from company_directory.core.models import Company
from company_directory.geos.base import GeoDriver
from company_directory.geos.translit_bg import транслит, транслит_адрес, запомнить, _ядро
PORTAL = 'https://portal.registryagency.bg/CR/en'
SEARCH = f'{PORTAL}/reports/VerificationPersonOrg'
EXTRACT = f'{PORTAL}/Reports/ActiveConditionTabResult?uic='
_ФОРМА_КИР = {'eood': 'ЕООД', 'ood': 'ООД', 'ead': 'ЕАД', 'ad': 'АД', 'et': 'ЕТ', 'kd': 'КД', 'kda': 'КДА', 'sd': 'СД', 'dzzd': 'ДЗЗД', 'ltd': 'ООД', 'llc': 'ООД', 'limited': 'ООД', 'jsc': 'АД', 'plc': 'АД', 'inc': 'АД', 'corp': 'АД'}
_ФОРМЫ_КИР_ВСЕ = {'еоод', 'оод', 'еад', 'ад', 'ет', 'кд', 'кда', 'сд', 'дззд'}

def _форма_dnb(имя: str) -> str:
    """"""
    слова = re.sub('[«»\\"\'`.,]', ' ', (имя or '').lower()).split()
    return _ФОРМА_КИР.get(слова[-1], '') if слова else ''

def _форма_канд(имя: str) -> str:
    """"""
    слова = re.sub('[«»\\"\'`.,]', ' ', (имя or '').lower()).split()
    for w in reversed(слова):
        if w in _ФОРМЫ_КИР_ВСЕ:
            return w.upper()
    return ''

def подобрать_по_форме(cands: list, log_ядро: str, форма_кир: str) -> list:
    """"""
    from company_directory.geos.bulgaria import _норм_bg
    точные = [k for k in cands if _норм_bg(k.name) == log_ядро]
    if len(точные) <= 1:
        return точные
    if форма_кир:
        по_форме = [k for k in точные if _форма_канд(k.name) == форма_кир]
        if по_форме:
            return по_форме
    return точные

def bg_имя_адрес(c: Company) -> tuple[str, str, bool]:
    """"""
    полный_адрес = ', '.join((x for x in (c.address, c.city, c.zip_code) if x))
    имя, уверенно = транслит(c.name)
    return (имя, транслит_адрес(полный_адрес), уверенно)

def _норм_bg(имя: str) -> str:
    """"""
    return _ядро(имя)

class Bulgaria(GeoDriver):
    code, title = ('BG', 'Болгария')
    url = SEARCH
    method = 'print'
    номер_regex = '\\b(\\d{13}|\\d{9})\\b'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.uic = ''
        self.bg_name = ''
        self.имя_реестра = ''
        self.адрес_реестра = ''

    def search(self, c: Company) -> list[Candidate]:
        self.имя = c.name
        self.адрес = ', '.join((x for x in (c.address, c.city, c.zip_code) if x))
        еик = str(c.extra.get('eik') or '').strip()
        if еик.isdigit() and len(еик) in (9, 13):
            self.uic = еик
            self.bg_name = (c.extra.get('bg_name') or '').strip()
            self.log_ядро = ''
            return [Candidate(name=c.name, address=self.адрес, ref=еик)]
        self.bg_name = (c.extra.get('bg_name') or транслит(c.name)[0]).strip()
        log_ядро = _норм_bg(self.bg_name)
        self.br.goto(f'{SEARCH}?count=0&includeHistory=true&name={quote(self.bg_name)}&page=1&pageSize=25&selectedSearchFilter=1')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(1500)
        self._подожди_лимит(c.name)
        self.br.check_captcha(c.name)
        cands = self.кандидаты_страницы()
        if not cands:
            cands = self._поиск_формой()
        if not cands:
            self.human.stuck(f'по «{self.bg_name}» реестр ничего не показал. Найди фирму руками (кириллицей, без формы), открой её и нажми «Продолжить».', c.name)
            return [Candidate(name=self.bg_name, address='', ref='HUMAN')]
        точные = подобрать_по_форме(cands, log_ядро, _форма_dnb(c.name))
        if len(точные) <= 1:
            return точные or cands
        bg_addr = c.extra.get('bg_addr', '') or self.адрес
        if bg_addr:
            for k in точные[:4]:
                адр = self._адрес_карточки(str(k.ref))
                if адр and адрес_похож(bg_addr, адр):
                    return [k]
        return точные

    def _адрес_карточки(self, uic: str) -> str:
        """"""
        try:
            self.br.goto(f'{EXTRACT}{uic}')
            self.page.wait_for_load_state('networkidle')
            self._подожди_лимит()
            txt = self.page.inner_text('body')
        except Exception:
            return ''
        m = re.search('5\\.\\s*Head office[^\\n]*\\n(.*?)(?:\\n\\s*\\d+\\.\\s|\\Z)', txt, re.I | re.S)
        return re.sub('\\s+', ' ', m.group(1)).strip() if m else ''

    def _лимит(self) -> bool:
        try:
            низ = self.page.inner_text('body').lower()
        except Exception:
            return False
        return 'maximum number of requests' in низ or ('максим' in низ and 'заявк' in низ)

    def _подожди_лимит(self, company: str='') -> None:
        """"""
        попыток = 0
        while self._лимит() and попыток < 3:
            попыток += 1
            self.page.wait_for_timeout(20000)
            try:
                self.page.reload()
                self.page.wait_for_load_state('networkidle')
            except Exception:
                pass
        if self._лимит():
            self.human.stuck('реестр Болгарии ограничил число запросов («Reached maximum number of requests»). Подожди ~минуту (можно обновить страницу) и нажми «Продолжить».', company)
            try:
                self.page.reload()
                self.page.wait_for_load_state('networkidle')
            except Exception:
                pass

    def _поиск_формой(self) -> list[Candidate]:
        try:
            self.br.goto(SEARCH)
            self.page.wait_for_timeout(800)
            try:
                self.page.get_by_text('Legal entity', exact=True).first.click(timeout=3000)
            except Exception:
                pass
            поле = self.page.get_by_label('Company/name')
            if not поле.count():
                поле = self.page.get_by_placeholder('Company/name')
            поле.first.fill(self.bg_name, timeout=6000)
            try:
                self.page.get_by_role('button', name='Search').first.click(timeout=5000)
            except Exception:
                поле.first.press('Enter')
            self.page.wait_for_load_state('networkidle')
            self.page.wait_for_timeout(1500)
            self._подожди_лимит()
            return self.кандидаты_страницы()
        except Exception:
            return []

    def кандидаты_страницы(self) -> list[Candidate]:
        """"""
        cands: list[Candidate] = []
        виденные: set[str] = set()
        строки = self.page.get_by_role('row')
        for i in range(min(строки.count(), 60)):
            row = строки.nth(i)
            try:
                текст = row.inner_text()
            except Exception:
                continue
            m = re.search('\\b(\\d{9})\\b', текст)
            if not m:
                continue
            uic = m.group(1)
            if uic in виденные:
                continue
            виденные.add(uic)
            ссылка = row.get_by_role('link').first
            имя = ссылка.inner_text().strip() if ссылка.count() else текст.split('\n')[0].strip()
            cands.append(Candidate(name=имя, address='', ref=uic))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            текст = ''
            try:
                текст = self.page.inner_text('body')
            except Exception:
                pass
            m = re.search('uic=(\\d{9})', self.page.url) or re.search('\\b(\\d{9})\\b', текст)
            self.uic = m.group(1) if m else ''
            if self.uic:
                self.br.goto(f'{EXTRACT}{self.uic}')
                self.page.wait_for_load_state('networkidle')
            return
        self.uic = str(cand.ref)
        self.bg_name = cand.name or self.bg_name
        self.br.goto(f'{EXTRACT}{self.uic}')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_timeout(1000)

    def check(self, c: Company) -> tuple[bool, str]:
        try:
            текст = self.page.inner_text('body')
        except Exception:
            текст = ''
        низ = текст.lower()
        for плохо in ('в ликвидация', 'ликвидация', 'in liquidation', 'несъстоятелност', 'insolvency', 'bankrupt', 'заличен', 'заличаване', 'struck off', 'deleted'):
            if плохо in низ:
                return (False, f'статус-стоп: {плохо}')
        if not self.uic:
            m = re.search('\\b(\\d{9})\\b', текст)
            self.uic = m.group(1) if m else ''
        m2 = re.search('2\\.\\s*Company\\s*/?\\s*Name\\s*\\n\\s*([^\\n]+)', текст, re.I)
        if m2:
            self.имя_реестра = m2.group(1).strip()
            запомнить(c.name, self.имя_реестра)
        m5 = re.search('5\\.\\s*Head office[^\\n]*\\n(.*?)(?:\\n\\s*\\d+\\.\\s|\\Z)', текст, re.I | re.S)
        if m5:
            self.адрес_реестра = re.sub('\\s+', ' ', m5.group(1)).strip()
        return (True, '')

    def номер(self) -> str:
        return self.uic or super().номер()

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес, 'сайт': ''}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
