"""check_captcha умеет ЖДАТЬ появления капчи, а не проверять мгновенно."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
from common.browser import Browser
from common.human import HumanGate

ошибок = 0


class ФейкЛокатор:
    def __init__(self, страница, sel):
        self.страница, self.sel = страница, sel
    @property
    def first(self):
        return self
    def is_visible(self, timeout=0):
        # капча «появляется» через 2 секунды после старта
        поздно = time.monotonic() - self.страница.старт > 2.0
        return поздно and self.sel == ".g-recaptcha"


class ФейкСтраница:
    def __init__(self):
        self.старт = time.monotonic()
    def locator(self, sel):
        return ФейкЛокатор(self, sel)
    def wait_for_timeout(self, ms):
        time.sleep(ms / 1000)


class ФейкБраузер(Browser):
    def __init__(self, human):
        self.human = human
        self.page = ФейкСтраница()
        self.log = lambda s: None


звали = []
class Человек(HumanGate):
    def captcha(self, company=""):
        звали.append(company or "—")


print("=== без ожидания: капчи ещё нет, человека НЕ зовём ===")
br = ФейкБраузер(Человек())
br.check_captcha("ФИРМА")
print("   звали:", звали or "нет", "(ждём «нет» — капча ещё не отрисовалась)")
if звали:
    ошибок += 1

print()
print("=== с ожиданием 6 с: дожидаемся и зовём ===")
звали.clear()
br2 = ФейкБраузер(Человек())
старт = time.monotonic()
br2.check_captcha("ФИРМА", ждать_мс=6000)
прошло = time.monotonic() - старт
print(f"   звали: {звали or 'нет'}   ждали {прошло:.1f} с")
if not звали:
    ошибок += 1
    print("   ✘ не дождались капчи")
elif прошло > 5.5:
    ошибок += 1
    print("   ✘ ждали до упора, хотя капча появилась раньше")
else:
    print("   ✔ дождался и позвал, не тратя весь лимит")

print()
print("=== капчи нет вовсе: ждём лимит и молча выходим ===")
звали.clear()
class ПустаяСтраница(ФейкСтраница):
    def locator(self, sel):
        class Нет:
            first = property(lambda s: s)
            def is_visible(self, timeout=0): return False
        н = Нет(); н.first = н
        return н
br3 = ФейкБраузер(Человек())
br3.page = ПустаяСтраница()
старт = time.monotonic()
br3.check_captcha("ФИРМА", ждать_мс=1500)
прошло = time.monotonic() - старт
print(f"   звали: {звали or 'нет'}   ждали {прошло:.1f} с (ждём ~1.5)")
if звали:
    ошибок += 1
    print("   ✘ позвал без капчи")

print()
print("ошибок:", ошибок)
