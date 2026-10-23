"""
ТЕМА AURORA — единый вид всех окон приложения.

Палитра взята из «Генератора ЦСВ» (ppc_gemini.pyw) — это эталон стиля
пользователя, и держать два разных вида у соседних инструментов незачем.

Из Aurora берём ровно четыре цвета и градиент, больше ничего. Фон, поля и текст
остаются нейтральными: иначе цвет расползается по всему окну и читать тяжело.

Модуль отдельный, а не внутри app.py, потому что окно очереди заданий и любые
будущие окна должны краситься тем же вызовом, без копирования кода.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

AURORA = ("#7a34e6", "#d6389e", "#3b74ed")      # фиолетовый -> маджента -> синий
ЗОЛОТО = "#e8a531"

ТЕМА = {
    "bg": "#100c1c", "surface": "#1a1430", "surface2": "#20193a",
    "ink": "#f2ecff", "muted": "#a99fc4", "line": "#2c2444",
    "field": "#20193a", "field_ink": "#f2ecff",
}

# На тёмном фоне тёмно-красный нечитаем, поэтому ошибки светлее обычного.
УСПЕХ, ОПАСНОСТЬ = "#4cc98a", "#ff6b6b"

# Панель человека: фон должен ЧИТАТЬСЯ КАК СИГНАЛ, оставаясь частью тёмной темы.
# Поэтому не яркий красный, а тёмное вино — тревога считывается, глаза не режет.
ПАНЕЛЬ_ПОКОЙ = "#20193a"        # ничего не нужно — панель сливается с окном
ПАНЕЛЬ_ЧЕЛОВЕК = "#4a1228"      # нужен человек
ПАНЕЛЬ_ДОБОР = "#152a52"        # ввод нового слова

# Кнопки панели человека. Тёмная тема: заливка насыщенная, текст белый.
КН_УСПЕХ = ("#2f9e63", "#268253")
КН_ДЕЙСТВИЕ = ("#3b74ed", "#2b5cc4")
КН_НЕЙТРАЛЬ = ("#3a3358", "#2c2444")
КН_ОПАСНОСТЬ = ("#b3324e", "#8f2740")


def смешать(c1: str, c2: str, t: float) -> str:
    """Цвет между c1 и c2 в точке t от 0 до 1."""
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def аврора(t: float) -> str:
    """Точка градиента Aurora от 0 до 1."""
    if t <= 0.5:
        return смешать(AURORA[0], AURORA[1], t * 2)
    return смешать(AURORA[1], AURORA[2], (t - 0.5) * 2)


# Тема clam рисует галочку в чекбоксе КРЕСТИКОМ, и непонятно, это «включено»
# или «закрыто». Подменяем индикатор своими картинками: пустой квадрат —
# выключено, фиолетовый с белой галочкой — включено.
_КАРТИНКИ = []          # PhotoImage надо держать, иначе сборщик их съест
_ГАЛКА = [(4, 8), (5, 9), (6, 10), (7, 11),
          (8, 10), (9, 9), (10, 8), (11, 7), (12, 6)]


def _картинки_чекбокса(style, t) -> None:
    размер, зазор = 16, 6          # зазор — отступ до подписи, рисуем фоном
    выкл = tk.PhotoImage(width=размер + зазор, height=размер)
    вкл = tk.PhotoImage(width=размер + зазор, height=размер)
    for x in range(размер + зазор):
        for y in range(размер):
            if x >= размер:
                выкл.put(t["bg"], to=(x, y))
                вкл.put(t["bg"], to=(x, y))
                continue
            край = x in (0, размер - 1) or y in (0, размер - 1)
            выкл.put(t["line"] if край else t["field"], to=(x, y))
            вкл.put(AURORA[0], to=(x, y))
    for x, y in _ГАЛКА:                 # галочка в два пикселя толщиной
        вкл.put("#ffffff", to=(x, y))
        вкл.put("#ffffff", to=(x, y - 1))
    _КАРТИНКИ.extend((выкл, вкл))
    try:
        style.element_create("Aurora.indicator", "image", вкл,
                             ("!selected", выкл), sticky="", border=0)
    except tk.TclError:
        return                          # элемент уже создан в этой сессии Tk
    style.layout("TCheckbutton", [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Aurora.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                ("Checkbutton.label", {"sticky": "nswe"})]})]})])


def применить(root, t=ТЕМА):
    """
    Перекрасить ttk в цвета Aurora.

    Стандартные темы Windows рисуют кнопки и поля средствами системы и цвет
    игнорируют — поэтому переходим на clam, единственную встроенную, которая
    красится насквозь.
    """
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=t["bg"])
    root.option_add("*Font", ("Segoe UI", 10))

    style.configure(".", background=t["bg"], foreground=t["ink"],
                    fieldbackground=t["field"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"],
                    troughcolor=t["surface"], focuscolor=AURORA[0])
    for w in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton",
              "TNotebook", "TSeparator", "TLabelframe"):
        style.configure(w, background=t["bg"])
    style.configure("TLabel", foreground=t["ink"])
    style.configure("TSeparator", background=t["line"])
    style.configure("TCheckbutton", foreground=t["ink"], padding=(0, 2))
    style.map("TCheckbutton", background=[("active", t["bg"])])
    style.configure("TRadiobutton", foreground=t["ink"],
                    indicatorcolor=t["field"], padding=(0, 2))
    style.map("TRadiobutton", background=[("active", t["bg"])],
              indicatorcolor=[("selected", AURORA[0]), ("!selected", t["field"])])
    _картинки_чекбокса(style, t)

    # Рамка «Ход работы»: заголовок цветом Aurora, чтобы читался как раздел
    style.configure("TLabelframe", bordercolor=t["line"], relief="solid")
    style.configure("TLabelframe.Label", background=t["bg"], foreground=AURORA[1])

    style.configure("TButton", background=t["surface2"], foreground=t["ink"],
                    bordercolor=t["line"], relief="flat", padding=(10, 4))
    style.map("TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[0]),
                          ("disabled", t["surface"])],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff"),
                          ("disabled", t["muted"])],
              bordercolor=[("active", AURORA[0])])

    # Главная кнопка прогона — заливка Aurora, её видно сразу
    style.configure("Пуск.TButton", background=AURORA[0], foreground="#ffffff",
                    padding=(10, 7))
    style.map("Пуск.TButton",
              background=[("pressed", AURORA[1]), ("active", смешать(AURORA[0], AURORA[1], .5)),
                          ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TEntry", fieldbackground=t["field"], foreground=t["field_ink"],
                    insertcolor=t["field_ink"], bordercolor=t["line"], padding=4)
    style.map("TEntry", bordercolor=[("focus", AURORA[0])],
              fieldbackground=[("disabled", t["surface"])])
    style.configure("TSpinbox", fieldbackground=t["field"], foreground=t["field_ink"],
                    background=t["surface2"], arrowcolor=t["ink"],
                    bordercolor=t["line"], padding=3)
    style.configure("TCombobox", fieldbackground=t["field"], background=t["surface2"],
                    foreground=t["field_ink"], arrowcolor=t["ink"],
                    bordercolor=t["line"], padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", t["field"]), ("disabled", t["surface"])],
              foreground=[("readonly", t["field_ink"]), ("disabled", t["muted"])],
              bordercolor=[("focus", AURORA[0])])
    # Выпадающий список Combobox — это классический tk.Listbox, ttk его не видит.
    root.option_add("*TCombobox*Listbox.background", t["surface2"])
    root.option_add("*TCombobox*Listbox.foreground", t["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", AURORA[0])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style.configure("TNotebook", bordercolor=t["line"])
    style.configure("TNotebook.Tab", background=t["bg"], foreground=t["muted"],
                    bordercolor=t["line"], padding=(16, 7))
    style.map("TNotebook.Tab",
              background=[("selected", t["surface"]), ("active", t["surface2"])],
              foreground=[("selected", AURORA[0])])

    # ТАБЛИЦА (Treeview). Тема её не знала, и список гео выходил БЕЛЫМ пятном
    # на тёмном окне — читать невозможно. Красим здесь, а не в окне: следующее
    # окно со списком иначе наступит на те же грабли.
    style.configure("Treeview", background=t["surface"],
                    fieldbackground=t["surface"], foreground=t["ink"],
                    bordercolor=t["line"], borderwidth=0, rowheight=26)
    style.configure("Treeview.Heading", background=t["surface2"],
                    foreground=t["muted"], bordercolor=t["line"],
                    relief="flat", padding=(8, 6))
    style.map("Treeview", background=[("selected", AURORA[0])],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", t["line"])])
    # Полосы через строку — глазу легче вести взгляд по цифрам.
    style.configure("Полосатый.Treeview", background=t["surface"])

    for полоса in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(полоса, background=t["surface2"], troughcolor=t["bg"],
                        bordercolor=t["bg"], arrowcolor=t["muted"], relief="flat")
        style.map(полоса, background=[("active", AURORA[0])])
    return style


def покрасить(widget, t=ТЕМА, поверхность="surface2"):
    """
    tk.Text, tk.Listbox и tk.Canvas ttk не красит — делаем это руками.
    Возвращает сам виджет, чтобы можно было писать в одну строку.

    Опции применяем ПО ОДНОЙ и только те, что виджет понимает. Раньше здесь был
    один configure() со всем сразу, и на tk.Listbox он падал: у списка нет
    insertbackground (это опция поля ввода). Падало не тихо — рушилась вся
    сборка окна, и «Выбрать страны…» открывалось ПУСТЫМ, без списка и кнопок.
    """
    хочу = {"bg": t[поверхность], "fg": t["ink"], "insertbackground": t["ink"],
            "selectbackground": AURORA[0], "selectforeground": "#ffffff",
            "relief": "flat", "highlightthickness": 1,
            "highlightbackground": t["line"], "highlightcolor": AURORA[0]}
    умеет = set(widget.keys())
    for имя, значение in хочу.items():
        if имя in умеет:
            try:
                widget.configure(**{имя: значение})
            except Exception:
                pass          # экзотический виджет — просто пропускаем опцию
    return widget
