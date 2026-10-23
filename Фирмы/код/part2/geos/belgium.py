"""
БЕЛЬГИЯ — KBO Public Search (kbopub.economie.fgov.be). Драйвер «печать страницы»
(как Швейцария): официальный PDF реестр бесплатно не отдаёт, поэтому печатаем
страницу карточки в PDF через CDP.

Поток ТОЧНО по инструкции (стр. 19–20):
  1. форма «zoek op naam» (фонетический поиск) → вбиваем имя в Zoekwoord → «Zoek»
     (галочка «Enkel actieve...» — только активные — на форме уже стоит)
  2. в выдаче кликаем Ondernemingsnummer нужной фирмы → карточка
     «Gegevens van de geregistreerde entiteit»
  3. проверяем Status = Actief (Rechtstoestand: Normale toestand)
  4. печатаем страницу в PDF (Ctrl+P → «Сохранить как PDF»)

Номер фирмы — Ondernemingsnummer вида 0897.961.464 (10 цифр, формат 4.3.3).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver


class Belgium(GeoDriver):
    code, title = "BE", "Бельгия"
    url = "https://kbopub.economie.fgov.be/kbopub/zoeknaamfonetischform.html"
    method = "print"

    # Ondernemingsnummer: 0897.961.464 — постоянный ключ фирмы
    номер_regex = r"\b(\d{4}\.\d{3}\.\d{3})\b"

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        # поле «Zoekwoord (verplicht)» + кнопка «Zoek»
        (self.page
         .locator("input[name='searchWord'], input#searchWord, input[type='text']")
         .first.fill(c.name))
        (self.page
         .locator("input[value='Zoek'], button:has-text('Zoek'), input[type='submit']")
         .first.click())
        self.page.wait_for_load_state("networkidle")
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        # ОДНА СТРОКА ВЫДАЧИ = ОДИН КАНДИДАТ, и берём ТОЛЬКО юрлицо (ENT RP),
        # а НЕ филиал (VE): у фирмы может быть две строки с одним номером —
        # ENT RP (Rechtspersoon) и VE (Vestigingseenheid). Нам нужен ENT RP.
        cands: list[Candidate] = []
        строки = self.page.locator("tr:has(a[href*='ondernemingsnummer'])")
        for i in range(строки.count()):
            строка = строки.nth(i)
            ячейки = [строка.locator("td").nth(j).inner_text().strip()
                      for j in range(строка.locator("td").count())]
            if not ячейки:
                continue
            # Берём ТОЛЬКО юрлицо со статусом «ENT RP». Пропускаем филиалы (VE)
            # и физлиц (ENT NP). Колонки: [№ | ENT/VE Status | Номер | Info | Naam | Adres],
            # поэтому ищем «ENT RP» по ЛЮБОЙ ячейке (не по первой — там номер строки).
            if not any("ENT RP" in re.sub(r"\s+", " ", т.upper()) for т in ячейки):
                continue
            ссылка = строка.locator("a[href*='ondernemingsnummer']").first
            # порядок колонок: Status | Ondernemingsnummer | (Info VE) | Naam | Adres
            имя = ячейки[-2] if len(ячейки) >= 2 else ссылка.inner_text().strip()
            адрес = ячейки[-1] if ячейки else ""
            cands.append(Candidate(name=имя, address=адрес, ref=ссылка))
        return cands

    def следующая_страница(self) -> bool:
        # KBO листает выдачу ссылкой «Volgende» — жмём её, пока она есть
        try:
            ссылка = self.page.locator(
                "a:has-text('Volgende'), a:has-text('volgende')").first
            if ссылка.count() and ссылка.is_visible():
                ссылка.click()
                self.page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        return False

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        cand.ref.click()
        self.page.wait_for_load_state("networkidle")

    def check(self, c: Company) -> tuple[bool, str]:
        # ВАЖНО: проверяем ИМЕННО поля Status и Rechtstoestand, а не всю страницу.
        # Слово «stopgezet» есть в карточке даже активной фирмы (в истории видов
        # деятельности) — сканировать весь текст нельзя, ловятся ложные срабатывания.
        text = self.page.inner_text("body")
        m = re.search(r"Status:\s*([^\n]+)", text, re.I)
        статус = (m.group(1) if m else "").strip().lower()
        m2 = re.search(r"Rechtstoestand:\s*([^\n]+)", text, re.I)
        состояние = (m2.group(1) if m2 else "").strip().lower()
        if "actief" not in статус:
            return False, f"статус не Actief ({статус or '—'})"
        # здоровое состояние — «Normale toestand». Иначе банкротство/ликвидация.
        if состояние and "normale toestand" not in состояние:
            return False, f"Rechtstoestand: {состояние}"
        return True, ""

    def данные_реестра(self) -> dict:
        """Имя и адрес с карточки KBO — для колонки «Платёжный профиль выписки»."""
        text = self.page.inner_text("body")
        m = re.search(r"Adres van de zetel:\s*(.+?)(?:Sinds |Telefoonnummer|"
                      r"Type entiteit|\n\s*\n)", text, re.I | re.S)
        адрес = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        n = re.search(r"Naam:\s*([^\n]+)", text, re.I)
        return {"имя": (n.group(1).strip() if n else ""), "адрес": адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        return self.br.print_to_pdf(dest)      # Ctrl+P → «Сохранить как PDF»
