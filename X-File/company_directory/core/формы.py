""""""
from __future__ import annotations
import unicodedata
ЗАПРЕЩЁННЫЕ_ФОРМЫ: dict[str, tuple[str, ...]] = {'UK': ('community interest company', 'limited by guarantee', 'dormant', 'charitable incorporated'), 'CH': ('verein', 'stiftung', 'genossenschaft', 'association', 'foundation', 'cooperative'), 'FR': ('association', 'societe civile', 'sci', 'snc', 'societe en nom collectif'), 'PL': ('fundacja', 'stowarzyszenie', 'spoldzielnia'), 'SE': ('ideell forening', 'stiftelse', 'forening'), 'LV': ('biedriba', 'nodibinajums'), 'EE': ('mtu', 'sihtasutus', 'foundation'), 'AU': ('incorporated association', 'trust', 'deregistered'), 'DK': ('fond', 'forening'), 'CZ': ('z.s.', 'o.p.s.', 'druzstvo', 'spolek'), 'FI': ('yhdistys', 'saatio', 'association', 'foundation'), 'BE': ('asbl', 'vzw', 'stichting'), 'BG': ('fondaciya', 'sdruzhenie', 'фондация', 'сдружение'), 'HU': ('egyesulet', 'alapitvany'), 'HR': ('udruga', 'zadruga'), 'NO': ('stiftelse', 'forening'), 'DE': ('e.v.', 'stiftung'), 'NL': ('stichting', 'vereniging'), 'AT': ('verein', 'stiftung'), 'SI': ('drustvo', 'zavod', 'zadruga'), 'US': ('nonprofit', 'non-profit', 'cooperative')}
ЗАПРЕЩЁННЫЕ_СТАТУСЫ: tuple[str, ...] = ('likvidac', 'likwidac', 'liquidation', 'liquidat', 'upadlo', 'konkurs', 'konkurssi', 'insolven', 'insolvenz', 'bankrupt', 'dissolved', 'deregistered', 'radiee', 'felszamol', 'likvideerimisel', 'faillissement', 'faillite', 'opholrt', 'ophort', 'ceased')

def _фолд(s: str) -> str:
    """"""
    s = unicodedata.normalize('NFKD', (s or '').lower())
    s = ''.join((c for c in s if not unicodedata.combining(c)))
    for a, b in (('ł', 'l'), ('ø', 'o'), ('đ', 'd'), ('ß', 'ss')):
        s = s.replace(a, b)
    return s

def проверить_форму(geo: str, форма: str) -> str:
    """"""
    ф = _фолд(форма)
    if not ф:
        return ''
    for стоп in ЗАПРЕЩЁННЫЕ_ФОРМЫ.get((geo or '').upper(), ()):
        if _фолд(стоп) in ф:
            return f'форма не подходит для Google Ads: {форма.strip()}'
    return ''

def проверить_статус(статус: str) -> str:
    """"""
    с = _фолд(статус)
    if not с:
        return ''
    for стоп in ЗАПРЕЩЁННЫЕ_СТАТУСЫ:
        if стоп in с:
            return f'статус-стоп: {статус.strip()}'
    return ''
