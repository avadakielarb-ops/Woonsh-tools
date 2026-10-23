""""""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from company_directory.browser import Browser
from company_directory.browser import HumanGate
from company_directory.core.matching import Candidate
from company_directory.core.models import Company

class GeoDriver(ABC):
    @property
    def page(self):
        return self.br.page
    code: str = ''
    title: str = ''
    url: str = ''
    method: str = 'download'
    log = staticmethod(print)

    def __init__(self, br: Browser, human: HumanGate):
        self.br = br
        self.human = human
        self.log = print

    @property
    def page(self):
        """"""
        return self.br.page

    @abstractmethod
    def search(self, c: Company) -> list[Candidate]:
        """"""

    @abstractmethod
    def open(self, cand: Candidate) -> None:
        """"""

    def check(self, c: Company) -> tuple[bool, str]:
        """"""
        return (True, '')

    @abstractmethod
    def fetch(self, c: Company, dest: Path) -> Path:
        raise RuntimeError('Этот модуль перенесён только для поиска. Создание документов отключено.')
    номер_regex: str = '\\b(\\d[\\d\\s./-]{5,})\\b'

    def номер(self) -> str:
        """"""
        import re
        try:
            m = re.search(self.номер_regex, self.page.inner_text('body'))
            return m.group(1).strip() if m else ''
        except Exception:
            return ''

    def данные_реестра(self) -> dict:
        """"""
        return {}

    def следующая_страница(self) -> bool:
        """"""
        return False

    def кандидаты_страницы(self) -> list:
        """"""
        return []
