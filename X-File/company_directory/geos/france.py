""""""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from company_directory.core.matching import Candidate
from company_directory.core.models import Company
from company_directory.core.формы import проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://annuaire-entreprises.data.gouv.fr'

class France(GeoDriver):
    code, title = ('FR', 'Франция')
    url = f'{BASE}/rechercher'
    method = 'download'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.siren = ''
        self.siret = ''
        self.имя = ''
        self.адрес = ''

    def индекс_фирмы(self, c: Company) -> str:
        """"""
        прямой = re.sub('\\D', '', c.zip_code or '')[:5]
        if len(прямой) == 5:
            return прямой
        from part1.data.address_rules import разобрать
        разбор = разобрать(c.address or '', 'FR')
        return разбор.индекс if len(разбор.индекс or '') == 5 else ''

    def search(self, c: Company) -> list[Candidate]:
        """"""
        индекс = self.индекс_фирмы(c)
        ступени = []
        if индекс:
            ступени.append((f'&cp_dep={индекс}&cp_dep_type=cp', f'индекс {индекс}', ''))
            ступени.append((f'&cp_dep={индекс[:2]}&cp_dep_type=dep', f'департамент {индекс[:2]}', индекс[:2]))
        ступени.append(('', 'вся Франция', ''))
        for н, (фильтр, как, департамент) in enumerate(ступени):
            self.br.goto(f'{self.url}?terme={quote(c.name)}{фильтр}')
            self.page.wait_for_load_state('networkidle')
            if н == 0:
                self.br.check_captcha(c.name)
            cands = self._кандидаты()
            if департамент:
                свои = [к for к in cands if re.search(f'\\b{департамент}\\d{{3}}\\b', к.address or '')]
                if свои:
                    self.log(f'  · {как}: {len(свои)} шт. вместо всей Франции')
                    return свои
                cands = []
            if cands:
                if фильтр:
                    self.log(f'  · {как}: {len(cands)} шт. вместо всей Франции')
                else:
                    cands = self._по_городу(c, cands)
                return cands
            if н + 1 < len(ступени):
                self.log(f'  · по «{как}» пусто — пробую {ступени[н + 1][1]}')
        return []

    def _по_городу(self, c: Company, cands: list[Candidate]) -> list[Candidate]:
        """"""
        город = re.sub('[\\d\\s]+$', '', (c.city or '').strip()).upper()
        if len(город) < 3:
            return cands
        свои = [к for к in cands if город in (к.address or '').upper()]
        if свои and len(свои) < len(cands):
            self.log(f'  · по всей Франции {len(cands)} шт., из них в городе {город}: {len(свои)}')
            return свои
        return cands

    def _кандидаты(self) -> list[Candidate]:
        cands = []
        виденные: set[str] = set()
        for item in self.page.locator("a[href*='/entreprise/']").all()[:60]:
            название = (item.inner_text() or '').strip().split('\n')[0].strip()
            href = item.get_attribute('href') or ''
            if not название or not href:
                continue
            if re.match('^\\d+\\s+[ée]tablissement', название, re.I):
                continue
            m = re.search('(\\d{9})(?:\\D|$)', href)
            ключ = m.group(1) if m else href
            if ключ in виденные:
                continue
            виденные.add(ключ)
            адрес_блок = название
            anc = item
            for _ in range(6):
                anc = anc.locator('xpath=..')
                try:
                    t = anc.inner_text()
                except Exception:
                    break
                if re.search('\\b\\d{5}\\b', t):
                    адрес_блок = re.sub('\\s+', ' ', t).strip()
                    break
            cands.append(Candidate(name=название, address=адрес_блок, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            return
        url = cand.ref if cand.ref.startswith('http') else BASE + cand.ref
        self.br.goto(url)
        self.page.wait_for_load_state('networkidle')

    def check(self, c: Company) -> tuple[bool, str]:
        body = self.page.inner_text('body')
        if 'EN ACTIVITÉ' not in body.upper() and 'EN ACTIVITE' not in body.upper():
            return (False, 'нет статуса EN ACTIVITÉ')
        if 'RADIÉE' in body.upper() or 'LIQUIDATION' in body.upper():
            return (False, 'фирма закрыта / в ликвидации')
        mf = re.search('forme juridique est\\s+([^.\\n]+)', body, re.I)
        причина = проверить_форму('FR', mf.group(1) if mf else '')
        if причина:
            return (False, причина)
        m = re.search('(\\d{9})(?:\\D|$)', self.page.url)
        if not m:
            m = re.search('\\bSIREN\\b[^\\d]*(\\d[\\d\\s]{8,})', body)
        self.siren = re.sub('\\s', '', m.group(1))[:9] if m else ''
        ms = re.search('\\bSIRET\\b[^\\d]*(\\d[\\d\\s]{13,})', body)
        self.siret = re.sub('\\s', '', ms.group(1))[:14] if ms else self.siren + '00000' if self.siren else ''
        if not self.siren:
            return (False, 'не нашёл SIREN')
        return (True, '')

    def номер(self) -> str:
        return self.siren

    def данные_реестра(self) -> dict:
        """"""
        try:
            body = self.page.inner_text('body')
        except Exception:
            return {'имя': self.имя, 'адрес': self.адрес}
        h1 = self.page.locator('h1').first
        if h1.count() and h1.inner_text().strip():
            self.имя = h1.inner_text().strip()
        m = re.search('Adresse\\s*\\n\\s*([^\\n]+)', body, re.I)
        if not m:
            m = re.search('([^\\n]*\\b\\d{5}\\b[^\\n]*)', body)
        if m:
            self.адрес = re.sub('\\s+', ' ', m.group(1)).strip()
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
