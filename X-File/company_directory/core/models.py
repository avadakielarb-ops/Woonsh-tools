""""""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

@dataclass
class Company:
    """"""
    row: int
    name: str
    address: str = ''
    city: str = ''
    zip_code: str = ''
    website: str = ''
    extra: dict = field(default_factory=dict)

class Status(str, Enum):
    OK = 'ok'
    NOT_FOUND = 'not_found'
    AMBIGUOUS = 'ambiguous'
    INACTIVE = 'inactive'
    SKIPPED = 'skipped'
    ERROR = 'error'

@dataclass
class Result:
    """"""
    company: Company
    status: Status
    file_path: Optional[str] = None
    final_name: str = ''
    reason: str = ''
    human_steps: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)
