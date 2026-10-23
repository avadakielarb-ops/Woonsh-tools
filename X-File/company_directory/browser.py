"""Dedicated browser profile; site checks are always handled by the user."""
from pathlib import Path
import re
import winreg


def default_browser():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as entry:
            progid=winreg.QueryValueEx(entry,'ProgId')[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,progid+r'\shell\open\command') as entry:
            command=winreg.QueryValueEx(entry,'')[0]
        match=re.match(r'\s*"([^"]+\.exe)"|\s*(.+?\.exe)(?:\s|$)',command,re.I)
        exe=Path((match.group(1) or match.group(2))) if match else None
        if not exe or not exe.is_file():raise OSError('Browser path unavailable')
        if 'firefox' in exe.name.lower():
            raise RuntimeError('Браузер по умолчанию Firefox: этот драйвер поддерживает Chromium-браузеры. Выберите Chrome или Edge браузером по умолчанию для автоматизации.')
        return exe
    except OSError:
        raise RuntimeError('Не удалось определить браузер по умолчанию для HTTPS. Назначьте Chrome, Edge или другой Chromium-браузер в настройках Windows.') from None


class SkipCompany(RuntimeError):
    pass


class HumanGate:
    def __init__(self, ask):
        self.ask = ask

    def stuck(self, message, keyword=''):
        self.ask(message + ('\nКлючевое слово: ' + keyword if keyword else ''))

    def сайт_не_отвечает(self, title, url, keyword=''):
        self.stuck(title + ': сайт не отвечает. Проверьте в браузере: ' + url, keyword)

    def login(self, title, keyword=''):
        self.stuck('Войдите самостоятельно: ' + title, keyword)

    def исполнить_приказ(self, *args):
        self.stuck('Выполните необходимое действие на странице реестра и продолжите.')
        return True


class Browser:
    def __init__(self, folder, human, stop):
        self.folder, self.human, self.stop = Path(folder), human, stop

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.runtime = sync_playwright().start()
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            self.ctx = self.runtime.chromium.launch_persistent_context(
                str(self.folder), executable_path=str(default_browser()), headless=False,
                viewport={'width': 1280, 'height': 850})
        except Exception as exc:
            self.runtime.stop()
            raise RuntimeError('Не удалось открыть браузер поиска: '+str(exc)) from None
        self.ctx.set_default_timeout(12000)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def goto(self, url):
        if self.stop.is_set():raise RuntimeError('Поиск остановлен.')
        self.page.goto(url,wait_until='domcontentloaded',timeout=45000)

    def dismiss_popups(self):
        pass

    def check_captcha(self, keyword=''):
        if self.stop.is_set():
            raise RuntimeError('Поиск остановлен.')
        text = self.page.locator('body').inner_text(timeout=15000).lower()
        if any(word in text for word in ('verify you are human', 'checking your browser',
                'проверки безопасности', 'just a moment', 'access denied', 'captcha')):
            self.human.stuck('Сайт показывает проверку доступа. Пройдите её самостоятельно в окне браузера, затем нажмите «Продолжить». Если доступ запрещён, отмените поиск.', keyword)

    def __exit__(self, *args):
        try:
            self.ctx.close()
        finally:
            self.runtime.stop()
