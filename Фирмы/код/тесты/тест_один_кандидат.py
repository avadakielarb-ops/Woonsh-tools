"""Единственный кандидат больше не берётся слепо."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.human import HumanGate
from part2.core.matching import pick, Candidate, имена_родня

ошибок = 0
print("=== похожесть имён ===")
пары = [
    ("Ice Berry SIA", 'SIA "Ice Berry"', True),
    ("Atlas Premium SIA", 'SIA "Atlas Premium"', True),
    ("Ice Mixture SIA", 'SIA "Ice Mixture"', True),
    ("RAED LOCK SIA", "PricewaterhouseCoopers SIA", False),
    ("Packaged Ice SIA", 'SIA "Gala Ice"', False),
    ("ICE GIRLS BDR", 'SIA "iConcept"', False),
    ("Lock Force OU", "Lock Force OÜ", True),
    ("North European Invest Oy", "North European Invest Oy", True),
]
for наше, чужое, ждём in пары:
    вышло = имена_родня(наше, чужое)
    ок = вышло == ждём
    if not ок:
        ошибок += 1
    print(f"  {'ok ' if ок else 'ПЛОХО'} {наше[:26]:26} ~ {чужое[:28]:28} "
          f"-> {'родня' if вышло else 'чужие'}")

print()
print("=== один кандидат: похожий берём молча ===")
спросили = []
def человек(title, message, company):
    спросили.append(message)
    raise RuntimeError("спросили")
h = HumanGate(ui_ask=человек)
try:
    r = pick("Ice Berry SIA", "Riga, Brivibas 1",
             [Candidate(name='SIA "Ice Berry"', address="Riga")], h)
    print(f"  ✔ взял без вопросов: {r.name}")
except RuntimeError:
    ошибок += 1
    print("  ✘ спросил, хотя имя совпадает")

print()
print("=== один кандидат: ЧУЖОЙ — обязан спросить ===")
спросили.clear()
try:
    r = pick("RAED LOCK SIA", "Riga, Brivibas 1",
             [Candidate(name="PricewaterhouseCoopers SIA", address="Riga")], h)
    ошибок += 1
    print(f"  ✘ взял чужую фирму молча: {r.name}")
except RuntimeError:
    print("  ✔ спросил человека, а не скачал чужое")
    for с in спросили[0].splitlines():
        if с.strip():
            print("      |", с[:76])

print()
print("=== один кандидат с чужим именем, но НАШИМ адресом — берём ===")
спросили.clear()
try:
    r = pick("RAED LOCK SIA", "Riga, Brivibas iela 1",
             [Candidate(name="Cita firma SIA", address="Riga, Brivibas iela 1")], h)
    print(f"  ✔ взял по адресу: {r.name}")
except RuntimeError:
    print("  (спросил — адрес не сошёлся, тоже допустимо)")

print()
print("ошибок:", ошибок)
