"""
Быстрая смена слова на dnb: 4 секунды вместо 30 — но только когда безопасно.

Замер 25.08.2026 на живом сайте: полный круг 29,7 с, смена слова прямым
адресом 4,3 с (в 6,9 раза быстрее), фильтр страны сохраняется.
Опасность одна: перейти по адресу и не заметить, что выдача осталась прежней
или уехала на другую страну. Тогда фирмы уедут не в тот лист.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part1.dnb import DnB

ошибок = 0
АДРЕС = ("https://www.dnb.com/site-search-results.html"
         "#BusinessDirectoryPageNumber=1&BusinessDirectorySearch=granite"
         "&tab=Business%20Directory")


class ФейкСтраница:
    def __init__(self):
        self.url = АДРЕС
        self.переходы = []

    def goto(self, url, **k):
        self.переходы.append(url)
        self.url = url

    def wait_for_function(self, *a, **k): pass
    def wait_for_timeout(self, ms): pass


class Фейк(DnB):
    """Только механика смены слова — без браузера."""
    def __init__(self, строк=5, страна_ок=True):
        self.page = ФейкСтраница()
        self.log = lambda s: None
        self._строк, self._страна_ок = строк, страна_ок
        self._адрес_выдачи = АДРЕС
        self._слово_выдачи = "granite"
        self._страна_выдачи = "Poland"

    def rows(self):
        return list(range(self._строк))

    def страна_выдачи_совпадает(self, name, порог=0.8):
        return (self._страна_ок, "проверка")


print("=== 1. Слово в адресе подменяется, страна не трогается ===")
d = Фейк()
ок = d.сменить_слово("falcon", "Poland")
адрес = d.page.переходы[-1] if d.page.переходы else ""
print("   перешли на:", адрес[-70:])
if not ок:
    ошибок += 1
    print("   ✘ быстрый путь не сработал")
elif "BusinessDirectorySearch=falcon" not in адрес:
    ошибок += 1
    print("   ✘ слово в адресе не подменилось")
elif "granite" in адрес:
    ошибок += 1
    print("   ✘ старое слово осталось в адресе")
else:
    print("   ✔")

print()
print("=== 2. ДРУГАЯ СТРАНА — быстрый путь запрещён ===")
d2 = Фейк()
ок2 = d2.сменить_слово("falcon", "Latvia")
print(f"   вернул {ок2}, переходов: {len(d2.page.переходы)}")
if ок2 or d2.page.переходы:
    ошибок += 1
    print("   ✘ полез быстрым путём в другую страну — фирмы уехали бы не в тот лист")
else:
    print("   ✔ отказался, пойдёт длинным путём")

print()
print("=== 3. Пустая выдача — быстрый путь честно признаёт неудачу ===")
d3 = Фейк(строк=0)
ок3 = d3.сменить_слово("falcon", "Poland")
print("   вернул:", ок3)
if ок3:
    ошибок += 1
    print("   ✘ принял пустую выдачу за успех")
else:
    print("   ✔ вернёт False → движок переищет длинным путём")

print()
print("=== 4. Страна в выдаче уехала — тоже отказ ===")
d4 = Фейк(страна_ок=False)
ок4 = d4.сменить_слово("falcon", "Poland")
print("   вернул:", ок4)
if ок4:
    ошибок += 1
    print("   ✘ записал бы фирмы чужой страны")
else:
    print("   ✔ отказался")

print()
print("=== 5. Первого поиска ещё не было — быстрый путь недоступен ===")
d5 = Фейк()
d5._адрес_выдачи = ""
ок5 = d5.сменить_слово("falcon", "Poland")
print("   вернул:", ок5)
if ок5:
    ошибок += 1
    print("   ✘ пошёл по пустому адресу")
else:
    print("   ✔")

print()
print("=== 6. Сайт сменил разметку адреса — отказ, а не мусорный переход ===")
d6 = Фейк()
d6._адрес_выдачи = "https://www.dnb.com/site-search-results.html#other=1"
ок6 = d6.сменить_слово("falcon", "Poland")
print(f"   вернул {ок6}, переходов: {len(d6.page.переходы)}")
if ок6 or d6.page.переходы:
    ошибок += 1
    print("   ✘ пошёл по адресу, в котором слова нет")
else:
    print("   ✔")

print()
print("ошибок:", ошибок)
