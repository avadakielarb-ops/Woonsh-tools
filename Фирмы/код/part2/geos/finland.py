"""
ФИНЛЯНДИЯ — virre.prh.fi (Virre, Кауппарекистери). ПЕРЕПИСАН 22.09.2026.

СТАРЫЙ САЙТ ЗАКРЫТ. Адрес `virre.prh.fi/novus/home?userLang=en` отдаёт
HTTP 404 — проверено запросом. Прежний драйвер ждал на нём поле поиска по
тридцать секунд и падал по таймауту на КАЖДОЙ фирме: замер по логам 11.09 —
32 фирмы, 0 скачано, четверть часа впустую. Человек видел «Sivua ei löydy».

Новый поток (по записи действий пользователя):
  1. https://virre.prh.fi/ → поле «Y-tunnus tai diaarinumero tai …»
     (номер, номер дела или имя) → кнопка `button_search`
  2. таблица результатов: строки с `data-testid="tableRow-N"`, в них ИМЯ
     (ссылка), ЗАРЕГИСТРИРОВАННЫЙ ОФИС и СТАТУС — по ним ядро и выбирает
  3. карточка фирмы. К выписке ДВА пути, и первый есть не всегда:
       · наверху кнопка `Avaa kaupparekisteriote`;
       · внизу СВЁРНУТЫЙ раздел «Avaa   Kaupparekisteriote -» → раскрыть →
         строка «Voimassaoleva ote» → кнопка с test-id `Avaa-button-`.
     Выписка открывается ПОПАПОМ («Ote kaupparekisteristä», PRH).
     Запись действий человека, дословно:
         page.get_by_test_id("tableRow-0").get_by_test_id("Aqua Oy").click()
         page.get_by_role("button", name="Avaa   Kaupparekisteriote -").click()
         with page.expect_popup():
             page.get_by_test_id("Avaa-button-").click()
  4. файл забираем `взять_документ` — он ловит и скачивание, и попап, и
     переход текущей вкладки, по сигнатуре %PDF

НЕ ЖДЁМ ЗДЕСЬ «ТИШИНЫ В СЕТИ». Virre — одностраничное приложение, оно
постоянно о чём-то спрашивает сервер, и `networkidle` не наступает НИКОГДА.
Два таких ожидания (после поиска и после открытия карточки) честно висели по
тридцать секунд и падали по таймауту на КАЖДОЙ фирме: живой прогон 15.10.2026
— «Timeout 30000ms exceeded» подряд, 0 скачано из 190. Ждать надо ТОГО, ЧЕГО
ЖДЁШЬ: строк выдачи и полей карточки.

Сайт говорит по-фински, но язык переключается, поэтому статусы и подписи
держим в двух написаниях. Номер — Y-tunnus (вида 0109160-2).
"""
from __future__ import annotations

import re
from pathlib import Path

from common.имена import без_формы
from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://virre.prh.fi"


