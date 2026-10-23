"""
Умершая вкладка не роняет страну до конца.

Прогоны 15–19.10.2026: рабочая вкладка закрылась (человек, сам сайт, сбой
Chrome) — и каждая следующая фирма падала с TargetClosedError: 59 ошибок
подряд. `прибраться` между фирмами держался за мёртвую страницу и честно
«выводил её вперёд». Теперь он сперва оживляет: вкладка мертва — берём
другую, мёртв весь браузер — поднимаем заново.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.browser import Browser

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


class Стр:
    def __init__(self, жива=True):
        self.жива = жива
        self.url = "https://x"

    def is_closed(self):
        return not self.жива

    def evaluate(self, *_):
        if not self.жива:
            raise RuntimeError("Target closed")
        return 1

    def bring_to_front(self):
        pass

    def close(self):
        self.жива = False


class Конт:
    def __init__(self, жив=True):
        self.жив = жив
        self.страницы = []

    @property
    def pages(self):
        if not self.жив:
            raise RuntimeError("Browser closed")
        return self.страницы

    def new_page(self):
        if not self.жив:
            raise RuntimeError("Browser closed")
        с = Стр()
        self.страницы.append(с)
        return с


def браузер(стр, конт):
    б = object.__new__(Browser)
    б.page, б.ctx, б._браузер = стр, конт, None
    б.log = lambda *_: None
    б.подняли = 0

    def _поднять():
        б.подняли += 1
        б.ctx = Конт()
        б.page = б.ctx.new_page()

    б._поднять = _поднять
    return б


print("=== 1. ЖИВАЯ ВКЛАДКА — НИЧЕГО НЕ ТРОГАЕМ ===")
с = Стр()
б = браузер(с, Конт())
проверить("оживлять не пришлось", б.ожить(), False)
проверить("та же вкладка", б.page is с, True)

print()
print("=== 2. ВКЛАДКА УМЕРЛА — БЕРЁМ НОВУЮ ===")
мёртвая = Стр(жива=False)
к = Конт()
к.страницы.append(мёртвая)
б = браузер(мёртвая, к)
проверить("оживили", б.ожить(), True)
проверить("рабочая вкладка живая", б.page.is_closed(), False)
проверить("браузер заново не поднимали", б.подняли, 0)

print()
print("=== 3. УМЕР ВЕСЬ БРАУЗЕР — ПОДНИМАЕМ ЗАНОВО ===")
б = браузер(Стр(жива=False), Конт(жив=False))
проверить("оживили", б.ожить(), True)
проверить("подняли заново", б.подняли, 1)
проверить("вкладка живая", б.page.is_closed(), False)

print()
print("=== 4. ПРИБРАТЬСЯ ОЖИВЛЯЕТ ===")
б = браузер(Стр(жива=False), Конт(жив=False))
б.прибраться()
проверить("после уборки вкладка живая", б.page.is_closed(), False)

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
