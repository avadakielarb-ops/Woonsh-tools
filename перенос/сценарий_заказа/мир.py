"""
Подставной мир для сквозного прогона заказа: DnB, реестры стран, бот, Google Таблица, человек.
Решения принимает НАСТОЯЩИЙ код владельца; здесь только то, что в жизни приходит из сети и от человека.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Фирма:
    имя: str                       # как на DnB
    гео: str
    город: str
    индекс: str
    улица: str
    сайт: str = ""
    отрасль: str = "Manufacturing"
    # что знает реестр страны
    в_реестре: bool = True
    статус_ок: bool = True         # False → ликвидирована / закрыта
    номер: str = ""
    имя_в_реестре: str = ""        # пусто = как на DnB; иначе фирма меняла имя
    сбоев_сети: int = 0            # сколько раз реестр «упадёт по таймауту» на этой фирме
    бот_знает: bool = False        # бот уже видел (дубль у команды)
    штат: str = ""                 # US: код штата в адресе DnB


class МирDnB:
    """Что показывает DnB: фирмы по слову и стране, страницами по 25."""
    НА_СТРАНИЦЕ = 25

    def __init__(self, фирмы: list[Фирма]):
        self.фирмы = фирмы
        self.поисков = 0

    def выдача(self, слово: str, гео: str) -> list[Фирма]:
        с = слово.lower()
        return [ф for ф in self.фирмы if ф.гео == гео and с in ф.имя.lower()]


def сделать_dnb(мир: МирDnB):
    from part1.models import Firm
    from part1.data.countries import to_code

    class ФейкDnB:
        def __init__(self, br, human, log):
            self.log = log
            self.строки_все: list[Фирма] = []
            self.стр = 0

        def сменить_слово(self, keyword, country):
            return False

        def search(self, keyword, country):
            мир.поисков += 1
            self.строки_все = мир.выдача(keyword, to_code(country))
            self.стр = 0
            return bool(self.строки_все)

        def страна_выдачи_совпадает(self, имя):
            return True, f"{len(self.rows())}/{len(self.rows())} строк из «{имя}»"

        def _страница(self):
            н = МирDnB.НА_СТРАНИЦЕ
            return self.строки_все[self.стр * н:(self.стр + 1) * н]

        def строк_в_таблице(self):
            return len(self._страница())

        def rows(self):
            out = []
            for ф in self._страница():
                город = f"{ф.город}, {ф.штат}" if ф.штат else ф.город
                out.append(Firm(name=ф.имя, industry=ф.отрасль, country=ф.гео,
                                city=город, zip_code=ф.индекс,
                                url=f"dnb://{ф.гео}/{ф.имя}"))
            return out

        def next_page(self):
            if (self.стр + 1) * МирDnB.НА_СТРАНИЦЕ < len(self.строки_все):
                self.стр += 1
                return True
            return False

        def enrich_website(self, f, code):
            ф = next(x for x in мир.фирмы if f"dnb://{x.гео}/{x.имя}" == f.url)
            город = f"{ф.город}, {ф.штат}" if ф.штат else ф.город
            return Firm(name=ф.имя, industry=ф.отрасль, country=ф.гео,
                        address=ф.улица, city=город, zip_code=ф.индекс,
                        website=ф.сайт, url=f.url,
                        payment_profile=f"{ф.имя}\nAddress: {ф.улица}, {ф.индекс} {ф.город}"
                        + (f"\nWebsite: {ф.сайт}" if ф.сайт else ""))
    return ФейкDnB


class ФейкСтраница:
    url = "about:blank"

    def wait_for_timeout(self, *_): pass
    def inner_text(self, *_): return ""
    def screenshot(self, *_, **__): pass


class ФейкБраузер:
    """Вместо Playwright: контекст-менеджер, у которого всё — тихие заглушки."""
    def __init__(self, *a, **k):
        self.page = ФейкСтраница()

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def __getattr__(self, имя):
        return lambda *a, **k: None


def сделать_драйвер(мир_фирм: list[Фирма], гео: str):
    """Драйвер реестра страны по контракту part2/geos/base.py."""
    from part2.core.matching import Candidate, normalize
    from part2.geos.base import GeoDriver

    class ФейкРеестр(GeoDriver):
        code = гео
        title = f"Реестр {гео} (подставной)"
        method = "download"

        def _моя(self, имя):
            к = normalize(имя)
            for ф in мир_фирм:
                if ф.гео == гео and ф.в_реестре and к and (
                        к in normalize(ф.имя_в_реестре or ф.имя)
                        or к in normalize(ф.имя)):
                    yield ф

        def search(self, c):
            # Сменившую имя фирму реестр показывает с прежним именем (как UK «previous names»).
            return [Candidate(name=ф.имя_в_реестре or ф.имя,
                              address=f"{ф.улица}, {ф.индекс} {ф.город}",
                              ref=ф.номер,
                              aliases=(ф.имя,) if ф.имя_в_реестре else ())
                    for ф in self._моя(c.name)]

        def open(self, cand):
            ф = next(x for x in мир_фирм if x.номер == cand.ref)
            if ф.сбоев_сети > 0:
                ф.сбоев_сети -= 1
                raise TimeoutError("реестр не ответил (подставной таймаут)")
            self.тек = ф

        def check(self, c):
            ф = self.тек
            return (True, "") if ф.статус_ок else (False, "статус: in liquidation")

        def номер(self):
            return getattr(self, "тек", None) and self.тек.номер or ""

        def данные_реестра(self):
            ф = self.тек
            return {"имя": ф.имя_в_реестре or ф.имя,
                    "адрес": f"{ф.улица}, {ф.индекс} {ф.город}"}

        def fetch(self, c, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 " + self.тек.номер.encode())
            return dest
    return ФейкРеестр


def ответ_бота(пакет: list[dict], мир_фирм: list[Фирма]) -> str:
    """Бот Used Companies: «уже есть» для известных команде, «добавлена» для новых."""
    from common.имена import без_формы_ascii
    знает = {без_формы_ascii(ф.имя_в_реестре or ф.имя).lower() for ф in мир_фирм if ф.бот_знает}
    знает |= {без_формы_ascii(ф.имя).lower() for ф in мир_фирм if ф.бот_знает}
    строки = []
    for з in пакет:
        имя = з["для_бота"]
        строки.append(("уже есть: " if имя.lower() in знает else "добавлена: ") + имя)
    return "\n".join(строки)


class ФейкТаблица:
    """Google Таблица владельца (Apps Script) в памяти: листы как списки строк."""
    def __init__(self):
        self.листы: dict[str, list[list[str]]] = {}
        self.записей = 0

    # --- то, что зовёт код владельца ---
    def настроена(self): return True

    def создать(self, гео=None):
        for г in гео or []:
            self.листы.setdefault(г, [])
        return {}

    def читать(self, лист, сколько=50, всё=False):
        return [list(с) for с in self.листы.get(лист, [])]

    def дописать(self, лист, строки, пачка=400):
        from common import раскладка
        л = self.листы.setdefault(лист, [])
        if not л:
            л.append(list(ШАПКА_РЕЕСТРА) if лист == "Реестр" else list(раскладка.КОЛОНКИ))
        for с in строки:
            л.append(["" if v is None else str(v) for v in с])
        self.записей += len(строки)
        return len(строки)

    def всё(self, листы=None, служебные=False, **_):
        return [{"имя": и, "скрыт": False, "строк": max(0, len(с) - 1),
                 "строки": [list(x) for x in с]}
                for и, с in self.листы.items()
                if (листы is None or и in листы) and (служебные or и not in ("Реестр",))]

    def _найти(self, лист, орг, ид):
        с = self.листы.get(лист) or []
        if not с:
            return None, None
        ш = с[0]
        for стр in с[1:]:
            if (ид and "ID" in ш and стр[ш.index("ID")] == ид) or \
               (стр[ш.index("Организация")] == орг):
                return ш, стр
        return ш, None

    def обновить(self, правки, пачка=150):
        n = 0
        for п in правки:
            ш, стр = self._найти(п["лист"], п.get("орг", ""), п.get("ид", ""))
            if стр is None:
                continue
            for к, v in (п.get("поля") or {}).items():
                if к not in ш:
                    ш.append(к)
                    for x in self.листы[п["лист"]][1:]:
                        x.append("")
                стр[ш.index(к)] = str(v)
            n += 1
        return {"обновлено": n}

    def перенести(self, куда, ид, пачка=200):
        n = 0
        цель = self.листы.setdefault(куда, [])
        for имя, с in list(self.листы.items()):
            if имя == куда or not с or "ID" not in с[0]:
                continue
            i = с[0].index("ID")
            остались = [с[0]]
            for стр in с[1:]:
                if стр[i] in ид:
                    if not цель:
                        цель.append(list(с[0]))
                    цель.append(стр)
                    n += 1
                else:
                    остались.append(стр)
            self.листы[имя] = остались
        return {"перенесено": n}

    def отработать(self, отметки, дата="", пачка=200):
        n = 0
        for о in отметки:
            ш, стр = self._найти(о["лист"], о.get("орг", ""), о.get("ид", ""))
            if стр is not None and "Статус" in ш:
                стр[ш.index("Статус")] = "отработано"
                n += 1
        return {"помечено": n}

    # --- для проверок сценария ---
    def строки_листа(self, лист) -> list[dict]:
        с = self.листы.get(лист) or []
        if not с:
            return []
        return [dict(zip(с[0], стр)) for стр in с[1:]]


ШАПКА_РЕЕСТРА = ["Ключ", "Гео", "Организация", "Статус", "Дата", "Слово", "Откуда", "ID"]


class Робот:
    """
    Человек у окна. автономно=True — отвечает то, что назвал движок (как окно владельца в режиме «Автономно»).
    Иначе — по сценарию: ответы[заголовок] = ключ кнопки; нет в сценарии — тоже авто.
    """
    def __init__(self, автономно=True, ответы: dict | None = None):
        from common.human import HumanChoice, HumanGate
        self.вопросы: list[str] = []
        self.g = HumanGate()
        self.g.ui_menu = self._меню
        self.g.ui_ask = self._спросить
        self.g.ui_keyword = lambda msg: self.g.answer_keyword("")
        self.автономно = автономно
        self.ответы = ответы or {}
        self._HC = HumanChoice

    def _меню(self, заголовок, сообщение, варианты, фирма=""):
        self.вопросы.append(заголовок)
        ключ = self.ответы.get(заголовок) if not self.автономно else None
        self.g.answer_menu(ключ or self.g.авто or "")

    def _спросить(self, заголовок, сообщение, фирма=""):
        self.вопросы.append(заголовок)
        self.g.answer(self._HC.SKIP)


def нормально(текст: str) -> str:
    return re.sub(r"\s+", " ", (текст or "")).strip()
