"""
Буфер слов: выданное не возвращается, повтор даёт другое, файл переживает
перезапуск. Без сети — Gemini здесь не участвует.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part1.запас import Запас
from part1 import слова as словарь

ошибок = 0
врем = Path("запас_тест.json")
врем.unlink(missing_ok=True)
Path("запас_тест.tmp").unlink(missing_ok=True)

з = Запас(path=врем)
print("=== 1. Пополнение и дедуп ===")
n1 = з.пополнить("PL", ["jaspis", "kwarc", "ametyst", "szafir"])
n2 = з.пополнить("PL", ["kwarc", "szafir", "rubin"])      # два уже есть
print(f"   первый раз: +{n1}, второй: +{n2} (ждём 4 и 1)")
if (n1, n2) != (4, 1):
    ошибок += 1
    print("   ✘ дедуп при пополнении не работает")
else:
    print("   ✔")

print()
print("=== 2. Выданное не выдаётся снова ===")
a = з.взять("PL", 2)
b = з.взять("PL", 2)
print(f"   первая выдача: {a}")
print(f"   вторая выдача: {b}")
if set(a) & set(b):
    ошибок += 1
    print("   ✘ выдал одно и то же дважды")
else:
    print("   ✔ пересечений нет")

print()
print("=== 3. Файл переживает перезапуск ===")
з2 = Запас(path=врем)
осталось = з2.свободно("PL")
print(f"   свободно после перезапуска: {осталось} (ждём 1)")
if осталось != 1:
    ошибок += 1
    print("   ✘ состояние не сохранилось")
else:
    print("   ✔")

print()
print("=== 4. Буфер имеет приоритет над встроенным словарём ===")
з2.пополнить("EE", ["kadakas", "pistrik", "kobras"])
выдача = словарь.предложить("EE", 3, [], буфер=з2)
if set(x.lower() for x in выдача) != {"kadakas", "pistrik", "kobras"}:
    ошибок += 1
    print("   ✘ взял не из буфера:", выдача)
else:
    print("   ✔ взял из буфера:", выдача)

print()
print("=== 5. Буфер кончился — переходим на встроенный словарь ===")
ещё = словарь.предложить("EE", 3, [], буфер=з2)
если_из_словаря = all(any(x in слова for слова in словарь.СЛОВАРЬ.values())
                      for x in ещё)
print(f"   {ещё}")
if not ещё or not если_из_словаря:
    ошибок += 1
    print("   ✘ не подхватил встроенный словарь")
else:
    print("   ✔ подхватил встроенный словарь")

print()
print("=== 6. Битый файл не роняет прогон ===")
битый = Path("запас_битый.json")
битый.write_text("{это не json", encoding="utf-8")
строки = []
з3 = Запас(path=битый, log=строки.append)
if з3.данные != {}:
    ошибок += 1
    print("   ✘ не начал с пустого")
else:
    print("   ✔ начал с пустого:", (строки[0] if строки else "")[:60])
битый.unlink(missing_ok=True)
Path("запас_битый.битый").unlink(missing_ok=True)

врем.unlink(missing_ok=True)
Path("запас_тест.tmp").unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
