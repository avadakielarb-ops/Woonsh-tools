"""
ПОЛЬША — krs-pobierz.pl.

Поток по инструкции:
  1. поиск по имени → выдача (имя · KRS · NIP · Regon · Adres)
  2. сверяем имя И адрес (в DnB имя часто КОРОТКОЕ, в KRS ПОЛНОЕ — матчинг по имени
     держится на срезанных формах в normalize() + подтверждение адресом)
  3. открываем карточку → Status = aktywna, ещё раз адрес
  4. «Pobierz odpis KRS» → скачивается PDF (odpis-krs-<KRS>)

Карточка (по HTML): таблица #basicDataTable со строками Status / KRS / Adres,
имя в <h1>, кнопка-ссылка «Pobierz odpis KRS» → /odpis-krs-<KRS>.
Номер — KRS (10 цифр).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from common.имена import без_формы
from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

BASE = "https://krs-pobierz.pl"


class Poland(GeoDriver):
    code, title = "PL", "Польша"
    сам_режет_форму = True
    url = f"{BASE}/"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.krs = ""

    def search(self, c: Company) -> list[Candidate]:
        # Ищем ТОЛЬКО ПО НАЗВАНИЮ, БЕЗ правовой формы (форма в поиске мешает).
        #
        # Своих упрощений («первые два слова», «первое слово» — MUZO) тут
        # больше нет: они давали выдачу из сотни чужих фирм, где нашей нет, и
        # время уходило на листание. Как ещё спросить, решает ядро — у него
        # есть реестровое написание от модели (см. part2/местные_имена.py).
        q = без_формы(c.name) or (c.name or "").strip()
        self.br.goto(f"{BASE}/szukaj?q={quote(q)}")
        self.page.wait_for_load_state("domcontentloaded")
        self._cookie()                                   # баннер «Akceptuj wszystkie»
        self.br.check_captcha(c.name)
        # если сайт сразу открыл КАРТОЧКУ (ровно 1 результат) — она и есть,
        # не читаем «Polecane profile» как кандидатов
        if self._на_карточке():
            return [self._карточка_как_кандидат()]
        return self.кандидаты_страницы()

    def _на_карточке(self) -> bool:
        """Мы на странице фирмы (а не на списке): есть таблица данных + кнопка odpis."""
        try:
            return bool(self.page.locator("#basicDataTable").count()) and bool(
                self.page.locator("a:has-text('Pobierz odpis KRS')").count())
        except Exception:
            return False

    def _карточка_как_кандидат(self) -> Candidate:
        h1 = self.page.locator("h1").first
        имя = h1.inner_text().strip() if h1.count() else ""
        адрес = re.sub(r"\s+", " ", self._ячейка("Adres")).strip()
        url = self.page.url
        return Candidate(name=имя, address=адрес, url=url, ref=url)

    СЕЛЕКТОРЫ_COOKIE = (
        "button:has-text('Akceptuj wszystkie')",
        "button:has-text('Zaakceptuj wszystkie')",
        "button:has-text('Akceptuj')",
        "button:has-text('Zgadzam się')",
        "button:has-text('Zezwól na wszystkie')",
        "#onetrust-accept-btn-handler",
        "#truste-consent-button",
        "[id*='cookie'] button:has-text('Akcept')",
        "[class*='cookie'] button:has-text('Akcept')",
    )

    def _cookie(self) -> None:
        """
        Cookie-баннер krs-pobierz: «Akceptuj wszystkie». Принять ОБЯЗАТЕЛЬНО —
        иначе клики и скачивание блокируются.

        ЖДЁМ баннер, а не проверяем один раз: он поднимается скриптом уже после
        загрузки страницы, и прежняя версия просто пробегала мимо, пока его ещё
        не было. Ровно так же мы обожглись на TrustArc у dnb.com — там баннер
        перехватывал клик по кнопке поиска.
        """
        try:
            self.page.wait_for_selector(
                ", ".join(self.СЕЛЕКТОРЫ_COOKIE), state="visible", timeout=6000)
        except Exception:
            pass          # баннера нет (согласие уже дано) — и хорошо
        for сел in self.СЕЛЕКТОРЫ_COOKIE:
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click(timeout=4000)
                    self.page.wait_for_timeout(600)
                    return
            except Exception:
                continue
        # Не нашли свою кнопку — пробуем общий список попапов проекта.
        try:
            self.br.dismiss_popups()
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        # ссылки на карточки фирм оканчиваются на «-i<KRS>» (напр. …-i0000384182)
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("a[href*='-i0']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            href = ссылка.get_attribute("href") or ""
            m = re.search(r"-i(\d{6,})", href)
            if not m or m.group(1) in виденные:
                continue
            # ПРОПУСКАЕМ блок «Polecane profile» (рекомендации) — это не выдача
            try:
                if ссылка.locator(
                        "xpath=ancestor::*[contains(., 'Polecane')]").count():
                    continue
            except Exception:
                pass
            имя = ссылка.inner_text().strip()
            if not имя:
                continue
            виденные.add(m.group(1))
            # адрес — из блока результата (строка «Adres: …»)
            адрес = ""
            блок = ссылка.locator("xpath=ancestor::*[contains(.,'Adres')][1]")
            if блок.count():
                ma = re.search(r"Adres:\s*([^\n]+)", блок.inner_text())
                if ma:
                    адрес = ma.group(1).strip()
            cands.append(Candidate(name=имя, address=адрес, url=href, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        url = str(cand.ref)
        self.br.goto(url if url.startswith("http") else BASE + url)
        self.page.wait_for_load_state("domcontentloaded")
        self._cookie()

    def check(self, c: Company) -> tuple[bool, str]:
        статус = self._ячейка("Status").lower()
        if "aktywna" not in статус:
            return False, f"статус не aktywna ({статус or '—'})"
        h1 = self.page.locator("h1").first
        имя = h1.inner_text().strip() if h1.count() else ""
        if re.search(r"w likwidacji|w upad|wykreślon", имя, re.I):
            return False, "ликвидация / банкротство / вычеркнута"
        self.имя = имя
        self.krs = re.sub(r"\D", "", self._ячейка("KRS"))
        self.адрес = re.sub(r"\s+", " ", self._ячейка("Adres")).strip()
        return True, ""

    def _ячейка(self, подпись: str) -> str:
        """Значение из таблицы карточки по подписи (th → td)."""
        try:
            яч = self.page.locator(
                f"#basicDataTable tr:has(th:text-is('{подпись}')) td").first
            return яч.inner_text().strip() if яч.count() else ""
        except Exception:
            return ""

    def номер(self) -> str:
        return self.krs

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        сел = "a:has-text('Pobierz odpis KRS')"
        # (а) клик может сразу отдать файл
        try:
            with self.page.expect_download(timeout=12000) as dl:
                self.page.click(сел)
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass
        # (б) перешли на страницу odpis — может быть капча и кнопка/ссылка на PDF
        self.br.check_captcha(c.name)
        try:
            return self.br.click_download(
                "a:has-text('Pobierz'), button:has-text('Pobierz'), a[href$='.pdf']",
                dest, c.name)
        except Exception:
            self.human.stuck(
                "скачать odpis KRS автоматически не вышло.\n"
                "Нажми «Pobierz odpis KRS» (реши капчу, если появится), сохрани PDF, "
                "потом «Продолжить».", c.name)
            raise RuntimeError("PL: PDF не скачался")
