""
from __future__ import annotations

import re
import unicodedata


ДЛИННЫЕ = (r"SPO[LŁ]KA\s+Z\s+OGRANICZON[AĄ]\s+ODPOWIEDZIALNO[SŚ]CI[AĄ]|"
           r"KORLATOLT\s+FELELOSSEGU\s+TARSASAG|"
           r"GESELLSCHAFT\s+MIT\s+BESCHRANKTER\s+HAFTUNG|"
           r"MITTETULUNDUS[UÜ]HING|OSA[UÜ]HING|AKTSIASELTS|"
           r"SPOLKA\s+AKCYJNA|AKTIENGESELLSCHAFT")

ФОРМЫ = (r"O[UÜ]|MT[UÜ]|AS|SIA|UAB|SP\.?\s*Z\s*O\.?\s*O\.?|"
         r"S\.?R\.?O\.?|A\.?S\.?|D\.?O\.?O\.?|KFT|ZRT|BT|GMBH|AG|BV|NV|"
         r"SARL|SAS|S\.?A\.?|S\.?P\.?|LTD|LIMITED|PLC|LLC|INC|APS|OY|AB|"
         r"EOOD|OOD|PTY")


def без_формы(имя: str) -> str:
    ""
    т = имя or ""
    т = re.sub(rf"(?i)(^|\s){ДЛИННЫЕ}(\s|$)", " ", т)
    было = None
    while было != т:
        было = т
        т = re.sub(rf"(?i)(^|\s)(?:{ФОРМЫ})\.?(?=\s|$)", " ", т)
                                                                                
    return re.sub(r"\s+", " ", т).strip(" .,«»\"'")


def без_формы_ascii(имя: str) -> str:
    ""
    т = unicodedata.normalize("NFKD", имя or "")
    т = "".join(c for c in т if not unicodedata.combining(c))
    for a, b in (("ł", "l"), ("Ł", "L"), ("ø", "o"), ("đ", "d"), ("ß", "ss")):
        т = т.replace(a, b)
    т = re.sub(rf"(?i)(^|\s){ДЛИННЫЕ}(\s|$)", " ", т)
    было = None
    while было != т:
        было = т
        т = re.sub(rf"(?i)(^|\s)(?:{ФОРМЫ})\.?(?=\s|$)", " ", т)
    return re.sub(r"\s+", " ", т).strip(" .,")
