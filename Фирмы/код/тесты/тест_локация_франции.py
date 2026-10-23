"""
Франция: фирму ищем ПО ЛОКАЦИИ, а не по всей стране.

Живой случай 10.09.2026. Фирма «AQUA», адрес «4 B CHE DE LA FONDERIE 26200,
MONTELIMAR». Колонка «Индекс» пустая (Часть 1 разбирала адрес только у фирм
С САЙТОМ), фильтра не вышло, поиск ушёл по всей Франции: 3773 результата,
девять чужих «AQUA» человеку на выбор — и он их, конечно, пропустил.
А по индексу 26200 наша фирма ПЕРВАЯ из четырёх.

Проверяем три вещи: индекс достаётся из адреса; лестница коммуна →
департамент → страна идёт по порядку и останавливается на первой удаче;
выдачу департамента просеиваем сами, чтобы «фильтр перестал работать»
не выглядело как «нашлось».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.geos.france import France

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


class Стр:
    url = ""

    def wait_for_load_state(self, *a, **к):
        pass


class Бр:
    """Браузер, который только запоминает, куда его послали."""

    def __init__(self, выдача: dict):
        self.выдача, self.ходы, self.адрес = выдача, [], ""
        self.page = Стр()          # драйвер берёт вкладку у браузера, не хранит

    def goto(self, url):
        self.ходы.append(url)
        self.адрес = url

    def check_captcha(self, *a):
        pass


СТРАНА = "вся страна"      # ключ выдачи для запроса БЕЗ фильтра локации


def драйвер(выдача: dict) -> France:
    """
    France без браузера: выдачу подменяем по кусочку URL.

    Ключ `СТРАНА` срабатывает только на запросе БЕЗ `cp_dep` — иначе он
    совпадал бы и с запросом по коммуне (в нём тоже есть `terme=`), и
    проверка «дошли ли до всей Франции» ничего бы не проверяла.
    """
    d = object.__new__(France)
    d.br = Бр(выдача)
    d.log = lambda *a, **к: None

    def кандидаты():
        for ключ, значение in выдача.items():
            подошло = ("cp_dep" not in d.br.адрес if ключ == СТРАНА
                       else ключ in d.br.адрес)
            if подошло:
                return list(значение)
        return []

    d._кандидаты = кандидаты
    return d


АДРЕС = "4 B CHE DE LA FONDERIE 26200, MONTELIMAR, AUVERGNE RHONE ALPES France"
наша = Candidate(name="AQUA", address="4 B CHEMIN DE LA FONDERIE 26200 MONTELIMAR",
                 ref="/entreprise/aqua-980813281")
чужие = [Candidate(name="AQUA", address="LES TERRES NOIRES 85710 GARNACHE (LA)",
                   ref="/entreprise/aqua-1"),
         Candidate(name="AQUA", address="6 RUE DU COMMANDANT JOUBIN 09100 PAMIERS",
                   ref="/entreprise/aqua-2")]

print("=== 1. Индекс берём из адреса, если колонка пустая ===")
d = драйвер({})
проверить("из колонки", d.индекс_фирмы(Company(row=2, name="AQUA", zip_code="26200")),
          "26200")
проверить("из адреса, колонка пуста",
          d.индекс_фирмы(Company(row=2, name="AQUA", address=АДРЕС)), "26200")
проверить("индекса нет вовсе",
          d.индекс_фирмы(Company(row=2, name="AQUA", address="PARIS 6, ILE DE FRANCE")),
          "")

print()
print("=== 2. Первой идёт коммуна, и на ней всё кончается ===")
d = драйвер({"cp_dep=26200": [наша]})
вышло = d.search(Company(row=2, name="AQUA", address=АДРЕС))
проверить("нашли нашу фирму", [к.ref for к in вышло], [наша.ref])
проверить("сходили ровно один раз", len(d.br.ходы), 1)
проверить("фильтр по коммуне в адресе", "cp_dep=26200&cp_dep_type=cp" in d.br.ходы[0],
          True)

print()
print("=== 3. Коммуна пуста — идём в департамент, а не сразу по всей стране ===")
d = драйвер({"cp_dep=26&cp_dep_type=dep": [наша] + чужие})
вышло = d.search(Company(row=2, name="AQUA", address=АДРЕС))
проверить("вернули только фирму своего департамента",
          [к.ref for к in вышло], [наша.ref])
проверить("ступеней пройдено", len(d.br.ходы), 2)

print()
print("=== 4. Фильтр департамента не сработал — это НЕ находка ===")
# Сайт отдал всю Францию: ни одного индекса на «26». Принять такое за выдачу
# департамента значит показать человеку девять чужих фирм и назвать это
# сужением по локации.
d = драйвер({"cp_dep=26&cp_dep_type=dep": чужие, СТРАНА: чужие})
вышло = d.search(Company(row=2, name="AQUA", address=АДРЕС))
проверить("дошли до всей Франции", len(d.br.ходы), 3)
проверить("отдали то, что есть, человеку", len(вышло), len(чужие))

print()
print("=== 5. Индекса нет — сразу по стране, лишних ходов не делаем ===")
d = драйвер({СТРАНА: чужие})
вышло = d.search(Company(row=2, name="AQUA", address="PARIS 6, ILE DE FRANCE, France"))
проверить("ход один", len(d.br.ходы), 1)
проверить("фильтра в адресе нет", "cp_dep" in d.br.ходы[0], False)

print()
print("=== 6. Индекса нет, но есть город — просеиваем выдачу по нему ===")
d = драйвер({СТРАНА: чужие + [наша]})
вышло = d.search(Company(row=2, name="AQUA", city="MONTELIMAR",
                         address="MONTELIMAR, AUVERGNE RHONE ALPES, France"))
проверить("остались только свои", [к.ref for к in вышло], [наша.ref])

# Город устарел или фирма переехала — оставить человека НИ С ЧЕМ нельзя.
d = драйвер({СТРАНА: чужие})
вышло = d.search(Company(row=2, name="AQUA", city="MONTELIMAR",
                         address="MONTELIMAR, AUVERGNE RHONE ALPES, France"))
проверить("никого в нашем городе — отдаём всех", len(вышло), len(чужие))

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
