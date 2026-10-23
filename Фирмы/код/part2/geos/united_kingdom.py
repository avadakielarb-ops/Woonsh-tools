"""
БРИТАНИЯ — Companies House (find-and-update.company-information.service.gov.uk).

Поток ТОЧНО по инструкции пользователя:
  1. поиск по имени → вкладка Companies
  2. фирма могла ПЕРЕИМЕНОВЫВАТЬСЯ: в выдаче есть «Matching previous names».
     На DnB может стоять СТАРОЕ имя (AQUALECTRICS LTD), а в реестре текущее
     (AQUA LTD) — считаем это совпадением.
  3. карточка: Company status = Active, НЕТ «overdue» (Accounts / Confirmation
     statement), Company type ∈ {Private limited company, Public limited company}
  4. Filing history → category=incorporation → «View PDF» открывает НОВУЮ ВКЛАДКУ
     (кнопки «скачать» нет!) — забираем адрес PDF и качаем с сессией браузера
  5. Incorporation + все документы о смене имени → склеиваем в ОДИН PDF по
     возрастанию даты (Incorporation первым). Имя не менялось — только он.
     Склейка не вышла → папка с названием фирмы и отдельными файлами.

Файл называется ТЕКУЩИМ именем из реестра — по нему и подаём.
"""
from __future__ import annotations

import re
from pathlib import Path

from common.human import SkipCompany
from part2.core.matching import Candidate, normalize
from part2.core.models import Company
from part2.core.pdf_merge import склеить
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://find-and-update.company-information.service.gov.uk"

МЕСЯЦЫ = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

# Берём ТОЛЬКО эти документы. Фильтр «Incorporation» в URL сбрасывается скриптом
# сайта, поэтому не полагаемся на него — отбираем строки ПО ОПИСАНИЮ.
# Companies House описывает смену имени ТРЕМЯ способами (видели оба кейса):
#   • «Change of name by resolution»            (NM01)
#   • «Change company name resolution on …»     (RES15)
#   • «Company name changed …\certificate issued on …»  (CERTNM) — этот и упускался
НУЖНЫЕ_ДОКУМЕНТЫ = ("incorporation", "change of name",
                    "change company name", "company name changed")


