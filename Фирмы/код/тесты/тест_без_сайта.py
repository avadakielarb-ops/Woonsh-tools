import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import inspect
from pathlib import Path
from openpyxl import load_workbook
from part1.excel_out import ExcelWriter
from part1.models import Firm

ф = Path("_проверка_безсайта.xlsx")
if ф.exists():
    ф.unlink()

def фирма(имя, город="Город"):
    return Firm(name=имя, industry="", location_type="", city=город,
                zip_code="12345", address="ул. Тест 1", url="")

print("=== режим только_без_сайта: датированный лист НЕ создаётся ===")
w = ExcelWriter(ф, "PL", только_без_сайта=True)
print("sheet_name:", repr(w.sheet_name))
print("ws:", w.ws)
w.гео = "PL"
print("записал ALPHA:", w.без_сайта(фирма("ALPHA SP Z O O")))
print("записал BETA :", w.без_сайта(фирма("BETA SP Z O O")))
print("повтор ALPHA :", w.без_сайта(фирма("ALPHA SP Z O O")), "(должно быть False)")

wb = load_workbook(ф)
print("листы в файле:", wb.sheetnames, "(датированного быть не должно)")
print("строк в «Без сайта»:", wb["Без сайта"].max_row - 1, "(ждём 2)")

print()
print("=== дубли ловятся и МЕЖДУ запусками ===")
w2 = ExcelWriter(ф, "PL", только_без_сайта=True)
print("снова ALPHA  :", w2.без_сайта(фирма("ALPHA SP Z O O")), "(должно быть False)")
print("новая GAMMA  :", w2.без_сайта(фирма("GAMMA SP Z O O")), "(должно быть True)")
wb = load_workbook(ф)
print("строк в «Без сайта»:", wb["Без сайта"].max_row - 1, "(ждём 3)")
for r in wb["Без сайта"].iter_rows(min_row=1, max_col=4, values_only=True):
    print("   ", r)

print()
print("=== сигнатуры ===")
import part1.engine as д1
print("run           :", inspect.signature(д1.run))
print("run_мультигео :", inspect.signature(д1.run_мультигео))

ф.unlink()
print()
print("прибрано")
