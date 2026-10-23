"""
«Продолжить» не должен превращаться в молчаливый прыжок к следующей фирме.

Проверяем три вещи без браузера:
  1. карточка открылась в НОВОЙ вкладке — драйвер должен читать её, а не старую;
  2. карточка не готова с первого раза — переспрашиваем человека, а не бросаем;
  3. человек так и не открыл — пропуск ОБЪЯВЛЕН в логе, а не втихую.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.human import HumanGate, SkipCompany
from part2.core.matching import Candidate
from part2.core.models import Company
import part2.engine as д2

ошибок = 0


class ФейкВкладка:
    def __init__(self, url, фокус=False):
        self.url, self._фокус = url, фокус
        self._closed = False

    def is_closed(self): return self._closed
    def evaluate(self, js): return self._фокус
    def bring_to_front(self): pass
    def wait_for_load_state(self, *a, **k): pass
    def wait_for_timeout(self, ms): pass
    def close(self): self._closed = True


class ФейкБраузер:
    """Две вкладки: старая выдача и новая карточка (в ней фокус)."""
    def __init__(self, вкладки, активная=0):
        self.вкладки = вкладки
        self.page = вкладки[активная]
        self.переходов = 0

    def вкладка_человека(self, log=None):
        self.переходов += 1
        для = [p for p in self.вкладки if p.evaluate("")] or self.вкладки
        сменилась = для[-1] is not self.page
        self.page = для[-1]
        if log and сменилась:
            log(f"  · перешёл на вкладку человека: {self.page.url}")
        return self.page


class ФейкДрайвер:
    """Номер умеет достать ТОЛЬКО с адреса карточки."""
    def __init__(self, br, готов_с_попытки=1):
        self.br = br
        self.готов = готов_с_попытки
        self.попыток = 0
        self.orgnr = ""

    @property
    def page(self): return self.br.page

    def open(self, cand):
        self.попыток += 1
        if self.попыток < self.готов:
            return
        if "/enheter/" in self.page.url:
            self.orgnr = self.page.url.rsplit("/", 1)[-1]

    def номер(self): return self.orgnr
    def карточка_открыта(self): return bool(self.номер())


ВЫБОР = Candidate(name="Ice Drift AS", address="", ref="HUMAN")
c = Company(row=0, name="Ice Drift AS", address="Sikterigata 6",
            city="MO I RANA", zip_code="8622", website="")

print("=== 1. Карточка в НОВОЙ вкладке — берём её, а не старую ===")
строки = []
br = ФейкБраузер([ФейкВкладка("https://brreg.no/en/oppslag/enheter?navn=Ice", False),
                  ФейкВкладка("https://brreg.no/en/oppslag/enheter/992700335", True)])
d = ФейкДрайвер(br)
human = HumanGate(ui_ask=lambda *a: (_ for _ in ()).throw(RuntimeError("человек")))
try:
    д2._принять_от_человека(d, br, c, ВЫБОР, human, строки.append)
    print(f"   ✔ принял карточку, номер {d.номер()}")
    if not any("вкладку человека" in s for s in строки):
        ошибок += 1
        print("   ✘ в логе не сказано, что перешли на вкладку человека")
except Exception as e:
    ошибок += 1
    print(f"   ✘ {type(e).__name__}: {e}")
for s in строки:
    print("      ", s)

print()
print("=== 2. Страница не готова — ПЕРЕСПРАШИВАЕМ, а не бросаем ===")
строки.clear()
спрошено = []
def спросить(title, message, company):
    спрошено.append(title)
    human2.answer(__import__("common.human", fromlist=["HumanChoice"]).HumanChoice.CONTINUE)
human2 = HumanGate(ui_ask=спросить)
br2 = ФейкБраузер([ФейкВкладка("https://brreg.no/en/oppslag/enheter/992700335", True)])
d2_ = ФейкДрайвер(br2, готов_с_попытки=2)      # с первого раза не выходит
try:
    д2._принять_от_человека(d2_, br2, c, ВЫБОР, human2, строки.append)
    print(f"   ✔ со второй попытки принял, номер {d2_.номер()}")
    if not спрошено:
        ошибок += 1
        print("   ✘ человека не переспросили")
    else:
        print(f"   ✔ переспросил: «{спрошено[0]}»")
except Exception as e:
    ошибок += 1
    print(f"   ✘ сдался: {type(e).__name__}: {e}")

print()
print("=== 3. Так и не открыл — пропуск ОБЪЯВЛЕН, а не молча ===")
строки.clear()
human3 = HumanGate(ui_ask=lambda t, m, co: human3.answer(
    __import__("common.human", fromlist=["HumanChoice"]).HumanChoice.CONTINUE))
br3 = ФейкБраузер([ФейкВкладка("https://brreg.no/en/oppslag/enheter?navn=Ice", True)])
d3 = ФейкДрайвер(br3)
try:
    д2._принять_от_человека(d3, br3, c, ВЫБОР, human3, строки.append)
    ошибок += 1
    print("   ✘ сделал вид, что всё хорошо")
except SkipCompany as e:
    print(f"   ✔ SkipCompany с причиной: «{e}»")
    if not any("не вижу карточку" in s.lower() for s in строки):
        ошибок += 1
        print("   ✘ в логе нет предупреждений")
    else:
        print(f"   ✔ и {len(строки)} строк в логе — прыжок больше не молчит")

print()
print("ошибок:", ошибок)
