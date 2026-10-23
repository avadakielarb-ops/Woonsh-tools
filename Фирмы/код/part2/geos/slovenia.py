"""
СЛОВЕНИЯ — AJPES ePRS (Slovenian Business Register).

Поток (из записи codegen + скриншоты):
  1. /prs/default.asp?language=english → баннер «ALLOW»
  2. ГЛАВНОЕ: выдача закрыта — «Data not available. Registered users please log in.»
     Обходится БЕЗ пароля: LOGIN → «Log in as an anonymous user» → «Continue».
     Сессия живёт в профиле браузера, для следующих фирм вход уже не нужен.
  3. выдача по ПРЯМОМУ URL (status=1 — только действующие):
        /prs/rezultati.asp?podrobno=0&tip=0&naziv=<имя>&maticna=&davcna=&status=1&ulica=
     Колонки: Name(ссылка) | Short name | Address | Identification number | Tax Number
  4. карточка «Basic Information about the Entity» (блок #accordianBody1):
        Entity status              registered
        Registration number        6329632000
        Full company name          AQUA - SO 23 vodne storitve in inženiring d.o.o.
        Short company name         AQUA - SO 23 d.o.o
        Business address           Sodji Vrh 24, 8333 Semič
        Legal organizational form  Limited liability company (d.o.o.)
  5. внизу «REGULAR EXTRACT» — это ССЫЛКА и она даёт ПРЯМОЕ СКАЧИВАНИЕ PDF
     (проверено записью). PRINT не жмём — он открывает системный диалог.

В поле «Name:» есть автокомплит (role=option), но мы идём прямым URL выдачи —
он надёжнее. Сайт бывает капризным (страницы не грузятся) — делаем повтор перехода.
Номер — Registration number (10 цифр). Типы: 🔴 društvo / zavod / zadruga.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://www.ajpes.si"


class Slovenia(GeoDriver):
    code, title = "SI", "Словения"
    url = f"{BASE}/prs/default.asp?language=english"
    method = "download"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.рег = ""

    # ---------- поиск ----------

    @staticmethod
    def _улица(c: Company) -> str:
        """
        Название улицы из адреса Части 1 — БЕЗ номера дома и корпуса.

        AJPES фильтрует по полю `ulica` вхождением, а в реестре улица пишется
        по-словенски целиком («Vurnikova ulica 2»). Наш адрес — «Vurnikova
        ulica 2». Берём только буквенные слова: номер дома у DnB и у реестра
        расходится чаще, чем название улицы.
        """
        слова = [w for w in re.split(r"[\s,]+", (c.address or "").strip())
                 if len(w) >= 4 and re.match(r"^[^\d]+$", w)]
        return слова[0] if слова else ""

    def _url_выдачи(self, имя: str, улица: str = "", стр: int = 1) -> str:
        return (f"{BASE}/prs/rezultati.asp?podrobno=0&tip=0"
                f"&naziv={quote(имя)}&maticna=&davcna=&status=1"
                f"&ulica={quote(улица)}" + (f"&frm_pos={стр}" if стр > 1 else ""))

    def search(self, c: Company) -> list[Candidate]:
        """
        Сперва СУЖАЕМ выдачу улицей, и только потом ищем по всей стране.

        Живой разбор «ONE d.o.o.»: по одному имени AJPES отдаёт 51 фирму по
        десять на страницу, и наша — «ONE storitve d.o.o.», Vurnikova ulica 2 —
        стоит на ЧЕТВЁРТОЙ странице. Прежний код смотрел только первую и звал
        человека с десятью чужими «ONE». Тот же запрос с `ulica=Vurnikova`
        даёт РОВНО ОДНУ фирму — нужную.
        """
        self.br.goto(self.url)
        self._allow()
        self._имя, self._улица_поиска = c.name, ""
        улица = self._улица(c)

        выдача = self._url_выдачи(c.name, улица)
        self._перейти(выдача)
        # выдача закрыта → входим анонимно и повторяем
        if re.search(r"not available|please log in", self.page.inner_text("body"), re.I):
            self._аноним(c.name)
            self._перейти(выдача)

        if улица:
            найдено = self.кандидаты_страницы()
            if найдено:
                self.log(f"  · фильтр по улице «{улица}»: {len(найдено)} шт.")
                self._улица_поиска = улица
                return найдено
            self.log(f"  · по улице «{улица}» пусто — ищу по всей Словении")
            self._перейти(self._url_выдачи(c.name))
        self._стр = 1
        return self.кандидаты_страницы()

    # ---------- листание (фирма бывает на 4-й странице) ----------

    def следующая_страница(self) -> bool:
        стр = getattr(self, "_стр", 1) + 1
        тело = self.page.inner_text("body")
        m = re.search(r"Hits:\s*(\d+)\s*\(showing\s*(\d+)\s*-\s*(\d+)\)", тело, re.I)
        if not m or int(m.group(3)) >= int(m.group(1)):
            return False                       # показали всё, дальше нечего
        self._стр = стр
        self._перейти(self._url_выдачи(getattr(self, "_имя", ""),
                                       getattr(self, "_улица_поиска", ""), стр))
        return True

    def _перейти(self, url: str) -> None:
        """AJPES иногда не отдаёт страницу — пробуем ещё раз."""
        for _ in range(3):
            try:
                self.br.goto(url)
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(600)
                if "chrome-error" not in self.page.url:
                    return
            except Exception:
                pass
            self.page.wait_for_timeout(1200)

    def _allow(self) -> None:
        try:
            b = self.page.get_by_role("link", name="ALLOW", exact=True).first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    def _аноним(self, фирма: str) -> None:
        """
        Вход БЕЗ пароля: LOGIN → «Log in as an anonymous user» → «Continue».
        Именно так открывается выдача (из записи codegen).
        """
        try:
            вход = self.page.get_by_role("link", name="LOGIN").first
            if вход.count() and вход.is_visible():
                вход.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(600)
            аноним = self.page.get_by_text("Log in as an anonymous user").first
            if аноним.count() and аноним.is_visible():
                аноним.click()
                self.page.wait_for_timeout(600)
                кнопка = self.page.get_by_role("button", name="Continue").first
                if кнопка.count() and кнопка.is_visible():
                    кнопка.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(800)
                return
        except Exception:
            pass
        # не вышло автоматически — пусть человек войдёт руками
        self.human.login("AJPES (ajpes.si) — «Log in as an anonymous user»", фирма)

    def кандидаты_страницы(self) -> list[Candidate]:
        # Name(ссылка) | Short name | Address | Identification number | Tax Number
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for строка in self.page.locator("table tr").all():
            # ИМЕННО ссылка на карточку («podjetje.asp»), а не первая в строке.
            # У фирм с частями первой идёт значок «⊕» — раскрывашка, и её href
            # ведёт ОБРАТНО В ПОИСК («rezultati.asp?maticna=…»). Мы её и брали:
            # имя выходило пустым, а «карточка» открывалась страницей выдачи и
            # ждала данных, которых там нет. В логе это выглядело как
            # «карточка так и не открылась (капча)» — при живом и рабочем сайте.
            ссылка = строка.locator("a[href*='podjetje']").first
            if not ссылка.count():
                continue
            if not (ссылка.inner_text() or "").strip():
                continue
            ячейки = [строка.locator("td").nth(j).inner_text().strip()
                      for j in range(строка.locator("td").count())]
            if len(ячейки) < 4:
                continue
            href = ссылка.get_attribute("href") or ""
            if not href or href in виденные:
                continue
            виденные.add(href)
            # SHORT NAME (колонка 2) — второе официальное имя фирмы, и как раз
            # оно совпадает с тем, что даёт DnB: полное «ONE storitve d.o.o.»,
            # короткое «ONE d.o.o.» — а у нас в Excel именно «ONE d.o.o.».
            # Кладём в aliases: ядро сверяет и текущее имя, и прежние/краткие.
            коротко = ячейки[1].strip() if len(ячейки) > 1 else ""
            cands.append(Candidate(name=ссылка.inner_text().strip(),
                                   address=ячейки[2], ref=href,
                                   aliases=(коротко,) if коротко else ()))
        return cands

    # ---------- карточка ----------

    # У AJPES ДВЕ РАЗНЫЕ КАРТОЧКИ, И ПОДПИСИ НА НИХ НЕ СОВПАДАЮТ.
    #
    #   судебный реестр (d.o.o.)      деловой реестр, podjetje.asp (s.p.)
    #   ─────────────────────────     ─────────────────────────────────────
    #   Entity status: registered     поля статуса НЕТ вовсе
    #   Registration number           Identification number
    #   Full company name             Full name / Contracted name
    #   Business address              Address + City + Post office
    #
    # Пока ждали только левый столбец, на частных предпринимателях драйвер
    # висел два раза по 20 секунд и писал «карточка так и не открылась» —
    # при открытой и полной карточке. Замер по логам 08.10.2026: 40 фирм,
    # у которых «карточка не открылась», и среди них НИ ОДНОЙ d.o.o.
    ПРИЗНАК_КАРТОЧКИ = (
        "() => /Registration number|Entity status|Business address"
        "|Matična številka|Poslovni naslov"
        "|Identification number|Contracted name|PRS unit"
        "/i.test(document.body.innerText)")

    def _дождаться_карточки(self, фирма: str = "") -> bool:
        """
        AJPES открывает карточку НЕ СРАЗУ — ждём, пока на странице появятся
        поля реестра.

        Пока этого не ждали, выходило вот что: `check()` читал ещё пустую
        страницу и возвращал «статус: —»; ядро честно переспрашивало человека,
        тот жал «Продолжить», и `fetch()` печатал в PDF страницу сайта вместо
        выписки. Десять «скачанных» файлов по 120–200 КБ — и все мимо.

        ПРО КАПЧУ БОЛЬШЕ НЕ ВЫДУМЫВАЕМ. Прежнее сообщение «карточка за
        проверкой CAPTCHA» печаталось по ЛЮБОМУ таймауту — это была догадка,
        а не факт с экрана, и она увела разбор в сторону. Замер по логам
        11.09.2026: из 80 неоткрывшихся карточек 62 — частные предприниматели
        (s.p.), а из 40 удачных 35 — d.o.o. Все скачанные выписки пришли с
        `podjetjeSRG.asp`, то есть из СУДЕБНОГО реестра, где s.p. нет вовсе.
        Значит мы стучались не туда, а «капча» была ни при чём.
        Теперь пишем в лог, что НА САМОМ ДЕЛЕ на странице: адрес и первые
        слова текста. Следующий прогон сам расскажет, куда нас привели.
        """
        for попытка in (1, 2):
            try:
                self.page.wait_for_function(self.ПРИЗНАК_КАРТОЧКИ, timeout=20000)
                return True
            except Exception:
                pass
            # ЗДЕСЬ ЧЕЛОВЕК И ЖДЁТ ДОЛЬШЕ ВСЕГО — два раза по двадцать секунд.
            # Между попытками слушаем ручное управление: нажатое «Обновить»
            # перечитает страницу, и следующая попытка пойдёт уже по свежей.
            # Исполняет приказ ЭТОТ поток — Playwright чужого не прощает.
            if self.human.исполнить_приказ(self.br, self.log):
                continue
            if попытка == 1:
                # ПИШЕМ ФАКТ, А НЕ ДОГАДКУ. Раньше здесь стояло «проверяю
                # капчу и жду» — и печаталось это ПО ЛЮБОМУ таймауту, до
                # всякой проверки. Человек читал лог, шёл смотреть на сайт и
                # видел обычную открытую карточку без намёка на капчу.
                # Сама `check_captcha` не врёт: она молчит, если капчи нет, и
                # зовёт человека, только когда действительно её видит. Пусть
                # она и будет единственным, кто про капчу заговаривает.
                self.log("  · SI: карточка ещё не прочиталась — жду")
                self.br.check_captcha(фирма, ждать_мс=4000)
        self.log(f"  ⚠ SI: карточка так и не открылась — {self._что_на_экране()}")
        return False

    def _что_на_экране(self) -> str:
        """Адрес и начало текста страницы — чтобы лог говорил, а не гадал."""
        try:
            адрес = self.page.url or "—"
        except Exception:
            адрес = "—"
        try:
            текст = re.sub(r"\s+", " ", self.page.inner_text("body"))[:120]
        except Exception:
            текст = ""
        return f"адрес {адрес} · на странице: «{текст}»"

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            self._дождаться_карточки()
            return
        url = str(cand.ref)
        self._перейти(url if url.startswith("http") else f"{BASE}/prs/{url.lstrip('/')}")
        self._дождаться_карточки(cand.name)

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")

        статус = self._поле(текст, "Entity status")
        if статус:
            # Судебный реестр: статус написан прямо.
            if "registered" not in статус.lower():
                return False, f"статус: {статус or '—'}"
            причина = проверить_статус(статус)
            if причина:
                return False, причина
        else:
            # ДЕЛОВОЙ РЕЕСТР: поля статуса нет, и ждать его бессмысленно.
            # Факт регистрации написан в шапке карточки: «… | Registered in
            # Slovenian Business Register on day 08.10.2026». Плюс выдача, из
            # которой мы сюда пришли, строится с `status=1` — то есть только
            # действующие. Отсутствие поля — не повод терять живую фирму.
            if not self._карточка_prs(текст):
                return False, "статус: —"

        причина = проверить_форму("SI", self._поле(текст, "Legal organizational form"))
        if причина:
            return False, причина

        # правда из реестра
        self.имя = (self._поле(текст, "Full company name")
                    or self._поле(текст, "Short company name")
                    or self._поле(текст, "Full name")
                    or self._поле(текст, "Contracted name") or c.name)
        self.адрес = (self._поле(текст, "Business address")
                      or self._адрес_prs(текст))
        self.рег = re.sub(r"\D", "", self._поле(текст, "Registration number")
                          or self._поле(текст, "Identification number"))
        return True, ""

    @staticmethod
    def _карточка_prs(текст: str) -> bool:
        """Это карточка делового реестра и фирма в нём зарегистрирована."""
        return bool(re.search(r"Registered in Slovenian Business Register",
                              текст, re.I)
                    or re.search(r"Basic information on the PRS unit",
                                 текст, re.I))

    def _адрес_prs(self, текст: str) -> str:
        """
        Деловой реестр разносит адрес по строкам: Address / City / Post office.
        Собираем обратно в одну — такой же вид, как у судебного реестра.
        """
        части = [self._поле(текст, "Address"),
                 self._поле(текст, "Post office") or self._поле(текст, "City")]
        return ", ".join(ч for ч in части if ч)

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        """
        Значение рядом с подписью — на СЛЕДУЮЩЕЙ строке или на той же.

        Судебный реестр рисует таблицу так, что inner_text переносит значение
        на новую строку, деловой — бывает, что оставляет в той же. Раньше
        шаблон требовал перевода строки, и на карточке s.p. не читалось
        ничего.
        """
        m = re.search(rf"\b{re.escape(подпись)}\b\s*:?[ \t]*\n[ \t]*([^\n]+)",
                      текст, re.I)
        if not m:
            m = re.search(rf"\b{re.escape(подпись)}\b\s*:[ \t]*([^\n]+)",
                          текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.рег

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    # ---------- выписка ----------

    def fetch(self, c: Company, dest: Path) -> Path:
        """
        «REGULAR EXTRACT» — ссылка, отдающая настоящую выписку.

        ПЕЧАТЬ КАРТОЧКИ БОЛЬШЕ НЕ ТИХИЙ ЗАПАСНОЙ ВАРИАНТ. Раньше при любой
        осечке молча уходили в `print_to_pdf`, и в папку ложился PDF со
        страницей сайта (а то и с капчей) — по виду файл есть, по сути брак,
        и в логе об этом ни слова. Теперь: не нашли ссылку — ждём карточку,
        зовём человека, и только совсем в конце печатаем, СКАЗАВ ОБ ЭТОМ.
        """
        self._дождаться_карточки(c.name)

        # ЧЕМ КАЧАТЬ — ЗАВИСИТ ОТ КАРТОЧКИ.
        #   судебный реестр (d.o.o.) — ссылка «REGULAR EXTRACT»;
        #   деловой реестр (s.p.)    — кнопка «PDF» рядом с «PRINT».
        # Пока искали только первое, на предпринимателях драйвер доходил до
        # «ссылки нет — зову человека» и вставал на каждой фирме. Кнопка PDF
        # отдаёт тот же документ, что человек забирает руками.
        def взять() -> Path | None:
            искать = (
                lambda: self.page.get_by_role("link", name="REGULAR EXTRACT").first,
                lambda: self.page.get_by_text("REGULAR EXTRACT").first,
                lambda: self.page.get_by_role("link", name=re.compile(r"^\s*PDF\s*$", re.I)).first,
                lambda: self.page.get_by_role("button", name=re.compile(r"^\s*PDF\s*$", re.I)).first,
                lambda: self.page.locator("a[href*='pdf' i]").first,
            )
            for сел in искать:
                try:
                    эл = сел()
                    if not эл.count():
                        continue
                    эл.scroll_into_view_if_needed(timeout=4000)
                    путь = self.br.взять_документ(lambda: эл.click(), dest,
                                                  c.name, log=self.log)
                    if путь:
                        return путь
                except Exception:
                    continue
            return None

        путь = взять()
        if путь:
            return путь

        # ЧЕЛОВЕКА БОЛЬШЕ НЕ ЗОВЁМ. Раньше здесь стоял `stuck`, и на каждой
        # фирме без ссылки приходилось жать «Продолжить» — а дальше всё равно
        # печаталась карточка. Просьба человека 08.10.2026: «каждый раз когда
        # нету пдф я нажимаю продолжить — сделай, чтобы печатал сам».
        # Спрашивать о том, что всё равно сделаем, — это не осторожность, а
        # лишний клик на каждой фирме.
        self.log("  ⚠ SI: ни «REGULAR EXTRACT», ни кнопки PDF на карточке")
        путь = self.br._pdf_со_страницы(self.page, dest)
        if путь:
            return путь

        # последний рубеж: печать карточки. Это НЕ официальная выписка —
        # говорим прямо, чтобы такой файл не считали нормальным результатом.
        self.log("  ⚠ SI: официальной выписки не получил — печатаю карточку. "
                 "ЭТО НЕ ВЫПИСКА, проверь файл руками.")
        return self.br.print_to_pdf(dest)
