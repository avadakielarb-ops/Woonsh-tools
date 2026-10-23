"""Структуры Части 1."""
from dataclasses import dataclass


@dataclass
class Firm:
    """Фирма, снятая с DnB."""
    name: str                # ПОЛНОЕ имя как на карточке DnB (без обрезки)
    industry: str = ""       # видно в таблице выдачи, до открытия карточки
    location_type: str = ""  # Independent / Subsidiary ...
    country: str = ""
    address: str = ""        # улица
    city: str = ""
    zip_code: str = ""
    state: str = ""          # штат — только US/AU
    website: str = ""
    url: str = ""            # ссылка на карточку DnB
    payment_profile: str = ""  # колонка B: имя + Address: + Website:
    # ПО КАКОМУ СЛОВУ НАЙДЕНА. Едет вместе с фирмой, а не берётся из состояния
    # писаря: в реестровой линии один прогон перебирает несколько слов подряд,
    # и «текущее слово» к моменту записи уже другое.
    слово: str = ""


@dataclass
class Rejected:
    """Отсеянная фирма — уходит в лист «Лог»."""
    name: str
    industry: str
    website: str
    reason: str
