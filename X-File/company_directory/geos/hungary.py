""""""
from __future__ import annotations
import re
from pathlib import Path
from company_directory.core.matching import Candidate, normalize
from company_directory.core.models import Company
from company_directory.core.формы import проверить_статус, проверить_форму
from company_directory.geos.base import GeoDriver
BASE = 'https://www.e-cegjegyzek.hu'
ПЛОХОЕ_ИМЯ = ('felszámolás', 'felszamolas', 'végelszámolás', 'vegelszamolas', 'kényszertörlés', 'kenyszertorles', 'csődeljárás', 'csodeljaras')

class Hungary(GeoDriver):
    code, title = ('HU', 'Венгрия')
    url = f'{BASE}/?cegkereses'
    method = 'print'

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ''
        self.адрес = ''
        self.cegjegyzek = ''

    def search(self, c: Company) -> list[Candidate]:
        self._заглушить_печать()
        self.br.goto(self.url)
        try:
            центр = self.page.locator('#kozep').first
            if центр.count():
                центр.click(timeout=2000)
        except Exception:
            pass
        self._cookie()
        try:
            поле = self.page.get_by_placeholder('név', exact=True).first
            поле.click()
            поле.fill(c.name)
            self.page.get_by_role('button', name='Keresés', exact=True).first.click()
        except Exception:
            self.human.stuck('вбей имя фирмы в «Cégnév kezdete», нажми Keresés и «Продолжить».', c.name)
        self.page.wait_for_timeout(1500)
        self.log('  · жду капчу (реши её и нажми «Продолжить»)')
        self._капча_и_дальше(c.name)
        cands = self.кандидаты_страницы()
        self.log(f'  · после капчи/условий вижу {len(cands)} фирм в выдаче')
        if not cands and (self._есть_условия() or self._есть_tovabb()):
            self.human.stuck('доведи шаг вручную: пролистай условия ВНИЗ, поставь галку «Felhasználási feltételek elfogadása», нажми Tovább, дождись списка фирм и нажми «Продолжить».', c.name)
            cands = self.кандидаты_страницы()
        return cands

    def _заглушить_печать(self) -> None:
        """"""
        if getattr(self, '_печать_заглушена', False):
            return
        try:
            self.page.add_init_script('window.print = function(){};')
            self._печать_заглушена = True
        except Exception:
            pass

    def _cookie(self) -> None:
        try:
            b = self.page.get_by_role('button', name='Elfogadom').first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    def _капча_и_дальше(self, фирма: str) -> None:
        """"""
        self.br.check_captcha(фирма, ждать_мс=10000)
        self._нажать_tovabb()
        self.page.wait_for_timeout(1000)
        if self._принять_условия():
            self._нажать_tovabb()
            self.page.wait_for_timeout(1000)

    def _есть_условия(self) -> bool:
        try:
            h = self.page.get_by_text('Felhasználási feltételek elfogadása').first
            return bool(h.count()) and h.is_visible()
        except Exception:
            return False

    def _есть_tovabb(self) -> bool:
        try:
            b = self.page.get_by_role('button', name='Tovább').first
            return bool(b.count()) and b.is_visible()
        except Exception:
            return False

    def _принять_условия(self) -> bool:
        """"""
        if not self._есть_условия():
            return False
        метка = self.page.get_by_text('Felhasználási feltételek elfogadása').first
        try:
            метка.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        self.page.wait_for_timeout(200)
        try:
            cb0 = self.page.locator('input[type=checkbox]:visible').last
            if cb0.count() and cb0.is_checked():
                return True
        except Exception:
            pass
        try:
            метка.click(timeout=2500)
        except Exception:
            try:
                метка.click(force=True, timeout=2500)
            except Exception:
                pass
        self.page.wait_for_timeout(300)
        try:
            cb = self.page.locator('input[type=checkbox]:visible').last
            if cb.count() and (not cb.is_checked()):
                cb.check(force=True, timeout=2500)
        except Exception:
            pass
        return True

    def _нажать_tovabb(self) -> bool:
        """"""
        try:
            b = self.page.get_by_role('button', name='Tovább').first
            if b.count() and b.is_visible() and b.is_enabled():
                try:
                    b.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                b.click(timeout=3000)
                self.page.wait_for_timeout(700)
                return True
        except Exception:
            pass
        return False
    _ФОРМА_РЕ = re.compile('\\b(Kft|Zrt|Nyrt|Bt|Kkt|Rt|Kht|Kdt)\\b\\.?|\\bTársaság\\b', re.I)

    def кандидаты_страницы(self) -> list[Candidate]:
        """"""
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator('a')
        for i in range(min(ссылки.count(), 150)):
            ссылка = ссылки.nth(i)
            try:
                имя = (ссылка.inner_text() or '').strip().split('\n')[0].strip()
            except Exception:
                continue
            if not имя or len(имя) < 4:
                continue
            if not self._ФОРМА_РЕ.search(имя):
                continue
            блок = ссылка.locator("xpath=ancestor::*[contains(.,'Cégjegyzékszám')][1]")
            if not блок.count():
                continue
            try:
                текст = блок.inner_text()
            except Exception:
                continue
            if len(текст) > 900:
                continue
            mnum = re.search('\\b(\\d{2}-\\d{2}-\\d{6})\\b', текст)
            if not mnum or mnum.group(1) in виденные:
                continue
            виденные.add(mnum.group(1))
            href = (ссылка.get_attribute('href') or '').strip()
            ref = href if href and href != '#' and (not href.lower().startswith('javascript')) else 'CLICK'
            cands.append(Candidate(name=имя, address=re.sub('\\s+', ' ', текст).strip(), ref=ref))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == 'HUMAN':
            self.log('  · фирму выбрал человек')
            return
        ref = cand.ref
        if isinstance(ref, str) and ref.startswith('http'):
            self.br.goto(ref)
        else:
            self.log(f'  · кликаю по фирме: «{cand.name}»')
            self._кликнуть_результат(cand.name)
        try:
            self.page.wait_for_function('() => /\\d{2}-\\d{2}-\\d{6}/.test(document.body.innerText)', timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
        try:
            тело = self.page.inner_text('body')
            m = re.search('\\b\\d{2}-\\d{2}-\\d{6}\\b', тело)
            if m:
                self.log(f'  · открылась карточка (Cégjegyzékszám {m.group(0)})')
            else:
                загол = next((s.strip() for s in тело.split('\n') if s.strip()), '')[:50]
                self.log(f'  · это НЕ карточка, на экране: «{загол}…»')
        except Exception:
            pass

    def _кликнуть_результат(self, имя: str) -> None:
        """"""
        for тип, loc in (('link', self.page.get_by_role('link', name=имя)), ('text', self.page.get_by_text(имя, exact=False))):
            try:
                эл = loc.first
                if эл.count():
                    try:
                        эл.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    эл.click(timeout=6000)
                    self.log(f'  · клик по результату ({тип})')
                    return
            except Exception:
                continue
        self.log('  · НЕ нашёл ссылку результата для клика!')

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text('body')
        if not re.search('\\b\\d{2}-\\d{2}-\\d{6}\\b', текст):
            return (False, 'не карточка фирмы (нет Cégjegyzékszám) — открылась не та страница')
        до = [s.strip() for s in текст.split('Cégjegyzékszám')[0].split('\n') if s.strip()]
        полное = до[-1] if до else ''
        короткое = до[-2] if len(до) >= 2 else ''
        if not полное:
            h1 = self.page.locator('h1').first
            полное = h1.inner_text().strip() if h1.count() else c.name
        self.имя = полное or короткое or c.name
        низ = f'{полное} {короткое}'.lower()
        for плохо in ПЛОХОЕ_ИМЯ:
            if плохо in низ:
                return (False, f'в названии стоп-статус: {плохо}')
        причина = проверить_статус(self.имя) or проверить_форму('HU', self.имя)
        if причина:
            return (False, причина)
        self.cegjegyzek = self._поле(текст, 'Cégjegyzékszám')
        self.адрес = self._поле(текст, 'Székhely')
        return (True, '')

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(f'\\b{re.escape(подпись)}\\b:?\\s*\\n?\\s*([^\\n]+)', текст, re.I)
        if not m:
            return ''
        return re.sub('\\s*Térkép\\s*$', '', m.group(1)).strip()

    def номер(self) -> str:
        return self.cegjegyzek

    def данные_реестра(self) -> dict:
        return {'имя': self.имя, 'адрес': self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
