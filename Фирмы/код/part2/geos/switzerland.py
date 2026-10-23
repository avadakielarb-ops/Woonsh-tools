"""
ШВЕЙЦАРИЯ — Zefix (Central Business Name Index). Драйвер «печать страницы».

Поток (из записи codegen + скриншот карточки):
  1. https://www.zefix.ch/en/search/entity/list  (EN — поля называются по-английски)
  2. поле-комбобокс «business name or UID» → Enter; баннер «Agree» принимаем
  3. в выдаче кликаем ссылку с именем фирмы → карточка
  4. карточка (строки таблицы label → value):
        address       St. Gallerstrasse 25
        ZIP / Town    8645 Jona
        legal form    Limited Liability Company
        seat          Rapperswil-Jona
        status        active
  5. печатаем страницу в PDF через CDP (кнопку «print» НЕ жмём — она открывает
     системный диалог печати, который скриптом не закрыть).

Типы: отсеиваем только 🔴 (Verein, Stiftung, Genossenschaft) — part2/core/формы.py.
GmbH/AG/SA/Sàrl/Sagl и Einzelfirma проходят. Номер — UID (CHE-###.###.###).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://www.zefix.ch"


class Switzerland(GeoDriver):
    code, title = "CH", "Швейцария"
    url = f"{BASE}/en/search/entity/list"
    method = "print"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.uid = ""

    def search(self, c: Company) -> list[Candidate]:
        # ПРЯМЫМ АДРЕСОМ И ЖДЁМ ВЫДАЧУ, а не «тишину в сети». Zefix —
        # одностраничное приложение: после Enter прежний код читал страницу
        # раньше, чем на ней появлялись строки, и Швейцария давала 0 из 10
        # (живой прогон 20.10.2026; в том же Chrome «AQUA AG» стоит в выдаче
        # третьей строкой).
        self.br.goto(f"{self.url}?mainSearch={quote(c.name)}")
        self._agree()
        try:
            self.page.wait_for_function(
                "() => /Number of results|\\b0 of 0\\b/.test(document.body.innerText)"
                " || /\\/firm\\/\\d+/.test(location.pathname)"
                " && /CHE-\\d{3}\\.\\d{3}\\.\\d{3}/.test(document.body.innerText)",
                timeout=20000)
        except Exception:
            pass
        self.page.wait_for_timeout(600)
        self._agree()
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def _agree(self) -> None:
        """Баннер согласия: кнопка «Agree» (из записи codegen)."""
        try:
            b = self.page.get_by_role("button", name="Agree").first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    # Мусор, который сайт кладёт в те же ячейки: служебные подписи ссылок.
    _МУСОР = ("opens in a new tab", "cantonal excerpt", "che-")

    def на_карточке(self) -> bool:
        """
        Zefix при ЕДИНСТВЕННОМ совпадении сразу открывает КАРТОЧКУ фирмы
        (адрес .../entity/list/firm/<id>), а не список. Прежний разбор этого не
        знал и читал строки карточки как список результатов — получались
        «фирмы» вида «CHE-109.550.483 - Opens in a new tab» и
        «Handelsregisteramt des Kantons Luzern». Именно их человек видел в окне
        «неоднозначное совпадение», и решать по ним было нечего.
        """
        return "/firm/" in (self.page.url or "")

    def _имя_карточки(self) -> str:
        # Имя фирмы — h3. h2 на странице — это меню сайта («Service
        # navigation»), его и брали за имя фирмы.
        for sel in ("main h3", "h3", "h1"):
            try:
                э = self.page.locator(sel).first
                if э.count():
                    имя = э.inner_text().strip().splitlines()[0].strip()
                    if имя and len(имя) > 2:
                        return имя
            except Exception:
                continue
        return ""

    def _поле_карточки(self, подпись: str) -> str:
        """Значение строки карточки: «ZIP / Town» → «6340 Baar»."""
        try:
            строка = self.page.locator(f"tr:has-text('{подпись}')").first
            if строка.count():
                я = строка.locator("td").first
                if я.count():
                    return я.inner_text().strip()
        except Exception:
            pass
        return ""

    def _карточка_как_кандидат(self) -> Candidate:
        адрес = " ".join(x for x in (self._поле_карточки("address"),
                                     self._поле_карточки("ZIP / Town")) if x)
        return Candidate(name=self._имя_карточки() or "", address=адрес, ref="CARD")

    def кандидаты_страницы(self) -> list[Candidate]:
        # единственное совпадение — Zefix уже на карточке
        if self.на_карточке():
            return [self._карточка_как_кандидат()]

        cands: list[Candidate] = []
        виденные: set[str] = set()
        # Имя фирмы — это текст ССЫЛКИ НА ЕЁ КАРТОЧКУ. Прочие ссылки строки
        # («cantonal excerpt», UID) ведут на чужие сайты — их не берём.
        for строка in self.page.locator("table tr").all():
            ссылка = строка.locator("a[href*='/firm/']").first
            if not ссылка.count():
                continue
            href = ссылка.get_attribute("href") or ""
            имя = ссылка.inner_text().strip()
            if not имя or not href or href in виденные:
                continue
            виденные.add(href)
            ячейки = [строка.locator("td").nth(j).inner_text().strip()
                      for j in range(строка.locator("td").count())]
            # место (seat) — последняя ОСМЫСЛЕННАЯ ячейка: без UID и служебных
            # подписей, иначе в адрес попадал «- Opens in a new tab».
            место = ""
            for я in reversed(ячейки):
                низ = я.lower()
                if я and я != имя and not any(м in низ for м in self._МУСОР):
                    место = я
                    break
            cands.append(Candidate(name=имя, address=место, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref in ("HUMAN", "CARD"):
            return                     # уже на нужной странице
        ссылка = str(cand.ref)
        self.br.goto(ссылка if ссылка.startswith("http") else BASE + ссылка)
        try:
            self.page.wait_for_function(
                "() => /CHE-\\d{3}\\.\\d{3}\\.\\d{3}/.test(document.body.innerText)"
                " && /status/i.test(document.body.innerText)", timeout=20000)
        except Exception:
            pass
        self.page.wait_for_timeout(600)
        self._agree()

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")

        статус = self._поле(текст, "status")
        if "activ" not in статус.lower():
            return False, f"статус: {статус or '—'}"
        причина = проверить_статус(статус)
        if причина:
            return False, причина

        форма = self._поле(текст, "legal form")
        причина = проверить_форму("CH", форма)
        if причина:
            return False, причина

        # правда из реестра
        self.имя = self._имя_карточки() or c.name
        улица = self._поле(текст, "address")
        индекс_город = self._поле(текст, "ZIP / Town")
        self.адрес = ", ".join(x for x in (улица, индекс_город) if x)
        mu = re.search(r"(CHE-\d{3}\.\d{3}\.\d{3})", текст)
        self.uid = mu.group(1) if mu else ""
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """
        Значение строки карточки. Читаем ДВА вида разметки:

          1) в ОДНОЙ строке через табуляцию (так отдаёт сайт сейчас):
             «status\\tactive», «ZIP / Town\\t6340 Baar»
          2) на СЛЕДУЮЩЕЙ строке (так было раньше):
             «legal form\\nLimited Liability Company»

        Понимали только второй вид — и статус читался ПУСТЫМ у всех фирм,
        то есть «✘ статус: —» по всей Швейцарии. Ровно та же беда была
        у Финляндии.
        """
        m = re.search(rf"\b{re.escape(подпись)}\b[ \t]*\t[ \t]*([^\n]+)", текст, re.I)
        if not m:
            m = re.search(rf"\b{re.escape(подпись)}\b\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.uid

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        # печать через CDP — как Ctrl+P → «Сохранить как PDF», без диалога
        return self.br.print_to_pdf(dest)
