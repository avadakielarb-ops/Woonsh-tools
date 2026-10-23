"""
Словения: карточка ЧАСТНОГО ПРЕДПРИНИМАТЕЛЯ (s.p.) читается и качается.

У AJPES две разные карточки, и подписи на них не совпадают:

    судебный реестр (d.o.o.)      деловой реестр, podjetje.asp (s.p.)
    ─────────────────────────     ─────────────────────────────────────
    Entity status: registered     поля статуса НЕТ вовсе
    Registration number           Identification number
    Full company name             Full name / Contracted name
    Business address              Address + City + Post office
    ссылка «REGULAR EXTRACT»      кнопка «PDF» рядом с «PRINT»

Пока драйвер знал только левый столбец, на s.p. он висел два раза по 20
секунд, писал «карточка так и не открылась» при открытой карточке, потом
«статус: —» и вставал на каждой фирме. Замер по логам 08.10.2026: 40 фирм,
у которых карточка «не открылась», и среди них НИ ОДНОЙ d.o.o.

Текст ниже — с живой карточки, присланной человеком.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.geos.slovenia import Slovenia

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


# ─── карточка s.p., как её отдаёт inner_text ───
SP = """To content ABOUT AJPES ONLINE REGISTERS FINANCIAL DATA STARTING A BUSINESS
Anonimni uporabnik Login time: 15:00
Online Registers / Slovenian Business Register / ePRS
Search Search results Selected company
POSLOVNO SVETOVANJE RENATO FÄNRICH S.P. | Identification Number 1699890000 | Registered in Slovenian Business Register on day 08.10.2026
Basic information on the PRS unit
Full name:
POSLOVNO SVETOVANJE RENATO FÄNRICH S.P.
Contracted name:
AQUA TEAM RENATO FÄNRICH S.P.
Address:
Selovec 13A
City:
Selovec
Post office:
2373 Šentjanž pri Dravogradu
Municipality:
Dravograd
Region:
KOROŠKA
AJPES branch office:
MARIBOR
Phone, fax, e-mail:
041 743 558 (GSM)
Identification data
Identification number:
1699890000
Tax number**:
29401178
Bank accounts:
IBAN SI56 6100 0002 6044 847 (T) DH d.d.
"""

# ─── карточка d.o.o. из судебного реестра — она должна работать как и раньше ───
DOO = """Basic Information about the Entity
Entity status:
registered
Registration number:
6329632000
Full company name:
AQUA - SO 23 vodne storitve in inženiring d.o.o.
Business address:
Sodji Vrh 24, 8333 Semič
Legal organizational form:
Limited liability company (d.o.o.)
REGULAR EXTRACT
"""


class Фирма:
    name = "AQUA TEAM RENATO FANRICH S.P."


class Страница:
    def __init__(self, текст):
        self._текст = текст

    def inner_text(self, _sel):
        return self._текст


class Драйвер(Slovenia):
    """Берём только разбор — ни браузера, ни сети."""
    def __init__(self, текст):
        self.имя = self.адрес = self.рег = ""
        self._стр = Страница(текст)

    @property
    def page(self):
        return self._стр


print("=== 1. КАРТОЧКА s.p. ЧИТАЕТСЯ ===")
d = Драйвер(SP)
ok, why = d.check(Фирма())
проверить("фирма принята", (ok, why), (True, ""))
проверить("номер из «Identification number»", d.рег, "1699890000")
проверить("имя из «Full name»", d.имя,
          "POSLOVNO SVETOVANJE RENATO FÄNRICH S.P.")
проверить("адрес собран из Address + Post office", d.адрес,
          "Selovec 13A, 2373 Šentjanž pri Dravogradu")

print()
print("=== 2. ПРИЗНАК ОТКРЫТОЙ КАРТОЧКИ ЛОВИТ ОБЕ ===")
import re as _re
шаблон = _re.search(r"/(.+?)/i\.test", Slovenia.ПРИЗНАК_КАРТОЧКИ.replace("\n", ""))
ре = _re.compile(шаблон.group(1), _re.I)
проверить("видит карточку s.p.", bool(ре.search(SP)), True)
проверить("видит карточку d.o.o.", bool(ре.search(DOO)), True)
проверить("пустую страницу не считает карточкой",
          bool(ре.search("To content ABOUT AJPES ONLINE REGISTERS")), False)

print()
print("=== 3. СУДЕБНЫЙ РЕЕСТР РАБОТАЕТ КАК РАНЬШЕ ===")
d2 = Драйвер(DOO)
ok2, why2 = d2.check(Фирма())
проверить("фирма принята", (ok2, why2), (True, ""))
проверить("номер из «Registration number»", d2.рег, "6329632000")
проверить("адрес из «Business address»", d2.адрес, "Sodji Vrh 24, 8333 Semič")

print()
print("=== 4. ЗАКРЫТУЮ ФИРМУ ПО-ПРЕЖНЕМУ ОТСЕИВАЕМ ===")
мертвая = DOO.replace("registered", "deleted from the register")
ok3, why3 = Драйвер(мертвая).check(Фирма())
проверить("не принята", ok3, False)

print()
print("=== 5. ПУСТАЯ СТРАНИЦА — ЭТО «СТАТУС: —», А НЕ ГОДНАЯ ===")
# Иначе мы бы «подтверждали» фирму по недогруженной странице.
ok4, why4 = Драйвер("To content ABOUT AJPES ONLINE REGISTERS\n").check(Фирма())
проверить("не принята", (ok4, why4), (False, "статус: —"))

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
