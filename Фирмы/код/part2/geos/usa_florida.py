"""
США — ФЛОРИДА (search.sunbiz.org). Драйвер «печать страницы».

Поток по инструкции (стр. 33–34):
  1. «Search by Entity Name» → имя → Search
  2. в списке «Entity Name List» берём фирму со статусом Active → карточка
     «Detail by Entity Name»
  3. проверяем Status = ACTIVE
  4. печатаем страницу в PDF («Сохранить как PDF»)

Код гео — "US". Часть 1 набирает фирмы США только из разрешённых штатов
(FL, NY, WA, GA — см. РЕГИОНЫ в part1/data/countries.py). Этот драйвер умеет
ПОКА ТОЛЬКО ФЛОРИДУ; для остальных штатов драйверы ещё предстоит написать.
Номер — Document Number вида P23000040761.
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://search.sunbiz.org"


class USAFlorida(GeoDriver):
    code, title = "US", "США (Флорида)"
    url = f"{BASE}/Inquiry/CorporationSearch/ByName"
    method = "print"

    # Document Number: P23000040761 (буква + цифры) или старый чисто цифровой
    номер_regex = r"Document Number\s+([A-Z]?\d{6,12})"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        (self.page
         .locator("input#SearchTerm, input[name='SearchTerm'], input[type='text']")
         .first.fill(c.name))
        (self.page
         .locator("input[type='submit'], button:has-text('Search')")
         .first.click())
        self.page.wait_for_load_state("networkidle")

        cands: list[Candidate] = []
        строки = self.page.locator("table tbody tr")
        for i in range(строки.count()):
            строка = строки.nth(i)
            ссылка = строка.locator("a").first          # Corporate Name — ссылка
            if not ссылка.count():
                continue
            текст = строка.inner_text().strip()
            if "active" not in текст.lower():           # только Active, INACT пропускаем
                continue
            cands.append(Candidate(name=ссылка.inner_text().strip(),
                                   address=текст, ref=ссылка))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        cand.ref.click()
        self.page.wait_for_load_state("networkidle")

    def check(self, c: Company) -> tuple[bool, str]:
        # читаем ПОЛЕ «Status», а не всю страницу: раньше проверка проходила,
        # если слово ACTIVE встречалось где угодно (в т.ч. в меню/подсказках)
        текст = self.page.inner_text("body")
        статус = self._поле(текст, "Status")
        # ВАЖНО: «INACTIVE» содержит «active» — простой `in` пропускал мёртвые фирмы.
        # Sunbiz пишет ACTIVE / INACT / INACTIVE / CROSS RF, сверяем строго с начала.
        if not re.match(r"\s*active\b", статус, re.I):
            return False, f"статус: {статус or '—'}"
        причина = проверить_статус(статус) or проверить_форму("US", статус)
        if причина:
            return False, причина

        # правда из реестра
        m = re.search(r"Corporation Name\s*\n\s*([^\n]+)", текст, re.I)
        if not m:
            m = re.search(r"Detail by Entity Name\s*\n\s*([^\n]+)\s*\n\s*([^\n]+)", текст, re.I)
            self.имя = m.group(2).strip() if m else c.name
        else:
            self.имя = m.group(1).strip()
        адр = self._поле(текст, "Principal Address") or self._поле(текст, "Mailing Address")
        self.адрес = адр
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"\b{re.escape(подпись)}\b:?\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        return self.br.print_to_pdf(dest)
