"""
ЭСТОНИЯ — ariregister.rik.ee (e-Business Register).

Поток по инструкции:
  1. поиск по имени → выдача (Name · Registry code · Status · Address).
     Удалённые («Deleted» / «Deletion warning») пропускаем. Сверка имени + адреса.
  2. карточка. ДВЕ проверки: Status = «Entered into the register» и НЕТ красных
     флагов (несданные годовые отчёты / штрафы / удаление).
     Третьей была «есть номер НДС» — снята 08.09.2026, подробности в check().
  3. «Data extract» → снять все галочки, оставить только «Registry card» → Download PDF.

Номер — Registry code (8 цифр). Красные флаги ищем в ВИДИМОМ тексте (подсказка
«Origin and meaning» лежит в атрибуте, не в тексте — ложно не сработает).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.base import GeoDriver

ROOT = "https://ariregister.rik.ee"
BASE = f"{ROOT}/eng"

# Правовые формы. По ним реестр НИЧЕГО не находит — замер на живом сайте
# 23.08.2026: «Lock Force OU» → 0 результатов, «Lock Force» → 1;
# «OU SLG Energy» → 0, «SLG Energy» → 7; «N.R. Energy Osauhing» → 0,
# «N.R. Energy» → 2. Из-за этого Эстония давала 0 из 10 весь прогон.
# Форма бывает и В КОНЦЕ, и В НАЧАЛЕ, и написанной словом.
#
# Свой список форм тут был до 20.10.2026 — и спорил с общим: искали без
# «Osaühing», а сравнивали с ним. Теперь список один, в common/имена.py.
from common.имена import без_формы


class Estonia(GeoDriver):
    code, title = "EE", "Эстония"
    сам_режет_форму = True
    url = BASE
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.код = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(BASE)
        поле = self.page.locator("#company_search, input[name='name_or_code']").first
        запрос = без_формы(c.name)
        if запрос != c.name:
            self.log(f"  · EE: ищу без правовой формы — «{запрос}»")
        поле.fill(запрос)
        (self.page.locator("button.btn-search, button[aria-label='Search']")
         .first.click())
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(800)
        self.br.check_captcha(c.name)
        return self.кандидаты_страницы()

    # блоки страницы, которые ВЫГЛЯДЯТ как выдача, но ею не являются
    НЕ_ВЫДАЧА = ".ar__subheader, .ar__subheader__recent_search, header, footer, nav"

    def кандидаты_страницы(self) -> list[Candidate]:
        """
        Кандидаты ИЗ ВЫДАЧИ — и только из неё.

        Сайт держит вверху панель «Last viewed» с теми же ссылками
        `/eng/company/<код>/…`. Мы забирали и их: в кандидаты попадали фирмы,
        просмотренные ранее, БЕЗ адреса (в панели его нет). Отсюда в логе
        «адресов в выдаче нет — смотрю карточки» и повторяющиеся имена, из-за
        которых ядро не могло выбрать и звало человека. Замер по «N.R. Energy»:
        четыре ссылки, из них две — «Last viewed».

        Адрес ищем, поднимаясь по предкам, пока в тексте не появится
        эстонский адрес: разметка выдачи — вложенные div, а не таблица,
        и прежний поиск «ближайшая строка/tr» упирался в подпись из 20 символов.
        """
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("a[href*='/company/']")
        for i in range(ссылки.count()):
            ссылка = ссылки.nth(i)
            try:
                if ссылка.evaluate(
                        f"e => !!e.closest({self.НЕ_ВЫДАЧА!r})"):
                    continue                              # «Last viewed» и меню
            except Exception:
                pass
            href = ссылка.get_attribute("href") or ""
            m = re.search(r"/company/(\d+)", href)
            if not m or m.group(1) in виденные:
                continue
            имя = ссылка.inner_text().strip()
            if not имя or имя.lower() in ("in english", "eesti keel"):
                continue
            текст, адрес = имя, ""
            узел = ссылка
            for _ in range(6):
                узел = узел.locator("xpath=..")
                try:
                    текст = узел.inner_text()
                except Exception:
                    break
                ma = re.search(r"([^\n]*(?:maakond|linn|vald)[^\n]*)", текст)
                if ma:
                    адрес = re.sub(r"\s*Open map\s*$", "", ma.group(1)).strip()
                    break
                if len(текст) > 400:                      # ушли выше строки
                    break
            # ОТСЕВ В ВЫДАЧЕ — ТОЛЬКО ДЛЯ УДАЛЁННЫХ, И ВСЛУХ.
            #
            # Было: выбрасывали и «Deleted», и «Deletion warning», причём молча.
            # Разбор 08.09.2026 на «Aqua Loard OÜ»: фирма в реестре есть, руками
            # находится с первого раза, а прогон говорил «похожего нет». Потому
            # что у неё в выдаче стоит Deletion warning — кандидат исчезал ещё
            # до сверки имени. Дальше включалась лестница упрощённых запросов,
            # реестр отвечал «слишком много запросов», и звали человека. Человек
            # открывал карточку, и она всё равно отваливалась по красному флагу.
            # Тот же итог, только через четыре лишних запроса и вопрос к живому.
            #
            # Теперь: «Deleted» — фирмы правда нет, пропускаем. «Deletion
            # warning» — предупреждение, а не приговор; кандидата ОСТАВЛЯЕМ,
            # решение принимает check() на карточке, где живут все остальные
            # красные флаги. Фильтровать в двух местах по разным правилам —
            # верный способ получить «не нашлось» там, где на самом деле «не
            # подошло».
            if re.search(r"\bDeleted\b", текст, re.I):
                self.log(f"  · EE: «{имя}» удалена из реестра — пропускаю")
                continue
            if re.search(r"\bDeletion warning\b", текст, re.I):
                self.log(f"  · EE: «{имя}» — стоит Deletion warning, "
                         f"беру и проверю на карточке")
            виденные.add(m.group(1))
            cands.append(Candidate(name=имя, address=адрес, url=href, ref=href))
        return cands

    def open(self, cand: Candidate) -> None:
        """
        Карточка по ПРЯМОМУ URL. Клик по ссылке в выдаче открыл бы её в НОВОЙ
        вкладке (`target=_blank`, видно в записи действий) — переход по адресу
        избавляет от этой возни целиком.

        Регистрационный код берём ИЗ АДРЕСА: /eng/company/12364776/NR-Energy…
        Раньше его читали только со страницы, полем «Registry code», и он не
        читался НИ РАЗУ — все десять выписок прогона ушли в Excel с «номер —».
        """
        if cand.ref == "HUMAN":
            self.код = self._код_из_url(self.page.url) or self.код
            return
        url = str(cand.ref)
        self.код = self._код_из_url(url) or self.код
        self.br.goto(url if url.startswith("http") else ROOT + url)
        self.page.wait_for_load_state("networkidle")
        self.код = self._код_из_url(self.page.url) or self.код

    @staticmethod
    def _код_из_url(url: str) -> str:
        m = re.search(r"/company/(\d{6,9})", url or "")
        return m.group(1) if m else ""

    def check(self, c: Company) -> tuple[bool, str]:
        text = self.page.inner_text("body")
        low = text.lower()

        статус = self._поле(text, "Status").lower()
        if "entered into the register" not in статус:
            return False, f"статус: {статус or '—'}"
        if any(w in статус for w in ("liquidation", "bankrupt", "deleted")):
            return False, f"статус: {статус}"

        # НЕСДАННЫЕ ОТЧЁТЫ И ШТРАФЫ БОЛЬШЕ НЕ ОТСЕИВАЮТ (решение 16.09.2026).
        # Правило пользователя простое: «если фирма активна — берём, если нет —
        # в мусор». Отчёты и штрафы — бюрократия, а не смерть: фирма в реестре,
        # выписка выдаётся, для Google Ads этого хватает. Цена прежнего правила
        # по логам 11–12.09: 131 фирма, САМАЯ ЧАСТАЯ причина отказа по Эстонии.
        # Говорим о флаге в лог — пусть видно, но дорогу не перекрываем.
        for флаг, причина in (
                ("non-submitted annual report", "не сданы годовые отчёты"),
                ("unpaid fine", "неоплаченные штрафы")):
            if флаг in low:
                self.log(f"  · {c.name}: {причина} — беру всё равно, фирма активна")
                break

        # ПРЕДУПРЕЖДЕНИЕ ОБ УДАЛЕНИИ ТОЖЕ НЕ ОТСЕИВАЕТ (правило уточнено
        # 17.09.2026: «просрочила годовой отчёт — берём, не берём только тех,
        # кто в ликвидации»). В Эстонии предупреждение и выносят ИМЕННО за
        # несданные отчёты — это та же причина, просто следующим шагом. Пока
        # фирма в реестре и не в ликвидации, она годится. Говорим в лог: если
        # реестр всё же вычеркнет её, по логу будет видно, что знали заранее.
        #
        # Настоящая смерть — статус выше: ликвидация, банкротство, «Deleted».
        # «Deleted» отсеивается ещё в выдаче, до карточки.
        for флаг, причина in (
                ("deletion warning", "предупреждение об удалении"),
                ("a deletion notice concerning", "уведомление об удалении")):
            if флаг in low:
                self.log(f"  · {c.name}: {причина} — беру, фирма ещё в реестре")
                break

        # НОМЕР НДС БОЛЬШЕ НЕ ТРЕБУЕМ (решение 08.09.2026).
        # Было: нет «EE» и девяти цифр на странице — фирма выбрасывалась.
        # Почему убрано. В Эстонии номер плательщика НДС дают только тем, кто
        # встал на учёт, а обязательно это лишь при обороте примерно от 40 000 €
        # в год. Живая маленькая OÜ его просто не имеет, и мы резали по РАЗМЕРУ
        # бизнеса, а не по пригодности. Цена: 49 фирм за всё время, 44 из них за
        # один прогон 08.09 — самая частая причина отказа по Эстонии, больше,
        # чем несданные отчёты. При этом сам номер никуда не сохранялся: ни в
        # колонку, ни в выписку. Выбрасывали из-за поля, которым не пользуемся.
        # Что фирма живая и не при смерти, доказывают две проверки выше —
        # статус в реестре и красные флаги; они остаются.
        # Ни у одного другого гео такой проверки нет и не было.

        # снимаем правду
        h = self.page.locator(".header-name-print").first
        имя = h.inner_text().strip() if h.count() else c.name
        self.имя = re.sub(r"\s*\(\d+\)\s*$", "", имя).strip()
        self.код = (self._код_из_url(self.page.url)
                    or re.sub(r"\D", "", self._поле(text, "Registry code"))
                    or self.код)
        ma = re.search(r"([^\n]*(?:maakond|linn|vald)[^\n]*\d{4,5})", text)
        self.адрес = ma.group(1).strip() if ma else ""
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"{re.escape(подпись)}\s*\n\s*([^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.код

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def fetch(self, c: Company, dest: Path) -> Path:
        # открыть модалку «Data extract»
        (self.page.locator(".btn__modal_print__js, button:has-text('Data extract')")
         .first.click())
        self.page.wait_for_selector("#printStartButton", timeout=10000)
        self.page.wait_for_timeout(400)

        # ВАЖНО: часть пунктов ОТМЕЧЕНА по умолчанию, а нам нужен ЧИСТЫЙ список +
        # только Registry card. Поэтому сперва снимаем всё через «Select all»
        # (#printSelectAll): пусто/частично → клик выделяет всё, второй клик снимает
        # всё; уже отмечен → один клик снимает. Кликаем по <label> (input скрыт).
        try:
            selall_label = self.page.locator("label[for='printSelectAll']").first
            if self.page.locator("#printSelectAll").is_checked():
                selall_label.click()
            else:
                selall_label.click()
                self.page.wait_for_timeout(250)
                selall_label.click()
            self.page.wait_for_timeout(300)
        except Exception:
            pass

        # теперь отметить ТОЛЬКО «Registry card» (#reg_card)
        try:
            if not self.page.locator("#reg_card").is_checked():
                self.page.locator("label[for='reg_card']").first.click()
                self.page.wait_for_timeout(200)
        except Exception:
            pass

        # «Download PDF» (#printStartButton) → прямое скачивание (без попапа, по записи)
        try:
            with self.page.expect_download(timeout=30000) as dl:
                self.page.locator("#printStartButton").click()
            return self.br.сохранить(dl.value, dest)
        except Exception:
            pass
        self.human.stuck(
            "открой «Data extract» → отметь «Registry card» → «Download PDF», "
            f"сохрани под «{c.name}», потом «Продолжить».", c.name)
        raise RuntimeError("EE: PDF сохраняет человек")
