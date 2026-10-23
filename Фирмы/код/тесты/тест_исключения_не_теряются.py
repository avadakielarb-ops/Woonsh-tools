"""
Список исключений нельзя потерять по неосторожности.

Живая потеря: тестовый скрипт удалил «исключения.txt», и восемнадцать записей
с гео, собранных вручную, исчезли без следа. Ни копии, ни предупреждения.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part2.исключения import Исключения

ошибок = 0
# СВОЙ файл, а не боевой: проверка не имеет права трогать рабочие данные
врем = Path("искл_сохранность_тест.txt")
for p in (врем, врем.with_suffix(".bak")):
    p.unlink(missing_ok=True)

и = Исключения(path=врем)
и.сохранить("AT: ice com Handelsges.m.b.H.\nUK: BIRDS EYE LIMITED\nBE: ICE SA")
print("=== 1. Записалось ===")
print(f"   строк: {len(и.строки)}")
if len(и.строки) != 3:
    ошибок += 1
    print("   ✘")
else:
    print("   ✔")

print()
print("=== 2. Перезапись делает копию .bak ===")
и.сохранить("PL: BLUE ICE SP Z O O")
бак = врем.with_suffix(".bak")
print(f"   .bak есть: {бак.exists()}")
if not бак.exists():
    ошибок += 1
    print("   ✘ копии нет — прежний список потерян навсегда")
else:
    старое = бак.read_text(encoding="utf-8-sig")
    вернулись = [с for с in ("ice com", "BIRDS EYE", "ICE SA") if с in старое]
    print(f"   в копии сохранились: {вернулись}")
    if len(вернулись) != 3:
        ошибок += 1
        print("   ✘ копия неполная")
    else:
        print("   ✔ прежние записи можно вернуть из .bak")

print()
print("=== 3. Из копии восстанавливается ===")
и2 = Исключения(path=бак)
if not и2.исключена("ICE SA", "BE"):
    ошибок += 1
    print("   ✘ копия не читается как список исключений")
else:
    print("   ✔ читается")

print()
print("=== 4. Пустое сохранение не оставляет мусора ===")
и.сохранить("")
print(f"   строк после пустого сохранения: {len(и.строки)}")
if и.строки:
    ошибок += 1
    print("   ✘")
else:
    print("   ✔ (а .bak хранит предыдущее)")
    бак2 = бак.read_text(encoding="utf-8-sig")
    print("   в .bak:", "BLUE ICE" in бак2)

for p in (врем, бак):
    p.unlink(missing_ok=True)
print()
print("ошибок:", ошибок)
