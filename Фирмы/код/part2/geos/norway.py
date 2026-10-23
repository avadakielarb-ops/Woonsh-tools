"""
НОРВЕГИЯ — virksomhet.brreg.no (Brønnøysundregistrene).

Поток (из записи codegen + скриншоты):
  1. выдача по ПРЯМОМУ URL:  /en/oppslag/enheter?navn=<имя>
  2. результат — карточка со ссылкой data-testid="card-link-<оргномер>";
     в блоке видно Type of organisation и Business address
  3. карточка по ПРЯМОМУ URL:  /en/oppslag/enheter/<оргномер>
     Поля идут списком dt/dd:
        Organisation number:   926 457 438
        Business address:      Risyxegatan 6 / SE21376 Malmö
        Country:               Sverige
        Type of organisation:  Utenlandsk enhet
        Web address:           www.powerheat.se
  4. «Download information» → «Download all information (PDF)» → прямое скачивание.

РЕШЕНО (сохранено): иностранные сущности («Utenlandsk enhet», адрес вне Норвегии)
нам ГОДЯТСЯ. Отсеиваем только 🔴 (stiftelse / forening) и статусы-стопы.
Поиск очень широкий — спасает точный матч по имени + адрес. Номер — оргномер (9 цифр).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://virksomhet.brreg.no/en/oppslag/enheter"
ПЛОХОЙ_СТАТУС = ("konkurs", "avvikling", "slettet", "tvangs", "oppløst", "opplost")


class Norway(GeoDriver):
    code, title = "NO", "Норвегия"
    url = BASE
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.orgnr = ""
        self.сайт = ""          # brreg даёт «Web address» — используем его вместо DnB

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(f"{BASE}?navn={quote(c.name)}")     # прямой URL выдачи
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(900)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("[data-testid^='card-link-']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            orgnr = re.sub(r"\D", "", ссылка.get_attribute("data-testid") or "")
            if not orgnr or orgnr in виденные:
                continue
            виденные.add(orgnr)
            # ВЕСЬ БЛОК карточки — это текст ссылки. Имя фирмы лежит в h3 внутри.
            # Раньше именем брали весь блок целиком, и в окне человека стояло
            # «ICE DRIFT AS\nOrganisation number: 992 700 335\nType of
            # organisation\nAksjeselskap\nBusiness address\nSikterigata 6…».
            # Сравнить такое «имя» с нашим невозможно: точного совпадения нет
            # никогда. А по адресу три фирмы на Sikterigata 6 (ICE DRIFT AS,
            # ICE DRIFT EIENDOM AS, ICE DRIFT HOLDING AS) — тоже не различить.
            # Итог: Норвегия звала человека там, где имя разрешало всё само.
            текст = ссылка.inner_text()
            загол = ссылка.locator("h3, h2").first
            имя = (загол.inner_text().strip() if загол.count()
                   else текст.split("\n")[0].strip())
            cands.append(Candidate(name=имя, address=self._адрес(текст), ref=orgnr))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            m = re.search(r"/enheter/(\d{9})", self.page.url)
            self.orgnr = m.group(1) if m else ""
            return
        self.orgnr = str(cand.ref)
        self.имя = cand.name
        self.br.goto(f"{BASE}/{self.orgnr}")             # прямой URL карточки
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(700)

    def check(self, c: Company) -> tuple[bool, str]:
        # читаем БЛОК основных данных, а не всю страницу с меню
        текст = ""
        try:
            секция = self.page.get_by_test_id("basisopplysninger")
            if секция.count():
                текст = секция.inner_text()
        except Exception:
            текст = ""
        if not текст:
            текст = self.page.inner_text("body")

        низ = текст.lower()
        for плохо in ПЛОХОЙ_СТАТУС:
            if плохо in низ:
                return False, f"статус-стоп: {плохо}"

        тип = self._поле(текст, "Type of organisation")
        причина = проверить_форму("NO", тип) or проверить_статус(тип)
        if причина:
            return False, причина

        # правда из реестра
        h1 = self.page.locator("h1").first
        if h1.count() and h1.inner_text().strip():
            self.имя = h1.inner_text().strip()
        адрес = self._адрес(текст)
        if адрес:
            self.адрес = адрес
        # brreg публикует сайт («Web address») — он вернее, чем с DnB
        self.сайт = self._поле(текст, "Web address")
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"\b{re.escape(подпись)}\b:?\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _адрес(текст: str) -> str:
        """«Business address:\\nRisyxegatan 6\\nSE21376 Malmö» → одной строкой."""
        m = re.search(r"Business address:?\s*\n\s*([^\n]+)\n\s*([^\n]+)", текст, re.I)
        if m and not re.match(r"(Country|Type of|Web|E-?mail|Phone|Organisation)",
                              m.group(2).strip(), re.I):
            return f"{m.group(1).strip()}, {m.group(2).strip()}"
        m = re.search(r"Business address:?\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.orgnr

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес, "сайт": self.сайт}

    def fetch(self, c: Company, dest: Path) -> Path:
        try:
            self.page.get_by_role("button", name="Download information").first.click()
            self.page.wait_for_timeout(900)
            with self.page.expect_download(timeout=30000) as dl:
                (self.page.get_by_role("button", name="Download all information")
                 .first.click())
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass
        self.human.stuck(
            "нажми «Download information» → «Download all information (PDF)», "
            f"сохрани под «{c.name}», потом «Продолжить».", c.name)
        raise RuntimeError("NO: PDF не скачался")
