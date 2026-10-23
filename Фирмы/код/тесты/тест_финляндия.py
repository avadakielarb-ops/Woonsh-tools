"""
Финляндия: не ждём «тишины в сети» и знаем оба пути к выписке.

Живой прогон 15.10.2026: «Timeout 30000ms exceeded» на КАЖДОЙ фирме подряд,
0 скачано из 190. Причина — `wait_for_load_state("networkidle")`: Virre это
одностраничное приложение, оно постоянно о чём-то спрашивает сервер, и
тишины в сети не наступает НИКОГДА. Ожидание висело свои тридцать секунд и
падало — дважды на фирму, после поиска и после открытия карточки.

Второе: к выписке ДВА пути, и верхней кнопки `Avaa kaupparekisteriote` на
карточке может не быть. Тогда внизу лежит СВЁРНУТЫЙ раздел
«Kaupparekisteriote»: раскрыть → «Voimassaoleva ote» → «Avaa».
Пока этого не знали, драйвер искал кнопку, которой на экране ещё нет.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.geos.finland import Finland

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


print("=== 1. НИ ОДНОГО ОЖИДАНИЯ «networkidle» ===")
# Оно не наступает на этом сайте никогда и стоило 190 фирм за прогон.
текст = Path(__file__).resolve().parent.parent.joinpath(
    "part2/geos/finland.py").read_text(encoding="utf-8")
# Ищем именно ВЫЗОВ, разбирая код: в пояснениях слово остаётся намеренно —
# чтобы следующий, кто сюда придёт, знал, почему здесь так нельзя. Поиск по
# тексту на этом и спотыкался: он не отличает код от рассказа о коде.
import ast

вызовы = [у for у in ast.walk(ast.parse(текст))
          if isinstance(у, ast.Call)
          and getattr(у.func, "attr", "") == "wait_for_load_state"
          and any(isinstance(а, ast.Constant) and а.value == "networkidle"
                  for а in у.args)]
проверить("вызовов не осталось", len(вызовы), 0)

print()
print("=== 2. ЖДЁМ ТОГО, ЧЕГО ЖДЁМ — И УСЛОВИЯ ДЕЙСТВИТЕЛЬНО РАБОТАЮТ ===")
проверить("есть помощник ожидания", hasattr(Finland, "_дождаться"), True)
# ГЛАВНАЯ ПРОВЕРКА. Первая правка ждала через locator() со списком
# «CSS, text=/…/» через запятую — Playwright такую смесь движков не
# принимает и падает: «Unexpected token "=" while parsing css selector».
# Ожидание молча проваливалось, страница читалась пустой, и прогон не нашёл
# НИ ОДНОЙ фирмы из 190. Поэтому проверяем не наличие слов в тексте, а то,
# что условия — настоящий рабочий JS.
import ast

дерево = ast.parse(текст)
условия = [у.args[0].value for у in ast.walk(дерево)
           if isinstance(у, ast.Call)
           and getattr(у.func, "attr", "") == "_дождаться"
           and у.args and isinstance(у.args[0], ast.Constant)]
# Ожидание выдачи — константа класса: оно собрано из двух частей (строки
# выдачи ЛИБО сразу карточка), и в вызове его строкой не увидеть.
условия += [Finland.ВЫДАЧА_ГОТОВА, Finland.ПРИЗНАК_КАРТОЧКИ]
проверить("условия ожидания найдены", len(условия) >= 3, True)

from playwright.sync_api import sync_playwright

сломанные = []
with sync_playwright() as p:
    бр = p.chromium.launch()
    стр = бр.new_page()
    стр.set_content("<body><div data-testid='tableRow-0'>"
                    "Y-tunnus Perustiedot</div></body>")
    стр.set_content("<body><div data-testid='tableRow-0'>"
                    "Y-tunnus 1234567-8 Perustiedot</div></body>")
    for в in условия:
        try:
            стр.wait_for_function(f"() => {в}", timeout=3000)
        except Exception as e:
            сломанные.append(f"{в[:40]}: {type(e).__name__}")

    # ОДНА ФИРМА — НЕ «ПУСТО». На единственное совпадение Virre сразу
    # открывает карточку, строк выдачи нет — и драйвер отвечал «ничего».
    # РАЗМЕТКА — КАК НА ЖИВОЙ КАРТОЧКЕ 20.10.2026: строки tableRow-N, подпись
    # в ячейке basicDetailsTitle, значение — в basicDetailsCurrentInfo. Имя
    # фирмы подписано «Toiminimi», а не «Nimi».
    def ряд(i, подпись, значение):
        return (f"<tr data-testid='tableRow-{i}'>"
                f"<td data-testid='tableCell-basicDetailsTitle'><div>{подпись}</div></td>"
                f"<td data-testid='tableCell-basicDetailsCurrentInfo'><div>{значение}</div></td>"
                "<td data-testid='tableCell-basicDetailsDate'><div></div></td></tr>")
    стр.set_content("<body><p>Perustiedot</p><table><tr><th>Tieto</th>"
                    "<th>Viimeisin tieto</th></tr>"
                    + ряд(0, "Y-tunnus", "1234567-8") + ряд(1, "Toiminimi", "Aqua Oy")
                    + ряд(2, "Kotipaikka", "Helsinki") + "</table></body>")
    ждали_карточку = True
    try:
        стр.wait_for_function(f"() => {Finland.ВЫДАЧА_ГОТОВА}", timeout=3000)
    except Exception:
        ждали_карточку = False

    class Д(Finland):
        def __init__(self, page):
            self._p = page
            self.log = lambda *_: None

        @property
        def page(self):
            return self._p

    одна = Д(стр)._карточка_как_кандидат()
    стр.set_content("<body><p>Ei hakutuloksia</p></body>")
    пусто = Д(стр)._карточка_как_кандидат()
    бр.close()
проверить("одна карточка — ожидание дождалось", ждали_карточку, True)
проверить("одна карточка — кандидат с именем",
          одна and (одна.name, одна.ref.get("bid")), ("Aqua Oy", "1234567-8"))
проверить("пустая выдача — не карточка", пусто, None)
проверить("все условия — рабочий JS", сломанные, [])
проверить("ждём строки выдачи", any("tableRow-" in в for в in условия), True)
проверить("ждём поля карточки", any("Y-tunnus" in в for в in условия), True)

print()
print("=== 3. ЗНАЕМ ОБА ПУТИ К ВЫПИСКЕ ===")
проверить("верхняя кнопка", "Avaa kaupparekisteriote" in текст, True)
проверить("свёрнутый раздел", hasattr(Finland, "_через_раздел"), True)
# Кнопка внутри раздела — это test-id `Avaa-button-`, а НЕ ссылка с подписью
# «Avaa»: подпись у самого раздела тоже начинается с «Avaa», и поиск по
# тексту попадал в него. Взято из записи действий человека.
проверить("кнопка внутри раздела по test-id",
          "Avaa-button-" in текст, True)
проверить("имя фирмы в строке — тоже по test-id",
          "get_by_test_id(имя)" in текст, True)


print()
print("=== 4. РАЗДЕЛ РАСКРЫВАЕМ, А НЕ СВОРАЧИВАЕМ ОБРАТНО ===")
# Если он уже раскрыт, второй клик спрячет кнопку — и мы снова её не найдём.
class Эл:
    def __init__(self, раскрыт, есть=True):
        self._раскрыт = раскрыт
        self._есть = есть
        self.кликов = 0

    @property
    def first(self):           # Playwright: .first возвращает сам локатор
        return self

    def count(self):
        return 1 if self._есть else 0

    def scroll_into_view_if_needed(self, timeout=0):
        pass

    def get_attribute(self, имя):
        return "true" if (имя == "aria-expanded" and self._раскрыт) else "false"

    def click(self):
        self.кликов += 1


def кликов_по_полосе(раскрыт: bool) -> int:
    полоса = Эл(раскрыт)

    class Стр:
        def get_by_role(self, *_a, **_k):
            return Эл(False, есть=False)

        def locator(self, *_a, **_k):
            return полоса

        def wait_for_timeout(self, *_a):
            pass

    class Д(Finland):
        def __init__(self):
            self.log = lambda *_: None

        @property
        def page(self):
            return Стр()

    Д()._через_раздел(type("C", (), {"name": "X"})(), Path("."))
    return полоса.кликов


проверить("свёрнутый — раскрываем", кликов_по_полосе(False), 1)
проверить("раскрытый — не трогаем", кликов_по_полосе(True), 0)

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
