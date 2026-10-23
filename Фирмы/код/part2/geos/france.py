"""
ФРАНЦИЯ — annuaire-entreprises.data.gouv.fr.

Поток ТОЧНО по инструкции (прямая ссылка INPI даёт 403 — нужно идти через кнопки сайта):
  1. вводим имя → поиск
  2. кликаем результат → карточка
  3. проверяем EN ACTIVITÉ
  4. считываем SIREN(9)/SIRET(14) → в таблицу (колонки K/L)
  5. переходим на страницу justificatif:
        annuaire-entreprises.data.gouv.fr/justificatif-immatriculation-pdf/<SIREN>
  6. жмём "Télécharger le justificatif d'immatriculation" — качается PDF
     (перехватываем download ИЛИ новую вкладку, сессия сайта уже есть)
  7. сохраняем в выписки/FR под именем фирмы
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://annuaire-entreprises.data.gouv.fr"


class France(GeoDriver):
    code, title = "FR", "Франция"
    url = f"{BASE}/rechercher"
    method = "download"

    # Типы: отсеиваем ТОЛЬКО 🔴 (Association, SCI, SNC) — см. part2/core/формы.py.
    # SAS/SASU/SARL/EURL/SA, а также EI и micro-entrepreneur проходят.

    def __init__(self, br, human):
        super().__init__(br, human)
        self.siren = ""
        self.siret = ""
        self.имя = ""
        self.адрес = ""

    def индекс_фирмы(self, c: Company) -> str:
        """
        Пять цифр французского индекса. Из колонки, а нет её — ИЗ АДРЕСА.

        Колонка «Индекс» пустая у всей линии «без сайта»: Часть 1 разбирала
        адрес только когда у фирмы есть сайт (починено 10.09.2026), и у тысяч
        уже лежащих в таблице строк индекс остался внутри адреса —
        «4 B CHE DE LA FONDERIE 26200, MONTELIMAR, AUVERGNE RHONE ALPES».
        Ждать, пока их перезальют, нельзя: качаем по ним сегодня.

        Разбор берём тот же, что у Части 1, а не свою регулярку: во Франции
        индекс стоит ПЕРЕД первой запятой, и «последние пять цифр в строке»
        поймали бы номер дома в другой раскладке.
        """
        прямой = re.sub(r"\D", "", c.zip_code or "")[:5]
        if len(прямой) == 5:
            return прямой
        from part1.data.address_rules import разобрать
        разбор = разобрать(c.address or "", "FR")
        return разбор.индекс if len(разбор.индекс or "") == 5 else ""

    def search(self, c: Company) -> list[Candidate]:
        """
        Ищем ПО ЛОКАЦИИ, лестницей: коммуна → департамент → вся Франция.

        Так подсказал живой разбор «CRYSTAL». Без фильтра «CRYSTAL» даёт 2336
        результатов; первые двадцать — фирмы со всей Франции, среди них нашей
        нет, и человеку показывали девять чужих «CRYSTAL» с непохожими
        адресами. Выбрать из такого невозможно. Тот же запрос с индексом 93600
        даёт 18 результатов, и наша — вторая. Сайт умеет фильтровать по
        коммуне (`cp_dep` + `cp_dep_type=cp`) — грех не пользоваться.

        ДЕПАРТАМЕНТ — вторая ступень, добавлена 10.09.2026 по случаю «AQUA».
        Коммуна может промахнуться: фирма переехала внутри департамента,
        реестр пишет индекс соседнего кантона, в DnB опечатка. Раньше после
        промаха мы сразу срывались на всю страну — 3773 результата и девять
        однофамильцев человеку на выбор. Департамент 26 даёт 33.

        Кандидатов ступени «департамент» ПРОСЕИВАЕМ САМИ по индексу: если
        фильтр сайта однажды переименуют, мы этого не заметим, а молча
        показать всю Францию под видом департамента — худший исход.
        """
        индекс = self.индекс_фирмы(c)
        ступени = []
        if индекс:
            ступени.append((f"&cp_dep={индекс}&cp_dep_type=cp",
                            f"индекс {индекс}", ""))
            ступени.append((f"&cp_dep={индекс[:2]}&cp_dep_type=dep",
                            f"департамент {индекс[:2]}", индекс[:2]))
        ступени.append(("", "вся Франция", ""))

        for н, (фильтр, как, департамент) in enumerate(ступени):
            # quote(): символы & / пробел кодируем правильно, иначе «AS&M …»
            # рвётся на «AS»
            self.br.goto(f"{self.url}?terme={quote(c.name)}{фильтр}")
            self.page.wait_for_load_state("networkidle")
            if н == 0:
                self.br.check_captcha(c.name)
            cands = self._кандидаты()
            if департамент:
                свои = [к for к in cands
                        if re.search(rf"\b{департамент}\d{{3}}\b", к.address or "")]
                if свои:
                    self.log(f"  · {как}: {len(свои)} шт. вместо всей Франции")
                    return свои
                cands = []
            if cands:
                if фильтр:
                    self.log(f"  · {как}: {len(cands)} шт. вместо всей Франции")
                else:
                    cands = self._по_городу(c, cands)
                return cands
            if н + 1 < len(ступени):
                self.log(f"  · по «{как}» пусто — пробую {ступени[н + 1][1]}")
        return []

    def _по_городу(self, c: Company, cands: list[Candidate]) -> list[Candidate]:
        """
        Выдачу по всей стране просеять по ГОРОДУ — последнее, что у нас есть.

        Половина французских строк живёт вообще без индекса: в адресе стоит
        только «PARIS 6, ILE DE FRANCE, France». Фильтровать сайт по такому
        нечем, но выдачу — есть чем: у чужой фирмы в адресе будет свой город.
        Замер по «AQUA»: девять кандидатов из GARNACHE, PAMIERS, SAINT-JEAN-DE-
        LOSNE, MEZEL, SIGNES — ни одного из нашего города.

        НЕ НАШЛОСЬ НИ ОДНОГО — ОТДАЁМ ВСЕХ. Город мог устареть, фирма могла
        переехать, и решать это человеку. Просеивание только убирает заведомо
        чужих, но никогда не оставляет человека ни с чем.
        """
        город = re.sub(r"[\d\s]+$", "", (c.city or "").strip()).upper()
        if len(город) < 3:
            return cands
        свои = [к for к in cands if город in (к.address or "").upper()]
        if свои and len(свои) < len(cands):
            self.log(f"  · по всей Франции {len(cands)} шт., "
                     f"из них в городе {город}: {len(свои)}")
            return свои
        return cands

    def _кандидаты(self) -> list[Candidate]:
        cands = []
        виденные: set[str] = set()
        for item in self.page.locator("a[href*='/entreprise/']").all()[:60]:
            название = (item.inner_text() or "").strip().split("\n")[0].strip()
            href = item.get_attribute("href") or ""
            if not название or not href:
                continue
            # «1 établissement en activité» — это ссылка-счётчик, не имя фирмы
            if re.match(r"^\d+\s+[ée]tablissement", название, re.I):
                continue
            # ДЕДУП по SIREN из href: одна фирма = одна ссылка (иначе адрес совпадает
            # с двумя «кандидатами» одной фирмы → ложная неоднозначность)
            m = re.search(r"(\d{9})(?:\D|$)", href)
            ключ = m.group(1) if m else href
            if ключ in виденные:
                continue
            виденные.add(ключ)
            # АДРЕС — не заголовок ссылки, а БЛОК результата (там строка адреса с
            # индексом, напр. «… LA COUARDIERE 2 RUE SAINT ROCH 56800 PLOERMEL»).
            # Идём вверх к ближайшему предку, где есть французский индекс (5 цифр).
            адрес_блок = название
            anc = item
            for _ in range(6):
                anc = anc.locator("xpath=..")
                try:
                    t = anc.inner_text()
                except Exception:
                    break
                if re.search(r"\b\d{5}\b", t):
                    адрес_блок = re.sub(r"\s+", " ", t).strip()
                    break
            cands.append(Candidate(name=название, address=адрес_блок, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        url = cand.ref if cand.ref.startswith("http") else BASE + cand.ref
        self.br.goto(url)
        self.page.wait_for_load_state("networkidle")

    def check(self, c: Company) -> tuple[bool, str]:
        body = self.page.inner_text("body")
        if "EN ACTIVITÉ" not in body.upper() and "EN ACTIVITE" not in body.upper():
            return False, "нет статуса EN ACTIVITÉ"
        if "RADIÉE" in body.upper() or "LIQUIDATION" in body.upper():
            return False, "фирма закрыта / в ликвидации"

        # правовая форма: «Sa forme juridique est Société civile immobilière.»
        mf = re.search(r"forme juridique est\s+([^.\n]+)", body, re.I)
        причина = проверить_форму("FR", mf.group(1) if mf else "")
        if причина:
            return False, причина

        # SIREN из URL карточки (…-<9 цифр>) или из текста
        m = re.search(r"(\d{9})(?:\D|$)", self.page.url)
        if not m:
            m = re.search(r"\bSIREN\b[^\d]*(\d[\d\s]{8,})", body)
        self.siren = re.sub(r"\s", "", m.group(1))[:9] if m else ""

        ms = re.search(r"\bSIRET\b[^\d]*(\d[\d\s]{13,})", body)
        self.siret = re.sub(r"\s", "", ms.group(1))[:14] if ms else \
            (self.siren + "00000" if self.siren else "")

        if not self.siren:
            return False, "не нашёл SIREN"
        return True, ""

    def номер(self) -> str:
        return self.siren

    def данные_реестра(self) -> dict:
        """Имя и адрес с карточки annuaire — для колонки «Платёжный профиль выписки»."""
        try:
            body = self.page.inner_text("body")
        except Exception:
            return {"имя": self.имя, "адрес": self.адрес}
        # ВСЕГДА читаем с ТЕКУЩЕЙ карточки (без guard'ов «if not» — они тянули
        # имя/адрес от предыдущей фирмы: KALAM CONSEIL получал имя KEROPS).
        h1 = self.page.locator("h1").first
        if h1.count() and h1.inner_text().strip():
            self.имя = h1.inner_text().strip()
        m = re.search(r"Adresse\s*\n\s*([^\n]+)", body, re.I)
        if not m:          # запас: строка с французским индексом (5 цифр)
            m = re.search(r"([^\n]*\b\d{5}\b[^\n]*)", body)
        if m:
            self.адрес = re.sub(r"\s+", " ", m.group(1)).strip()
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        # переходим на страницу justificatif (там кнопка скачивания с сессией сайта)
        self.br.goto(f"{BASE}/justificatif-immatriculation-pdf/{self.siren}")
        self.page.wait_for_load_state("networkidle")

        селектор = ("a:has-text(\"Télécharger le justificatif\"), "
                    "button:has-text(\"Télécharger le justificatif\"), "
                    "a:has-text('Télécharger'), button:has-text('Télécharger')")

        # PDF может (а) скачаться как download, (б) открыться в новой вкладке
        try:
            with self.page.expect_download(timeout=20000) as dl:
                self.page.click(селектор)
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass

        # (б) новая вкладка с PDF
        try:
            with self.br.ctx.expect_page(timeout=15000) as new_tab:
                self.page.click(селектор)
            tab = new_tab.value
            tab.wait_for_load_state("domcontentloaded")
            pdf_url = tab.url
            tab.close()
            if pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower():
                return self.br.download_url(pdf_url, dest)
        except Exception:
            pass

        # не вышло автоматически — зовём человека
        self.human.stuck(
            "не удалось скачать выписку Франции автоматически.\n"
            "Нажми «Télécharger le justificatif d'immatriculation» в браузере, "
            "сохрани PDF, потом «Продолжить».", c.name)
        raise RuntimeError("FR: PDF не скачался автоматически")

    def extra_fields(self) -> dict:
        return {"siren": self.siren, "siret": self.siret}
