"""
АВСТРИЯ — GISA (Gewerbeinformationssystem Austria).

Поток (из записи codegen + скриншоты):
  1. форма запроса (lang=en) → вкладка «Search by legal person»
     (по умолчанию открыта «by natural person» — обязательно переключаемся!)
  2. поле «Name/designation» → кнопка «Forward»
     Галочки «terminated business licences» и «foreign intermediaries» НЕ трогаем —
     так в выдачу попадают только ДЕЙСТВУЮЩИЕ лицензии.
  3. выдача, колонки:
        Generate document | GISA code | Holder of rights and duties | Address | Name of trade
     В «Holder of the business licence» стоит «Ovivo Aqua Austria GmbH;093915k»,
     где 093915k — номер в Фирменбухе. В «Address» — «Location 8074 Raaba-Grambach».
  4. качаем ссылку «GISA extract incl. historical data» (НЕ «Generate business
     licence»!) — открывается НОВАЯ ВКЛАДКА и оттуда идёт скачивание PDF.

GISA — реестр лицензий: у одной фирмы бывает НЕСКОЛЬКО строк (разные лицензии).
Склеиваем по номеру Фирменбуха, берём одну запись на фирму.
Номер — Фирменбух (напр. 093915k). Типы: 🔴 verein / stiftung.
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://www.gisa.gv.at"
# Форма открывается ТОЛЬКО со своими pid/pn. Короткий адрес «?lang=en» с
# какого-то момента отвечает «Diese Seite darf nur unter Angabe eines konkreten
# Formulars aufgerufen werden!» — и Австрия не находила ничего (живая проверка
# 20.10.2026). Адрес дал человек.
ФОРМА = (f"{BASE}/fshost-gisa-p/user/formular.aspx?"
         "pid=3e8b81d122df415db65b1ec312d5a452&pn=Be2102a48c44b427fa29b85296c7f6b3f"
         "&lang=en")


class Austria(GeoDriver):
    code, title = "AT", "Австрия"
    url = ФОРМА
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.фб = ""
        self._ссылка = None
        self._текст = ""

    # ---------- поиск ----------

    def search(self, c: Company) -> list[Candidate]:
        # СНАЧАЛА — ЖИВ ЛИ САЙТ. gisa.gv.at лежит регулярно, и раньше это
        # выглядело как «Скрипт застрял»: человек читал «доведи шаг руками»,
        # хотя доводить нечего — страницы нет. Спрашиваем прямо и по делу.
        try:
            self.br.goto(self.url)
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception as e:
            self.log(f"  ✘ AT: реестр не открылся ({type(e).__name__})")
            self.human.сайт_не_отвечает("Австрии (GISA)", self.url, c.name)
        self.page.wait_for_timeout(800)
        if not self.page.get_by_text("Search by legal person").count():
            self.log("  ✘ AT: формы поиска на странице нет — похоже, сайт лежит")
            self.human.сайт_не_отвечает("Австрии (GISA)", self.url, c.name)
        try:  # ОБЯЗАТЕЛЬНО: вкладка «по юрлицу», иначе ищет физлиц
            self.page.get_by_text("Search by legal person").first.click()
            self.page.wait_for_timeout(600)
        except Exception:
            pass
        try:
            поле = self.page.get_by_label("Name/designation").first
            поле.click()
            поле.fill(c.name)
            self.page.get_by_role("button", name="Forward").first.click()
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(800)
        except Exception:
            self.human.stuck(
                "не нашёл форму GISA — выбери «Search by legal person», впиши имя "
                "и нажми «Forward», потом «Продолжить».", c.name)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    def кандидаты_страницы(self) -> list[Candidate]:
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator("table tr").all():
            ссылка = строка.locator("a:has-text('GISA extract incl')").first
            if not ссылка.count():
                continue
            текст = строка.inner_text()
            m = re.search(
                r"Holder of the business licence\s*\n?\s*([^;\n]+?)\s*(?:;\s*([^\s\n]+))?\s*\n",
                текст, re.I)
            имя = m.group(1).strip() if m else ""
            фб = (m.group(2) or "").strip() if m else ""
            if not имя:
                continue
            ключ = фб or имя                       # одна фирма = несколько лицензий
            if ключ in виденные:
                continue
            виденные.add(ключ)
            ma = re.search(r"Location\s*\n?\s*([^\n]+)", текст, re.I)
            cands.append(Candidate(
                name=имя, address=(ma.group(1).strip() if ma else ""),
                ref={"ссылка": ссылка, "фб": фб, "имя": имя,
                     "адрес": (ma.group(1).strip() if ma else ""), "текст": текст}))
        return cands

    # ---------- «карточка» = строка выдачи ----------

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        d = cand.ref
        self._ссылка, self.фб = d["ссылка"], d["фб"]
        self.имя, self.адрес, self._текст = d["имя"], d["адрес"], d["текст"]

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self._текст or self.page.inner_text("body")
        if not re.search(r"Licence valid", текст, re.I):
            return False, "лицензия не действующая"
        причина = (проверить_форму("AT", self.имя) or проверить_статус(self.имя)
                   or проверить_статус(текст[:200]))
        if причина:
            return False, причина
        return True, ""

    def номер(self) -> str:
        return self.фб

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    # ---------- выписка ----------

    def fetch(self, c: Company, dest: Path) -> Path:
        if self._ссылка is None:
            self.human.stuck("не нашёл ссылку «GISA extract incl. historical data» — "
                             "скачай вручную и нажми «Продолжить».", c.name)
            raise RuntimeError("AT: нет ссылки на выписку")

        # Скачивание идёт из НОВОЙ вкладки. Вешаем слушатель на любые новые
        # страницы ЗАРАНЕЕ — иначе можно пропустить событие download.
        скачанные: list = []
        def на_новую_страницу(p):
            try:
                p.on("download", lambda d: скачанные.append(d))
            except Exception:
                pass
        self.br.ctx.on("page", на_новую_страницу)
        self.page.on("download", lambda d: скачанные.append(d))
        try:
            self._ссылка.click()
            for _ in range(60):                     # ждём до 30 секунд
                self.page.wait_for_timeout(500)
                if скачанные:
                    break
        except Exception:
            pass
        finally:
            try:
                self.br.ctx.remove_listener("page", на_новую_страницу)
            except Exception:
                pass

        if скачанные:
            self.br.сохранить(скачанные[0], dest)
            for стр in list(self.br.ctx.pages):     # закрыть вкладку выписки
                if стр is not self.page and "auszug" in (стр.url or ""):
                    try:
                        стр.close()
                    except Exception:
                        pass
            return dest

        self.human.stuck(
            "нажми «GISA extract incl. historical data», сохрани PDF под "
            f"«{c.name}», потом «Продолжить».", c.name)
        raise RuntimeError("AT: PDF не скачался")
