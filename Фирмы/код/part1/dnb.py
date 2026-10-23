"""
ПАРСЕР DNB — переписан под нынешний сайт (по скриншотам выдачи и карточек, 19-07-2026).

ГЛАВНОЕ: страница выдачи — настоящая ТАБЛИЦА с колонками
    Company Name | Industry | Location Type | Country/Region
Имя, отрасль, город/страна берём ПРЯМО ИЗ ТАБЛИЦЫ, до открытия карточки.
Карточку открываем ТОЛЬКО ради сайта (поле «Website:» внизу справа) и адреса.

Так надёжнее (не путаем колонки) и быстрее (отсеиваем до открытия карточки).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

from common.browser import Browser
from common.human import HumanGate

from .data.countries import to_name
from .data.address_rules import разобрать, штат
from .models import Firm

BASE = "https://www.dnb.com"
DIRECTORY = f"{BASE}/business-directory.html"

KILL_POPUPS_JS = """
document.querySelectorAll(
  '#trustarc-wrapper, #truste-consent-track, .trustarc-banner-wrapper, .modal-backdrop, [id*="onetrust"]'
).forEach(el => el.remove());
document.body.style.overflow = 'auto';
"""

# Сайт фирмы: не всякая ссылка годится (в подвале живёт dnbcountryrisk.com и соцсети)
_НЕ_САЙТ = [
    ln.strip().lower()
    for ln in (Path(__file__).parent / "data" / "not_a_website.txt")
        .read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.startswith("#")
]


def это_сайт_фирмы(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http") or "dnb.com" in u or "dnbcountryrisk" in u:
        return False
    return not any(d in u for d in _НЕ_САЙТ)


class DnB:
    # ─── СЕЛЕКТОРЫ, КОТОРЫЕ САЙТ УЖЕ МЕНЯЛ ───────────────────────────────────
    # Держим их одним списком и ищем по ЧАСТИ подписи, а не по точному тексту.
    # 02.09.2026 dnb сменил вёрстку: подпись поля поиска стала другой, поле
    # страны потеряло placeholder и обзавелось id, а таблица выдачи стала
    # набором div-ов. Каждая жёсткая привязка тогда уронила Часть 1 целиком.
    ПОЛЕ_ПОИСКА = (
        'input[placeholder*="Search by company name" i], '   # 09.2026
        'input[placeholder="Search here...."], '             # прежняя вёрстка
        'input[placeholder*="Search" i]:visible'             # общий запас
    )
    ПОЛЕ_СТРАНЫ = (
        '#us-bd-country-input, '                             # 09.2026
        'input[placeholder*="Country" i], '                  # прежняя вёрстка
        'input.us-bd-filter__input'
    )
    # Блок карточки со строками «Address: …», «Phone: …», «Website: …».
    # Сам формат строк не менялся — сменился только контейнер.
    БЛОК_КАРТОЧКИ = ".cip-info-rows, #company_profile_snapshot"

    def __init__(self, br: Browser, human: HumanGate, log=print):
        self.br = br
        self.human = human
        self.page = br.page
        self.log = log

    def _kill_popups(self) -> None:
        try:
            self.page.evaluate(KILL_POPUPS_JS)
        except Exception:
            pass

    def _закрыть_попапы(self, ждать: bool = False) -> None:
        """
        На dnb.com ДВА окна (из записи codegen):
          1) согласие «Agree & Proceed»
          2) второй попап с кнопкой «Close» (их на странице несколько — жмём видимые)

        ждать=True — на только что открытой странице. Баннер согласия грузится
        асинхронно (скрипт с consent.trustarc.com), и если проскочить мимо него,
        он поднимется поверх и будет ПЕРЕХВАТЫВАТЬ клики — Playwright тогда
        честно пишет «intercepts pointer events» и не может нажать ни Search,
        ни подсказку страны.
        """
        if ждать:
            try:
                self.page.wait_for_selector("#truste-consent-button",
                                            state="visible", timeout=8000)
            except Exception:
                pass          # баннера нет (согласие уже дано в профиле) — и хорошо
        for сел in ("#truste-consent-button",            # TrustArc: «Agree & Proceed»
                    "button:has-text('Agree & Proceed')",
                    "#onetrust-accept-btn-handler",
                    "button:has-text('Accept All')"):
            try:
                эл = self.page.locator(сел).first
                if эл.count() and эл.is_visible():
                    эл.click()
                    self.page.wait_for_timeout(600)
            except Exception:
                continue
        # в записи попап закрывался через get_by_label('Close').nth(4) — жмём ВСЕ
        # видимые «Close» (и по aria-label, и по доступному имени)
        for наб in (self.page.get_by_label("Close"),
                    self.page.locator("[aria-label='Close'], button[title='Close']")):
            try:
                for i in range(min(наб.count(), 10)):
                    try:
                        э = наб.nth(i)
                        if э.is_visible():
                            э.click(timeout=2000)
                            self.page.wait_for_timeout(250)
                    except Exception:
                        continue
            except Exception:
                continue
        self._kill_popups()

    # ---------- поиск ----------

    # ── БЫСТРАЯ СМЕНА СЛОВА ────────────────────────────────────────────────
    # Замер 25.08.2026: полный круг (открыть каталог, погасить баннеры, вбить
    # слово, выбрать страну) — 29,5 секунды. Переход прямым адресом с другим
    # словом — 4,5 секунды, и ФИЛЬТР СТРАНЫ СОХРАНЯЕТСЯ: 22 из 22 строк
    # остались польскими. Значит страна живёт в сессии, а не в адресе.
    #
    # На авто-доборе слово меняется по 5–10 раз на страну, то есть экономия
    # 2–4 минуты на каждом гео и около часа на прогоне из восемнадцати.
    #
    # Первый заход по стране — всё равно полный: он и ставит фильтр.

    _адрес_выдачи: str = ""      # URL после удачного поиска
    _слово_выдачи: str = ""      # какое слово в этом URL
    _страна_выдачи: str = ""     # под какую страну он получен

    def сменить_слово(self, keyword: str, country: str) -> bool:
        """
        Сменить слово БЕЗ полного круга. False — не вышло, зовите search().

        Проверяем не «загрузилось ли», а ЕСТЬ ЛИ СТРОКИ и та ли страна: адрес
        мог отработать, а выдача остаться прежней или уехать на другую страну.
        Тогда честно возвращаем False и идём длинным путём.
        """
        from urllib.parse import quote
        if (not self._адрес_выдачи or not self._слово_выдачи
                or to_name(country) != self._страна_выдачи):
            return False
        старое = quote(self._слово_выдачи)
        адрес = self._адрес_выдачи.replace(
            f"BusinessDirectorySearch={старое}",
            f"BusinessDirectorySearch={quote(keyword)}")
        if "BusinessDirectorySearch=" not in адрес or адрес == self._адрес_выдачи:
            # слово в адресе не нашлось (сайт сменил разметку) — длинный путь
            return False
        try:
            self.log(f"  · быстрый переход на «{keyword}» (страна остаётся)")
            self.page.goto(адрес, wait_until="domcontentloaded", timeout=45000)
            # ждём САМУ выдачу, а не таймер: сколько думает страница, столько
            # и ждём, но не дольше десяти секунд
            try:
                self.page.wait_for_function(
                    "() => document.querySelectorAll('table tr').length > 1",
                    timeout=10000)
            except Exception:
                pass
            self.page.wait_for_timeout(400)
        except Exception as e:
            self.log(f"  · быстрый переход не вышел ({type(e).__name__})")
            return False
        if not self.rows():
            self.log("  · по быстрому адресу пусто — проверю длинным путём")
            return False
        ок, пояснение = self.страна_выдачи_совпадает(to_name(country))
        if not ок:
            self.log(f"  · после быстрого перехода страна не та ({пояснение})")
            return False
        self._адрес_выдачи, self._слово_выдачи = адрес, keyword
        return True

    def search(self, keyword: str, country: str) -> bool:
        # ПОРЯДОК СТРОГО ПО ЗАПИСИ codegen (пользователь прислал рабочий флоу):
        #   fill("Search here....") → click Search → закрыть попап →
        #   Enter Country/Region → fill → кнопка «France (1856)»
        self.log("  · открываю dnb.com/business-directory…")
        self.page.goto(DIRECTORY, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(1500)

        # 0) ПРОВЕРКА БЕЗОПАСНОСТИ. dnb.com сидит за Cloudflare и периодически
        # встречает страницей «подтвердите, что вы человек». Раньше её никто не опознавал,
        # и шаг просто падал по таймауту («поле поиска не найдено») — потому что поля
        # на этой странице и нет. Теперь зовём человека сразу и по делу.
        self.br.check_captcha(keyword)

        # СОГЛАСИЕ НА КУКИ — гасим ДО поиска, а не после.
        # Раньше попапы закрывались только после клика по Search, и баннер TrustArc
        # успевал перехватить этот клик на себя.
        self._закрыть_попапы(ждать=True)

        # 1) ПОИСК.
        # Подпись поля СМЕНИЛАСЬ (перемер 02.09.2026): было «Search here....»,
        # стало «Search by company name or D-U-N-S Number». Жёсткая привязка к
        # старой подписи роняла Часть 1 целиком: поле не находилось, и каждая
        # фирма упиралась в «Скрипт застрял». Поэтому ищем по ЧАСТИ подписи и
        # держим запасные селекторы — подпись поменяют снова.
        try:
            поле = self.page.locator(self.ПОЛЕ_ПОИСКА).first
            поле.wait_for(state="visible", timeout=15000)
            поле.click()
            поле.fill(keyword)
            self.log(f"  · вбил «{keyword}», жму Search")
            self.page.get_by_role("button", name="Search", exact=True).click(timeout=8000)
        except Exception as e:
            self.log(f"  · поиск не сработал ({type(e).__name__}) — зову человека")
            self.human.stuck(
                "вбей слово в строку поиска, нажми Search и «Продолжить».",
                keyword)

        # 2) ПОПАП после поиска (в записи — get_by_label('Close').nth(4))
        self.page.wait_for_timeout(2500)
        self._закрыть_попапы()
        self.br.check_captcha()

        # 3) СТРАНА
        self.log(f"  · выбираю страну: {to_name(country)}")
        предложена = self._выбрать_страну(to_name(country))
        self._чип_или_выдача(to_name(country))
        if not предложена:
            # Страны нет в подсказке — по слову в ней фирм не нашлось. Возврат
            # False, и движок возьмёт ДРУГОЕ СЛОВО. Человека звать не за чем:
            # руками он тоже ничего не выберет, выбирать не из чего.
            return False
        self.log("  · страна применена, читаю фирмы")
        # запоминаем адрес удачной выдачи — по нему потом меняем слово за 4 с
        # вместо полного круга в 30 (см. сменить_слово)
        try:
            self._адрес_выдачи = self.page.url
            self._слово_выдачи = keyword
            self._страна_выдачи = to_name(country)
        except Exception:
            self._адрес_выдачи = ""
        return True

    def _выбрать_страну(self, name: str) -> bool:
        """
        Фильтр «Enter Country/Region» — СТРОГО ПО ЗАПИСИ:
          get_by_placeholder("Enter Country/Region").click()/fill(name)
          → get_by_role("button", name="France (1856)").click()
        Число в скобках («1856») меняется — ловим кнопку «<Страна> (<число>)» regex-ом.
        ВОЗВРАЩАЕТ: предложил ли dnb эту страну вообще.

        И это САМОЕ ВАЖНОЕ здесь. В подсказке страны стоят с числом найденного:
        «Austria (502)». Если страны в подсказке НЕТ — значит по этому слову в
        ней нет ни одной фирмы. Не «сайт затупил», не «поле не нашлось», а
        честный ответ: слово для этой страны пустое, нужно другое.

        Раньше этот ответ терялся: функция ничего не возвращала, а несовпадение
        лечили вызовом человека. В автономном режиме за человека отвечал робот
        «пропустить», и это заканчивало ВСЮ СТРАНУ. 09.09.2026 так, на первом
        же слове, погибли шесть стран из девятнадцати.
        """
        try:
            поле = self.page.locator(self.ПОЛЕ_СТРАНЫ).first
            if not поле.count():
                self.log("  · поля страны на странице нет")
                return False
            поле.click(timeout=6000)
            поле.fill(name, timeout=6000)
            self.page.wait_for_timeout(2500)          # ждём выпадающую подсказку
            # подсказка — КНОПКА вида «France (1856)» (число своё у каждой страны)
            кнопка = self.page.get_by_role(
                "button", name=re.compile(rf"^{re.escape(name)}\s*\(\d[\d\s]*\)", re.I)
            ).first
            if кнопка.count() and кнопка.is_visible():
                кнопка.click(timeout=6000)
                self.page.wait_for_timeout(3000)
                self._kill_popups()
                return True
            # запас: пункт списка, начинающийся с имени страны. Число в скобках
            # могло не прорисоваться — но сам пункт есть, значит фирмы есть.
            зап = self.page.locator(
                f"button:has-text('{name}'), [role='option']:has-text('{name}')").first
            if зап.count() and зап.is_visible():
                зап.click(force=True, timeout=6000)
                self.page.wait_for_timeout(3000)
                self._kill_popups()
                return True
            # Страны в подсказке НЕТ — по этому слову тут фирм не найдено.
            self.log(f"  · «{name}» в подсказке не предложена — по слову в этой "
                     f"стране фирм нет")
            return False
        except Exception as e:
            self.log(f"  · сам страну не выбрал ({type(e).__name__})")
            return False
        # ЧИП — ПРИЗНАК, А НЕ ПРИГОВОР. Здесь стоял вызов человека: не увидел
        # чипа — встань и выбери страну руками. В автономном режиме отвечать
        # за человека некому, ответ «пропустить» вылетал как SkipCompany и
        # заканчивал ВСЮ СТРАНУ. Замер 09.09.2026: так, на первом же поиске,
        # погибли Австрия, Бельгия, Болгария, Швейцария, Дания и Эстония —
        # шесть стран из девятнадцати.
        #
        # А чип и не должен решать: решает САМА ВЫДАЧА (страна_выдачи_совпадает),
        # и об этом прямо написано в _страна_применена. Проверка по строкам идёт
        # следом, она переищет сама, а если выдача правда чужая — там и позовут
        # человека, уже по делу.
    def _чип_или_выдача(self, name: str) -> None:
        """
        Чип — признак, а не приговор: решает САМА ВЫДАЧА
        (страна_выдачи_совпадает), и об этом прямо написано в _страна_применена.
        Здесь только пишем в лог, чтобы в разборе было видно.
        """
        if not self._страна_применена(name):
            self.log(f"  · чипа «{name}» не видно — проверю по самой выдаче")
        self._kill_popups()

    def _страна_применена(self, name: str) -> bool:
        """
        Фильтр применён ИМЕННО на эту страну?

        ОСТОРОЖНО, здесь была ловушка. Раньше хватало видимой ссылки «Clear All» —
        но она есть при ЛЮБОМ применённом фильтре, в том числе оставшемся от
        ПРЕДЫДУЩЕЙ страны. В мультигео это означало бы: перешли с Франции на Польшу,
        фильтр не переключился, проверка сказала «применено» — и в польский лист
        поехали французские фирмы. Признак «Clear All» убран.

        Решающее слово — за САМОЙ ВЫДАЧЕЙ (см. страна_выдачи_совпадает).
        Чип проверяем лишь как быстрый предварительный признак.
        """
        try:
            чип = self.page.locator(
                f"[class*='chip']:has-text('{name}'), [class*='tag']:has-text('{name}'), "
                f"[class*='pill']:has-text('{name}'), "
                f"[class*='selected']:has-text('{name}')").first
            return bool(чип.count() and чип.is_visible())
        except Exception:
            return False

    # У DnB в колонке Country/Region бывает не то же слово, что в фильтре.
    СИНОНИМЫ_СТРАН = {
        "czech republic": ("czech republic", "czechia"),
        "united kingdom": ("united kingdom", "great britain"),
        "united states": ("united states", "usa"),
        "netherlands":   ("netherlands", "holland"),
    }

    def страна_выдачи_совпадает(self, name: str, порог: float = 0.8) -> tuple[bool, str]:
        """
        ГЛАВНАЯ проверка страны — по самим строкам выдачи, а не по элементам фильтра.

        Чип и «Clear All» могут врать (остаться от прошлой страны, не перерисоваться),
        а колонка Country/Region в строках — нет. Смотрим, какая доля строк
        действительно из нужной страны.

        Возвращает (совпало, пояснение для лога).
        """
        строки = self.rows()
        if not строки:
            return False, "в выдаче нет строк"
        варианты = self.СИНОНИМЫ_СТРАН.get(name.lower(), (name.lower(),))
        свои = sum(1 for f in строки
                   if any(в in (f.address or "").lower() for в in варианты))
        доля = свои / len(строки)
        чужая = next((f.address for f in строки
                      if not any(в in (f.address or "").lower() for в in варианты)), "")
        пояснение = f"{свои} из {len(строки)} строк — «{name}»"
        if чужая:
            пояснение += f"; чужая строка: «{чужая[:50]}»"
        return доля >= порог, пояснение

    # ---------- ТАБЛИЦА ВЫДАЧИ (главный источник данных) ----------

    # ВЫДАЧА БОЛЬШЕ НЕ ТАБЛИЦА (перемер 02.09.2026). Раньше это был <table> с
    # <td>; теперь строка — div.search-result-flex-row, а колонки — четыре
    # div.search-result-flex-cell в том же порядке:
    #     0 Company Name   1 Industry   2 Location Type   3 Country/Region
    # `table tr` на новой странице даёт НОЛЬ, поэтому Часть 1 переставала
    # видеть фирмы вовсе.
    СТРОКА_ВЫДАЧИ = ".search-result-flex-row"
    ЯЧЕЙКА_ВЫДАЧИ = ".search-result-flex-cell"
    # Мусор внутри ячейки с именем: ссылки-приманки, которых в старой таблице
    # не было. Само имя берём из <a>, но подстрахуемся и здесь.
    МУСОР_В_ИМЕНИ = ("Business Credit Reports", "View D-U-N-S® Number",
                     "View D-U-N-S Number", "Company Profile")

    def rows(self) -> list[Firm]:
        """
        Строки выдачи. Каждая = фирма с колонками
        Company Name | Industry | Location Type | Country/Region.
        Имя/отрасль/город берём отсюда — карточка не нужна для отсева.
        """
        out: list[Firm] = []
        строки = self.page.locator(self.СТРОКА_ВЫДАЧИ).all()
        if not строки:                      # запасной путь на старую вёрстку
            строки = self.page.locator("table tbody tr, .search-results tr").all()
        for row in строки:
            ссылка = row.locator("a[href*='/business-directory/company-profiles']").first
            if not ссылка.count():
                continue
            имя = ссылка.inner_text().strip()
            href = ссылка.get_attribute("href") or ""
            if not имя or not href:
                continue
            for м in self.МУСОР_В_ИМЕНИ:
                имя = имя.replace(м, " ")
            имя = re.sub(r"\s+", " ", имя).strip()
            if not имя:
                continue

            ячейки = row.locator(self.ЯЧЕЙКА_ВЫДАЧИ).all() or row.locator("td").all()
            def текст(i: int) -> str:
                try:
                    return ячейки[i].inner_text().strip().replace("\n", " ") \
                        if len(ячейки) > i else ""
                except Exception:
                    return ""
            отрасль, тип, страна_город = текст(1), текст(2), текст(3)
            город, индекс = _город_индекс(страна_город)

            out.append(Firm(
                name=имя, industry=отрасль, location_type=тип,
                city=город, zip_code=индекс, address=страна_город,
                url=urljoin(BASE, href),
            ))
        return out

    def строк_в_таблице(self) -> int:
        """
        Сколько строк в таблице выдачи ФИЗИЧЕСКИ — до всякого разбора.

        Зачем отдельно от rows(). rows() пропускает строки без ссылки на
        карточку, и полная страница из 25 строк возвращается как 24 или 23
        (по логам: 105 страниц ровно по 25, но 47 раз по 24 и 15 по 23).
        Считать «последняя ли страница» по разобранным строкам поэтому нельзя:
        каждая вторая полная страница сойдёт за последнюю, и слово будет
        брошено с половиной непросмотренных фирм.
        """
        try:
            n = self.page.locator(self.СТРОКА_ВЫДАЧИ).count()
            if not n:
                n = self.page.locator("table tbody tr, .search-results tr").count()
            return n
        except Exception:
            return 0

    def next_page(self) -> bool:
        """
        Листаем на следующую страницу выдачи. False — страниц больше нет.
        Проверяем, что выдача РЕАЛЬНО сменилась (иначе можно решить, что кнопка
        сработала, хотя список тот же).
        """
        try:
            было = self._первая_фирма()
            # из записи: кнопка «> Next» (именно button) — пробуем её первой
            for sel in ["button:has-text('Next')", "a:has-text('Next')",
                        "a[aria-label*='Next' i]", "[aria-label*='next' i]",
                        "a[rel='next']", "li.next a", ".next-page", "button.next",
                        ".pagination a:has-text('>')", "a:has-text('>')"]:
                nxt = self.page.locator(sel).first
                if not nxt.count():
                    continue
                # прокручиваем РОВНО к кнопке (раньше мотали в самый низ и
                # проскакивали пагинацию — из-за этого «Next» не находился)
                try:
                    nxt.scroll_into_view_if_needed(timeout=3000)
                    self.page.wait_for_timeout(300)
                except Exception:
                    continue
                if nxt.is_visible() and nxt.is_enabled():
                    nxt.click(force=True)
                    # ждём СМЕНЫ выдачи опросом до ~20 с (фиксированной паузы мало:
                    # DnB грузится долго, и мы зря решали, что страницы кончились)
                    for _ in range(40):
                        self.page.wait_for_timeout(500)
                        сейчас = self._первая_фирма()
                        if сейчас and сейчас != было:
                            self._kill_popups()
                            return True
                    # Кликнули — и не дождались. НЕ пробуем остальные селекторы:
                    # они попадут в другие «next» на странице, и мы отлистаем
                    # лишнего, потратив ещё по 20 секунд на каждый.
                    self.log("  · нажал «Next», но выдача не сменилась за 20 с")
                    return False
        except Exception:
            pass
        return False

    def _первая_фирма(self) -> str:
        """
        Имя первой фирмы В ТАБЛИЦЕ — маркер того, что выдача сменилась.

        ИМЕННО В ТАБЛИЦЕ. Раньше брали .first по ВСЕЙ странице, а над выдачей
        у DnB висит рекламный блок («Intercontinental Exchange, Inc.MSCI…»),
        который не меняется никогда. Ссылок на фирмы на странице 34, а в
        таблице 24 — .first цеплялся за рекламу. Итог: страница перелистывалась
        за СЕКУНДУ, а next_page() двадцать секунд ждал смены неизменного
        маркера и говорил «не смог перелистнуть». Человек жал «попробуй ещё
        раз», всё повторялось, и только «я перелистнул сам» сдвигало прогон.
        """
        try:
            строки = self.page.locator(self.СТРОКА_ВЫДАЧИ)
            if not строки.count():           # запас на прежнюю вёрстку
                строки = self.page.locator("table tbody tr, .search-results tr")
            for i in range(min(строки.count(), 10)):
                ссылка = строки.nth(i).locator(
                    "a[href*='/business-directory/company-profiles']").first
                if ссылка.count():
                    имя = ссылка.inner_text().strip()
                    if имя:
                        return имя
        except Exception:
            pass
        return ""

    # ---------- КАРТОЧКА (только ради сайта + точного адреса) ----------

    def enrich_website(self, f: Firm, geo: str) -> Firm:
        """
        Открыть карточку, взять имя (h1), ВЕСЬ блок Address и Website. ВСЕГДА
        возвращает Firm (решает движок):
          • ЕСТЬ САЙТ → колонка B (имя+Address+Website целиком) + разбор на колонки;
          • НЕТ САЙТА → website="" , полный адрес кладём в f.address (движок запишет
            такую фирму в отдельный лист «Без сайта» — организация + адрес).
        """
        page = self.br.ctx.new_page()
        try:
            page.goto(f.url, wait_until="domcontentloaded", timeout=25000)
            # ЖДЁМ ДАННЫЕ, А НЕ ТАЙМЕР. Здесь стояла глухая пауза 1500 мс, и
            # блок карточки часто не успевал дорисоваться: поле «Website»
            # приходит на мгновение позже адреса. Фирма с сайтом уезжала в
            # «нет сайта» — то есть выбрасывалась.
            #
            # Замер на США: при 1500 мс сайт находился у 4 карточек из 6,
            # при ожидании поля — у 6 из 6. И это ещё и БЫСТРЕЕ: ожидание
            # занимало 0,0–1,1 секунды вместо глухих полутора.
            #
            # Ждём в два приёма: сперва адрес (он есть всегда), потом даём
            # секунды на Website. У фирмы без сайта второе ожидание истечёт —
            # это её честная цена, а не потеря живой фирмы.
            сел = self.БЛОК_КАРТОЧКИ.replace("'", "\\'")
            ЕСТЬ_АДРЕС = ("() => {const e=document.querySelector('" + сел + "');"
                          "return e && /Address:\\s*\\S/i.test(e.innerText);}")
            ЕСТЬ_САЙТ = ("() => {const e=document.querySelector('" + сел + "');"
                         "return e && /Website:\\s*\\S/i.test(e.innerText);}")
            # 8 секунд на адрес — потолок, а не норма: обычно он приходит за
            # доли секунды. Если не пришёл вовсе, адрес возьмём из таблицы
            # выдачи, поэтому ждать дольше смысла нет.
            for условие, предел in ((ЕСТЬ_АДРЕС, 8000), (ЕСТЬ_САЙТ, 2500)):
                try:
                    page.wait_for_function(условие, timeout=предел)
                except Exception:
                    pass

            # --- ИМЯ ---
            # Имя фирмы берём ИЗ ТАБЛИЦЫ выдачи (f.name) — оно уже верное
            # (BARRIQUAND HEAT EXCHANGERS, VIKING CRUISES SA…). Карточку как источник
            # имени НЕ используем: её шапка #company_new_header — это хлебные крошки
            # (HOME / BUSINESS DIRECTORY / …) + баннер «D&B Business Directory»,
            # оттуда лезло «HOME» и «D&B Business Directory». Никакого перебора дивов.
            имя = f.name

            # --- АДРЕС и САЙТ: блок #company_profile_snapshot (из записи codegen).
            # Там строки вида «Address: Kút utca 14. Cegléd…» и «Website: www.aquarius.hu».
            снимок = ""
            try:
                бл = page.locator(self.БЛОК_КАРТОЧКИ).first
                if бл.count():
                    снимок = бл.inner_text()
            except Exception:
                снимок = ""

            website = ""
            mw = re.search(r"Website:\s*(\S+)", снимок, re.I)
            if mw:
                w = mw.group(1).strip().rstrip(".,;)")
                website = w if w.startswith("http") else "http://" + w
            if not это_сайт_фирмы(website):          # запас: ссылка на странице
                подпись = page.locator("text=/Website:?/i").first
                if подпись.count():
                    a = подпись.locator("xpath=following::a[1]").first
                    if a.count():
                        website = a.get_attribute("href") or ""
            есть_сайт = это_сайт_фирмы(website)

            сырой_адрес = ""
            ma = re.search(
                r"Address:\s*(.+?)(?:\n\s*(?:Website|Phone|Employees|Industry|"
                r"Doing Business|Key Principal|See Other Location)|\n\s*\n|$)",
                снимок, re.I | re.S)
            if ma:
                сырой_адрес = re.sub(r"\s+", " ", ma.group(1)).strip(" ,")
            if not сырой_адрес:                      # запас: адрес из таблицы выдачи
                сырой_адрес = f.address

            f.name = имя
            if есть_сайт:
                f.website = website
                сайт_кратко = re.sub(r"^https?://", "", website).rstrip("/")
                # колонка B — ПОЛНОСТЬЮ, без обрезки; из неё режем остальные колонки
                f.payment_profile = (
                    f"{имя}\nAddress: {сырой_адрес}\nWebsite: {сайт_кратко}")
                if сырой_адрес:
                    r = разобрать(сырой_адрес, geo)
                    f.address = r.улица or сырой_адрес
                    f.city = r.город or f.city
                    f.zip_code = r.индекс or f.zip_code
                    f.state = штат(сырой_адрес, geo, r.город, r.индекс)
            else:
                f.website = ""
                f.address = сырой_адрес              # полный адрес — для листа «Без сайта»
                # ПЛАТЁЖКА СОБИРАЕТСЯ И ЗДЕСЬ. Раньше она жила только в ветке
                # «есть сайт», и вся линия «без сайта» приезжала в таблицу с
                # пустыми колонками D «Платёжный профиль» и P «Исходное с dnb».
                # Замер 22.09.2026: пусто у ВСЕХ 8520 таких строк. То есть у
                # основной нынешней добычи не было платёжки вовсе — до тех пор,
                # пока Часть 2 не скачает выписку и не запишет свою в колонку C.
                #
                # СТРОКИ «Website» ТУТ НЕТ, и это осознанно: у фирмы нет сайта,
                # писать пустое поле в платёжку незачем (прямая просьба).
                if имя:
                    f.payment_profile = (f"{имя}\nAddress: {сырой_адрес}"
                                         if сырой_адрес else имя)
                # ГОРОД И ИНДЕКС РАЗБИРАЕМ И ЗДЕСЬ.
                #
                # Раньше разбор стоял ТОЛЬКО в ветке «есть сайт», и вся линия
                # «без сайта» — а это сегодня основная добыча — приезжала в
                # таблицу с пустой колонкой «Индекс»: индекс так и оставался
                # внутри строки «4 B CHE DE LA FONDERIE 26200, MONTELIMAR…».
                #
                # Дальше по конвейеру за это платит Часть 2. Французский
                # драйвер сужает поиск в реестре по индексу, а без него ищет
                # по всей стране. Замер 10.09.2026, фирма «AQUA»: без индекса
                # 3773 результата и девять чужих однофамильцев человеку на
                # выбор; с индексом 26200 — четыре, и наша первая.
                #
                # АДРЕС НЕ ТРОГАЕМ: для платёжки «без сайта» нужен полный.
                # И ЗАПОЛНЯЕМ ТОЛЬКО ПУСТОЕ, а не «что разобралось». Город уже
                # пришёл из таблицы выдачи и обычно верен, а разбор без улицы
                # ошибается: «PARIS 6, ILE DE FRANCE, France» он читает как
                # улицу «PARIS 6» и город «ILE DE FRANCE» — то есть подменил бы
                # настоящий город регионом.
                if сырой_адрес:
                    r = разобрать(сырой_адрес, geo)
                    f.city = f.city or r.город
                    f.zip_code = f.zip_code or r.индекс
                    f.state = f.state or штат(сырой_адрес, geo, r.город, r.индекс)
            return f
        except Exception:
            return f
        finally:
            page.close()



def _город_индекс(текст: str) -> tuple[str, str]:
    """Из «ROANNE, AUVERGNE RHONE ALPES, France» или адреса — город и индекс."""
    индекс = ""
    m = re.search(r"\b([A-Z]{0,2}[-\s]?\d{4,6}(?:-\d{4})?)\b", текст)
    if m:
        индекс = m.group(1).strip()
    части = [p.strip() for p in текст.split(",") if p.strip()]
    город = части[0] if части else ""
    return город, индекс
