"""
Трёхэтапный подбор: сам → карточки за адресом (только для полных тёзок) → человек.
Проверяем на подставном драйвере, без сети.

Правило 20.10.2026: адрес — второстепенный признак. Он различает фирмы с
ОДИНАКОВЫМ именем, но не выбирает фирму с другим: раньше «SIA Delta»
выбиралась как «SIA Beta» только потому, что у Beta в карточке наш адрес, — а
DnB часто держит адрес бухгалтера, и в том же здании сидят десятки фирм.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.human import HumanGate
from part2.core.matching import Candidate
from part2.core.models import Company
import part2.engine as д2

д2._пауза_между_запросами = lambda *a, **к: None

НАШ_АДРЕС = "Rupnicu iela 4, LV-2114, Olaine"

class ФейкСтраница:
    def wait_for_timeout(self, ms): pass

class ФейкДрайвер:
    """
    Выдача без адресов (как в жизни), адрес есть только в карточке.
    Считаем, сколько карточек открыли.
    """
    code = "LV"

    def __init__(self, адреса, кандидаты):
        self.адреса = адреса
        self._канд = кандидаты
        self.открыто = []
        self.текущий = None
        self.page = ФейкСтраница()
        self.поисков = 0

    def search(self, c):
        self.поисков += 1
        return list(self._канд)

    def следующая_страница(self):
        return False

    def кандидаты_страницы(self):
        return list(self._канд)

    def open(self, cand):
        self.открыто.append(str(cand.ref))
        self.текущий = str(cand.ref)

    def check(self, c):
        return True, ""

    def данные_реестра(self):
        return {"адрес": self.адреса.get(self.текущий, "")}


def прогнать(имя, кандидаты, адреса):
    спрошено = {}
    def человек(title, message, company):
        спрошено["msg"] = message
        raise RuntimeError("человек")
    human = HumanGate(ui_ask=человек)
    d = ФейкДрайвер(адреса, кандидаты)
    c = Company(row=0, name=имя, address="Rupnicu iela 4", city="Olaine",
                zip_code="LV-2114", website="")
    try:
        выбор = д2._выбрать_фирму(d, c, НАШ_АДРЕС, human, lambda s: print("   ", s))
        return выбор, d, спрошено
    except RuntimeError:
        return None, d, спрошено


ошибок = 0

print("=== 1. ПОЛНЫЕ ТЁЗКИ, адрес только в карточке — выбираем САМИ ===")
канд = [Candidate(name="SIA Delta", address="", ref="111"),
        Candidate(name="Delta SIA", address="", ref="222"),
        Candidate(name='SIA "DELTA"', address="", ref="333")]
адреса = {"111": "Riga, Cita iela 9",
          "222": "Olaine, Rupnicu iela 4, LV-2114",
          "333": "Liepaja, Kada iela 1"}
выбор, d, спрошено = прогнать("SIA Delta", канд, адреса)
if выбор and str(выбор.ref) == "222":
    print(f"   ✔ выбрал сам: {выбор.name} (открыл карточек: {len(d.открыто)})")
else:
    ошибок += 1
    print(f"   ✘ не выбрал: {выбор}")
if спрошено:
    ошибок += 1
    print("   ✘ человека всё-таки спросили")

print()
print("=== 1б. ДРУГОЕ ИМЯ С НАШИМ АДРЕСОМ — НЕ ВЫБИРАЕМ ===")
чужие = [Candidate(name="SIA Alfa", address="", ref="111"),
         Candidate(name="SIA Beta", address="", ref="222")]
выбор, d, спрошено = прогнать("SIA Delta", чужие, адреса)
if выбор is not None:
    ошибок += 1
    print(f"   ✘ выбрал по адресу фирму с чужим именем: {выбор.name}")
else:
    print("   ✔ не выбрал — решает человек")
if d.открыто:
    ошибок += 1
    print("   ✘ ходил в карточки ради чужих имён")

print()
print("=== 2. Имена ПОХОЖИ, но не точные — человек ===")
похожие = [Candidate(name="SIA Delta Riga", address="", ref="111"),
           Candidate(name="SIA Delta Serviss", address="", ref="222")]
выбор, d, спрошено = прогнать("SIA Delta", похожие, {"111": "Riga, Cita iela 9",
                                                     "222": "Ventspils, Osta 3"})
if выбор is not None:
    ошибок += 1
    print(f"   ✘ выбрал наугад: {выбор.name}")
elif not спрошено:
    ошибок += 1
    print("   ✘ человека не спросили")
else:
    print("   ✔ спросил человека")

print()
print("=== 2б. Кандидаты СОВСЕМ чужие — сдаёмся ЧЕЛОВЕКУ, а не молча ===")
адреса2б = {"111": "Riga, Cita iela 9",
            "222": "Ventspils, Osta 3",
            "333": "Liepaja, Kada iela 1"}
alfa = [Candidate(name="SIA Alfa", address="", ref="111"),
        Candidate(name="SIA Beta", address="", ref="222"),
        Candidate(name="SIA Gamma", address="", ref="333")]
выбор, d, спрошено = прогнать("SIA Delta", alfa, адреса2б)
if выбор is not None:
    ошибок += 1
    print(f"   ✘ выбрал чужую: {выбор.name}")
elif not спрошено:
    ошибок += 1
    print("   ✘ решил за человека, что фирмы в реестре нет")
else:
    print("   ✔ спросил человека, прежде чем сказать «нет в реестре»")

print()
print("=== 3. Не больше пяти карточек ===")
много = [Candidate(name="SIA Delta", address="", ref=str(i)) for i in range(12)]
адреса3 = {str(i): f"Gorod {i}, Ulica {i}" for i in range(12)}
выбор, d, спрошено = прогнать("SIA Delta", много, адреса3)
print(f"   открыто карточек: {len(d.открыто)} (предел {д2.МАКС_КАРТОЧЕК})")
if len(d.открыто) > д2.МАКС_КАРТОЧЕК:
    ошибок += 1
    print("   ✘ открыл больше предела")
else:
    print("   ✔ предел соблюдён")

print()
print("=== 4. Если адреса в выдаче УЖЕ есть — карточки не трогаем ===")
с_адресами = [Candidate(name="SIA Delta", address="Riga, Cita iela 9", ref="111"),
              Candidate(name="SIA Delta", address="Olaine, Rupnicu iela 4", ref="222")]
выбор, d, спрошено = прогнать("SIA Delta", с_адресами, адреса)
print(f"   открыто карточек: {len(d.открыто)} (ждём 0)")
if d.открыто:
    ошибок += 1
    print("   ✘ полез в карточки без нужды")
else:
    print("   ✔ лишних заходов нет")
if not (выбор and str(выбор.ref) == "222"):
    ошибок += 1
    print("   ✘ тёзок с адресами в выдаче не различил:", выбор)

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