class Finland(GeoDriver):
    code, title = "FI", "Финляндия"
    сам_режет_форму = True
    url = f"{BASE}/"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.bid = ""

    def search(self, c: Company) -> list[Candidate]:
        self.br.goto(self.url)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1200)               # приложение поднимается
        self._закрыть()
        # ПОЛЕ ОДНО НА ВСЁ: «Y-tunnus tai diaarinumero tai yrityksen nimi» —
        # номер, номер дела или имя. Ищем по началу подписи: хвост у неё
        # длинный и сайт его подправляет.
        поле = self.page.get_by_role(
            "textbox", name="Y-tunnus tai diaarinumero tai").first
        if not поле.count():
            поле = self.page.locator(
                "input[type='text']:visible, input[type='search']:visible").first
        поле.click()
        # БЕЗ ПРАВОВОЙ ФОРМЫ: реестр ищет по началу имени, и хвост «Oy» сужает
        # выдачу до нуля, если в реестре форма записана иначе.
        поле.fill(без_формы(c.name) or c.name)
        self.page.wait_for_timeout(400)
        кнопка = self.page.get_by_test_id("button_search").first
        if кнопка.count():
            кнопка.click()
        else:
            поле.press("Enter")
        # НЕ ЖДЁМ «ТИШИНЫ В СЕТИ». Virre — одностраничное приложение: оно
        # постоянно о чём-то спрашивает сервер, и networkidle не наступает
        # НИКОГДА. Ожидание честно висело свои 30 секунд и падало по таймауту
        # на КАЖДОЙ фирме — 190 из 190 (живой прогон 15.10.2026).
        # Ждём то, чего ждём на самом деле: строки выдачи ЛИБО честное «ничего
        # не нашлось» — иначе на пустом запросе стояли бы все двадцать секунд.
        # ...либо сразу КАРТОЧКУ: на единственное совпадение Virre открывает её
        # без таблицы.
        self._дождаться(self.ВЫДАЧА_ГОТОВА)
        self.page.wait_for_timeout(400)
        self.br.check_captcha(c.name)
        cands = self.кандидаты_страницы()
        if not cands:
            одна = self._карточка_как_кандидат()
            if одна:
                return [одна]
        return cands

    # Карточка фирмы: есть Y-tunnus и поля «Perustiedot / Yritysmuoto».
    ПРИЗНАК_КАРТОЧКИ = ("(/\\b\\d{7}-\\d\\b/.test(document.body.innerText)"
                        " && /Perustiedot|Yritysmuoto|Business ID|Company type/i"
                        ".test(document.body.innerText))")
    КАРТОЧКА_ДОРИСОВАНА = ("/Toiminimi|Company name/i.test(document.body.innerText)"
                           " && /Rekisteriss|In the register|Lakannut|Ceased/i"
                           ".test(document.body.innerText)")
    ВЫДАЧА_ГОТОВА = ("document.querySelector(\"[data-testid^='tableRow-']\") !== null"
                     " || /ei (haku)?tuloksia|no results|ei löytynyt/i"
                     ".test(document.body.innerText) || " + ПРИЗНАК_КАРТОЧКИ)

    def _карточка_как_кандидат(self) -> Candidate | None:
        """
        ОДНА ФИРМА — ЭТО НЕ «ПУСТО». На единственное совпадение Virre сразу
        открывает её карточку, без таблицы. Строк выдачи нет — и драйвер
        отвечал «ничего не нашлось», хотя фирма стояла на экране. Теперь
        карточка сама становится кандидатом, а выбирает её ядро — по имени,
        как любую строку выдачи.
        """
        try:
            на_карточке = bool(re.search(r"/yritys/\d{7}-\d", self.page.url or ""))
            if not на_карточке and not self.page.evaluate(
                    f"() => {self.ПРИЗНАК_КАРТОЧКИ}"):
                return None
            текст = self.page.inner_text("body")
        except Exception:
            return None
        # ИМЯ НА КАРТОЧКЕ — «Toiminimi» (по-английски «Company name»). Первая
        # версия искала «Nimi» и не находила его никогда: \b не даёт «Nimi»
        # внутри «Toiminimi». Живой прогон 20.10.2026: Anvil Holdings Oy,
        # Apukka Resort Oy, AH S.Lindén стояли на экране, а в логе «0 шт.».
        имя = (self._поле_карточки("Toiminimi") or self._поле_карточки("Company name")
               or self._поле(текст, "Toiminimi") or self._поле(текст, "Company name"))
        mb = (re.search(r"/yritys/(\d{7}-\d)", self.page.url or "")
              or re.search(r"\b(\d{7}-\d)\b", текст))
        if not имя or not mb:
            return None
        офис = (self._поле(текст, "Kotipaikka")
                or self._поле(текст, "Registered office")
                or self._поле(текст, "Domicile"))
        return Candidate(name=имя, address=офис,
                         ref={"карточка": True, "bid": mb.group(1), "имя": имя})

    def _поле_карточки(self, подпись: str) -> str:
        """
        Значение поля карточки ПО РАЗМЕТКЕ: строка, где ячейка
        «basicDetailsTitle» равна подписи, → её «basicDetailsCurrentInfo».

        Не по тексту страницы: в узком окне Virre перестраивает таблицу, и
        следом за «Toiminimi» в тексте шёл заголовок колонки «Viimeisin tieto»
        — его и брали за имя фирмы. textContent видит и скрытые ячейки.
        """
        try:
            return (self.page.evaluate(
                """(подпись) => {
                    for (const tr of document.querySelectorAll("[data-testid^='tableRow-']")) {
                        const т = tr.querySelector("[data-testid='tableCell-basicDetailsTitle']");
                        const з = tr.querySelector("[data-testid='tableCell-basicDetailsCurrentInfo']");
                        if (т && з && т.textContent.trim().toLowerCase() === подпись.toLowerCase())
                            return з.textContent.trim();
                    }
                    return "";
                }""", подпись) or "").strip()
        except Exception:
            return ""

    def _закрыть(self) -> None:
        """Информационный баннер сверху («Close»)."""
        try:
            b = self.page.get_by_role("button", name="Close").first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    # Живые статусы реестра. Сайт говорит по-фински, но язык переключается,
    # поэтому держим оба написания: гадать, какой стоит сейчас, незачем.
    ЖИВЫЕ_СТАТУСЫ = ("rekisteriss", "in the register")

    def кандидаты_страницы(self) -> list[Candidate]:
        """
        Строки выдачи нового Virre: у каждой свой `data-testid="tableRow-N"`.

        Что берём: ИМЯ (ссылка), ЗАРЕГИСТРИРОВАННЫЙ ОФИС и СТАТУС — ровно те
        три поля, что показывает таблица. Имя и офис уходят в сопоставление
        ядра (имя плюс подтверждение адресом), статус отсеивает нерабочие
        прямо здесь: открывать карточку ликвидированной фирмы незачем.

        ПЕРВУЮ СТРОКУ ВСЛЕПУЮ НЕ БЕРЁМ. В записи действий стоит
        `tableRow-0`, и соблазн взять её велик, но по слову вроде «aqua»
        выдача даёт десятки фирм: выбирать должно ядро — по имени и адресу,
        как во всех остальных гео.
        """
        cands: list[Candidate] = []
        виденные: set[str] = set()
        # НА КАРТОЧКЕ ВЫДАЧИ НЕТ. Её поля («Y-tunnus», «Toiminimi»…) свёрстаны
        # теми же tableRow-N, и читать их как строки выдачи значит получить
        # ноль «действующих» и объявить найденную фирму ненайденной.
        if re.search(r"/yritys/\d{7}-\d", self.page.url or ""):
            return []
        строки = self.page.locator("[data-testid^='tableRow-']")
        всего = строки.count()
        if not всего:                       # разметка сменилась — общий путь
            строки = self.page.locator("table tbody tr")
            всего = строки.count()
        for i in range(всего):
            строка = строки.nth(i)
            try:
                текст = строка.inner_text()
            except Exception:
                continue
            низ = текст.lower()
            if not any(с in низ for с in self.ЖИВЫЕ_СТАТУСЫ):
                continue                    # только действующие
            # Y-TUNNUS — ИЗ ССЫЛКИ «yritys/<Y-tunnus>», а не из текста строки.
            # В узком окне Virre прячет колонку номера, и inner_text её не
            # видит: номер пропадал, карточка не открывалась (живой прогон
            # 20.10.2026 в обычном Chrome — 4 из 10).
            href = ""
            try:
                а = строка.locator("a[href*='yritys/']").first
                href = (а.get_attribute("href") or "") if а.count() else ""
            except Exception:
                pass
            mb = (re.search(r"yritys/(\d{7}-\d)", href)
                  or re.search(r"\b(\d{7}-\d)\b", текст))
            ключ = mb.group(1) if mb else re.sub(r"\s+", " ", текст)[:60]
            if ключ in виденные:
                continue
            виденные.add(ключ)
            ссылка = строка.locator("a").first
            имя = (ссылка.inner_text().strip() if ссылка.count()
                   else self._ячейка(строка, "companyPrimaryName"))
            # ГОРОД — ячейка «domicile» (Kotipaikka). Прежде искали
            # «registeredOffice», которой нет, и подставляли ВСЮ строку:
            # «Aitoleipä Oy2048211-5LempääläO…» «спорила» с нашим адресом, и
            # фирма с точным именем отклонялась.
            адрес = (self._ячейка(строка, "domicile")
                     or self._ячейка(строка, "registeredOffice"))
            if not имя:
                continue
            cands.append(Candidate(name=имя, address=адрес,
                                   ref={"строка": i, "bid": ключ, "имя": имя}))
        return cands

    def _ячейка(self, строка, поле: str) -> str:
        """Значение ячейки строки по её `data-testid`. Нет такой — пусто."""
        try:
            я = строка.locator(f"[data-testid='tableCell-{поле}']").first
            return я.inner_text().strip() if я.count() else ""
        except Exception:
            return ""

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            return
        self.bid = cand.ref.get("bid", "")
        if cand.ref.get("карточка"):
            return                      # мы уже на ней: поиск сразу открыл карточку
        # ПРЯМЫМ АДРЕСОМ, А НЕ КЛИКОМ. Ссылка строки ведёт на «yritys/<Y-tunnus>»,
        # а Y-tunnus у нас уже есть. Клик по имени висел свои 30 секунд и падал
        # (живой прогон 20.10.2026: Anna Linden, Anvil IP Oy, Aqua Palvelu Oy —
        # выбраны верно, ни одна не открылась). Клик остаётся запасным путём.
        if re.fullmatch(r"\d{7}-\d", self.bid or ""):
            self.br.goto(f"{BASE}/yritys/{self.bid}")
        else:
            строка = self.page.locator("[data-testid^='tableRow-']").nth(
                cand.ref.get("строка", 0))
            имя = cand.ref.get("имя", "")
            ссылка = строка.get_by_test_id(имя).first if имя else None
            if ссылка is None or not ссылка.count():
                ссылка = строка.locator("a").first
            ссылка.click(timeout=10000)
        # Карточка — то же одностраничное приложение: номер в адресе есть
        # сразу, а поля дорисовываются позже. Ждём сами поля, иначе check()
        # читает пустоту («статус: —» у трёх из десяти, живая проверка).
        self._дождаться(self.КАРТОЧКА_ДОРИСОВАНА)
        # Та же беда, что и в поиске: ждём не «тишины», а признаков карточки.
        self._дождаться(
            "/Y-tunnus|Perustiedot|Business ID|Yritysmuoto/i"
            ".test(document.body.innerText)")
        self.page.wait_for_timeout(400)

    def _дождаться(self, условие: str, мс: int = 20000) -> bool:
        """
        Дождаться, что на странице ПОЯВИЛОСЬ нужное. Условие — выражение JS.

        Заменяет `wait_for_load_state("networkidle")`, которого на этом сайте
        не бывает: Virre — одностраничное приложение и сеть у него не затихает.

        ПОЧЕМУ JS, А НЕ СЕЛЕКТОР. Первая правка ждала через `locator(...)` со
        списком «CSS, text=/…/» через запятую — Playwright такую смесь движков
        не принимает и падает: «Unexpected token "=" while parsing css
        selector». Ожидание молча проваливалось, страница читалась пустой, и
        прогон 15.10.2026 не нашёл НИ ОДНОЙ фирмы из 190. Прежний
        `networkidle` при этом хотя бы случайно давал странице свои тридцать
        секунд на отрисовку — поэтому раньше фирмы находились.

        Не дождались — не падаем: дальше `check` прочитает, что есть, и честно
        скажет, если пусто.
        """
        try:
            self.page.wait_for_function(f"() => {условие}", timeout=мс)
            return True
        except Exception:
            return False

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")

        # ПОДПИСИ В ДВУХ ЯЗЫКАХ. Сайт финский, язык переключается — искать
        # только английское «Status of company» значит прочитать пусто и
        # объявить живую фирму нерабочей.
        статус = (self._поле_карточки("Yrityksen tila")
                  or self._поле_карточки("Status of company")
                  or self._поле_карточки("Tila")
                  or self._поле(текст, "Status of company")
                  or self._поле(текст, "Yrityksen tila")
                  or self._поле(текст, "Tila"))
        if not any(с in статус.lower() for с in self.ЖИВЫЕ_СТАТУСЫ):
            return False, f"статус: {статус or '—'}"
        причина = проверить_статус(статус)
        if причина:
            return False, причина

        тип = (self._поле_карточки("Yritysmuoto") or self._поле_карточки("Company type")
               or self._поле(текст, "Company type")
               or self._поле(текст, "Yritysmuoto"))
        причина = проверить_форму("FI", тип)
        if причина:
            return False, причина

        # правда из реестра
        self.имя = (self._поле_карточки("Toiminimi") or self._поле_карточки("Company name")
                    or self._поле(текст, "Toiminimi") or self._поле(текст, "Company name")
                    or self._поле(текст, "Name") or self._поле(текст, "Nimi")
                    or c.name)
        self.адрес = (self._поле(текст, "Postal address")
                      or self._поле(текст, "Registered office")
                      or self._поле(текст, "Kotipaikka"))
        if not self.bid:
            mb = re.search(r"\b(\d{7}-\d)\b", текст)
            self.bid = mb.group(1) if mb else ""
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """
        Значение поля карточки. Читаем ДВА вида разметки:

          1) в ОДНОЙ строке через табуляцию (так отдаёт сайт сейчас):
             «Status of company\\tIn the register\\t30.06.2009»
          2) на СЛЕДУЮЩЕЙ строке (так было раньше):
             «Company type\\nLimited company\\n01.01.1000»

        Из-за того что понимали только второй вид, ВСЕ поля карточки читались
        пустыми — и Финляндия давала «✘ статус: —» по всем десяти фирмам,
        то есть 0 из 10 при полностью рабочем поиске.

        \\b обязательны: иначе «Name» цепляется за «Company names» в меню.
        """
        m = re.search(rf"\b{re.escape(подпись)}\b[ \t]*\t[ \t]*([^\n]+)", текст, re.I)
        if not m:
            m = re.search(rf"\b{re.escape(подпись)}\b\s*\n\s*([^\n]+)", текст, re.I)
        if not m:
            return ""
        знач = m.group(1).strip()
        # справа может стоять дата начала (и вторая, «last date») — отрезаем
        знач = re.sub(r"(\s*\d{2}\.\d{2}\.\d{4})+\s*$", "", знач).strip()
        # значение и дата разделены табом — берём то, что до первой даты
        знач = re.split(r"\t", знач)[0].strip()
        return знач

    def номер(self) -> str:
        return self.bid

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    def _через_раздел(self, c: Company, dest: Path):
        """
        Раскрыть «Kaupparekisteriote» и нажать «Avaa» у действующей выписки.

        Порядок на живой карточке (скриншоты человека 15.10.2026):
            1. внизу полоса-раздел «Kaupparekisteriote» — СВЁРНУТА;
            2. раскрывается кликом, внутри строка «Voimassaoleva ote»;
            3. справа от неё кнопка «Avaa» — она и открывает выписку
               новой вкладкой (PDF «Ote kaupparekisteristä»).

        Раздел раскрываем ДО поиска кнопки: пока он свёрнут, «Avaa» в DOM
        может и быть, но кликать по невидимому Playwright откажется.
        """
        полоса = self.page.get_by_role(
            "button", name=re.compile(r"Kaupparekisteriote", re.I)).first
        if not полоса.count():
            полоса = self.page.locator(
                ":is(button,[role='button'],h2,h3,summary)"
                ":has-text('Kaupparekisteriote')").first
        if полоса.count():
            try:
                полоса.scroll_into_view_if_needed(timeout=4000)
                # Уже раскрыт — второй клик свернёт обратно.
                раскрыт = (полоса.get_attribute("aria-expanded") or "").lower()
                if раскрыт != "true":
                    полоса.click()
                    self.page.wait_for_timeout(700)
            except Exception:
                pass

        # КНОПКА ВНУТРИ РАЗДЕЛА — `Avaa-button-`, а не ссылка с текстом «Avaa».
        # Из записи действий человека: после раскрытия раздела жмётся именно
        # `get_by_test_id("Avaa-button-")`, и она открывает ПОПАП со встроенным
        # просмотрщиком PDF. Искать «ссылку с подписью Avaa» было пальцем в
        # небо: подпись у самого раздела тоже начинается с «Avaa».
        for найти in (
            lambda: self.page.get_by_test_id("Avaa-button-").first,
            lambda: self.page.locator("[data-testid^='Avaa-button']").first,
            lambda: self.page.get_by_role(
                "link", name=re.compile(r"^\s*Avaa\s*$", re.I)).first,
            lambda: self.page.get_by_role(
                "button", name=re.compile(r"^\s*Avaa\s*$", re.I)).first,
            # на всякий случай — английская раскладка того же сайта
            lambda: self.page.get_by_role(
                "link", name=re.compile(r"^\s*Open\s*$", re.I)).first,
        ):
            try:
                эл = найти()
                if not эл.count():
                    continue
                эл.scroll_into_view_if_needed(timeout=4000)
                self.log("  · раскрыл «Kaupparekisteriote», жму «Avaa»")
                путь = self.br.взять_документ(
                    lambda: эл.click(), dest, c.name, log=self.log)
                if путь:
                    return путь
            except Exception:
                continue
        return None

    _ЛОВУШКА_PDF = """() => {
      window.__пдф = null;
      if (!window.__ловушка_пдф) {
        const было = URL.createObjectURL;
        URL.createObjectURL = function (b) {
          try { if (b && /pdf/i.test(b.type || "")) window.__пдф = b; } catch (e) {}
          return было.apply(this, arguments);
        };
        window.__ловушка_пдф = true;
      }
    }"""
    _ЗАБРАТЬ_PDF = """async () => {
      const b = window.__пдф;
      if (!b) return "";
      const буф = new Uint8Array(await b.arrayBuffer());
      let s = "";
      for (let i = 0; i < буф.length; i += 0x8000)
        s += String.fromCharCode.apply(null, буф.subarray(i, i + 0x8000));
      return btoa(s);
    }"""

    def _выписка_из_blob(self, dest: Path) -> Path | None:
        """Нажать «Avaa kaupparekisteriote» и забрать PDF-blob со страницы."""
        import base64
        кнопка = self.page.get_by_test_id("Avaa kaupparekisteriote").first
        if not кнопка.count():
            return None
        страницы_до = set(id(p) for p in self.br.ctx.pages)
        try:
            self.page.evaluate(self._ЛОВУШКА_PDF)
            кнопка.click(timeout=10000)
            self.page.wait_for_function("() => !!window.__пдф", timeout=30000)
            данные = base64.b64decode(self.page.evaluate(self._ЗАБРАТЬ_PDF) or "")
        except Exception as e:
            self.log(f"  · выписку со страницы не забрал ({type(e).__name__})")
            return None
        finally:
            # Пустая вкладка, которую открыл сайт, нам не нужна.
            for p in list(self.br.ctx.pages):
                if id(p) not in страницы_до and p is not self.page:
                    try:
                        p.close()
                    except Exception:
                        pass
        if not данные.startswith(b"%PDF"):
            return None
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(данные)
        self.log(f"  · выписка взята со страницы ({len(данные) // 1024} КБ)")
        return dest

    def fetch(self, c: Company, dest: Path) -> Path:
        """
        «Open a Trade Register extract free of charge» → выписка открывается
        В НОВОЙ ВКЛАДКЕ, а не скачивается.

        Сайт об этом честно пишет прямо на карточке: «The Trade Register extract
        will open in a new tab. If the extract does not open automatically, you
        can open it through this link.» Прежний код ждал события download на
        СТАРОЙ вкладке — тридцать секунд, потом «FI: PDF не скачался». Человек
        при этом смотрел на уже открытую выписку и не понимал, чего от него
        хотят. Теперь `взять_документ` ловит все три исхода (скачивание,
        новая вкладка, переход текущей) и тянет байты по сигнатуре %PDF.
        """
        # 0) ГЛАВНЫЙ ПУТЬ — ЗАБРАТЬ PDF ИЗ СТРАНИЦЫ. Живая проверка 20.10.2026:
        #    «Avaa kaupparekisteriote» собирает выписку на странице как blob
        #    (application/pdf) и открывает ПУСТУЮ вкладку about:blank, куда
        #    потом подставляет её. Ни скачивания, ни адреса с PDF нет — ловить
        #    вкладку бесполезно, и прогон стоял на «Скрипт застрял» на каждой
        #    фирме. Подменяем URL.createObjectURL ДО клика и забираем сам blob.
        путь = self._выписка_из_blob(dest)
        if путь:
            return путь

        # 1) обычный путь — кнопка на карточке. На новом Virre она зовётся
        #    «Avaa kaupparekisteriote» и открывает выписку ПОПАПОМ со
        #    встроенным просмотрщиком PDF; `взять_документ` этот случай знает.
        кнопка = self.page.get_by_test_id("Avaa kaupparekisteriote").first
        if not кнопка.count():
            кнопка = self.page.get_by_role(
                "button", name="Avaa kaupparekisteriote").first
        if not кнопка.count():
            кнопка = self.page.get_by_role(
                "button", name="Open a Trade Register extract").first
        if not кнопка.count():
            кнопка = self.page.get_by_role(
                "link", name="Open a Trade Register extract").first
        if кнопка.count():
            путь = self.br.взять_документ(
                lambda: кнопка.click(), dest, c.name, log=self.log)
            if путь:
                return путь

        # 2) НАСТОЯЩИЙ ПУТЬ, если кнопки наверху нет: внизу карточки лежит
        #    СВЁРНУТЫЙ раздел «Kaupparekisteriote». Его надо раскрыть, и
        #    только тогда появится «Voimassaoleva ote» с кнопкой «Avaa»,
        #    которая и открывает выписку новой вкладкой.
        #    Пока этого не знали, драйвер искал кнопку, которой на экране
        #    ещё нет, и уходил звать человека на каждой фирме.
        путь = self._через_раздел(c, dest)
        if путь:
            return путь

        # 3) запасной путь — ссылка «you can open it through this link» из жёлтой
        #    плашки. Сайт сам предлагает её, когда вкладка не открылась.
        ссылка = self.page.locator(
            "a:has-text('through this link'), a:has-text('this link')").first
        if ссылка.count():
            self.log("  · вкладка не открылась — жму «open it through this link»")
            путь = self.br.взять_документ(
                lambda: ссылка.click(), dest, c.name, log=self.log)
            if путь:
                return путь

        self.human.stuck(
            "нажми «Open a Trade Register extract free of charge» — выписка "
            "откроется в НОВОЙ ВКЛАДКЕ. Оставь её открытой и нажми "
            "«Продолжить»: я заберу файл сам.", c.name)
        # человек открыл вкладку с выпиской — забираем её
        self.br.вкладка_человека(self.log)
        путь = self.br._pdf_со_страницы(self.page, dest)
        if путь:
            return путь
        raise RuntimeError("FI: PDF не скачался")
