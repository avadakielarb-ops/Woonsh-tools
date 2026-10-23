import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import inspect
from app import App

app = App()
app.withdraw()
print("окно собралось")

print("мультигео:", app.мультигео.get(), "| мультилист:", app.мультилист.get())
app.мультигео.set(True)
app.мультигео_страны = ["France", "Poland", "Germany"]
app._обновить_подпись_мг()
print("подпись:", app.подпись_мг["text"])

app.мультилист.set(True)
app._переключить_мультилист()
print("мультилист вкл → гео:", str(app.гео["state"]), "| лист:", str(app.лист2["state"]),
      "(лист должен остаться выбираемым)")
app.мультилист.set(False)
app._переключить_мультилист()
print("мультилист выкл → гео:", str(app.гео["state"]))

import part1.engine as д1, part2.engine as д2
print()
print("run_мультигео :", inspect.signature(д1.run_мультигео))
print("run_мультилист:", inspect.signature(д2.run_мультилист))
print("run (часть 2) :", inspect.signature(д2.run))
app.destroy()
print()
print("всё сходится")
