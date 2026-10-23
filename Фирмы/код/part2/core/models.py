"""Базовые структуры данных Части 2."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


@dataclass
class Company:
    """Одна фирма из Excel-таблицы Части 1."""
    row: int                 # номер строки в Excel (для отчёта)
    name: str                # Название
    address: str = ""        # Адрес
    city: str = ""
    zip_code: str = ""
    website: str = ""
    extra: dict = field(default_factory=dict)  # гео-данные (BG: bg_name/bg_addr)


class Status(str, Enum):
    OK = "ok"                      # выписка скачана
    NOT_FOUND = "not_found"        # фирма не найдена в реестре
    AMBIGUOUS = "ambiguous"        # несколько кандидатов, человек не выбрал
    INACTIVE = "inactive"          # фирма неактивна / не прошла проверку статуса
    SKIPPED = "skipped"            # человек нажал "Пропустить"
    ERROR = "error"                # техническая ошибка (таймаут, сайт лёг и т.п.)


@dataclass
class Result:
    """Итог обработки одной фирмы."""
    company: Company
    status: Status
    file_path: Optional[str] = None   # путь к сохранённому PDF
    final_name: str = ""              # имя, под которым фирма записана в реестре
                                      # (может отличаться от исходного — см. UK)
    reason: str = ""                  # человекочитаемая причина неудачи
    human_steps: list = field(default_factory=list)  # какие ручные шаги понадобились
    extra: dict = field(default_factory=dict)  # доп-поля гео (FR: siren/siret)
