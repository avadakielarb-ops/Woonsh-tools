""""""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from company_directory.browser import HumanGate
LEGAL_FORMS = ['ltd', 'limited', 'plc', 'llc', 'inc', 'corp', 'pty', 'gmbh', 'ag', 'kg', 'ohg', 'ug', 'sarl', 'sas', 'sa', 'eurl', 'bv', 'b.v.', 'nv', 'n.v.', 'ab', 'as', 'a/s', 'aps', 'oy', 'oyj', 'sp. z o.o.', 'spzoo', 'sro', 's.r.o.', 'a.s.', 'kft', 'zrt', 'bt', 'd.o.o.', 'doo', 'd.d.', 'sia', 'ou', 'oü', 'as', 'srl', 'spa', 's.p.a.', 'spolka z ograniczona odpowiedzialnoscia', 'spolka komandytowo akcyjna', 'spolka komandytowa', 'spolka akcyjna', 'spolka jawna', 'spolka cywilna', 'spolka partnerska', 'spolka', 'sabiedriba ar ierobezotu atbildibu', 'akciju sabiedriba', 'sp z o o', 's r o', 'd o o', 's p a', 'b v', 'n v', 's a', 'a s', 's c', 's k a', 's k', 's j', 's p']

def normalize(name: str) -> str:
    """"""
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join((c for c in s if not unicodedata.combining(c)))
    s = s.lower()
    for a, b in (('ł', 'l'), ('ø', 'o'), ('đ', 'd'), ('ð', 'd'), ('ħ', 'h'), ('ß', 'ss')):
        s = s.replace(a, b)
    s = re.sub('[.,\\"\'()\\-/]', ' ', s)
    s = re.sub('\\s+', ' ', s).strip()
    for form in sorted(LEGAL_FORMS, key=len, reverse=True):
        s = re.sub(f'(^|\\s){re.escape(form)}(\\s|$)', ' ', s)
    s = re.sub('\\s+', ' ', s).strip()
    сл = s.split()
    полов = len(сл) // 2
    if полов and сл[:полов] == сл[полов:]:
        s = ' '.join(сл[:полов])
    return s

def address_tokens(addr: str) -> set[str]:
    s = (addr or '').lower()
    s = re.sub('[^\\w\\s]', ' ', s)
    return {t for t in s.split() if len(t) > 2}

def address_match(ours: str, theirs: str) -> bool:
    """"""
    a, b = (address_tokens(ours), address_tokens(theirs))
    if not a or not b:
        return False
    return len(a & b) >= 2

def адрес_похож(часть1: str, реестр: str) -> bool:
    """"""

    def токены(s: str) -> set[str]:
        s = re.sub('[^\\w\\s]', ' ', (s or '').lower())
        return {t for t in s.split() if len(t) >= 2}
    p, r = (токены(часть1), токены(реестр))
    if not p or not r:
        return True
    return len(p - r) <= 1

@dataclass
class Candidate:
    """"""
    name: str
    address: str = ''
    url: str = ''
    ref: object = None
    aliases: tuple = ()

def имена_родня(наше: str, чужое: str) -> bool:
    """"""
    a = set(normalize(наше).split())
    b = set(normalize(чужое).split())
    if not a or not b:
        return False
    общие = a & b
    if not общие:
        return False
    меньшее = min(len(a), len(b))
    порог = (меньшее + 2) // 2
    return len(общие) >= порог

def pick(ours_name: str, ours_addr: str, candidates: list[Candidate], human: HumanGate) -> Candidate:
    """"""
    if not candidates:
        raise LookupError('в реестре ничего не найдено')
    if len(candidates) == 1:
        один = candidates[0]
        if имена_родня(ours_name, один.name) or address_match(ours_addr, один.address):
            return один
        human.choose(ours_name, [f"{один.name} — {один.address or '(адрес не показан)'}" + '   ← имя не похоже на наше'], наш_адрес=ours_addr)
        return Candidate(name=ours_name, address=ours_addr, ref='HUMAN')
    target = normalize(ours_name)
    exact = [c for c in candidates if normalize(c.name) == target]
    if len(exact) == 1:
        return exact[0]
    pool = exact or candidates
    by_addr = [c for c in pool if address_match(ours_addr, c.address)]
    if len(by_addr) == 1:
        return by_addr[0]
    human.choose(ours_name, [f"{c.name} — {c.address or '(адрес не показан в выдаче)'}" for c in pool], наш_адрес=ours_addr)
    return Candidate(name=ours_name, address=ours_addr, ref='HUMAN')