class UnitedKingdom(GeoDriver):
    code, title = "UK", "Британия"
    url = f"{BASE}/search/companies"
    method = "download"

    # Типы: отсеиваем ТОЛЬКО 🔴 (CIC, limited by guarantee, dormant) —
    # см. part2/core/формы.py. Ltd/PLC/LLP/LP/partnership проходят.

    def __init__(self, br, human):
        super().__init__(br, human)
        self.number = ""
        self.имя = ""              # текущее имя из реестра
        self.адрес = ""
        self.меняли_имя = False
        self._искомое = ""
        self._инкорп_имя = ""       # старейшее имя (на момент регистрации)
        self._инкорп_док = None     # (дата, href) документа Incorporation
        self._смены = []            # [(дата, href|"" )] — смены имени; "" = не скачать
        self._цепочка_полная = True
        # историю просмотрели целиком (фильтр стоял, страницы кончились)?
        # От этого зависит, «нет Incorporation» — это факт или недосмотр.
        self._история_прочитана = False

    # ---------- поиск ----------

    def search(self, c: Company) -> list[Candidate]:
        self._искомое = c.name
        self.br.goto(f"{self.url}?q={c.name.replace(' ', '+')}")
        self.page.wait_for_load_state("domcontentloaded")
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        for item in self.page.locator("li.type-company").all():
            ссылка = item.locator("a[href^='/company/']").first
            if not ссылка.count():
                continue
            href = ссылка.get_attribute("href") or ""
            текст = item.inner_text()
            if "dissolved" in текст.lower():          # распущенные не берём
                continue

            # ИМЯ = ТЕКУЩЕЕ (ссылка). Прежние имена («Matching previous names»)
            # НЕ подставляем в имя — иначе фирма, у которой искомое имя лишь в
            # ПРОШЛОМ, ложно сравнивается с той, у кого оно СЕЙЧАС. Кладём их в
            # aliases: ядро сматчит по прежнему имени, только если по текущему
            # никто не подошёл.
            имя = ссылка.inner_text().strip()
            m = re.search(r"Matching previous names:\s*(.+?)(?:\n\d{6,8}\b|"
                          r"Incorporated|Dissolved|$)", текст, re.I | re.S)
            прежние = tuple(x.strip() for x in m.group(1).split("\n")
                            if x.strip()) if m else ()

            cands.append(Candidate(name=имя, address=текст, url=href,
                                   ref=href, aliases=прежние))
        return cands

    def следующая_страница(self) -> bool:
        try:
            nxt = self.page.locator("a:has-text('Next'), a[rel='next']").first
            if nxt.count():
                nxt.scroll_into_view_if_needed(timeout=3000)
                if nxt.is_visible() and nxt.is_enabled():
                    nxt.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    return True
        except Exception:
            pass
        return False

    # ---------- карточка ----------

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            m = re.search(r"/company/([^/?#]+)", self.page.url)
            self.number = m.group(1) if m else ""
            return
        m = re.search(r"/company/([^/?#]+)", str(cand.ref))
        self.number = m.group(1) if m else ""
        self.br.goto(f"{BASE}/company/{self.number}")
        self.page.wait_for_load_state("domcontentloaded")

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")
        low = текст.lower()

        статус = self._поле(текст, "Company status")
        if "active" not in статус.lower():
            return False, f"статус не Active ({статус or '—'})"

        # Companies House сам помечает просрочку словом «overdue»
        if "overdue" in low:
            return False, "есть просрочка (overdue)"

        тип = self._поле(текст, "Company type")
        причина = проверить_форму("UK", тип) or проверить_статус(тип)
        if причина:
            return False, причина

        # снимаем правду из реестра
        h1 = self.page.locator("h1").first
        self.имя = h1.inner_text().strip() if h1.count() else ""
        self.адрес = self._поле(текст, "Registered office address")
        self.меняли_имя = "previous company names" in low
        self._инкорп_имя = self._старейшее_имя(текст) or self.имя

        # разбираем Filing history: какие документы есть и ВСЕ ЛИ скачиваемы
        self._собрать_документы()
        return True, ""

    def _старейшее_имя(self, текст: str) -> str:
        """
        Из «Previous company names» берём САМОЕ СТАРОЕ имя (на момент регистрации).
        Таблица идёт от новых к старым — старейшее это последняя строка.
        """
        if "Previous company names" not in текст:
            return ""
        блок = текст.split("Previous company names", 1)[-1]
        имена = [x.strip() for x in re.findall(
            r"([A-Z][^\n]*?)\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s*[-–]", блок)]
        имена = [x for x in имена if re.search(r"\b(limited|ltd|plc)\b", x, re.I)]
        return имена[-1] if имена else ""

    МАКС_СТРАНИЦ_ИСТОРИИ = 12

    def _собрать_документы(self) -> None:
        """
        Filing history (Incorporation): собрать документ регистрации и все смены
        имени. Помечаем, какие смены имени НЕ скачать («Request Document» —
        «not currently available online») → цепочка неполная.

        ЛИСТАЕМ СТРАНИЦЫ. Incorporation — САМЫЙ СТАРЫЙ документ фирмы, а история
        отсортирована свежими вперёд. У фирмы с большим числом подач он уезжает
        на вторую-третью страницу, и прежняя версия, читавшая только первую,
        честно сообщала «нет документа Incorporation» — четыре фирмы за прогон.
        """
        self._инкорп_док, self._смены = None, []
        self._история_прочитана = False
        self.br.goto(f"{BASE}/company/{self.number}/filing-history")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(800)
        фильтр_встал = self._включить_фильтр()

        страница = 1
        while страница <= self.МАКС_СТРАНИЦ_ИСТОРИИ:
            строки = self.page.locator("table#fhTable tr").all()
            if not строки:
                break
            for строка in строки:
                low = строка.inner_text().lower()
                if not any(k in low for k in НУЖНЫЕ_ДОКУМЕНТЫ):
                    continue
                pdf = строка.locator("a:has-text('View PDF')").first
                href = (pdf.get_attribute("href") or "") if pdf.count() else ""
                дата = self._дата(строка.inner_text())
                if "incorporation" in low and "change" not in low:
                    if href and not self._инкорп_док:
                        self._инкорп_док = (дата, href)
                elif (дата, href) not in self._смены:
                    self._смены.append((дата, href))

            if self._инкорп_док:
                if страница > 1:
                    self.log(f"  · UK: Incorporation нашёлся на странице {страница}")
                break
            if not self._на_следующую():
                # Страницы кончились. Если фильтр при этом стоял — историю мы
                # видели ЦЕЛИКОМ, и «нет Incorporation» это факт, а не недосмотр.
                self._история_прочитана = фильтр_встал
                break
            страница += 1

        self.меняли_имя = self.меняли_имя or bool(self._смены)
        # цепочка полная = у ВСЕХ смен имени есть скачиваемый PDF
        self._цепочка_полная = all(href for _, href in self._смены)

    def _включить_фильтр(self) -> bool:
        """
        Поставить галочку «Incorporation» в фильтре истории.

        Фильтр применяется ИМЕННО ГАЛОЧКОЙ, а не параметром адреса: кнопка
        «Apply filter» (#submit-filter-by-category) скрыта классом js-hidden,
        сайт перезагружает список сам по изменению чекбокса. Параметр
        ?category=incorporation в адресе НЕ РАБОТАЕТ — проверено: у фирмы
        00901522 с ним всё равно шла полная история (отчёты, назначения,
        залоги), и Incorporation 1967 года лежал на десятках страниц.
        """
        try:
            галка = self.page.locator("#filter-category-incorporation")
            if not галка.count():
                return False
            if not галка.is_checked():
                галка.check()
                self.page.wait_for_timeout(1500)
            # если скрипт не сработал — отправляем форму руками
            if "category=incorporation" not in self.page.url:
                try:
                    self.page.evaluate(
                        "document.getElementById('filing-history-filter').submit()")
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(1200)
                except Exception:
                    pass
            return "category=incorporation" in self.page.url
        except Exception:
            return False

    def _на_следующую(self) -> bool:
        """
        Перейти на следующую страницу истории ССЫЛКОЙ САЙТА.

        Именно ссылкой, а не собранным адресом: своя ссылка несёт с собой
        включённый фильтр, а goto по «?category=…&page=N» его сбрасывает —
        на это я и наступил в первой версии.
        """
        try:
            for sel in ("a[rel='next']", "a:has-text('Next')",
                        ".pager a:has-text('Next')"):
                ссылка = self.page.locator(sel).first
                if ссылка.count() and ссылка.is_visible():
                    ссылка.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(1000)
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"{re.escape(подпись)}\s*\n?\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.number

    def данные_реестра(self) -> dict:
        # цепочка неполная → подаём по Incorporation: имя = старейшее (инкорп-имя)
        неполная = self.меняли_имя and not self._цепочка_полная
        return {"имя": (self._инкорп_имя if неполная else self.имя),
                "адрес": self.адрес, "меняли_имя": self.меняли_имя,
                "цепочка_неполная": неполная}

    # ---------- выписка ----------

    def fetch(self, c: Company, dest: Path) -> Path:
        # документы уже собраны в check() → _собрать_документы()
        if not self._инкорп_док:
            if self._история_прочитана:
                # Историю посмотрели ЦЕЛИКОМ (фильтр применён, страницы кончились),
                # а Incorporation в ней нет. У старых фирм Companies House просто
                # не выкладывает документ регистрации онлайн: у FRONERI (1967 г.)
                # самое раннее — смена имени 1997 года. Человек его тоже не найдёт,
                # поэтому не зовём: фирма непригодна, уйдёт в не_вышло.xlsx,
                # Часть 1 доберёт замену.
                self.log("  · UK: документа Incorporation нет онлайн "
                         "(старая фирма) — беру замену")
                raise SkipCompany("UK: Incorporation не выложен онлайн")
            self.human.stuck(
                "не нашёл документ Incorporation в Filing history.\n"
                "Скачай PDF вручную и нажми «Продолжить».", c.name)
            raise RuntimeError("UK: нет документа Incorporation")

        неполная = self.меняли_имя and not self._цепочка_полная
        if неполная:
            # цепочка смены имени НЕПОЛНАЯ (какой-то документ = «Request Document»):
            # склейка была бы недействительной → берём ТОЛЬКО Incorporation,
            # профиль/имя файла — по инкорпу (см. данные_реестра)
            документы = [self._инкорп_док]
        else:
            # полная цепочка (или имя не менялось): инкорп + все смены имени
            документы = [self._инкорп_док] + [(д, h) for д, h in self._смены if h]
        документы.sort(key=lambda x: x[0])        # Incorporation первым, дальше по годам

        файлы: list[Path] = []
        for i, (_, href) in enumerate(документы, 1):
            файлы.append(self._скачать(href, dest.parent / f"{dest.stem}__{i}.pdf", c.name))

        # имя не менялось — один файл
        if len(файлы) == 1:
            файлы[0].replace(dest)
            return dest

        # склеиваем по порядку
        итог = склеить(файлы, dest)
        if итог:
            for f in файлы:
                try:
                    f.unlink()
                except Exception:
                    pass
            return итог

        # склейка не вышла — папка с названием фирмы, файлы внутри (склеишь руками)
        папка = dest.parent / dest.stem
        папка.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(файлы, 1):
            f.replace(папка / f"{i}. {dest.stem}.pdf")
        return папка

    def _скачать(self, href: str, dest: Path, company: str) -> Path:
        """
        «View PDF» открывает НОВУЮ ВКЛАДКУ — качаем с сессией браузера.
        ОБЯЗАТЕЛЬНО проверяем, что пришёл настоящий PDF: сервер может отдать
        HTML-страницу, её нельзя ни сохранять, ни склеивать (склейка падала).
        """
        url = href if href.startswith("http") else BASE + href
        # (а) прямая загрузка (редирект на S3 отработает сам, куки те же)
        for вариант in (url, url.replace("download=0", "download=1")):
            if self._сохранить(вариант, dest):
                return dest
        # (б) открываем вкладку просмотра и берём её адрес
        try:
            with self.br.ctx.expect_page(timeout=20000) as новая:
                self.page.click(f"a[href='{href}']")
            вкладка = новая.value
            вкладка.wait_for_load_state("domcontentloaded")
            адрес = вкладка.url
            вкладка.close()
            if self._сохранить(адрес, dest):
                return dest
        except Exception:
            pass
        self.human.stuck(
            "не удалось скачать PDF Британии.\n"
            "Открой «View PDF», сохрани файл и нажми «Продолжить».", company)
        raise RuntimeError("UK: PDF не скачался")

    def _сохранить(self, url: str, dest: Path) -> bool:
        """Скачать и сохранить, только если это действительно PDF (%PDF в начале)."""
        try:
            resp = self.br.ctx.request.get(url)
            if not resp.ok:
                return False
            данные = resp.body()
            if not данные[:4] == b"%PDF":
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(данные)
            return True
        except Exception:
            return False

    @staticmethod
    def _дата(текст: str) -> tuple:
        """«03 Mar 2010» → (2010, 3, 3) для сортировки по возрастанию."""
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", текст)
        if not m:
            return (9999, 12, 31)
        return (int(m.group(3)), МЕСЯЦЫ.get(m.group(2).lower(), 12), int(m.group(1)))
