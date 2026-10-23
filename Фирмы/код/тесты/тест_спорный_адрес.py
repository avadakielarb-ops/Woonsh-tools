"""
Уникальное совпадение ИМЕНИ ИЗ ОДНОГО СЛОВА не принимается, если адрес
прямо противоречит. А многословное имя адрес не отклоняет.

Живой случай: у нас «ICE SA», Rue de la Drève 44, 6600 Bastogne. В бельгийском
реестре ровно одна фирма «ICE» — но в Haacht. Имя совпало, и мы молча скачали
чужую выписку. Короткие имена собирают тёзок по всей стране.

Но правило пользователя 20.10.2026: «адрес с dnb может не биться с адресом
фирмы по выписке, а мы ориентируемся на выписку». DnB держит адрес
бухгалтера или старого офиса — и британская фирма с точным уникальным именем
из трёх слов отклонялась из-за него. Поэтому вето адреса — только для имён из
одного слова.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part2.core.matching import Candidate, токены_адреса
from part2.core.models import Company
import part2.engine as д2

ошибок = 0

print("=== 1. Диакритика в адресе не мешает ===")
ПАРЫ = [
    ("Jarve moisaallee 1 30331 Jarve kula",
     "Ida-Viru maakond, Jõhvi vald, Järve küla, Järve mõisaallee 1", True),
    ("Ulica Frana Galovica 29A Krizevci",
     "Križevci (Grad Križevci), Ulica Frana Galovića 29A", True),
    ("Rue de la Dreve 44 6600 Bastogne", "Gerzevien 23 3150 Haacht", False),
]
for наш, чужой, ждём in ПАРЫ:
    общие = токены_адреса(наш) & токены_адреса(чужой)
    факт = bool(общие)
    знак = "✔" if факт == ждём else "✘"
    if факт != ждём:
        ошибок += 1
    print(f"   {знак} {наш[:34]:34} ~ {чужой[:34]:34} общих: {sorted(общие)[:3]}")

print()
print("=== 2. Бельгия: чужой адрес — берём НЕ вслепую ===")
c = Company(row=0, name="ICE SA", address="Rue de la Drève 44",
            city="Bastogne", zip_code="6600", website="")
адрес1 = "Rue de la Drève 44 6600 Bastogne"
чужая = Candidate(name="ICE", address="Gerzevien 23 3150 Haacht", ref="1")
выбор = д2._подобрать(c, адрес1, [чужая])
if выбор is not None:
    ошибок += 1
    print(f"   ✘ взял чужую вслепую: {выбор.name} — {выбор.address}")
else:
    print("   ✔ не взял: имя совпало, но адрес спорит → решает человек")

print()
print("=== 3. Та же фирма по НУЖНОМУ адресу — берём ===")
своя = Candidate(name="ICE", address="Rue de la Drève 44 6600 Bastogne", ref="2")
выбор = д2._подобрать(c, адрес1, [своя])
if выбор is None or выбор.ref != "2":
    ошибок += 1
    print("   ✘ не взял свою же фирму:", выбор)
else:
    print("   ✔ взял:", выбор.address)

print()
print("=== 4. Скудный адрес (только город) спором НЕ считается ===")
c2 = Company(row=0, name="North European Invest Oy", address="Kirkkotie 1",
             city="Muonio", zip_code="99300", website="")
только_город = Candidate(name="North European Invest Oy", address="Muonio", ref="3")
выбор = д2._подобрать(c2, "Kirkkotie 1 99300 Muonio", [только_город])
if выбор is None:
    ошибок += 1
    print("   ✘ забраковал из-за короткого адреса реестра")
else:
    print("   ✔ взял:", выбор.name)

print()
print("=== 5. Наш индекс в адресе кандидата снимает подозрение ===")
c3 = Company(row=0, name="Star Register SIA", address="Brivibas iela 1",
             city="Riga", zip_code="LV-1010", website="")
инойформат = Candidate(name="Star Register SIA",
                       address="Riga, Kr. Valdemara 21, LV-1010", ref="4")
выбор = д2._подобрать(c3, "Brivibas iela 1 LV-1010 Riga", [инойформат])
if выбор is None:
    ошибок += 1
    print("   ✘ забраковал, хотя индекс совпал")
else:
    print("   ✔ взял по совпавшему индексу")

print()
print("=== 6. Многословное точное имя адрес НЕ отклоняет ===")
# UK, живой разбор 19.10: в DnB адрес бухгалтера, в реестре — юридический.
c4 = Company(row=0, name="BRONZE WING TRADING LTD", address="12 High Street",
             city="Leeds", zip_code="LS1 4AP", website="")
бухгалтер = Candidate(name="BRONZE WING TRADING LIMITED",
                      address="Unit 5 Quayside, Newcastle NE1 3DX", ref="5")
выбор = д2._подобрать(c4, "12 High Street LS1 4AP Leeds", [бухгалтер])
if выбор is None:
    ошибок += 1
    print("   ✘ отклонил точное имя из-за адреса DnB")
else:
    print("   ✔ взял: правда за реестром")

print()
print("ошибок:", ошибок)
