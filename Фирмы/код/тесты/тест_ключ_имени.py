"""
Один ключ имени и один выбор фирмы — без противоречий между копиями.

До 20.10.2026 правил было по нескольку на каждый вопрос, и они спорили.
Здесь — ровно те пары, на которых спор был доказан на живых данных:

  · «Osaühing AA Aqua» искалось как «AA Aqua», а сравнивалось как
    «osauhing aa aqua» — найденная фирма не совпадала сама с собой;
  · «BALTIC MTÜ» → запрос «BALTIC», сравнение «baltic mtu»;
  · обратный апостроф, «’», «&», «+» давали разные ключи одному имени;
  · пустой адрес считался «похожим» — фирма «подтверждалась» адресом,
    которого никто не видел;
  · британская фирма с точным уникальным именем отклонялась из-за адреса
    бухгалтера в DnB.

И главное: `normalize` — ключ ХРАНЕНИЯ — не меняется ни на букву.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.имена import без_формы, без_формы_ascii, ключ_имени
from part2.core.matching import Candidate, адрес_сходится, normalize, выбрать

ошибок = 0


def проверить(что, вышло, ждём):
    global ошибок
    ладно = вышло == ждём
    ошибок += not ладно
    print(f"   {'✔' if ладно else '✘'} {что}"
          + ("" if ладно else f": вышло {вышло!r}, ждали {ждём!r}"))


print("=== 1. ОДНА ФИРМА — ОДИН КЛЮЧ ===")
for а, б in [('SIA "AQUA-360"', "Aqua-360 SIA"),
             ("Osaühing AA Aqua", "AA AQUA OU"),
             ("MARK`S PLUMBING LTD", "Mark’s Plumbing Ltd"),
             ("MARK'S PLUMBING LTD", "MARK`S PLUMBING LIMITED"),
             ("A&B BUILD PTY. LTD.", "A and B Build Pty Ltd"),
             ("A+B BUILD", "A & B BUILD"),
             ("AH S.Lindén", "Ah S. Linden"),
             ("ICE CODE GAMES S A", "ICE CODE GAMES SPÓŁKA AKCYJNA"),
             ("Bau-Pro, s.r.o.", "BAU PRO SRO"),
             ("NAME (NAME)", "NAME")]:
    проверить(f"{а} = {б}", ключ_имени(а), ключ_имени(б))

print()
print("=== 2. ФОРМА — ТОЛЬКО С КРАЁВ, И НЕ ВСЁ ИМЯ ===")
проверить("форма в середине остаётся", ключ_имени("BALTIC AS GROUP"), "baltic as group")
проверить("имя из одной формы не пустеет", ключ_имени("OU"), "ou")
# «AD» спереди — не форма: «AD ASTRA» не должно искаться как «ASTRA».
проверить("спереди режем только настоящие передние формы",
          без_формы("AD ASTRA OÜ"), "AD ASTRA")

print()
print("=== 3. ЗАПРОС И СРАВНЕНИЕ РЕЖУТ ОДНО И ТО ЖЕ ===")
for имя in ("Osaühing AA Aqua", "BALTIC MTÜ", 'SIA "AQUA-360"',
            "TEST Sp. z o.o.", "Novák spol. s r.o."):
    проверить(f"«{имя}»: ключ запроса = ключ имени",
              ключ_имени(без_формы(имя)), ключ_имени(имя))
проверить("буквы в запросе свои", без_формы("Ķieģelis SIA"), "Ķieģelis")

print()
print("=== 4. АДРЕС: ТРИ ОТВЕТА, И ПУСТОЙ — «НЕ ЗНАЕМ» ===")
проверить("пустой у них", адрес_сходится("Kortrijkstraat 26", ""), None)
проверить("пустой у нас", адрес_сходится("", "Kortrijkstraat 26 2140 Antwerpen"), None)
проверить("сходится", адрес_сходится("Vilandes iela 13 Riga LV-1010",
                                     "Rīga, Vīlandes iela 13 - 5"), True)
проверить("спорит", адрес_сходится("Rue de la Dreve 44 6600 Bastogne",
                                   "Gerzevien 23 3150 Haacht"), False)
проверить("индекс решает", адрес_сходится("X", "Brisbane 4122 QLD", "4122"), True)

print()
print("=== 5. ВЫБОР: ИМЯ ГЛАВНОЕ, АДРЕС ВТОРОСТЕПЕННЫЙ ===")
k, _ = выбрать(["BRONZE WING TRADING LTD"], "12 High Street Leeds", "LS1 4AP",
               [Candidate("BRONZE WING TRADING LIMITED", "Quayside Newcastle NE1 3DX")])
проверить("UK: точное многословное имя берём при чужом адресе DnB",
          k and k.name, "BRONZE WING TRADING LIMITED")
k, _ = выбрать(["ICE SA"], "Rue de la Dreve 44 6600 Bastogne", "6600",
               [Candidate("ICE", "Gerzevien 23 3150 Haacht")])
проверить("одно слово + спорный адрес — к человеку", k, None)
k, _ = выбрать(["A.L Timber Components OU", "A.L. Timber Components OÜ"], "", "",
               [Candidate("A.L. Timber Components OÜ", "Tallinn")])
проверить("совпало с написанием от модели", k and k.name, "A.L. Timber Components OÜ")
# ОДНА КАРТОЧКА — НЕ «ПУСТО»: единственная похожая фирма в выдаче — она.
k, почему = выбрать(["Aqua Team OU"], "", "", [Candidate("Aqua Team Services OÜ", "")])
проверить("одна похожая фирма в выдаче — берём", k and k.name, "Aqua Team Services OÜ")
k, _ = выбрать(["ICE OU"], "", "", [Candidate("ICE CREAM OÜ", "")])
проверить("но не для имени из одного слова", k, None)
k, _ = выбрать(["Aqua Team OU"], "", "",
               [Candidate("Aqua Team Services OÜ", ""), Candidate("Aqua Teamwork OÜ", "")])
проверить("похожих двое — не угадываем", k, None)
k, _ = выбрать(["CAMAYA"], "LA COUARDIERE 2 RUE SAINT ROCH 56800", "56800",
               [Candidate("CAMAYA (ASV AGENCE MARKETING)",
                          "LA COUARDIERE 2 RUE SAINT ROCH 56800 PLOERMEL"),
                Candidate("CAMAYA", "06200 NICE")])
# Наш адрес — у «CAMAYA (ASV …)», но имя у неё другое: адрес её не выбирает.
# А точная «CAMAYA» — имя из одного слова с чужим адресом: тоже не берём.
проверить("адрес не выбирает фирму с другим именем — человек", k, None)
k, _ = выбрать(["AQUA FABRICATIONS LIMITED"], "", "",
               [Candidate("AQUA FABRICATIONS LIMITED", "", aliases=("AQUA SIGNAL LTD",)),
                Candidate("AQUA SIGNAL LTD", "", aliases=("AQUA FABRICATIONS LIMITED",))])
проверить("текущее имя важнее прежнего", k and k.name, "AQUA FABRICATIONS LIMITED")

print()
print("=== 5б. AU: «СЛОВО В СЛОВО, А НЕ ВЫБРАЛ» ===")
# Живой ABR 20.10.2026: рядом с нашей фирмой — чужое торговое имя без формы
# с другим ABN. Без формы ключи равны; решает имя вместе с формой.
k, почему = выбрать(["ANVIL ADVISORY PTY LTD"], "", "",
                    [Candidate("ANVIL ADVISORY PTY LTD", "4123 QLD", ref="72691528328"),
                     Candidate("Anvil Advisory", "4123 QLD", ref="87249386925"),
                     Candidate("ANVIL ADVISORY GROUP PTY LTD", "2560 NSW", ref="99690928682")])
проверить("взяли фирму с той же формой", k and k.ref, "72691528328")
k, _ = выбрать(["ANVIL ELECTRONICS PTY. LTD."], "", "",
               [Candidate("ANVIL ELECTRONICS PTY. LTD.", "5290 SA", ref="67076003533"),
                Candidate("ANVIL ELECTRONICS", "5290 SA", ref="31282421525")])
проверить("точки в форме не мешают", k and k.ref, "67076003533")
# Одна фирма двумя строками (Entity и Business Name, один ABN) — не тёзки.
k, _ = выбрать(["ACACIA RIDGE DOCTORS"], "", "",
               [Candidate("ACACIA RIDGE DOCTORS", "4110 QLD", ref="35362929392"),
                Candidate("ACACIA RIDGE DOCTORS", "4110 QLD", ref="35362929392")])
проверить("один ABN дважды — одна фирма", k and k.ref, "35362929392")

print()
print("=== 5в. ОБРЕЗАННОЕ DnB ИМЯ («...») ===")
from common.имена import без_обреза
проверить("многоточие и огрызок слова долой",
          без_обреза("A D T MARMUR I GRANIT S C JANISZEWSKI DA..."),
          "A D T MARMUR I GRANIT S C JANISZEWSKI")
проверить("необрезанное не трогаем", без_обреза("AQUA SIA"), "AQUA SIA")
k, почему = выбрать(["ICE CUBE LOGISTICS ZARTKORUEN MUKODO RESZVENY..."], "", "",
                    [Candidate("ICE CUBE LOGISTICS ZÁRTKÖRŰEN MŰKÖDŐ RÉSZVÉNYTÁRSASÁG", "")])
проверить("совпало по началу", k and почему, "имя обрезано, совпало начало")

print()
print("=== 6. КЛЮЧИ ХРАНЕНИЯ НЕ ТРОНУТЫ ===")
# По ним записаны журнал бота, отпечатки и «Реестр»: другой ответ — и всё
# записанное станет «новым».
проверить("normalize как был", normalize("ICE CODE GAMES S.A."), "ice code games")
проверить("normalize режет форму и в середине, как раньше",
          normalize("BALTIC AS GROUP"), "baltic group")
проверить("имя для бота как было",
          без_формы_ascii("ADELAIDE MARBLE SPECIALISTS PTY LTD"),
          "ADELAIDE MARBLE SPECIALISTS")

print()
print("ошибок:", ошибок)
sys.exit(1 if ошибок else 0)
