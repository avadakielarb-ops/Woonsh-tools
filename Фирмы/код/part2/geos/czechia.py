"""
ЧЕХИЯ — or.justice.cz (Veřejný rejstřík a Sbírka listin).

Поток ТОЧНО по инструкции:
  1. https://or.justice.cz/ias/ui/rejstrik → вбиваем название → «Hledat»
  2. в выдаче сверяем «Název subjektu» (имя) и «Sídlo» (адрес)
  3. жмём «Úplný výpis» → страница «Úplný výpis z obchodního rejstříku»
  4. листаем вниз: у строки «Tento výpis je neprodejný a byl pořízen na Internetu»
     справа ссылка «Stáhnout PDF verzi výpisu» → качаем, переименовываем

ВАЖНО про адрес: в полном выписе Sídlo идёт ИСТОРИЕЙ — старые адреса помечены
«vymazáno». Поэтому адрес и имя запоминаем СО СТРАНИЦЫ ВЫДАЧИ, где они уже
актуальные, и не разбираем историю.
Номер — IČO (Identifikační číslo).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

BASE = "https://or.justice.cz/ias/ui"


class Czechia(GeoDriver):
    code, title = "CZ", "Чехия"
    url = f"{BASE}/rejstrik"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.ico = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        поле = self.page.locator(
            "input[name='nazev'], input[type='text']:visible").first
        поле.fill(c.name)
        (self.page.locator("input[type='submit'], button:has-text('Hledat'), "
                           "input[value='Hledat'], input[value='Vyhledat']")
         .first.click())
        self.page.wait_for_load_state("domcontentloaded")
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        # каждый субъект — блок, где есть ссылка «Úplný výpis»
        for блок in self.page.locator("div:has(> a:has-text('Úplný výpis'))").all():
            имя = self._поле(блок.inner_text(), "Název subjektu")
            if not имя or имя == "*":
                continue
            cands.append(Candidate(name=имя,
                                   address=self._поле(блок.inner_text(), "Sídlo"),
                                   ref=блок))
        if cands:
            return cands
        # запасной разбор: текст ВЫДАЧИ (без формы поиска — см. _текст_выдачи)
        текст = self._текст_выдачи()
        имя = self._поле(текст, "Název subjektu")
        if имя and имя != "*":
            cands.append(Candidate(name=имя,
                                   address=self._поле(текст, "Sídlo"),
                                   ref="СТРАНИЦА"))
        return cands

    def _текст_выдачи(self) -> str:
        """
        Текст страницы БЕЗ формы поиска.

        КРИТИЧНО: над результатами висит форма, где у обязательных полей стоит
        звёздочка — «Název subjektu: *». Разбирая страницу целиком, мы забирали
        именно её и получали имя фирмы «*» (а из него — файл без названия).
        Отрезаем всё до строки «Počet nalezených subjektů».
        """
        текст = self.page.inner_text("body")
        m = re.search(r"Počet nalezených subjektů[^\n]*", текст, re.I)
        return текст[m.end():] if m else текст

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return                                   # карточку открыл человек
        # запоминаем АКТУАЛЬНЫЕ имя и адрес из выдачи (в выписе они историей)
        self.имя, self.адрес = cand.name, cand.address
        ссылка = (self.page.locator("a:has-text('Úplný výpis')").first
                  if cand.ref == "СТРАНИЦА"
                  else cand.ref.locator("a:has-text('Úplný výpis')").first)
        ссылка.click()
        self.page.wait_for_load_state("domcontentloaded")

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")

        # ВАЖНО: НЕ сканируем всю страницу на ключевые слова. В подвале сайта
        # висят постоянные ссылки «Insolvenční rejstřík» и «Evidence úpadců» —
        # они есть на КАЖДОЙ странице и раньше давали ложное «неплатёжеспособность»
        # у всех фирм подряд. По чешскому праву фирма в ликвидации/конкурсе несёт
        # это ПРЯМО В НАЗВАНИИ («… s.r.o. v likvidaci»), его и проверяем.
        # Плюс сам поиск идёт с «Jen platné» — недействующие в выдачу не попадают.
        имя = (self.имя or self._поле(текст, "Obchodní firma")).lower()
        for плохо, причина in (("v likvidaci", "в ликвидации"),
                               ("v konkursu", "в конкурсном производстве"),
                               ("v úpadku", "в банкротстве")):
            if плохо in имя:
                return False, причина

        # IČO — постоянный ключ фирмы
        m = re.search(r"Identifikační číslo:?\s*([\d\s]{6,})", текст)
        self.ico = re.sub(r"\s", "", m.group(1)) if m else ""
        # если имени/адреса из выдачи нет (человек открыл сам) — возьмём из выписа
        if not self.имя:
            self.имя = self._поле(текст, "Obchodní firma")
        if not self.адрес:
            self.адрес = self._поле(текст, "Sídlo")
        return True, ""

    def номер(self) -> str:
        return self.ico

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        ссылка = self.page.locator("a:has-text('Stáhnout PDF verzi výpisu')").first
        try:
            ссылка.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        return self.br.click_download(
            "a:has-text('Stáhnout PDF verzi výpisu')", dest, c.name)

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """
        «Sídlo: Rybníčky 453, 747 81 Otice» → значение справа от подписи.

        В таблице выдачи соседние ячейки идут через таб:
            «Název subjektu:⇥INVITAL aqua s.r.o.⇥IČO:⇥027 79 897»
        Берём строку целиком (иначе адрес обрывался на «747 81» без города),
        а потом отрезаем соседнюю ячейку по её подписи.
        """
        m = re.search(rf"{re.escape(подпись)}\s*:?[ \t]*\n?[ \t]*([^\n]*)", текст, re.I)
        if not m:
            return ""
        знач = m.group(1)
        for соседняя in ("IČO", "Den zápisu", "Spisová značka", "Právní forma",
                         "Identifikační číslo", "Datum vzniku", "Sídlo"):
            знач = re.split(rf"[\t ]{re.escape(соседняя)}\s*:", знач)[0]
        return re.sub(r"\s+", " ", знач).strip()
