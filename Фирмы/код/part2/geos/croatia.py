"""
ХОРВАТИЯ — sudreg.pravosudje.hr (Sudski registar). Драйвер «печать страницы».

Поток (из записи codegen + скриншоты):
  1. .../public/pretraga-subjekata → поле «Ime/Naziv pravnog subjekta» → «Pretraži»
  2. таблица выдачи, колонки:
        MBS | OIB | Sud | Status | Naziv / Ime subjekta | Status naziva | Adresa
     Берём только Status = «Aktivan». MBS — ссылка на карточку.
  3. карточка по ПРЯМОМУ URL:
        .../public/podaci-o-poslovnom-subjektu?p28_sbt_mbs=<MBS>
     Поля: Nadležni sud · MBS · OIB · EUID · Status («Bez postupka» — здоровый) ·
     Tvrtka · Sjedište/adresa · Pravni oblik
  4. печатаем страницу в PDF через CDP.
     Кнопку «Prikaži verziju za ispis» НЕ жмём — она вызывает системный диалог
     печати, который скриптом не закрыть.

Номер — MBS. Типы: 🔴 udruga / zadruga (part2/core/формы.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://sudreg.pravosudje.hr/ords/r/esudreg/public"
ПЛОХОЙ_СТАТУС = ("stečaj", "stecaj", "likvidacij", "brisan", "predsteč", "predstec")


class Croatia(GeoDriver):
    code, title = "HR", "Хорватия"
    url = f"{BASE}/pretraga-subjekata"
    method = "print"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.mbs = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1200)                 # APEX грузится
        поле = self.page.get_by_label("Ime/Naziv pravnog subjekta").first
        поле.click()
        поле.fill(c.name)
        self.page.get_by_role("button", name="Pretraži").first.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1200)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        # MBS | OIB | Sud | Status | Naziv/Ime | Status naziva | Adresa
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator("table tr").all():
            ячейки = [строка.locator("td").nth(j).inner_text().strip()
                      for j in range(строка.locator("td").count())]
            if len(ячейки) < 7:
                continue
            mbs = re.sub(r"\D", "", ячейки[0])
            if not mbs or mbs in виденные:
                continue
            if "aktiv" not in ячейки[3].lower():          # берём только активные
                continue
            виденные.add(mbs)
            cands.append(Candidate(name=ячейки[4], address=ячейки[6], ref=mbs))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            m = re.search(r"p28_sbt_mbs=(\d+)", self.page.url)
            self.mbs = m.group(1) if m else ""
            return
        self.mbs = str(cand.ref)
        self.имя, self.адрес = cand.name, cand.address
        # прямой URL карточки по MBS (из записи codegen)
        self.br.goto(f"{BASE}/podaci-o-poslovnom-subjektu?p28_sbt_mbs={self.mbs}")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)

    @staticmethod
    def _данные(текст: str) -> str:
        """
        Отрезать МЕНЮ и оставить блок данных.

        Вот из-за чего Хорватия давала мусор. Слева на карточке висит
        оглавление «Sadržaj» с теми же подписями: Nadležni sud, MBS, OIB,
        EUID, Status, Tvrtka, Sjedište/adresa, Pravni oblik… Наш поиск
        «подпись, а на следующей строке значение» цеплялся за ПЕРВОЕ
        вхождение — то есть за пункт меню, — и значением становился
        СЛЕДУЮЩИЙ ПУНКТ МЕНЮ. Замер на MATHEMA:
            Tvrtka       → «Sjedište/adresa»
            Status       → «Tvrtka»
            Pravni oblik → «Predmet poslovanja»
        Проверки статуса и формы сравнивали чепуху, в Excel уезжал чужой
        адрес — и всё это молча, потому что поля «читались».

        Данные начинаются после «Prikaži verziju za ispis» (или с первого
        «Nadležni sud» ПОСЛЕ меню). Режем по последнему вхождению якоря.
        """
        for якорь in ("Prikaži verziju za ispis", "Podaci o subjektu"):
            поз = текст.rfind(якорь)
            if поз >= 0:
                return текст[поз + len(якорь):]
        поз = текст.rfind("Nadležni sud")
        return текст[поз:] if поз >= 0 else текст

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self._данные(self.page.inner_text("body"))

        # ПОЛЕ Status (здоровый — «Bez postupka»), а не вся страница
        статус = self._поле(текст, "Status")
        низ = статус.lower()
        if any(w in низ for w in ПЛОХОЙ_СТАТУС):
            return False, f"статус: {статус}"
        причина = проверить_статус(статус)
        if причина:
            return False, причина

        причина = проверить_форму("HR", self._поле(текст, "Pravni oblik"))
        if причина:
            return False, причина

        # правда из реестра (в Tvrtka бывает две строки — берём первую, полную)
        self.имя = self._поле(текст, "Tvrtka") or self.имя
        адрес_карточки = self._адрес(текст)
        if адрес_карточки:
            self.адрес = адрес_карточки
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"\b{re.escape(подпись)}\b\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _адрес(текст: str) -> str:
        """«Sjedište/adresa\\nZagreb (Grad Zagreb)\\nRadnička cesta 80» → одной строкой."""
        m = re.search(r"Sjedište/adresa\s*\n\s*([^\n]+)\n\s*([^\n]+)", текст, re.I)
        if m:
            return f"{m.group(1).strip()}, {m.group(2).strip()}"
        m = re.search(r"Sjedište/adresa\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.mbs

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        """
        Сохраняем ПЕЧАТНУЮ ВЕРСИЮ карточки, а не саму страницу.

        На карточке есть ссылка «Prikaži verziju za ispis» — та же выписка без
        меню, оглавления и блока «Najnovije objave». Печать обычной страницы
        тащила в PDF всю навигацию сайта, и документ выглядел скриншотом, а не
        выпиской. Ссылки нет — печатаем как есть, это рабочий запасной путь
        (у гео method="print", официального файла реестр не отдаёт).
        """
        ссылка = self.page.get_by_text("Prikaži verziju za ispis").first
        if ссылка.count():
            было = self.page
            try:
                with self.br.ctx.expect_page(timeout=8000) as новая:
                    ссылка.click()
                вкладка = новая.value
                вкладка.wait_for_load_state("networkidle")
                вкладка.wait_for_timeout(1200)
                self.br.page = вкладка          # печатаем ИМЕННО её
                self.log("  · HR: печатаю версию для печати")
                путь = self.br.print_to_pdf(dest)
                вкладка.close()
                self.br.page = было
                return путь
            except Exception:
                # печатная версия могла открыться в ТОЙ ЖЕ вкладке
                self.br.page = было if было and not было.is_closed() else self.br.page
                try:
                    self.page.wait_for_load_state("networkidle")
                except Exception:
                    pass
        return self.br.print_to_pdf(dest)
