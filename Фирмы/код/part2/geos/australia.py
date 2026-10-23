"""
АВСТРАЛИЯ — ABN Lookup (abr.business.gov.au). Драйвер «скачивание».

Поток (из записи codegen — URL предсказуемые, форму поиска не трогаем):
  1. выдача:  /Search/ResultsActive?SearchText=<имя>
  2. карточка: /ABN/View?abn=<ABN>
  3. проверяем ПОЛЕ «ABN status» = Active
  4. кнопка «Pdf» → прямое скачивание (без попапа)

В выдаче одна фирма встречается дважды (Entity Name и Trading Name) с ОДНИМ ABN —
склеиваем по ABN. Различаем однофамильцев по ИНДЕКСУ («4122 QLD»), т.к. улицы
в выдаче нет. Номер — ABN (11 цифр).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

BASE = "https://abr.business.gov.au"


class Australia(GeoDriver):
    code, title = "AU", "Австралия"
    url = f"{BASE}/"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.abn = ""
        self.имя = ""
        self.адрес_dnb = ""      # ABR не публикует улицу — адрес берём с DnB

    def search(self, c: Company) -> list[Candidate]:
        # прямой URL выдачи — форму поиска не трогаем (из записи codegen)
        self.br.goto(f"{BASE}/Search/ResultsActive?SearchText={quote(c.name)}")
        self.page.wait_for_load_state("domcontentloaded")
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        # ОДИН ABN = ОДНА ФИРМА. В выдаче фирма встречается дважды — как Entity Name
        # и как Trading Name с тем же ABN. Склеиваем по ABN, берём первую строку.
        # В выдаче виден только ИНДЕКС («4122 QLD») — по нему ядро и различает.
        cands: list[Candidate] = []
        виденные: set[str] = set()
        строки = self.page.locator("table tbody tr")
        for i in range(строки.count()):
            строка = строки.nth(i)
            ссылка = строка.locator("a").first          # ABN — ссылка
            if not ссылка.count():
                continue
            abn = re.sub(r"\D", "", ссылка.inner_text())
            if not abn or abn in виденные:
                continue
            виденные.add(abn)
            ячейки = [строка.locator("td").nth(j).inner_text().strip()
                      for j in range(строка.locator("td").count())]
            имя = ячейки[1] if len(ячейки) > 1 else ссылка.inner_text().strip()
            # адрес = вся строка (там индекс «4122 QLD») — ядро различит по индексу
            локация = re.sub(r"\s+", " ", строка.inner_text()).strip()
            cands.append(Candidate(name=имя, address=локация, ref=abn))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            m = re.search(r"abn=(\d{11})", self.page.url)
            self.abn = m.group(1) if m else ""
            return
        # прямой URL карточки (из записи codegen)
        self.abn = str(cand.ref)
        self.имя = cand.name
        self.br.goto(f"{BASE}/ABN/View?abn={self.abn}")
        self.page.wait_for_load_state("domcontentloaded")

    def check(self, c: Company) -> tuple[bool, str]:
        # ВАЖНО: читаем ПОЛЕ «ABN status», а не всю страницу — слово «cancelled»
        # встречается в служебных подсказках ABR и раньше давало ложный отсев.
        # ABR не даёт улицу — адрес для колонки K берём из Части 1 (DnB)
        self.адрес_dnb = ", ".join(
            x for x in (c.address, c.zip_code, c.city) if x) if c else ""
        текст = self.page.inner_text("body")
        m = re.search(r"ABN status:?\s*\n?\s*([^\n]+)", текст, re.I)
        статус = (m.group(1) if m else "").strip()
        low = статус.lower()
        if "cancelled" in low:
            return False, f"ABN отменён ({статус})"
        if "active" not in low:
            return False, f"ABN status не Active ({статус or '—'})"
        # ТИП ОРГАНИЗАЦИИ. Смотрели только статус ABN — и скачали футбольный
        # клуб «ACACIA RIDGE F.C.INC.» (Other Incorporated Entity — так ABR
        # пишет incorporated association). Трасты и объединения Google Ads не
        # верифицирует (живой прогон 20.10.2026).
        mt = re.search(r"Entity type:?\s*\n?\s*([^\n]+)", текст, re.I)
        тип = (mt.group(1) if mt else "").strip()
        if re.search(r"trust|other incorporated entity|unincorporated|association|"
                     r"superannuation|government|charit", тип, re.I):
            return False, f"форма не подходит для Google Ads: {тип}"
        return True, ""

    def номер(self) -> str:
        if self.abn:
            return self.abn
        try:
            m = re.search(r"\b(\d{2}\s\d{3}\s\d{3}\s\d{3})\b",
                          self.page.inner_text("body"))
            return re.sub(r"\s", "", m.group(1)) if m else ""
        except Exception:
            return ""

    def данные_реестра(self) -> dict:
        # Имя — из реестра (Entity name). Адрес ABR не публикует (только «QLD 4122»),
        # поэтому в колонку K кладём адрес из DnB — так решили.
        try:
            m = re.search(r"Entity name:?\s*\n?\s*([^\n]+)",
                          self.page.inner_text("body"), re.I)
            if m:
                self.имя = m.group(1).strip()
        except Exception:
            pass
        return {"имя": self.имя, "адрес": self.адрес_dnb}

    def fetch(self, c: Company, dest: Path) -> Path:
        # (а) кнопка «Pdf» — это <input type="submit"> в форме action="/ABN/PDF",
        # клик шлёт POST и отдаёт файл. Ищем input, а не <a>/<button>.
        try:
            with self.page.expect_download(timeout=20000) as dl:
                self.page.locator(
                    "li.pdf input[type='submit'], input.inputpdf, "
                    "input[value='Pdf' i], button:has-text('Pdf')").first.click()
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass
        # (б) не вышло скачать файлом — печатаем текущую карточку
        try:
            return self.br.print_to_pdf(dest)
        except Exception:
            self.human.stuck(
                "скачать PDF Австралии автоматически не вышло.\n"
                "Нажми «Pdf» на карточке ABN, сохрани файл, потом «Продолжить».", c.name)
            raise RuntimeError("AU: PDF не скачался автоматически")
