"""
Человек открыл карточку и нажал «Продолжить» — карточку ОБЯЗАНЫ принять.

Живой случай 12.09.2026: Швейцария, AQUA AG, карточка открыта на
zefix.ch/…/firm/518110 — приложение трижды сказало «Не вижу карточку фирмы»
и выбросило фирму. Причина: `карточка_открыта()` спрашивала `номер()`, а
`номер()` у драйверов отдаёт поле, которое заполняет только `check()`. В этом
месте `check()` ещё не звали — поле пустое, ответ был предрешён.

Проверяем, что теперь:
  1. карточку читают ДО вопроса «видна ли она»;
  2. годится признак самого гео («/firm/» в адресе), даже если check() вышел
     раньше времени — например, у фирмы неподходящий статус;
  3. когда карточки правда нет, человека переспрашивают, а не молчат.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.engine import SkipCompany, _принять_от_человека
from part2.geos.base import GeoDriver

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


class Стр:
    def __init__(self, текст="", url=""):
        self._т, self.url = текст, url

    def inner_text(self, sel="body"):
        return self._т

    def wait_for_load_state(self, *a, **к):
        pass


class Бр:
    def __init__(self, стр):
        self.page = стр
        self.переходов = 0

    def вкладка_человека(self, log=None):
        self.переходов += 1


class Человек:
    def __init__(self):
        self.спрошено = 0

    def require(self, *a, **к):
        self.спрошено += 1


class КакВсе(GeoDriver):
    """
    Драйвер «как все»: номер живёт в поле, а поле заполняет check().

    Ровно так устроены 15 из 16 гео — поэтому проверка и стоит на такой
    подделке, а не на удобной.
    """
    code, title, method = "XX", "Тест", "print"

    def __init__(self, br, human, статус_годный=True):
        super().__init__(br, human)
        self.uid = ""
        self.статус_годный = статус_годный
        self.читали = 0

    def search(self, c):
        return []

    def open(self, cand):
        return                      # человек уже на нужной странице

    def check(self, c):
        self.читали += 1
        if not self.статус_годный:
            return False, "статус: вычеркнута"   # ВЫШЛИ ДО ЧТЕНИЯ НОМЕРА
        self.uid = "CHE-109.550.483"
        return True, ""

    def fetch(self, c, dest):
        return dest

    def номер(self):
        return self.uid


фирма = Company(row=2, name="AQUA AG", address="Steineggstrasse 34")
выбор = Candidate(name="AQUA AG", address="", ref="HUMAN")

print("=== 1. Карточка открыта, фирма годная — принимаем с первого раза ===")
ч = Человек()
стр = Стр("AQUA AG\nstatus active\nCHE-109.550.483",
          "https://www.zefix.ch/en/search/entity/list/firm/518110")
д = КакВсе(Бр(стр), ч)
_принять_от_человека(д, д.br, фирма, выбор, ч, lambda *a: None)
проверить("карточку прочитали", д.читали >= 1, True)
проверить("человека не дёргали", ч.спрошено, 0)
проверить("номер снят", д.номер(), "CHE-109.550.483")

print()
print("=== 2. Статус негодный — но карточка ВИДНА, и это разные вещи ===")
# check() выходит до чтения номера, поле пустое. Раньше человек получал
# «Не вижу карточку» вместо честного «фирма вычеркнута». Признак гео —
# «/firm/» в адресе — отвечает на вопрос независимо от check().


class СПризнаком(КакВсе):
    def на_карточке(self):
        return "/firm/" in (self.page.url or "")


ч2 = Человек()
д2 = СПризнаком(Бр(Стр("AQUA AG\nstatus deleted",
                       "https://www.zefix.ch/en/search/entity/list/firm/518110")),
                ч2, статус_годный=False)
_принять_от_человека(д2, д2.br, фирма, выбор, ч2, lambda *a: None)
проверить("карточку приняли", ч2.спрошено, 0)

print()
print("=== 3. Карточки правда нет — переспрашиваем, потом сдаёмся вслух ===")
ч3 = Человек()
д3 = КакВсе(Бр(Стр("Search business name", "https://www.zefix.ch/en/search/entity/list")),
            ч3, статус_годный=False)
try:
    _принять_от_человека(д3, д3.br, фирма, выбор, ч3, lambda *a: None)
    проверить("должны были сдаться", "прошли молча", "SkipCompany")
except SkipCompany:
    проверить("переспросили, а не бросили сразу", ч3.спрошено, 2)
    проверить("на вкладку человека ходили каждый раз", д3.br.переходов, 3)

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
