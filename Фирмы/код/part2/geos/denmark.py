"""
ДАНИЯ — datacvr.virk.dk (CVR).

Поток по инструкции:
  1. поиск по имени → выдача. У фирмы «CVR-nummer», у производственных единиц
     «P-nummer» — берём ТОЛЬКО фирмы (CVR). Имя/адрес/статус видны прямо в выдаче.
  2. сверяем имя + адрес + статус (Status = Normal)
  3. «Gem som PDF» → «PDF» — файл. Но ссылка ПРЕДСКАЗУЕМАЯ:
        /gateway/pdf/hentVirksomhedsvisningSomPdf?cvrnummer=<CVR>&locale=da
     поэтому качаем PDF по прямой ссылке с сессией браузера (клики не нужны).

Данные (имя/адрес/CVR/статус) снимаются со страницы ВЫДАЧИ — карточку открывать
не обязательно. Номер — CVR (8 цифр).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

BASE = "https://datacvr.virk.dk"
# плохие статусы (иначе — отсев). Хороший — «Normal».
ПЛОХОЙ_СТАТУС = ("konkurs", "tvangsopløs", "ophørt", "likvidation", "opløst",
                "reassum", "tvangsoplos")


class Denmark(GeoDriver):
    code, title = "DK", "Дания"
    url = f"{BASE}/"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.cvr = ""
        self.статус = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self._cookie()                                   # баннер «Accepter»
        поле = self.page.locator(
            "#forside-soegefelt-id, input[placeholder*='Søg efter']").first
        поле.fill(c.name)
        self._cookie()                                   # мог появиться после ввода
        (self.page.locator(
            "button[data-cy='forside-soegefelt-btn'], "
            "button[aria-label='Søg i CVR'], button.search-btn").first.click())
        try:                                             # SPA — ждём отрисовки выдачи
            self.page.wait_for_selector("span.bold.value", timeout=12000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _cookie(self) -> None:
        """Баннер cookie datacvr: ссылка/кнопка «Accepter» (из записи codegen)."""
        for сел in ("a:has-text('Accepter')", "button:has-text('Accepter')"):
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click()
                    self.page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        имена = self.page.locator("span.bold.value")
        for i in range(имена.count()):
            сп = имена.nth(i)
            карточка = сп.locator(
                "xpath=ancestor::*[contains(.,'CVR-nummer') or contains(.,'P-nummer')][1]")
            if not карточка.count():
                continue
            текст = карточка.inner_text()
            mc = re.search(r"CVR-nummer:?\s*(\d{8})", текст)
            if not mc:                       # это P-enhed (P-nummer) — пропускаем
                continue
            cvr = mc.group(1)
            if cvr in виденные:
                continue
            виденные.add(cvr)
            имя = сп.inner_text().strip()
            # адрес — строки между именем и «CVR-nummer»
            адрес = ""
            ma = re.search(re.escape(имя) + r"\s*(.+?)\s*CVR-nummer", текст, re.S)
            if ma:
                адрес = re.sub(r"\s+", " ", ma.group(1)).strip()
            статус = ""
            ms = re.search(r"Status:?\s*([^\n]+)", текст, re.I)
            if ms:
                статус = ms.group(1).strip()
            cands.append(Candidate(name=имя, address=адрес,
                                   ref={"cvr": cvr, "статус": статус,
                                        "имя": имя, "адрес": адрес}))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            # человек открыл карточку — снимаем данные с неё
            текст = self.page.inner_text("body")
            m = re.search(r"CVR-nummer\s*\n?\s*(\d{8})", текст)
            self.cvr = m.group(1) if m else ""
            h = self.page.locator("h1, h2").first
            self.имя = h.inner_text().strip() if h.count() else cand.name
            self.статус = self._поле(текст, "Status")
            адр = self._поле(текст, "Adresse")
            город = self._поле(текст, "Postnummer og by")
            self.адрес = ", ".join(x for x in (адр, город) if x)
            return
        d = cand.ref
        self.cvr, self.статус = d["cvr"], d["статус"]
        self.имя, self.адрес = d["имя"], d["адрес"]

    def check(self, c: Company) -> tuple[bool, str]:
        # статус берём ТОЛЬКО из поля. Раньше при пустом статусе шёл откат на
        # всю страницу — там слова вроде «konkurs» могли дать ложный отсев.
        статус = self.статус
        if not статус:
            статус = self._поле(self.page.inner_text("body"), "Status")
        low = статус.lower()
        if not low:
            return False, "не нашёл статус фирмы"
        if any(p in low for p in ПЛОХОЙ_СТАТУС):
            return False, f"статус: {статус}"
        if "normal" not in low and "aktiv" not in low:
            return False, f"статус не Normal ({статус})"
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"{re.escape(подпись)}\s*\n?\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.cvr

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        if not self.cvr:
            self.human.stuck("не нашёл CVR-номер — открой карточку, «Gem som PDF» → "
                             "«PDF», сохрани и нажми «Продолжить».", c.name)
            raise RuntimeError("DK: нет CVR")
        # ПРЯМАЯ ссылка на PDF (из HTML кнопки «PDF»)
        url = (f"{BASE}/gateway/pdf/hentVirksomhedsvisningSomPdf"
               f"?cvrnummer={self.cvr}&locale=da")
        # (а) прямая ссылка с сессией браузера (быстро и надёжно)
        try:
            return self.br.download_url(url, dest)
        except Exception:
            pass
        # (б) запасной путь ровно как в записи codegen:
        #     карточка → «Gem som PDF» → «#fisk» (открывается вкладка, качается файл)
        try:
            self.page.get_by_text(self.имя, exact=True).first.click()
            self.page.wait_for_load_state("networkidle")
            self.page.get_by_role("button", name="Gem som PDF").click()
            self.page.wait_for_timeout(500)
            with self.page.expect_download(timeout=25000) as dl:
                try:
                    with self.page.expect_popup(timeout=8000) as поп:
                        self.page.locator("#fisk").click()
                    поп.value.wait_for_load_state("domcontentloaded")
                    поп.value.close()
                except Exception:
                    pass
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass
        self.human.stuck(
            "открой карточку → «Gem som PDF» → «PDF», сохрани файл, потом «Продолжить».",
            c.name)
        raise RuntimeError("DK: PDF не скачался")
