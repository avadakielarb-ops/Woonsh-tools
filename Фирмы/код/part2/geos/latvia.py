"""
ЛАТВИЯ — info.ur.gov.lv (Uzņēmumu reģistrs). Angular-SPA.

Поток (по записи codegen):
  1. поиск по имени → выдача: у каждого результата ИМЯ, АДРЕС и «Reģ. Nr. : <11 цифр>»
     (струк-офф помечен «Izslēgts»). Рег.номер парсим из ТЕКСТА выдачи.
  2. карточка — по ПРЯМОМУ URL: /#/legal-entity/<рег.номер>
  3. закрыть баннер «Aizvērt» → клик «▼» (меню печати) →
     «Izdruka ar e-zīmogu (PDF)» → откроется попап, качается PDF.

normalize() срезает «Sabiedrība ar ierobežotu atbildību», так что матч по имени
работает, плюс подтверждение адресом. Номер — Vienotais reģistrācijas numurs (11 цифр).
"""
from __future__ import annotations

import re
from pathlib import Path

from common.имена import без_формы
from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

BASE = "https://info.ur.gov.lv"


class Latvia(GeoDriver):
    code, title = "LV", "Латвия"
    сам_режет_форму = True
    url = f"{BASE}/#/data-search"
    method = "download"

    номер_regex = r"\b(\d{11})\b"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.regnr = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_timeout(1500)                 # SPA
        self._закрыть()                                  # баннер «Aizvērt»
        поле = self.page.locator(
            "input[placeholder*='nosaukum'], input[placeholder*='Uzņēmuma'], "
            "input[type='search']:visible, input[type='text']:visible").first
        поле.click()
        # ИЩЕМ БЕЗ ПРАВОВОЙ ФОРМЫ. В реестре фирма записана как SIA "AQUA-360":
        # форма ВПЕРЕДИ, имя В КАВЫЧКАХ, — а у нас «AQUA-360 SIA». По полному
        # имени поиск отдаёт чужих: замер 17.09.2026 — «Aqua Unitā» и «SIA
        # AQUA», нашей в выдаче нет вовсе. По запросу «AQUA-360» она первая.
        # Буквы НЕ трогаем: латышское «Ķieģelis» без диакритики не найдётся.
        поле.fill(без_формы(c.name) or c.name)
        # ПАУЗА ПЕРЕД ENTER обязательна. Angular-поле принимает ввод не мгновенно:
        # нажатый сразу Enter уходит в пустоту, поиск не отправляется, и выдача
        # не появляется НИКОГДА. Замер: без паузы 0 кандидатов даже через 7 секунд,
        # с паузой те же данные находятся. Из-за этого Латвия давала 0 из 10.
        self.page.wait_for_timeout(700)
        поле.press("Enter")
        # Ждём саму ВЫДАЧУ, а не фиксированную паузу: сколько думает SPA, столько
        # и ждём, но не дольше 12 секунд.
        try:
            self.page.wait_for_function(
                r"() => /Re[gģ]\.?\s*Nr/.test(document.body.innerText)",
                timeout=12000)
        except Exception:
            pass          # не дождались — ниже честно вернётся пустой список
        self.page.wait_for_timeout(500)
        self._закрыть()
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _закрыть(self) -> None:
        """Баннер cookie/инфо: кнопка «Aizvērt» (Закрыть) — из записи codegen."""
        try:
            b = self.page.locator("button:has-text('Aizvērt')").first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        # парсим ТЕКСТ выдачи: перед «Reģ. Nr. : <11 цифр>» идут АДРЕС и ИМЯ
        текст = self.page.inner_text("body")
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for m in re.finditer(r"Re[gģ]\.?\s*Nr\.?\s*:?\s*(\d{11})", текст):
            regnr = m.group(1)
            if regnr in виденные:
                continue
            виденные.add(regnr)
            хвост = текст[m.end():m.end() + 140]
            if re.search(r"Izsl[eē]gt", хвост):          # струк-офф — мимо
                continue
            до = [s.strip() for s in текст[:m.start()].split("\n") if s.strip()]
            имя = до[-2] if len(до) >= 2 else (до[-1] if до else "")
            адрес = до[-1] if до else ""
            # прежнее имя («Iepriekš: …») — как в UK, матчим по нему запасным ходом
            прежние: tuple = ()
            mp = re.search(r"Iepriekš:?\s*([^\n]+)", хвост, re.I)
            if mp:
                прежние = (mp.group(1).strip(),)
            cands.append(Candidate(name=имя, address=адрес, ref=regnr,
                                   aliases=прежние))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            m = re.search(r"legal-entity/(\d{11})", self.page.url)
            self.regnr = m.group(1) if m else ""
            self._закрыть()
            return
        self.regnr = str(cand.ref)
        self.имя, self.адрес = cand.name, cand.address
        # прямой URL карточки
        self.br.goto(f"{BASE}/#/legal-entity/{self.regnr}")
        # ЖДЁМ ДАННЫЕ, а не таймер: Angular рисует карточку не мгновенно, и по
        # фиксированным 1800 мс мы регулярно жали по ещё пустой странице.
        try:
            self.page.wait_for_function(
                r"() => /\d{11}/.test(document.body.innerText)", timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(400)
        self._закрыть()

    def check(self, c: Company) -> tuple[bool, str]:
        # струк-офф уже отсеян в выдаче; здесь лёгкая проверка ВЕРХА карточки
        текст = self.page.inner_text("body")
        м = re.search(r"(Izsl[eē]gt\w*|likvid[āa]cij\w*|maks[āa]tnesp[eē]j\w*)",
                      текст, re.I)
        if м and м.start() < len(текст) * 0.5:
            return False, "исключена / ликвидация / неплатёжеспособность"
        if not self.адрес:
            ma = re.search(r"Adres\w*:?\s*\n?\s*([^\n]+)", текст, re.I)
            if ma:
                self.адрес = ma.group(1).strip()
        return True, ""

    def номер(self) -> str:
        return self.regnr

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        """
        «▼» (меню печати) → «Izdruka ar e-zīmogu (PDF)» → выписка открывается
        В ПОПАПЕ, во встроенном просмотрщике Chrome.

        Здесь и висло. Прежний код ловил попап, ЗАКРЫВАЛ его и ждал события
        download на исходной странице — двадцать пять секунд подряд. События нет
        и быть не может: PDF уже показан во вкладке, скачивать его должна кнопка
        внутри просмотрщика. Запись действий это подтвердила дословно:
        `page1.locator("embed").content_frame…get_by_role("button", name="Скачать")`.
        Теперь попап не закрываем, а забираем из него байты (`взять_документ`).
        """
        self._закрыть()
        # ждём, что карточка ДОГРУЗИЛАСЬ: меню печати появляется последним.
        # Раньше жали вслепую после фиксированной паузы — отсюда «нажало
        # скачать до прогрузки страницы и зависло».
        меню = self.page.get_by_text("▼").first
        try:
            меню.wait_for(state="visible", timeout=15000)
        except Exception:
            pass
        try:
            меню.click()
            self.page.wait_for_timeout(600)
        except Exception:
            pass

        пункт = self.page.get_by_text("Izdruka ar e-zīmogu (PDF)").first
        if пункт.count():
            путь = self.br.взять_документ(lambda: пункт.click(), dest, c.name,
                                          log=self.log)
            if путь:
                return путь

        self.human.stuck(
            "открой «▼» → «Izdruka ar e-zīmogu (PDF)». Выписка откроется В НОВОЙ "
            "ВКЛАДКЕ — оставь её открытой и нажми «Продолжить», файл заберу сам.",
            c.name)
        self.br.вкладка_человека(self.log)
        путь = self.br._pdf_со_страницы(self.page, dest)
        if путь:
            return путь
        raise RuntimeError("LV: PDF не скачался")
