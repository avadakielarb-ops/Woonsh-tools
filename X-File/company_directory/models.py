""
from dataclasses import dataclass
@dataclass
class Firm:
    ""
    name: str
    industry: str = ""
    location_type: str = ""
    country: str = ""
    address: str = ""
    city: str = ""
    zip_code: str = ""
    state: str = ""
    website: str = ""
    url: str = ""
    payment_profile: str = ""
    слово: str = ""
@dataclass
class Rejected:
    ""
    name: str
    industry: str
    website: str
    reason: str
