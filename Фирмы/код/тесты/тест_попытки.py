"""
«Не нашлось» больше не приговор: пробуем написание от модели и имя без
формы, потом спрашиваем человека, и НЕ помечаем фирму непригодной.

Упрощений «первые слова» больше нет (решение пользователя 20.10.2026: «с
упрощёнными запросами перебор»). Вместо угадывания — написание реестра,
которое модель дала ДО прогона (см. part2/местные_имена.py).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.human import HumanGate
from part2.core.matching import Candidate
from part2.core.models import Company
import part2.engine as д2

# Паузы между запросами — для живого реестра; здесь они только тормозят.
д2._пауза_между_запросами = lambda *a, **к: None

ошибок = 0


class ФейкСтраница:
    def wait_for_timeout(self, ms): pass


class ФейкДрайвер:
    """Находит фирму ТОЛЬКО по одному запросу, на остальные — чужая фирма."""
    code = "HU"

    def __init__(self, нужный_запрос, ответ):
        self.нужный, self.ответ = нужный_запрос, ответ
        self.запросы = []
        self.page = ФейкСтраница()

    def search(self, c):
        self.запросы.append(c.name)
        if c.name.upper() == self.нужный.upper():
            return list(self.ответ)
        return [Candidate(name="СОВСЕМ ДРУГАЯ ФИРМА", address="Другой город",
                          ref="999")]

    def следующая_страница(self): return False
    def кандидаты_страницы(self): return []
    def open(self, cand): pass
    def check(self, c): return True, ""
    def данные_реестра(self): return {}


class ПустойДрайвер(ФейкДрайвер):
    """Реестр на «не тот» запрос отдаёт ПУСТО — как Латвия на «Packaged Ice SIA»."""
    def search(self, c):
        self.запросы.append(c.name)
        if c.name.upper() == self.нужный.upper():
            return list(self.ответ)
        return []


спрошено = []


def человек(title, message, company):
    спрошено.append(title)
    raise RuntimeError("человек")


human = HumanGate(ui_ask=человек)
АДРЕС = "Fo utca 1 1011 Budapest"


def выбрать(d, c, говорить=True):
    return д2._выбрать_фирму(d, c, АДРЕС, human,
                             (lambda s: print("   ", s)) if говорить else (lambda s: None))


print("=== 1. Нашлось по написанию от модели — человека НЕ зовём ===")
спрошено.clear()
c = Company(row=0, name="ICE STAR Kereskedelmi Kft.", address="Fo utca 1",
            city="Budapest", zip_code="1011",
            extra={"написания": ["ICE STAR Kereskedelmi és Szolgáltató Kft."]})
d = ФейкДрайвер("ICE STAR Kereskedelmi és Szolgáltató Kft.",
                [Candidate(name="ICE STAR Kereskedelmi és Szolgáltató Kft.",
                           address="Budapest", ref="111")])
try:
    выбор = выбрать(d, c)
    if выбор and выбор.ref == "111":
        print(f"   ✔ нашёл: {выбор.name}")
    else:
        ошибок += 1
        print(f"   ✘ не тот: {выбор}")
except RuntimeError:
    ошибок += 1
    print("   ✘ позвал человека, хотя фирма находится")
print("   запросов сделано:", d.запросы)
if len(d.запросы) != 1:
    ошибок += 1
    print("   ✘ написание от модели должно быть первым запросом")

print()
print("=== 2. Не нашлось ничем — ОБЯЗАН спросить человека ===")
спрошено.clear()
c2 = Company(row=0, name="ICE STAR Kft.", address="Fo utca 1",
             city="Budapest", zip_code="1011")
d2 = ФейкДрайвер("НИКОГДА-НЕ-СОВПАДЁТ", [])
try:
    выбор = выбрать(d2, c2, говорить=False)
    ошибок += 1
    print(f"   ✘ решил сам, не спросив: {выбор}")
except RuntimeError:
    print("   ✔ спросил человека:", спрошено[0] if спрошено else "?")
print("   запросы:", d2.запросы)
if d2.запросы != ["ICE STAR Kft.", "ICE STAR"]:
    ошибок += 1
    print("   ✘ ждали ровно два запроса: имя и имя без формы")

print()
print("=== 3. Реестр пуст на полное имя, без формы — находит ===")
спрошено.clear()
d3 = ПустойДрайвер("ICE STAR", [Candidate(name="ICE STAR Kft.",
                                          address="Budapest", ref="111")])
try:
    выбор = выбрать(d3, c2)
    if выбор and выбор.ref == "111":
        print(f"   ✔ нашёл без формы: {выбор.name}")
    else:
        ошибок += 1
        print(f"   ✘ не нашёл: {выбор}")
except RuntimeError:
    ошибок += 1
    print("   ✘ сдался человеку, хотя запрос без формы находит")

print()
print("=== 4. Реестр пуст на ВСЕ запросы — человек, а не молчаливый отказ ===")
спрошено.clear()
d4 = ПустойДрайвер("НИКОГДА-НЕ-СОВПАДЁТ", [])
журнал = []
try:
    выбор = д2._выбрать_фирму(d4, c2, АДРЕС, human, журнал.append)
    ошибок += 1
    print(f"   ✘ молча вернул «нет в реестре»: {выбор}")
except RuntimeError:
    print("   ✔ спросил человека")
# Пустые запросы тоже в логе: раньше они молчали, и по логу было не понять,
# чем вообще искали.
пустые = [s for s in журнал if "— 0 шт." in s]
if len(пустые) != 2:
    ошибок += 1
    print("   ✘ пустые запросы не записаны в лог:", журнал)
else:
    print("   ✔ оба пустых запроса в логе")

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
