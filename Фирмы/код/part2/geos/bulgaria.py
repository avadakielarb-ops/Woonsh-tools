"""
БОЛГАРИЯ — официальный Търговски регистър (EPZEU), portal.registryagency.bg.
Cloudflare там НЕТ (в отличие от hithorizons, который жёстко банит).

ГЛАВНОЕ ОТЛИЧИЕ БОЛГАРИИ: искать нужно КИРИЛЛИЦЕЙ и БЕЗ правовой формы.
  DnB даёт «HEAT ENERGY OOD» (латиница) → реестр по латинице НИЧЕГО не находит.

ОСНОВНОЙ ПУТЬ (с 23.08.2026) — НЕ УГАДЫВАТЬ ИМЯ, А ВЗЯТЬ НОМЕР.
  Транслитерация принципиально ненадёжна: «ICE» она превращает в «ИСЕ», хотя
  по-болгарски это «АЙС» — побуквенные правила не знают, как записано английское
  ПРОИЗНОШЕНИЕ, а словарь всех слов не вместит. На этом сорвался живой прогон.
  Теперь ЭТАП 1 (part2.engine._собрать_еик) заранее собирает ЕИК всех болгарских
  фирм на hithorizons по английскому имени, кладёт в колонку «ЕИК», и драйвер
  идёт прямо на выписку: .../ActiveConditionTabResult?uic=<ЕИК>. Номер не переврать.

ЗАПАСНОЙ ПУТЬ — прежний поиск кириллицей: translit_bg.py (словарь + правила +
САМООБУЧЕНИЕ). Работает, когда ЕИК не нашёлся или кандидатов несколько. Движок
пишет болгарские имя/адрес в колонки «Название BG»/«Адрес BG» ДО прогона (человек
может поправить). Открыв карточку, драйвер запоминает реальное кириллическое имя
(запомнить()) — со временем транслит становится точнее.

Поток (по записи codegen + скринам):
  1. VerificationPersonOrg?...&name=<кириллица> → выдача: имя (кириллица) + UIC (9 цифр)
  2. выписка — ПРЯМОЙ URL:  .../Reports/ActiveConditionTabResult?uic=<UIC>
  3. печать «State of play» в PDF (через CDP).
Матч идёт по кириллице ВНУТРИ драйвера (ядро реестра сравнило бы латиницу и промахнулось).
Колонка K — АНГЛИЙСКИЙ (из Части 1). Болгарские данные карточки идут в доп-колонки для сверки.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate, адрес_сходится
from part2.core.models import Company
from part2.geos.base import GeoDriver
from part2.geos.translit_bg import транслит, транслит_адрес, запомнить, _ядро

PORTAL = "https://portal.registryagency.bg/CR/en"
SEARCH = f"{PORTAL}/reports/VerificationPersonOrg"
EXTRACT = f"{PORTAL}/Reports/ActiveConditionTabResult?uic="

# правовая форма из имени DnB (последнее слово) → кириллица реестра.
# Ею различаем тёзок: «AQUA SYSTEMS EAD» → нужен «АКВА СИСТЕМС ЕАД», не ООД/ЕООД.
_ФОРМА_КИР = {
    "eood": "ЕООД", "ood": "ООД", "ead": "ЕАД", "ad": "АД", "et": "ЕТ",
    "kd": "КД", "kda": "КДА", "sd": "СД", "dzzd": "ДЗЗД",
    "ltd": "ООД", "llc": "ООД", "limited": "ООД",   # иностранные ≈ ООД
    "jsc": "АД", "plc": "АД", "inc": "АД", "corp": "АД",
}
_ФОРМЫ_КИР_ВСЕ = {"еоод", "оод", "еад", "ад", "ет", "кд", "кда", "сд", "дззд"}


def _форма_dnb(имя: str) -> str:
    """Кириллическая форма по последнему слову имени DnB («… EAD» → «ЕАД»)."""
    слова = re.sub(r"[«»\"'`.,]", " ", (имя or "").lower()).split()
    return _ФОРМА_КИР.get(слова[-1], "") if слова else ""


def _форма_канд(имя: str) -> str:
    """Форма кандидата реестра («"АКВА СИСТЕМС" ЕАД» → «ЕАД»)."""
    слова = re.sub(r"[«»\"'`.,]", " ", (имя or "").lower()).split()
    for w in reversed(слова):
        if w in _ФОРМЫ_КИР_ВСЕ:
            return w.upper()
    return ""


def подобрать_по_форме(cands: list, log_ядро: str, форма_кир: str) -> list:
    """Тёзки по ядру имени → сузить правовой формой. Возвращает отфильтрованный список."""
    from part2.geos.bulgaria import _норм_bg  # локально, чтобы не плодить импорт
    точные = [k for k in cands if _норм_bg(k.name) == log_ядро]
    if len(точные) <= 1:
        return точные
    if форма_кир:
        по_форме = [k for k in точные if _форма_канд(k.name) == форма_кир]
        if по_форме:
            return по_форме
    return точные


def bg_имя_адрес(c: Company) -> tuple[str, str, bool]:
    """
    Болгарские черновики имени и адреса из данных Части 1 (для колонок Excel).
    Третий элемент — уверенность транслитерации имени (False → пометить «проверь»).
    """
    полный_адрес = ", ".join(x for x in (c.address, c.city, c.zip_code) if x)
    имя, уверенно = транслит(c.name)
    return имя, транслит_адрес(полный_адрес), уверенно


def _норм_bg(имя: str) -> str:
    """Ядро кириллического имени для сравнения кандидатов ВНУТРИ драйвера."""
    return _ядро(имя)


class Bulgaria(GeoDriver):
    code, title = "BG", "Болгария"
    один_запрос = True
    url = SEARCH
    method = "print"

    номер_regex = r"\b(\d{13}|\d{9})\b"    # ЕИК: 9 или 13 цифр

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""            # английские имя/адрес (для колонки K — финал на англ.)
        self.адрес = ""
        self.uic = ""
        self.bg_name = ""        # болгарское имя, по которому искали
        self.имя_реестра = ""    # что реально в карточке (кириллица) — для сверки
        self.адрес_реестра = ""

    # ---------- поиск ----------

    def search(self, c: Company) -> list[Candidate]:
        # английские данные из Части 1 — они пойдут в колонку K (финал на англ.)
        self.имя = c.name
        self.адрес = ", ".join(x for x in (c.address, c.city, c.zip_code) if x)

        # ЕИК известен (собран на hithorizons в ЭТАПЕ 1) — искать нечего.
        # Реестр отдаёт выписку прямым адресом по номеру, а номер, в отличие от
        # транслитерации имени, переврать невозможно. Это основной путь.
        еик = str(c.extra.get("eik") or "").strip()
        if еик.isdigit() and len(еик) in (9, 13):
            self.uic = еик
            self.bg_name = (c.extra.get("bg_name") or "").strip()
            self.log_ядро = ""
            return [Candidate(name=c.name, address=self.адрес, ref=еик)]
        # болгарское имя берём ИЗ КОЛОНКИ (движок положил в c.extra), БЕЗ попапа.
        # Пусто (нет колонки) — падаем на черновик транслитерации.
        self.bg_name = (c.extra.get("bg_name") or транслит(c.name)[0]).strip()
        log_ядро = _норм_bg(self.bg_name)

        # открыть выдачу прямым URL с кириллицей в параметре name
        self.br.goto(f"{SEARCH}?count=0&includeHistory=true&name={quote(self.bg_name)}"
                     f"&page=1&pageSize=25&selectedSearchFilter=1")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self._подожди_лимит(c.name)          # «Reached maximum...» — переждать, не считать «не найдено»
        self.br.check_captcha(c.name)

        cands = self.кандидаты_страницы()
        if not cands:                       # URL-поиск не отрисовал строки — форма (SPA)
            cands = self._поиск_формой()

        if not cands:
            self.human.stuck(
                f"по «{self.bg_name}» реестр ничего не показал. Найди фирму руками "
                "(кириллицей, без формы), открой её и нажми «Продолжить».", c.name)
            return [Candidate(name=self.bg_name, address="", ref="HUMAN")]

        # МАТЧ внутри драйвера: ИМЯ → ФОРМА → АДРЕС (как ты просил — имя+адрес).
        # Реестр лимитирует запросы, поэтому карточки НЕ перебираем без нужды.
        # 1) сузить тёзок по ядру имени + правовой форме (EAD→ЕАД…) — БЕЗ запросов
        точные = подобрать_по_форме(cands, log_ядро, _форма_dnb(c.name))
        if len(точные) <= 1:
            return точные or cands          # 0 точных → весь список человеку
        # 2) осталось несколько ОДНОЙ формы → сверяем АДРЕС, но открываем по одной
        #    карточке и ОСТАНАВЛИВАЕМСЯ на первом совпадении (экономим запросы)
        bg_addr = c.extra.get("bg_addr", "") or self.адрес
        if bg_addr:
            for k in точные[:4]:
                адр = self._адрес_карточки(str(k.ref))
                if адр and адрес_сходится(bg_addr, адр):
                    return [k]              # первый по адресу — берём, не мучаем реестр
        return точные                       # не различили → человек выберет

    def _адрес_карточки(self, uic: str) -> str:
        """Адрес (поле 5 «Head office») с выписки фирмы — для сверки тёзок."""
        try:
            self.br.goto(f"{EXTRACT}{uic}")
            self.page.wait_for_load_state("networkidle")
            self._подожди_лимит()
            txt = self.page.inner_text("body")
        except Exception:
            return ""
        m = re.search(r"5\.\s*Head office[^\n]*\n(.*?)(?:\n\s*\d+\.\s|\Z)", txt,
                      re.I | re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    # ---------- лимит запросов реестра ----------

    def _лимит(self) -> bool:
        try:
            низ = self.page.inner_text("body").lower()
        except Exception:
            return False
        return ("maximum number of requests" in низ
                or "максим" in низ and "заявк" in низ)

    def _подожди_лимит(self, company: str = "") -> None:
        """
        Реестр: «Reached maximum number of requests». НЕ принимаем за «не найдено»:
        ждём и перезагружаем несколько раз, потом зовём человека переждать минуту.
        """
        попыток = 0
        while self._лимит() and попыток < 3:
            попыток += 1
            self.page.wait_for_timeout(20000)          # 20с пауза между попытками
            try:
                self.page.reload()
                self.page.wait_for_load_state("networkidle")
            except Exception:
                pass
        if self._лимит():
            self.human.stuck(
                "реестр Болгарии ограничил число запросов («Reached maximum number "
                "of requests»). Подожди ~минуту (можно обновить страницу) и нажми "
                "«Продолжить».", company)
            try:
                self.page.reload()
                self.page.wait_for_load_state("networkidle")
            except Exception:
                pass

    def _поиск_формой(self) -> list[Candidate]:
        try:
            self.br.goto(SEARCH)
            self.page.wait_for_timeout(800)
            try:
                self.page.get_by_text("Legal entity", exact=True).first.click(timeout=3000)
            except Exception:
                pass
            поле = self.page.get_by_label("Company/name")
            if not поле.count():
                поле = self.page.get_by_placeholder("Company/name")
            поле.first.fill(self.bg_name, timeout=6000)
            try:
                self.page.get_by_role("button", name="Search").first.click(timeout=5000)
            except Exception:
                поле.first.press("Enter")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1500)
            self._подожди_лимит()
            return self.кандидаты_страницы()
        except Exception:
            return []

    def кандидаты_страницы(self) -> list[Candidate]:
        """Строки выдачи: имя (кириллица, ссылка) + UIC/PIC (9 цифр)."""
        cands: list[Candidate] = []
        виденные: set[str] = set()
        строки = self.page.get_by_role("row")
        for i in range(min(строки.count(), 60)):
            row = строки.nth(i)
            try:
                текст = row.inner_text()
            except Exception:
                continue
            m = re.search(r"\b(\d{9})\b", текст)      # UIC фирмы
            if not m:
                continue
            uic = m.group(1)
            if uic in виденные:
                continue
            виденные.add(uic)
            ссылка = row.get_by_role("link").first
            имя = (ссылка.inner_text().strip() if ссылка.count()
                   else текст.split("\n")[0].strip())
            cands.append(Candidate(name=имя, address="", ref=uic))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            текст = ""
            try:
                текст = self.page.inner_text("body")
            except Exception:
                pass
            m = (re.search(r"uic=(\d{9})", self.page.url)
                 or re.search(r"\b(\d{9})\b", текст))
            self.uic = m.group(1) if m else ""
            if self.uic:
                self.br.goto(f"{EXTRACT}{self.uic}")
                self.page.wait_for_load_state("networkidle")
            return
        self.uic = str(cand.ref)
        self.bg_name = cand.name or self.bg_name
        self.br.goto(f"{EXTRACT}{self.uic}")       # выписка «State of play» по UIC
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)

    def check(self, c: Company) -> tuple[bool, str]:
        try:
            текст = self.page.inner_text("body")
        except Exception:
            текст = ""
        низ = текст.lower()
        for плохо in ("в ликвидация", "ликвидация", "in liquidation",
                      "несъстоятелност", "insolvency", "bankrupt",
                      "заличен", "заличаване", "struck off", "deleted"):
            if плохо in низ:
                return False, f"статус-стоп: {плохо}"
        # UIC (на случай, если пришли через HUMAN и не сохранили)
        if not self.uic:
            m = re.search(r"\b(\d{9})\b", текст)
            self.uic = m.group(1) if m else ""
        # БОЛГАРСКИЕ имя/адрес из карточки — для СВЕРКИ (не для K). Идут в доп-колонки.
        m2 = re.search(r"2\.\s*Company\s*/?\s*Name\s*\n\s*([^\n]+)", текст, re.I)
        if m2:
            self.имя_реестра = m2.group(1).strip()
            # ОБУЧЕНИЕ: реестр — истина. Запоминаем «англ. имя → кириллица».
            запомнить(c.name, self.имя_реестра)
        m5 = re.search(r"5\.\s*Head office[^\n]*\n(.*?)(?:\n\s*\d+\.\s|\Z)", текст,
                       re.I | re.S)
        if m5:
            self.адрес_реестра = re.sub(r"\s+", " ", m5.group(1)).strip()
        return True, ""

    def номер(self) -> str:
        return self.uic or super().номер()

    def данные_реестра(self) -> dict:
        # колонка K — АНГЛИЙСКИЙ (имя/адрес из Части 1). Так решили.
        return {"имя": self.имя, "адрес": self.адрес, "сайт": ""}

    def fetch(self, c: Company, dest: Path) -> Path:
        # выписка «State of play» открыта — печатаем страницу в PDF (как Ctrl+P)
        try:
            return self.br.print_to_pdf(dest)
        except Exception:
            pass
        self.human.stuck(
            f"открой выписку по UIC {self.uic or '—'} (State of play), "
            "распечатай в PDF («Сохранить как PDF»), сохрани и нажми «Продолжить».",
            c.name)
        raise RuntimeError("BG: выписка не напечаталась автоматически")

    def extra_fields(self) -> dict:
        # для сверки: что реально в карточке реестра (кириллица). Колонки «Название BG»/
        # «Адрес BG» (наш поиск) уже записаны движком до прогона.
        поля = {}
        if self.имя_реестра:
            поля["Реестр имя BG"] = self.имя_реестра
        if self.адрес_реестра:
            поля["Реестр адрес BG"] = self.адрес_реестра
        return поля
