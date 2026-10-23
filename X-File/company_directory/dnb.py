""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urljoin
from .browser import Browser
from .browser import HumanGate
from .data.countries import to_name
from .data.address_rules import разобрать, штат
from .models import Firm
BASE = "https://www.dnb.com"
DIRECTORY = f"{BASE}/business-directory.html"
KILL_POPUPS_JS = ""
_НЕ_САЙТ = [
    ln.strip().lower()
    for ln in (Path(__file__).parent / "data" / "not_a_website.txt")
        .read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.startswith("#")
]
def это_сайт_фирмы(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http") or "dnb.com" in u or "dnbcountryrisk" in u:
        return False
    return not any(d in u for d in _НЕ_САЙТ)
class DnB:
    ПОЛЕ_ПОИСКА = (
        'input[placeholder*="Search by company name" i], '
        'input[placeholder="Search here...."], '
        'input[placeholder*="Search" i]:visible'
    )
    ПОЛЕ_СТРАНЫ = (
        '#us-bd-country-input, '
        'input[placeholder*="Country" i], '
        'input.us-bd-filter__input'
    )
    БЛОК_КАРТОЧКИ = ".cip-info-rows, #company_profile_snapshot"
    def __init__(self, br: Browser, human: HumanGate, log=print):
        self.br = br
        self.human = human
        self.page = br.page
        self.log = log
    def _kill_popups(self) -> None:
        try:
            pass  # Keep site security and consent overlays intact.
        except Exception:
            pass
    def _закрыть_попапы(self, ждать: bool = False) -> None:
        ""
        if ждать:
            try:
                self.page.wait_for_selector("#truste-consent-button",
                                            state="visible", timeout=8000)
            except Exception:
                pass
        for сел in ("#truste-consent-button",
                    "button:has-text('Agree & Proceed')",
                    "#onetrust-accept-btn-handler",
                    "button:has-text('Accept All')"):
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click()
                    self.page.wait_for_timeout(600)
            except Exception:
                continue
        for наб in (self.page.get_by_label("Close"),
                    self.page.locator("[aria-label='Close'], button[title='Close']")):
            try:
                for i in range(min(наб.count(), 10)):
                    try:
                        э = наб.nth(i)
                        if э.is_visible():
                            э.click(timeout=2000)
                            self.page.wait_for_timeout(250)
                    except Exception:
                        continue
            except Exception:
                continue
        self._kill_popups()
    _адрес_выдачи: str = ""
    _слово_выдачи: str = ""
    _страна_выдачи: str = ""
    def сменить_слово(self, keyword: str, country: str) -> bool:
        ""
        from urllib.parse import quote
        if (not self._адрес_выдачи or not self._слово_выдачи
                or to_name(country) != self._страна_выдачи):
            return False
        старое = quote(self._слово_выдачи)
        адрес = self._адрес_выдачи.replace(
            f"BusinessDirectorySearch={старое}",
            f"BusinessDirectorySearch={quote(keyword)}")
        if "BusinessDirectorySearch=" not in адрес or адрес == self._адрес_выдачи:
            return False
        try:
            self.log(f"  · быстрый переход на «{keyword}» (страна остаётся)")
            self.page.goto(адрес, wait_until="domcontentloaded", timeout=45000)
            try:
                self.page.wait_for_function(
                    "() => document.querySelectorAll('table tr').length > 1",
                    timeout=10000)
            except Exception:
                pass
            self.page.wait_for_timeout(400)
        except Exception as e:
            self.log(f"  · быстрый переход не вышел ({type(e).__name__})")
            return False
        if not self.rows():
            self.log("  · по быстрому адресу пусто — проверю длинным путём")
            return False
        ок, пояснение = self.страна_выдачи_совпадает(to_name(country))
        if not ок:
            self.log(f"  · после быстрого перехода страна не та ({пояснение})")
            return False
        self._адрес_выдачи, self._слово_выдачи = адрес, keyword
        return True
    def search(self, keyword: str, country: str) -> bool:
        self.log("  · открываю dnb.com/business-directory…")
        self.page.goto(DIRECTORY, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(1500)
        self.br.check_captcha(keyword)
        self._закрыть_попапы(ждать=True)
        try:
            поле = self.page.locator(self.ПОЛЕ_ПОИСКА).first
            поле.wait_for(state="visible", timeout=15000)
            поле.click()
            поле.fill(keyword)
            self.log(f"  · вбил «{keyword}», жму Search")
            self.page.get_by_role("button", name="Search", exact=True).click(timeout=8000)
        except Exception as e:
            self.log(f"  · поиск не сработал ({type(e).__name__}) — зову человека")
            self.human.stuck(
                "вбей слово в строку поиска, нажми Search и «Продолжить».",
                keyword)
        self.page.wait_for_timeout(2500)
        self._закрыть_попапы()
        self.br.check_captcha()
        self.log(f"  · выбираю страну: {to_name(country)}")
        предложена = self._выбрать_страну(to_name(country))
        self._чип_или_выдача(to_name(country))
        if not предложена:
            return False
        self.log("  · страна применена, читаю фирмы")
        try:
            self._адрес_выдачи = self.page.url
            self._слово_выдачи = keyword
            self._страна_выдачи = to_name(country)
        except Exception:
            self._адрес_выдачи = ""
        return True
    def _выбрать_страну(self, name: str) -> bool:
        ""
        try:
            поле = self.page.locator(self.ПОЛЕ_СТРАНЫ).first
            if not поле.count():
                self.log("  · поля страны на странице нет")
                return False
            поле.click(timeout=6000)
            поле.fill(name, timeout=6000)
            self.page.wait_for_timeout(2500)
            кнопка = self.page.get_by_role(
                "button", name=re.compile(rf"^{re.escape(name)}\s*\(\d[\d\s]*\)", re.I)
            ).first
            if кнопка.count() and кнопка.is_visible():
                кнопка.click(timeout=6000)
                self.page.wait_for_timeout(3000)
                self._kill_popups()
                return True
            зап = self.page.locator(
                f"button:has-text('{name}'), [role='option']:has-text('{name}')").first
            if зап.count() and зап.is_visible():
                зап.click(force=True, timeout=6000)
                self.page.wait_for_timeout(3000)
                self._kill_popups()
                return True
            self.log(f"  · «{name}» в подсказке не предложена — по слову в этой "
                     f"стране фирм нет")
            return False
        except Exception as e:
            self.log(f"  · сам страну не выбрал ({type(e).__name__})")
            return False
    def _чип_или_выдача(self, name: str) -> None:
        ""
        if not self._страна_применена(name):
            self.log(f"  · чипа «{name}» не видно — проверю по самой выдаче")
        self._kill_popups()
    def _страна_применена(self, name: str) -> bool:
        ""
        try:
            чип = self.page.locator(
                f"[class*='chip']:has-text('{name}'), [class*='tag']:has-text('{name}'), "
                f"[class*='pill']:has-text('{name}'), "
                f"[class*='selected']:has-text('{name}')").first
            return bool(чип.count() and чип.is_visible())
        except Exception:
            return False
    СИНОНИМЫ_СТРАН = {
        "czech republic": ("czech republic", "czechia"),
        "united kingdom": ("united kingdom", "great britain"),
        "united states": ("united states", "usa"),
        "netherlands":   ("netherlands", "holland"),
    }
    def страна_выдачи_совпадает(self, name: str, порог: float = 0.8) -> tuple[bool, str]:
        ""
        строки = self.rows()
        if not строки:
            return False, "в выдаче нет строк"
        варианты = self.СИНОНИМЫ_СТРАН.get(name.lower(), (name.lower(),))
        свои = sum(1 for f in строки
                   if any(в in (f.address or "").lower() for в in варианты))
        доля = свои / len(строки)
        чужая = next((f.address for f in строки
                      if not any(в in (f.address or "").lower() for в in варианты)), "")
        пояснение = f"{свои} из {len(строки)} строк — «{name}»"
        if чужая:
            пояснение += f"; чужая строка: «{чужая[:50]}»"
        return доля >= порог, пояснение
    СТРОКА_ВЫДАЧИ = ".search-result-flex-row"
    ЯЧЕЙКА_ВЫДАЧИ = ".search-result-flex-cell"
    МУСОР_В_ИМЕНИ = ("Business Credit Reports", "View D-U-N-S® Number",
                     "View D-U-N-S Number", "Company Profile")
    def rows(self) -> list[Firm]:
        ""
        out: list[Firm] = []
        строки = self.page.locator(self.СТРОКА_ВЫДАЧИ).all()
        if not строки:
            строки = self.page.locator("table tbody tr, .search-results tr").all()
        for row in строки:
            ссылка = row.locator("a[href*='/business-directory/company-profiles']").first
            if not ссылка.count():
                continue
            имя = ссылка.inner_text().strip()
            href = ссылка.get_attribute("href") or ""
            if not имя or not href:
                continue
            for м in self.МУСОР_В_ИМЕНИ:
                имя = имя.replace(м, " ")
            имя = re.sub(r"\s+", " ", имя).strip()
            if not имя:
                continue
            ячейки = row.locator(self.ЯЧЕЙКА_ВЫДАЧИ).all() or row.locator("td").all()
            def текст(i: int) -> str:
                try:
                    return ячейки[i].inner_text().strip().replace("\n", " ") \
                        if len(ячейки) > i else ""
                except Exception:
                    return ""
            отрасль, тип, страна_город = текст(1), текст(2), текст(3)
            город, индекс = _город_индекс(страна_город)
            out.append(Firm(
                name=имя, industry=отрасль, location_type=тип,
                city=город, zip_code=индекс, address=страна_город,
                url=urljoin(BASE, href),
            ))
        return out
    def строк_в_таблице(self) -> int:
        ""
        try:
            n = self.page.locator(self.СТРОКА_ВЫДАЧИ).count()
            if not n:
                n = self.page.locator("table tbody tr, .search-results tr").count()
            return n
        except Exception:
            return 0
    def next_page(self) -> bool:
        ""
        try:
            было = self._первая_фирма()
            for sel in ["button:has-text('Next')", "a:has-text('Next')",
                        "a[aria-label*='Next' i]", "[aria-label*='next' i]",
                        "a[rel='next']", "li.next a", ".next-page", "button.next",
                        ".pagination a:has-text('>')", "a:has-text('>')"]:
                nxt = self.page.locator(sel).first
                if not nxt.count():
                    continue
                try:
                    nxt.scroll_into_view_if_needed(timeout=3000)
                    self.page.wait_for_timeout(300)
                except Exception:
                    continue
                if nxt.is_visible() and nxt.is_enabled():
                    nxt.click(force=True)
                    for _ in range(40):
                        self.page.wait_for_timeout(500)
                        сейчас = self._первая_фирма()
                        if сейчас and сейчас != было:
                            self._kill_popups()
                            return True
                    self.log("  · нажал «Next», но выдача не сменилась за 20 с")
                    return False
        except Exception:
            pass
        return False
    def _первая_фирма(self) -> str:
        ""
        try:
            строки = self.page.locator(self.СТРОКА_ВЫДАЧИ)
            if not строки.count():
                строки = self.page.locator("table tbody tr, .search-results tr")
            for i in range(min(строки.count(), 10)):
                ссылка = строки.nth(i).locator(
                    "a[href*='/business-directory/company-profiles']").first
                if ссылка.count():
                    имя = ссылка.inner_text().strip()
                    if имя:
                        return имя
        except Exception:
            pass
        return ""
    def enrich_website(self, f: Firm, geo: str) -> Firm:
        ""
        page = self.br.ctx.new_page()
        try:
            page.goto(f.url, wait_until="domcontentloaded", timeout=25000)
            сел = self.БЛОК_КАРТОЧКИ.replace("'", "\\'")
            ЕСТЬ_АДРЕС = ("() => {const e=document.querySelector('" + сел + "');"
                          "return e && /Address:\\s*\\S/i.test(e.innerText);}")
            ЕСТЬ_САЙТ = ("() => {const e=document.querySelector('" + сел + "');"
                         "return e && /Website:\\s*\\S/i.test(e.innerText);}")
            for условие, предел in ((ЕСТЬ_АДРЕС, 8000), (ЕСТЬ_САЙТ, 2500)):
                try:
                    page.wait_for_function(условие, timeout=предел)
                except Exception:
                    pass
            имя = f.name
            снимок = ""
            try:
                бл = page.locator(self.БЛОК_КАРТОЧКИ).first
                if бл.count():
                    снимок = бл.inner_text()
            except Exception:
                снимок = ""
            website = ""
            mw = re.search(r"Website:\s*(\S+)", снимок, re.I)
            if mw:
                w = mw.group(1).strip().rstrip(".,;)")
                website = w if w.startswith("http") else "http://" + w
            if not это_сайт_фирмы(website):
                подпись = page.locator("text=/Website:?/i").first
                if подпись.count():
                    a = подпись.locator("xpath=following::a[1]").first
                    if a.count():
                        website = a.get_attribute("href") or ""
            есть_сайт = это_сайт_фирмы(website)
            сырой_адрес = ""
            ma = re.search(
                r"Address:\s*(.+?)(?:\n\s*(?:Website|Phone|Employees|Industry|"
                r"Doing Business|Key Principal|See Other Location)|\n\s*\n|$)",
                снимок, re.I | re.S)
            if ma:
                сырой_адрес = re.sub(r"\s+", " ", ma.group(1)).strip(" ,")
            if not сырой_адрес:
                сырой_адрес = f.address
            f.name = имя
            if есть_сайт:
                f.website = website
                сайт_кратко = re.sub(r"^https?://", "", website).rstrip("/")
                f.payment_profile = (
                    f"{имя}\nAddress: {сырой_адрес}\nWebsite: {сайт_кратко}")
                if сырой_адрес:
                    r = разобрать(сырой_адрес, geo)
                    f.address = r.улица or сырой_адрес
                    f.city = r.город or f.city
                    f.zip_code = r.индекс or f.zip_code
                    f.state = штат(сырой_адрес, geo, r.город, r.индекс)
            else:
                f.website = ""
                f.address = сырой_адрес
                if имя:
                    f.payment_profile = (f"{имя}\nAddress: {сырой_адрес}"
                                         if сырой_адрес else имя)
                if сырой_адрес:
                    r = разобрать(сырой_адрес, geo)
                    f.city = f.city or r.город
                    f.zip_code = f.zip_code or r.индекс
                    f.state = f.state or штат(сырой_адрес, geo, r.город, r.индекс)
            return f
        except Exception:
            return f
        finally:
            page.close()
def _город_индекс(текст: str) -> tuple[str, str]:
    ""
    индекс = ""
    m = re.search(r"\b([A-Z]{0,2}[-\s]?\d{4,6}(?:-\d{4})?)\b", текст)
    if m:
        индекс = m.group(1).strip()
    части = [p.strip() for p in текст.split(",") if p.strip()]
    город = части[0] if части else ""
    return город, индекс
