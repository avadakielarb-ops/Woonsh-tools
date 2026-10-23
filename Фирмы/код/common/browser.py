"""
Общая обёртка над Playwright — используется и Частью 1, и Частью 2.

Браузер ВСЕГДА видимый: человек должен видеть страницу, чтобы решить капчу,
залогиниться или поправить шаг. Профиль постоянный — куки и сессии живут между
запусками, поэтому человека дёргаем реже.

Работаем на НАСТОЯЩЕМ Google Chrome (channel="chrome"), а не на скачанном
Chromium: сайты реестров и dnb.com меньше придираются к нему, и окно выглядит
привычно. Профиль при этом ОТДЕЛЬНЫЙ, в папке проекта — свой обычный Chrome
можно держать открытым параллельно, он не блокируется.

Четыре способа получить PDF (Часть 2):
  A) прямая ссылка / API  -> download_url()
  B) кнопка Download      -> click_download()
  C) печать страницы      -> print_to_pdf()   (замена Ctrl+P -> «Сохранить как PDF»)
  D) шаблон .docx         -> part2/core/template_fill.py (браузер не нужен)
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from .human import HumanGate

# ДЫРА №1 (найдена на прогоне): у пользователя scraper.py использовал stealth —
# значит DnB уже пытался блокировать. Возвращаем. Нет пакета — работаем без него.
try:
    from playwright_stealth import Stealth
    _STEALTH = Stealth()
except Exception:
    _STEALTH = None


ПУТИ_CHROME = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def найти_chrome() -> str:
    """Путь к установленному Google Chrome. Не нашёлся — пустая строка."""
    import os
    for п in ПУТИ_CHROME:
        if Path(п).exists():
            return п
    свой = Path(os.environ.get("LOCALAPPDATA", "")) / \
        r"Google\Chrome\Application\chrome.exe"
    return str(свой) if свой.exists() else ""


# ОДИН ПРОФИЛЬ НА ВСЁ. Раньше у каждого гео была своя папка, и логин, сделанный
# для Болгарии, в Австралии не появлялся — приходилось входить заново под каждую
# страну. Сайты разные по доменам, куки друг другу не мешают, а вход нужен один.
# Имя гео остаётся в параметре Browser(profile=...) — оно идёт в лог, чтобы было
# видно, ЧТО за прогон, но папка теперь общая.
ОБЩИЙ = "общий"
КОРЕНЬ_ПРОФИЛЕЙ = Path("./.профиль_браузера")


def файл_кук(профиль: Path) -> Path | None:
    """Где Chrome держит куки этого профиля (путь менялся между версиями)."""
    for к in (профиль / "Default" / "Network" / "Cookies",
              профиль / "Default" / "Cookies"):
        if к.exists():
            return к
    return None


def сколько_кук(профиль: Path) -> int:
    """
    Сколько кук в профиле. Читаем КОПИЮ файла: живой Chrome держит его
    заблокированным. Не прочиталось — считаем, что кук нет.
    """
    import shutil
    import sqlite3
    import tempfile
    куки = файл_кук(профиль)
    if not куки:
        return 0
    врем = Path(tempfile.gettempdir()) / f"_куки_{профиль.name}.db"
    try:
        shutil.copy2(куки, врем)
        con = sqlite3.connect(str(врем))
        n = con.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
        con.close()
        return int(n)
    except Exception:
        return 0
    finally:
        try:
            врем.unlink(missing_ok=True)
        except Exception:
            pass


def что_в_профиле(профиль: Path) -> str:
    """
    Короткая сводка «что в профиле есть»: сколько кук и виден ли вход в Google.

    Нужна В ЛОГЕ. Строка «браузер: общий профиль» читалась как «мой чешский
    профиль НЕ используется» — и это было главным подозрением, когда Венгрия и
    Словения ловили капчу. На деле вход из Чехии лежит именно здесь. Пусть лог
    это доказывает, а не заставляет верить на слово.
    """
    import shutil
    import sqlite3
    import tempfile
    куки = файл_кук(профиль)
    if not куки:
        return "кук нет — вход не делали"
    врем = Path(tempfile.gettempdir()) / f"_свод_{профиль.name}.db"
    try:
        shutil.copy2(куки, врем)
        con = sqlite3.connect(str(врем))
        всего = con.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
        хосты = {h for (h,) in con.execute("SELECT DISTINCT host_key FROM cookies")}
        con.close()
    except Exception:
        return "куки прочитать не смог"
    finally:
        try:
            врем.unlink(missing_ok=True)
        except Exception:
            pass
    гугл = any("accounts.google.com" in h or h.endswith(".google.com") for h in хосты)
    return (f"{всего} кук, сайтов {len(хосты)}, "
            f"вход в Google {'есть ✔' if гугл else 'НЕ вижу ✘'}")


def _перенести_логины(куда: Path, log=None) -> None:
    """
    Первый запуск с общим профилем: перенести САМЫЙ БОГАТЫЙ из старых по-гео.

    Иначе человек, залогинившийся под одну страну, потерял бы вход и делал его
    заново. Выбираем по числу КУК, а не по дате: сначала брали «самый свежий»
    и промахнулись — свежим оказался профиль, где браузер просто открывался,
    а логины лежали в другом. Куки — прямой признак «здесь входили».

    Старые профили НЕ трогаем: лежат на месте, если понадобится откатиться.
    """
    import shutil
    старые = [p for p in КОРЕНЬ_ПРОФИЛЕЙ.glob("*")
              if p.is_dir() and p.name != ОБЩИЙ and not p.name.startswith("_")]
    с_куками = [(сколько_кук(п), п) for п in старые]
    с_куками = [(n, п) for n, п in с_куками if n > 0]
    if not с_куками:
        return
    с_куками.sort(key=lambda x: x[0], reverse=True)
    сколько, источник = с_куками[0]
    try:
        shutil.copytree(источник, куда, dirs_exist_ok=True)
        if log:
            log(f"  · общий профиль создан из «{источник.name}» ({сколько} кук) — "
                "логины оттуда сохранены. Старые профили остались на месте.")
    except Exception as e:
        if log:
            log(f"  · не смог перенести логины из «{источник.name}»: {e}")


def профиль_гео(profile: str = ОБЩИЙ, log=None) -> Path:
    """
    Папка постоянного профиля браузера. ОДНА на все гео и на Часть 1 —
    вход делается один раз и работает везде.
    """
    p = КОРЕНЬ_ПРОФИЛЕЙ / ОБЩИЙ
    новый = not p.exists()
    p.mkdir(parents=True, exist_ok=True)
    if новый:
        _перенести_логины(p, log)
    return p


def держат_профиль(папка: Path) -> list[int]:
    """
    PID процессов Chrome, которые сейчас держат НАШУ папку профиля.

    Один профиль Chrome можно занимать только одним запуском. После записи
    действий (и после аварийного закрытия прогона) в системе остаются
    ОСИРОТЕВШИЕ chrome.exe — без окна, невидимые в панели задач, но папку они
    держат. Следующий запуск в них и упирается: браузер не поднимается, а со
    стороны это выглядит как «приложение тупит». Замер после одной записи:
    одиннадцать таких процессов.
    """
    import subprocess
    иголка = str(папка.resolve())
    команда = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{иголка}*' }} | "
        "Select-Object -ExpandProperty ProcessId")
    try:
        р = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", команда],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    return [int(s) for s in (р.stdout or "").split() if s.strip().isdigit()]


def освободить_профиль(папка: Path, log=None) -> int:
    """Закрыть процессы, держащие профиль. Возвращает, сколько закрыли."""
    import subprocess
    pids = держат_профиль(папка)
    if not pids:
        return 0
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    if log:
        log(f"  · профиль был занят — закрыл {len(pids)} процессов Chrome")
    return len(pids)


# Отладочный порт: через него Playwright ПОДКЛЮЧАЕТСЯ к уже запущенному Chrome,
# вместо того чтобы запускать его самому (см. блок в классе Browser).
# Один и тот же номер и здесь, и в прогоне — иначе окно, открытое руками,
# прогон не найдёт и убьёт его как «занявшее профиль».
ПОРТ_ОТЛАДКИ = 9222


# РАБОТАТЬ И В СВЁРНУТОМ ОКНЕ. Свёрнутые, закрытые другими окнами и фоновые
# вкладки Chrome притормаживает: таймеры раз в минуту, отрисовка стоит, и
# одностраничные сайты реестров (Virre, Zefix) «не догружаются». Человек хочет
# свернуть окно и заниматься своим — эти флаги торможение выключают.
# Размер окна фиксируем: в узком окне Virre перестраивает вёрстку и прячет
# колонки (живой прогон 20.10.2026 — Финляндия 0 из 10 именно из-за этого).
ФЛАГИ_ФОНА = ["--disable-background-timer-throttling",
              "--disable-backgrounding-occluded-windows",
              "--disable-renderer-backgrounding",
              "--window-size=1440,960"]


def открыть_для_входа(profile: str, url: str = "") -> tuple[bool, str]:
    """
    Открыть ОБЫЧНЫЙ Chrome на профиле проекта — чтобы человек поработал руками:
    залогинился или прошёл проверку Cloudflare.

    Зачем отдельно от Playwright: Google (и не он один) ОТКАЗЫВАЕТ во входе,
    когда видит признаки автоматизации — «этот браузер или приложение
    небезопасны». Обойти это флагами нельзя и не нужно: логинимся в чистом
    Chrome, а прогон потом работает в ТОМ ЖЕ окне.

    Окно поднимаем С ОТЛАДОЧНЫМ ПОРТОМ. Без него получалось глупо: человек
    открывал окно, проходил Cloudflare, жал «Найти фирмы» — а прогон видел
    занятый профиль и УБИВАЛ это окно вместе с пройденной проверкой. С портом
    прогон вместо убийства подключается и продолжает прямо в нём.

    ПОЧЕМУ НЕ ТВОЙ РАБОЧИЙ CHROME. Замер 06.09.2026: Chrome 152, запущенный
    с --remote-debugging-port на обычной папке профиля (LOCALAPPDATA\\Google\\
    Chrome\\User Data), молча закрывается с кодом 0 — «эта или похожая проблема
    с профилем». Начиная с Chrome 136 отладка на профиле по умолчанию запрещена
    (защита от кражи кук). Поэтому рабочее окно — на профиле проекта; логины и
    куки в нём свои, накопленные, и Cloudflare этого профиля не различает.

    Возвращает (получилось, пояснение).
    """
    import subprocess
    exe = найти_chrome()
    if not exe:
        return False, "Google Chrome не найден — поставь его или залогинься иначе."
    папка = профиль_гео(profile)     # профиль ОБЩИЙ: вход один раз на все гео
    if держат_профиль(папка):
        # Профиль уже занят: второй Chrome на той же папке не поднимется, а
        # просто откроет вкладку в старом окне — и БЕЗ порта. Пусть человек
        # работает в том окне, что уже открыто.
        return True, str(папка)
    аргументы = [exe, f"--remote-debugging-port={ПОРТ_ОТЛАДКИ}",
                 f"--user-data-dir={папка.resolve()}",
                 "--no-first-run", "--no-default-browser-check",
                 "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
                 *ФЛАГИ_ФОНА]
    if url:
        аргументы.append(url)
    try:
        subprocess.Popen(аргументы)
    except Exception as e:
        return False, f"не смог запустить Chrome: {e}"
    return True, str(папка)


class Browser:
    def __init__(self, profile: str, human: HumanGate,
                 headless: bool = False, timeout_ms: int = 30_000, slow_mo_ms: int = 0,
                 log=print):
        self.profile = profile
        self.human = human
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.slow_mo_ms = slow_mo_ms
        self.log = log
        self._pw = None
        self.ctx = None
        self.page: Page | None = None
        self._браузер = None        # объект Playwright при подключении по CDP
        self._свой_chrome = None    # процесс Chrome, если запускали его мы

    # ─── ПОДКЛЮЧЕНИЕ К ОБЫЧНОМУ CHROME ──────────────────────────────────────
    #
    # Cloudflare на dnb.com перестал пускать нас вовсе — не помогала даже
    # галочка «Подтвердите, что вы человек», нажатая руками. Замер 06.09.2026
    # показал, почему:
    #
    #   Playwright сам запускает Chrome   navigator.webdriver = True   не пускает
    #   то же, но без --no-sandbox        navigator.webdriver = True   не пускает
    #   обычный Chrome + подключение CDP  navigator.webdriver = False  ПУСКАЕТ
    #
    # Playwright выставляет webdriver=True, когда САМ запускает браузер, и снять
    # это флагами нельзя. Поэтому Chrome запускаем как обычную программу —
    # без единого флага автоматизации — и лишь ПОДКЛЮЧАЕМСЯ к нему по отладочному
    # порту. Для сайта это обычный человек за обычным браузером.
    #
    # Скачивание при таком подключении проверено отдельно (06.09.2026), потому что
    # на нём держится вся Часть 2: клик по ссылке с attachment, переход через
    # location=, наш взять_документ() и PDF, открытый во вкладке — все пять путей
    # отдают файл. ВАЖНО: не трогать Browser.setDownloadBehavior. Замер показал,
    # что эта «настройка» как раз ЛОМАЕТ загрузки (файл не приходит никуда),
    # а без неё Chrome отдаёт их Playwright сам.
    ПОРТ_ОТЛАДКИ = globals()["ПОРТ_ОТЛАДКИ"]      # общий с открыть_для_входа

    def _порт_жив(self, порт: int | None = None) -> str:
        """Отвечает ли уже запущенный Chrome на отладочном порту."""
        import json as _json
        import urllib.request
        try:
            с = urllib.request.urlopen(
                f"http://127.0.0.1:{порт or self.ПОРТ_ОТЛАДКИ}/json/version",
                timeout=3).read()
            return _json.loads(с).get("Browser", "Chrome")
        except Exception:
            return ""

    def _подключиться(self, profile_dir: Path):
        """
        Подключиться к обычному Chrome; если он не запущен — запустить его.

        Запускаем через subprocess, а НЕ через Playwright: как только браузер
        стартует Playwright, в нём появляется navigator.webdriver=True и
        Cloudflare закрывает дверь.
        """
        import subprocess
        живой = self._порт_жив()
        if живой:
            self.log(f"  · работаю в уже открытом окне Chrome ({живой}) — "
                     "проверку Cloudflare в нём проходить заново не надо")
        else:
            exe = найти_chrome()
            if not exe:
                return None
            # Профиль занят чужим окном БЕЗ отладочного порта (человек открыл
            # Chrome мимо кнопки). Подключиться к такому нельзя, а поднять свой
            # на том же профиле — тоже: Chrome просто откроет вкладку в старом
            # окне и порт не появится. Спрашиваем, а не убиваем молча: там может
            # быть только что пройденная проверка или наполовину сделанный вход.
            if держат_профиль(profile_dir):
                self.log("  ⚠ Chrome уже открыт на профиле проекта, но без "
                         "отладочного порта — подключиться к нему нельзя")
                self.human.require(
                    "Закрой окно Chrome",
                    "Chrome с профилем проекта открыт, но запущен не отсюда —\n"
                    "работать в нём я не могу.\n\n"
                    "Закрой это окно и нажми «Продолжить»: я открою новое.\n"
                    "Чтобы проходить Cloudflare самому, открывай окно кнопкой\n"
                    "«Открыть Chrome для dnb» на вкладке «Настройки» —\n"
                    "такое окно прогон подхватывает как своё.")
            освободить_профиль(profile_dir, self.log)
            try:
                self._свой_chrome = subprocess.Popen(
                    [exe, f"--remote-debugging-port={self.ПОРТ_ОТЛАДКИ}",
                     f"--user-data-dir={profile_dir.resolve()}",
                     "--no-first-run", "--no-default-browser-check",
                     "--disable-session-crashed-bubble",
                     "--hide-crash-restore-bubble",
                     *ФЛАГИ_ФОНА,
                     "about:blank"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                self.log(f"  · не смог запустить Chrome: {e}")
                return None
            for _ in range(40):                     # до 20 секунд на старт
                живой = self._порт_жив()
                if живой:
                    break
                time.sleep(0.5)
            if not живой:
                self.log("  · Chrome не поднял отладочный порт")
                return None
            self.log(f"  · запустил обычный Chrome ({живой}), подключаюсь")
        try:
            self._браузер = self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.ПОРТ_ОТЛАДКИ}")
        except Exception as e:
            self.log(f"  · подключиться не вышло: {type(e).__name__}: {e}")
            return None
        ctx = (self._браузер.contexts[0] if self._браузер.contexts
               else self._браузер.new_context())
        return ctx

    def _запустить(self, profile_dir: Path, channel: str | None):
        """Запасной путь: Playwright сам поднимает браузер (Cloudflare такое
        видит, поэтому используем только если подключиться не удалось)."""
        return self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=channel,                      # "chrome" = настоящий Google Chrome
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
            accept_downloads=True,
            chromium_sandbox=True,                # иначе Playwright сам ставит
            viewport={"width": 1440, "height": 900},   # --no-sandbox: и жёлтый
            # профиль постоянный → после принудительных закрытий Chrome показывал
            # «Восстановить страницы?» и мог открыть главную. Глушим это.
            args=["--disable-session-crashed-bubble",
                  "--hide-crash-restore-bubble",
                  "--disable-infobars", "--no-first-run",
                  "--no-default-browser-check",
                  "--restore-last-session=false", *ФЛАГИ_ФОНА],
            ignore_default_args=["--enable-automation"],
        )

    def _одна_вкладка(self) -> Page:
        """
        Оставить РОВНО ОДНУ вкладку и вывести её вперёд.

        Профиль постоянный, поэтому со второго запуска Chrome нередко поднимает
        старую вкладку (там висит dnb) и рядом открывает пустую about:blank.
        Работали при этом на второй, фоновой — а фоновые вкладки Chrome
        притормаживает: таймеры замедляются, загрузка не идёт. Со стороны это и
        выглядит как «скрипт тупит на пустой вкладке, хотя рядом всё загружено».

        Держим одну вкладку: лишние закрываем, оставшуюся делаем активной.
        Какая именно останется — неважно, поиск всё равно начинается с goto().
        """
        страницы = list(self.ctx.pages)
        # Если подключились к окну, которое человек открыл сам (прошёл в нём
        # Cloudflare), оставляем ЕГО вкладку с сайтом, а не пустышку рядом:
        # пустая about:blank раньше выигрывала просто потому, что была первой.
        живые = [с for с in страницы if self._настоящая(с.url)]
        page = (живые[-1] if живые else
                страницы[0] if страницы else self.ctx.new_page())
        for лишняя in [с for с in страницы if с is not page]:
            try:
                лишняя.close()
            except Exception:
                pass
        try:
            page.bring_to_front()
        except Exception:
            pass
        return page

    # ---------- ходим за человеком ----------

    @staticmethod
    def _настоящая(url: str) -> bool:
        """Вкладка с реальной страницей, а не пустышка/служебная."""
        u = (url or "").strip().lower()
        return bool(u) and not u.startswith(("about:", "chrome:", "edge:", "devtools:"))

    def перезагрузить(self, log=None) -> bool:
        """
        Перечитать текущую страницу заново.

        Нужно для кнопки «Повтор последнего действия»: сайты реестров
        подвисают на ровном месте — страница вроде открыта, а данных на ней
        нет. Разбираться, почему именно, дороже, чем перезайти.

        Возвращаем, получилось ли: не получилось — значит вкладки уже нет,
        и повторять нечего.
        """
        try:
            self.page.reload(wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(800)
            if log:
                log("  · страница перечитана заново")
            return True
        except Exception as e:
            if log:
                log(f"  ⚠ перечитать страницу не вышло ({type(e).__name__})")
            return False

    def вкладка_человека(self, log=None) -> Page:
        """
        ПЕРЕЙТИ НА ТУ ВКЛАДКУ, ГДЕ СЕЙЧАС ЧЕЛОВЕК, и дальше работать с ней.

        Самая дорогая поломка прогона 25.08. Человек в окне «неоднозначное
        совпадение» открывал нужную карточку — часто по ссылке, которая
        открывает НОВУЮ ВКЛАДКУ, — и жал «Продолжить». А `self.page` всё это
        время указывал на СТАРУЮ вкладку со списком выдачи. Драйвер читал не ту
        страницу, номер фирмы не находил, ядро решало «человек не открыл
        карточку» и молча брало следующую фирму. Со стороны: «жму Продолжить —
        он перескакивает». Так пропали Эстония, Франция, Латвия, Норвегия,
        Польша — при том что человек всё сделал правильно.

        Как ищем. Сначала спрашиваем сами страницы, у какой ФОКУС
        (`document.hasFocus()`) — это ровно та вкладка, которую человек видит.
        Не ответил никто (окно свёрнуто, страница занята) — берём последнюю
        открытую с настоящим адресом: новые вкладки добавляются в конец.
        """
        живые = [p for p in list(self.ctx.pages) if not p.is_closed()]
        if not живые:
            self.page = self.ctx.new_page()
            return self.page

        выбор = None
        for p in живые:
            try:
                if p.evaluate("() => !!(document.hasFocus && document.hasFocus())"):
                    выбор = p
                    break
            except Exception:
                continue
        if выбор is None:
            настоящие = [p for p in живые if self._настоящая(p.url)]
            выбор = настоящие[-1] if настоящие else живые[-1]

        сменилась = выбор is not self.page
        self.page = выбор
        try:
            выбор.bring_to_front()
            выбор.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        if log and сменилась:
            log(f"  · перешёл на вкладку человека: {self.коротко(выбор.url)}")
        return выбор

    @staticmethod
    def коротко(url: str, предел: int = 70) -> str:
        u = (url or "").strip()
        return u if len(u) <= предел else u[:предел - 1] + "…"

    def ожить(self, log=None) -> bool:
        """
        ВЕРНУТЬ ЖИВУЮ ВКЛАДКУ, если рабочая умерла.

        Прогоны 15–19.10: вкладка закрылась (человек, сам сайт, сбой Chrome) —
        и каждая следующая фирма падала с TargetClosedError, 59 ошибок подряд
        до конца страны. `прибраться` держался за мёртвую self.page и
        честно её «выводил вперёд».

        Вкладка мертва, контекст жив — берём/открываем другую вкладку.
        Мёртв и контекст (закрыли окно Chrome) — поднимаем браузер заново.
        Возвращаем, пришлось ли оживлять.
        """
        log = log or self.log
        try:
            if self.page is not None and not self.page.is_closed():
                self.page.evaluate("() => 1")
                return False
        except Exception:
            pass
        try:
            живые = [p for p in list(self.ctx.pages) if not p.is_closed()]
            self.page = живые[-1] if живые else self.ctx.new_page()
            self.page.evaluate("() => 1")
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            log("  ⚠ рабочая вкладка умерла — взял живую")
            return True
        except Exception:
            pass
        log("  ⚠ браузер умер — поднимаю заново")
        try:
            if self._браузер is not None:
                self._браузер.close()
        except Exception:
            pass
        self.ctx = self._браузер = None
        self._поднять()
        return True

    def прибраться(self) -> None:
        """
        Закрыть все вкладки, кроме рабочей. Зовём в БЕЗОПАСНОЙ точке — между
        фирмами: за прогон человек и сайты наоткрывают вкладок, а фоновые
        Chrome притормаживает (см. `_одна_вкладка`).

        Сначала — оживить: держаться за мёртвую вкладку значит уронить все
        фирмы до конца страны (см. `ожить`).
        """
        try:
            self.ожить()
        except Exception as e:
            self.log(f"  ⚠ оживить браузер не вышло ({type(e).__name__})")
        try:
            for p in list(self.ctx.pages):
                if p is not self.page and not p.is_closed():
                    p.close()
        except Exception:
            pass
        try:
            if self.page and not self.page.is_closed():
                self.page.bring_to_front()
        except Exception:
            pass

    # ---------- диагностика: что на экране в момент беды ----------

    def снимок(self, повод: str = "") -> str:
        """
        PNG страницы в «логи/скриншоты». Возвращает путь или пустую строку.

        Делается ПЕРЕД каждым обращением к человеку. Окно человека без картинки
        бесполезно: разбор вчерашней поломки с Cloudflare занял час именно
        потому, что не было видно, что на самом деле было на экране.
        """
        try:
            папка = Path("логи") / "скриншоты"
            папка.mkdir(parents=True, exist_ok=True)
            чистый = "".join(c if c.isalnum() or c in " -_" else "_"
                             for c in (повод or "снимок"))[:60].strip() or "снимок"
            путь = папка / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{чистый}.png"
            self.page.screenshot(path=str(путь))
            return str(путь)
        except Exception:
            return ""

    def диагноз(self, ждём_строки: str = ""):
        """Что со страницей — см. common/диагноз.py. Никогда не бросает."""
        try:
            from .диагноз import определить
            return определить(self.page, ждём_строки)
        except Exception:
            return None

    def __enter__(self) -> "Browser":
        self._pw = sync_playwright().start()
        self._поднять()
        return self

    def _поднять(self) -> None:
        """Подключиться к Chrome или запустить его; общая часть входа и `ожить`."""
        # Папка ОДНА на все гео и на Часть 1 — вход делается один раз и работает
        # везде. self.profile остаётся только пометкой в логе: чей это прогон.
        profile_dir = профиль_гео(self.profile, self.log)
        # СВОДКУ СНИМАЕМ ДО ЗАПУСКА: живой Chrome держит файл кук заблокированным,
        # и после launch любая попытка прочитать его даёт «не смог».
        сводка = что_в_профиле(profile_dir)

        # СНАЧАЛА — обычный Chrome с подключением по CDP: только так Cloudflare
        # на dnb.com нас пускает (см. блок «ПОДКЛЮЧЕНИЕ К ОБЫЧНОМУ CHROME»).
        # Не вышло — идём прежним путём, он рабочий для реестров без защиты.
        try:
            self.ctx = self._подключиться(profile_dir)
        except Exception as e:
            self.log(f"  · подключение не удалось ({type(e).__name__}) — "
                     "запускаю браузер сам")
            self.ctx = None
        if self.ctx is not None:
            self.ctx.set_default_timeout(self.timeout_ms)
            self.log(f"  · браузер: обычный Chrome, профиль {profile_dir}, "
                     f"прогон «{self.profile}» — {сводка}")
            self.page = self._одна_вкладка()
            self.human.снимок = self.снимок
            self.human.диагноз = self.диагноз
            self.human.перезагрузить = self.перезагрузить
            return

        try:
            self.ctx = self._запустить(profile_dir, "chrome")
        except Exception as e:
            # ПЕРВАЯ подозреваемая — не отсутствие Chrome, а ЗАНЯТЫЙ ПРОФИЛЬ:
            # осиротевшие процессы после записи действий или после аварийного
            # закрытия прошлого прогона. Освобождаем и пробуем ещё раз, и лишь
            # потом уходим на Chromium.
            if освободить_профиль(profile_dir, self.log):
                try:
                    self.ctx = self._запустить(profile_dir, "chrome")
                except Exception:
                    self.ctx = None
            if self.ctx is None:
                self.log(f"⚠ Google Chrome не запустился ({e.__class__.__name__}), "
                         "работаю на Chromium. Поставь Chrome — будет надёжнее.")
                self.ctx = self._запустить(profile_dir, None)
        self.ctx.set_default_timeout(self.timeout_ms)
        self.log(f"  · браузер: общий профиль ({profile_dir}), прогон «{self.profile}» "
                 f"— {сводка}")
        self.page = self._одна_вкладка()
        # Отдаём «человеку в контуре» глаза и руки: он сам не знает про
        # браузер, но теперь может снять экран, спросить, что со страницей, и
        # перечитать её заново, не отвечая на вопрос.
        self.human.снимок = self.снимок
        self.human.диагноз = self.диагноз
        self.human.перезагрузить = self.перезагрузить
        if _STEALTH:
            try:
                _STEALTH.apply_stealth_sync(self.page)
            except Exception:
                pass

    def __exit__(self, *exc):
        """
        Закрыться НАДЁЖНО, что бы ни случилось.

        Раньше было `ctx.close()` а следом `_pw.stop()` без защиты. Если браузер
        уже мёртв (человек закрыл окно, упал Chrome), close() бросал
        TargetClosedError — и stop() НЕ ВЫПОЛНЯЛСЯ. Драйвер Playwright оставался
        висеть в потоке, и КАЖДЫЙ следующий запуск в этом же потоке падал с
        «Playwright Sync API inside the asyncio loop». В мультилисте так умерли
        все 16 стран подряд после одной закрытой вкладки.
        """
        # При ПОДКЛЮЧЕНИИ по CDP контекст чужой: ctx.close() закрыл бы браузер
        # человека вместе с его вкладками. Рвём только соединение, а Chrome
        # гасим лишь тот, который запустили сами.
        try:
            if self._браузер is not None:
                self._браузер.close()          # закрывает соединение, не браузер
            elif self.ctx:
                self.ctx.close()
        except Exception:
            pass
        try:
            if self._свой_chrome is not None:
                self._свой_chrome.terminate()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.ctx = self._pw = self.page = None
        self._браузер = self._свой_chrome = None

    # ---------- навигация ----------

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")
        self.dismiss_popups()

    POPUPS = [
        "#onetrust-accept-btn-handler",
        "#truste-consent-button",          # TrustArc — на нём сидит dnb.com
        "button:has-text('Agree & Proceed')",
        "button:has-text('Accept')", "button:has-text('Accept All')",
        "button:has-text('Принять')", "button:has-text('Godta')",
        "button:has-text('Accepter')", "a:has-text('Accepter')",
        "button:has-text('Akceptuj')",
        "button:has-text('Elfogad')", "button:has-text('Prihvaćam')",
        "button:has-text('Alle akzeptieren')",
        "[aria-label='Close']", "button.close", ".modal button:has-text('No thanks')",
    ]

    def dismiss_popups(self) -> None:
        """
        Cookie-баннер И второй попап (на dnb.com их два — ты про это говорил).
        Проходим по списку и щёлкаем всё, что нашли. Не нашли — не страшно.
        """
        for sel in self.POPUPS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=1500)
                    self.page.wait_for_timeout(300)
            except Exception:
                continue

    # ---------- капча ----------

    # Cloudflare добавлен после разбора: dnb.com встречает страницей «Выполнение проверки
    # безопасности» с галочкой Turnstile. Она НЕ ловилась — маркеров cloudflare не было,
    # а текст локализованный («Подтвердите, что вы человек»), под англоязычный шаблон
    # не подходил. Итог: человека не звали, шаг просто падал по таймауту.
    # Поэтому опознаём по ТЕХНИЧЕСКИМ признакам, они от языка не зависят.
    CAPTCHA_MARKERS = [
        # Cloudflare: dnb.com встречает страницей «Выполнение проверки безопасности»
        # с галочкой Turnstile. Раньше не ловилась вообще (маркеров cloudflare не было,
        # а текст локализованный) — человека не звали, шаг падал по таймауту.
        "iframe[src*='challenges.cloudflare.com']",
        ".cf-turnstile", "#cf-turnstile", "#challenge-running", "#challenge-form",
        # reCAPTCHA — ТОЛЬКО bframe. Это окно с картинками, оно всплывает лишь при
        # реальной проверке. Прежний общий 'recaptcha' ловил ещё и вечный невидимый
        # значок reCAPTCHA Enterprise, который висит на КАЖДОЙ странице dnb.com,
        # — и капча «находилась» там, где её нет.
        "iframe[src*='recaptcha'][src*='bframe']",
        "iframe[src*='hcaptcha'][src*='challenge']",
        ".g-recaptcha", "#captcha",
        "text=/verify you are human/i",
        "text=/подтвердите, что вы человек/i",
    ]

    def check_captcha(self, company: str = "", ждать_мс: int = 0) -> None:
        """
        Нашли капчу — зовём человека, ждём, продолжаем.

        ждать_мс — сколько ЖДАТЬ появления капчи там, где мы её ТОЧНО ожидаем
        (Венгрия капчит каждый запрос). Виджет reCAPTCHA рисуется скриптом и
        появляется не сразу: проверив страницу мгновенно, мы звали человека
        показывать пустоту — «капча не загрузилась». Ноль = проверить как есть.
        """
        конец = time.monotonic() + max(0, ждать_мс) / 1000
        while True:
            for sel in self.CAPTCHA_MARKERS:
                try:
                    if self.page.locator(sel).first.is_visible(timeout=500):
                        self.human.captcha(company)
                        return
                except Exception:
                    continue
            if time.monotonic() >= конец:
                return
            try:
                self.page.wait_for_timeout(500)
            except Exception:
                return

    # ---------- получение PDF ----------

    def click_download(self, selector: str, dest: Path, company: str = "") -> Path:
        """Способ B: клик по кнопке, которая отдаёт файл."""
        try:
            with self.page.expect_download(timeout=self.timeout_ms) as dl:
                self.page.click(selector)
            download = dl.value
        except PWTimeout:
            # Частая причина: блокировщик попапов / файл открылся в новой вкладке (Финляндия)
            self.human.stuck(f"скачивание по кнопке {selector}", company)
            raise
        return self.сохранить(download, dest)

    # Куда обычный Chrome складывает скачанное. Playwright, запуская браузер
    # сам, подменял эту папку на временную и подчищал её. Мы к браузеру
    # ПОДКЛЮЧАЕМСЯ (иначе Cloudflare не пускает на dnb), поэтому папка обычная.
    @staticmethod
    def папка_загрузок() -> Path:
        import os
        return Path(os.path.expanduser("~")) / "Downloads"

    @staticmethod
    def сохранить(download, dest: Path, log=None) -> Path:
        """
        Положить скачанный файл КУДА НАДО, УБЕДИТЬСЯ, что он не пустой, и
        только потом убрать оригинал из «Загрузок» браузера.

        ПОЧЕМУ ТАК СЛОЖНО. Разбор 08.09.2026, прогон Эстонии: в папке прогона
        оказалось 87 файлов ПО НУЛЮ БАЙТ, а их содержимое (по 170 КБ) лежало в
        «Загрузках». То есть save_as() создавал файл, но содержимое не
        доезжало, и прогон честно записывал «✔ скачано». Пустая выписка хуже
        отсутствующей: её видно в таблице как готовую.

        Причина — в подключении по CDP: для Playwright такой браузер
        «удалённый», и передача файла через save_as ненадёжна. На мелких
        файлах проходит, на настоящих выписках — нет.

        Поэтому: сохранили → ПРОВЕРИЛИ → если пусто, забрали файл напрямую из
        папки загрузок браузера → проверили снова. Пустой результат не
        выдаём за успех, а честно бросаем ошибку: пусть гео отчитается
        «не вышло», чем в таблице появится мнимая выписка.
        """
        import shutil
        dest.parent.mkdir(parents=True, exist_ok=True)
        сказать = log or (lambda s: None)

        try:
            download.save_as(str(dest))
        except Exception as e:
            сказать(f"  · save_as не сработал ({type(e).__name__}) — беру файл сам")

        if not dest.exists() or dest.stat().st_size == 0:
            имя = ""
            try:
                имя = download.suggested_filename or ""
            except Exception:
                pass
            исходник = Browser._дождаться_файла(Browser.папка_загрузок(), имя)
            if исходник is not None:
                shutil.copyfile(исходник, dest)
                сказать(f"  · файл забрал из «Загрузок» браузера ({исходник.name})")

        if not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError(
                "скачанный файл пуст — содержимое не доехало из браузера")

        try:
            download.delete()          # оригинал в «Загрузках» браузера
        except Exception:
            pass                       # не убрался — файл у нас уже есть, это не беда
        return dest

    @staticmethod
    def _дождаться_файла(папка: Path, имя: str, ждать_с: float = 20.0) -> Path | None:
        """
        Дождаться, пока браузер ДОПИШЕТ файл, и вернуть его.

        Ждём не появления, а СТАБИЛЬНОГО РАЗМЕРА: файл возникает сразу, но
        растёт ещё секунды, и скопированный в этот момент обрывок так же
        бесполезен, как пустой. Пока рядом лежит .crdownload — качается.
        """
        import time as _t
        цель = папка / имя if имя else None
        конец = _t.monotonic() + ждать_с
        было = -1
        while _t.monotonic() < конец:
            кандидат = цель if (цель and цель.exists()) else None
            if кандидат is None:
                свежие = sorted((p for p in папка.glob("*")
                                 if p.is_file() and p.suffix.lower() != ".crdownload"),
                                key=lambda p: p.stat().st_mtime, reverse=True)
                кандидат = свежие[0] if свежие else None
            if кандидат is not None and not кандидат.with_suffix(
                    кандидат.suffix + ".crdownload").exists():
                размер = кандидат.stat().st_size
                if размер and размер == было:
                    return кандидат
                было = размер
            _t.sleep(0.5)
        return None

    def _pdf_со_страницы(self, page: Page, dest: Path) -> Path | None:
        """
        Вкладка ПОКАЗЫВАЕТ PDF (встроенный просмотрщик Chrome) — забрать байты.

        Просмотрщик не порождает события download: файл уже «скачан» внутрь
        вкладки. Поэтому тянем тот же адрес запросом из КОНТЕКСТА — куки и
        сессия те же, значит сессионные ссылки (Virre: execution=e1sN) работают.
        Проверяем сигнатуру %PDF: HTML-страница по ошибке не станет «выпиской».
        """
        from urllib.parse import urljoin
        try:
            url = page.url
        except Exception:
            return None
        # about:blank НЕ пропускаем мимо: Латвия открывает выписку именно так —
        # пустая вкладка, а документ внутри <embed>. Просто не тянем сам адрес.
        адреса = [url] if self._настоящая(url) else []
        # PDF часто не сам адрес вкладки, а вложен: Chrome рисует его в <embed>,
        # а сайт — в <iframe>/<object>. Латвия открывает попап-обёртку, внутри
        # которой embed с настоящей ссылкой; по адресу самой вкладки приходит
        # HTML, и «выписка не скачалась» при открытом на экране документе.
        for сел, атрибут in (("embed[src]", "src"), ("iframe[src]", "src"),
                             ("object[data]", "data")):
            try:
                эл = page.locator(сел).first
                if not эл.count():
                    continue
                src = эл.get_attribute(атрибут) or ""
            except Exception:
                continue
            if not src or src.startswith("blob:"):
                continue
            # DATA-URI: Латвия отдаёт выписку не ссылкой, а телом прямо в
            # разметке попапа (`data:application/pdf;base64,JVBERi0…`), да ещё
            # на вкладке about:blank. Скачивать нечего и неоткуда — расшифруем.
            if src.startswith("data:"):
                import base64
                голова, _, тело64 = src.partition(",")
                if "pdf" not in голова.lower():
                    continue
                try:
                    тело = (base64.b64decode(тело64) if "base64" in голова
                            else тело64.encode())
                except Exception:
                    continue
                if тело[:4] == b"%PDF":
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(тело)
                    return dest
                continue
            адреса.append(urljoin(url, src))

        for адрес in адреса:
            try:
                resp = self.ctx.request.get(адрес, timeout=self.timeout_ms)
                if not resp.ok:
                    continue
                тело = resp.body()
            except Exception:
                continue
            if тело[:4] == b"%PDF":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(тело)
                return dest
        return None

    def взять_документ(self, действие, dest: Path, company: str = "",
                       ждать_мс: int = 30_000, log=None) -> Path | None:
        """
        Выполнить ДЕЙСТВИЕ (клик по кнопке) и забрать PDF, каким бы из трёх
        способов сайт его ни отдал:

          1) обычным скачиванием (событие download);
          2) НОВОЙ ВКЛАДКОЙ со встроенным просмотрщиком PDF;
          3) переходом текущей вкладки на PDF.

        Зачем. `expect_download` слушает ОДНУ вкладку и только событие
        скачивания. Финляндия («The Trade Register extract will open in a new
        tab») и UK отдают выписку вторым способом: вкладка открылась, PDF в ней
        виден — а мы 30 секунд ждали события на старой вкладке и объявляли
        «PDF не скачался». Человек видел открытый документ и не понимал,
        чего скрипт хочет.

        Возвращает путь или None (тогда зовущий решает: спросить человека).
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        поймано: dict = {}
        новые: list[Page] = []

        def _на_загрузку(d):
            поймано.setdefault("dl", d)

        def _на_страницу(p):
            новые.append(p)
            try:
                p.on("download", _на_загрузку)
            except Exception:
                pass

        self.ctx.on("page", _на_страницу)
        for p in list(self.ctx.pages):
            try:
                p.on("download", _на_загрузку)
            except Exception:
                pass
        try:
            действие()
            конец = time.monotonic() + max(1000, ждать_мс) / 1000
            while time.monotonic() < конец:
                if "dl" in поймано:
                    self.сохранить(поймано["dl"], dest)
                    if log:
                        log("  · выписка пришла скачиванием")
                    return dest
                for p in [*новые, self.page]:
                    if p is None or p.is_closed():
                        continue
                    try:
                        p.wait_for_load_state("domcontentloaded", timeout=1500)
                    except Exception:
                        pass
                    путь = self._pdf_со_страницы(p, dest)
                    if путь:
                        if log:
                            log(f"  · выписка открылась во вкладке — забрал оттуда "
                                f"({self.коротко(p.url, 50)})")
                        return путь
                try:
                    self.page.wait_for_timeout(400)
                except Exception:
                    break
        finally:
            try:
                self.ctx.remove_listener("page", _на_страницу)
            except Exception:
                pass
        return None

    def download_url(self, url: str, dest: Path) -> Path:
        """Способ A: прямая ссылка на PDF."""
        resp = self.ctx.request.get(url)
        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status} при скачивании {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.body())
        return dest

    def print_to_pdf(self, dest: Path) -> Path:
        """
        Способ C: то же, что Ctrl+P -> «Сохранить как PDF», без диалога.

        ДЫРА №6 (самая важная находка прогона): page.pdf() в Playwright работает
        ТОЛЬКО в headless. А нам нужен ВИДИМЫЙ браузер — иначе человек не решит капчу.
        Два столпа концепции конфликтовали. Решение: печатаем через CDP-сессию
        (Page.printToPDF) — она работает и в видимом окне.
        Это гео: Швейцария, Венгрия, Бельгия, Хорватия, Болгария.
        """
        import base64
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.page.emulate_media(media="print")
        cdp = self.ctx.new_cdp_session(self.page)
        result = cdp.send("Page.printToPDF", {
            "printBackground": True,
            "paperWidth": 8.27, "paperHeight": 11.69,        # A4 в дюймах
            "marginTop": 0.4, "marginBottom": 0.4,
            "marginLeft": 0.4, "marginRight": 0.4,
        })
        cdp.detach()
        self.page.emulate_media(media="screen")
        dest.write_bytes(base64.b64decode(result["data"]))
        return dest

    def has_text(self, *needles: str) -> bool:
        """Есть ли на странице хоть один из фрагментов текста (без учёта регистра)."""
        try:
            body = self.page.inner_text("body").lower()
        except Exception:
            return False
        return any(n.lower() in body for n in needles)
