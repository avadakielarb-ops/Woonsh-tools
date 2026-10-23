"""
Aurora theme — единая тема для всего приложения.
Взято из X-File visual_system.py + x-file.pyw apply_theme.
"""

import tkinter as tk
from tkinter import ttk

AURORA = ("#7a34e6", "#d6389e", "#3b74ed")
GOLD = "#e8a531"

COLORS = {
    "bg": "#100c1c", "surface": "#1a1430", "surface2": "#20193a",
    "ink": "#f2ecff", "muted": "#a99fc4", "line": "#2c2444",
    "field": "#20193a", "field_ink": "#f2ecff",
}

SEMANTIC = {
    "success": "#4cc98a", "danger": "#ff6b6b",
    "warning": GOLD, "info": AURORA[2], "gold": GOLD,
}

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
FONT_H = ("Segoe UI Semibold", 12)
FONT_T = ("Segoe UI Semibold", 17)
MONO = ("Consolas", 9)


def apply(root):
    """Применяет тему Aurora ко всему приложению."""
    t = COLORS
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=t["bg"])
    root.option_add("*Font", FONT)

    style.configure(".", background=t["bg"], foreground=t["ink"], font=FONT,
                    fieldbackground=t["field"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"],
                    troughcolor=t["surface"], focuscolor=AURORA[0])
    style.configure("TFrame", background=t["bg"])
    style.configure("TLabel", background=t["bg"], foreground=t["ink"])
    style.configure("Muted.TLabel", foreground=t["muted"])
    style.configure("Title.TLabel", font=FONT_T)
    style.configure("H.TLabel", font=FONT_H)

    for name, color in [("Success", SEMANTIC["success"]),
                        ("Danger", SEMANTIC["danger"]),
                        ("Warning", SEMANTIC["warning"])]:
        style.configure(f"{name}.TLabel", foreground=color)

    style.configure("Card.TFrame", background=t["surface"])
    style.configure("Card.TLabel", background=t["surface"], foreground=t["ink"])
    style.configure("CardMuted.TLabel", background=t["surface"], foreground=t["muted"])
    style.configure("CardH.TLabel", background=t["surface"], font=FONT_H)
    for name, color in [("Success", SEMANTIC["success"]),
                        ("Danger", SEMANTIC["danger"]),
                        ("Warning", SEMANTIC["warning"])]:
        style.configure(f"Card{name}.TLabel", background=t["surface"], foreground=color)

    style.configure("TSeparator", background=t["line"])

    style.configure("TCombobox", fieldbackground=t["field"], background=t["surface2"],
                    foreground=t["field_ink"], arrowcolor=t["muted"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"], padding=5)
    style.map("TCombobox",
              fieldbackground=[("readonly", t["field"]), ("disabled", t["surface"])],
              foreground=[("readonly", t["field_ink"]), ("disabled", t["muted"])],
              selectbackground=[("readonly", t["field"])],
              selectforeground=[("readonly", t["field_ink"])],
              bordercolor=[("focus", AURORA[0])])
    root.option_add("*TCombobox*Listbox.background", t["field"])
    root.option_add("*TCombobox*Listbox.foreground", t["field_ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", AURORA[0])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style.configure("TCheckbutton", background=t["bg"], foreground=t["ink"],
                    padding=(0, 5), indicatorcolor=t["field"])
    style.map("TCheckbutton",
              background=[("active", t["bg"])],
              foreground=[("disabled", t["muted"])],
              indicatorcolor=[("selected", AURORA[0]), ("!selected", t["field"])])
    style.configure("TRadiobutton", background=t["bg"], foreground=t["ink"],
                    padding=(0, 5), indicatorcolor=t["field"])
    style.map("TRadiobutton",
              background=[("active", t["bg"])],
              foreground=[("disabled", t["muted"])],
              indicatorcolor=[("selected", AURORA[0]), ("!selected", t["field"])])

    style.configure("TButton", background=t["surface2"], foreground=t["ink"],
                    bordercolor=t["line"], relief="flat", padding=(12, 6))
    style.map("TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[0]), ("disabled", t["surface"])],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff"), ("disabled", t["muted"])],
              bordercolor=[("active", AURORA[0])])
    style.configure("Accent.TButton", background=AURORA[0], foreground="#ffffff",
                    bordercolor=AURORA[0], relief="flat", padding=(16, 8), font=FONT_B)
    style.map("Accent.TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[2]), ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])
    style.configure("Danger.TButton", background="#4a1f2e", foreground="#ffd7d7",
                    bordercolor="#6b2c40", relief="flat", padding=(12, 6))
    style.map("Danger.TButton",
              background=[("active", "#a43a52"), ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TEntry", fieldbackground=t["field"], foreground=t["field_ink"],
                    insertcolor=t["field_ink"], bordercolor=t["line"], padding=6)
    style.map("TEntry", bordercolor=[("focus", AURORA[0])],
              fieldbackground=[("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TSpinbox", fieldbackground=t["field"], foreground=t["ink"],
                    arrowcolor=t["muted"], padding=6, insertcolor=t["ink"])
    style.configure("TMenubutton", background=t["field"], foreground=t["ink"],
                    padding=(10, 7), arrowcolor=t["muted"], relief="flat")
    style.map("TMenubutton",
              background=[("active", "#35234f")],
              foreground=[("disabled", t["muted"])])

    style.configure("TLabelframe", background=t["bg"], bordercolor=t["line"], relief="flat")
    style.configure("TLabelframe.Label", background=t["bg"], foreground=t["muted"], font=FONT_B)

    style.configure("Aurora.Horizontal.TProgressbar",
                    background=AURORA[0], troughcolor=t["surface"],
                    bordercolor=t["line"], lightcolor=AURORA[0], darkcolor=AURORA[0])
    style.configure("Horizontal.TProgressbar",
                    background=AURORA[0], troughcolor=t["surface"], borderwidth=0, thickness=5)

    for bar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(bar, background=t["surface2"], troughcolor=t["bg"],
                        bordercolor=t["bg"], arrowcolor=t["muted"], relief="flat")
        style.map(bar, background=[("active", AURORA[0])])

    style.configure("Treeview", background=t["field"], fieldbackground=t["field"],
                    foreground=t["ink"], rowheight=32, borderwidth=0, bordercolor=t["line"])
    style.map("Treeview",
              background=[("selected", AURORA[0])],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=t["surface2"], foreground=t["muted"],
                    relief="flat", padding=(10, 9), font=FONT_B)
    style.map("Treeview.Heading", background=[("active", t["line"])])

    style.configure("Nav.TButton", background=t["bg"], foreground=t["muted"],
                    font=FONT_B, padding=(14, 11), anchor="w")
    style.map("Nav.TButton", background=[("active", t["surface2"])])
    style.configure("NavSelected.TButton", background="#322048", foreground="#f6efff",
                    font=FONT_B, padding=(14, 11), anchor="w")
    style.map("NavSelected.TButton",
              background=[("disabled", "#322048")],
              foreground=[("disabled", "#f6efff")])
    style.configure("SidebarGroup.TLabel",
                    font=("Segoe UI Semibold", 9), foreground="#9c8bb7", padding=(2, 5))

    root.option_add("*Text.background", t["field"])
    root.option_add("*Text.foreground", t["ink"])
    root.option_add("*Text.insertBackground", t["ink"])
    root.option_add("*Listbox.background", t["field"])
    root.option_add("*Listbox.foreground", t["ink"])
    root.option_add("*Menu.background", t["surface2"])
    root.option_add("*Menu.foreground", t["ink"])
    root.option_add("*Menu.activeBackground", AURORA[0])
    root.option_add("*Menu.activeForeground", "#ffffff")

    _install_auto_skin(root, t)
    _install_dialogs(root, t)

    return style


def _install_auto_skin(root, t):
    accent = AURORA[0]
    primary_prefixes = (
        "Генерировать", "Найти через", "Сохранить", "Установить и",
        "Завершить", "Обновить и", "Загрузить", "Запустить",
    )

    def skin(widget):
        if isinstance(widget, str):
            try:
                widget = root.nametowidget(widget)
            except (KeyError, tk.TclError):
                return
        if not isinstance(widget, tk.Misc):
            return
        try:
            if not widget.winfo_exists():
                return
            if not getattr(widget, "_wt_skinned", False):
                if isinstance(widget, tk.Toplevel):
                    widget.configure(background=t["bg"])
                elif isinstance(widget, tk.Text):
                    widget.configure(
                        background=t["field"], foreground=t["ink"],
                        insertbackground=t["ink"], selectbackground=accent,
                        selectforeground="white", relief="flat", borderwidth=0,
                        highlightthickness=1, highlightbackground=t["line"],
                        highlightcolor=accent, padx=10, pady=8, font=FONT)
                elif isinstance(widget, tk.Listbox):
                    widget.configure(
                        background=t["field"], foreground=t["ink"],
                        selectbackground=accent, selectforeground="white",
                        relief="flat", borderwidth=0, highlightthickness=1,
                        highlightbackground=t["line"], font=FONT)
                elif isinstance(widget, tk.Entry):
                    widget.configure(
                        background=t["field"], foreground=t["ink"],
                        insertbackground=t["ink"], selectbackground=accent,
                        selectforeground="white", relief="flat",
                        highlightthickness=1, highlightbackground=t["line"],
                        highlightcolor=accent)
                elif isinstance(widget, tk.Button):
                    widget.configure(
                        background=t["surface2"], foreground=t["ink"],
                        activebackground=accent, activeforeground="white",
                        relief="flat", borderwidth=0, padx=14, pady=7)
                elif isinstance(widget, (tk.Frame, tk.Label)):
                    bg = str(widget.cget("background"))
                    if bg in ("SystemButtonFace", "SystemWindow", "#d9d9d9",
                              "white", "#ffffff"):
                        widget.configure(background=t["bg"])
                        if isinstance(widget, tk.Label):
                            widget.configure(foreground=t["ink"])
                elif isinstance(widget, ttk.Button):
                    st = widget.cget("style")
                    if st in ("", "TButton"):
                        text = str(widget.cget("text"))
                        if text.startswith(primary_prefixes):
                            widget.configure(style="Accent.TButton")
                        elif text.startswith("Удалить"):
                            widget.configure(style="Danger.TButton")
                widget._wt_skinned = True
            if isinstance(widget, ttk.Treeview):
                widget.tag_configure("wt_even", background="#1d172c")
                widget.tag_configure("wt_odd", background="#211a32")
                for i, item in enumerate(widget.get_children()):
                    tags = [t for t in widget.item(item, "tags")
                            if not t.startswith("wt_")]
                    if not tags:
                        widget.item(item, tags=("wt_even" if i % 2 == 0 else "wt_odd",))
            for child in widget.winfo_children():
                skin(child)
        except tk.TclError:
            pass

    def on_map(event):
        try:
            root.after_idle(lambda w=event.widget: skin(w))
        except tk.TclError:
            pass

    root.bind_all("<Map>", on_map, add="+")

    def tick():
        if not root.winfo_exists():
            return
        skin(root)
        root.after(1200, tick)

    root.after_idle(tick)


def _install_dialogs(root, t):
    from tkinter import messagebox

    layouts = {
        "ok": [("ok", "Понятно")],
        "okcancel": [("ok", "Продолжить"), ("cancel", "Отмена")],
        "yesno": [("yes", "Да"), ("no", "Нет")],
        "yesnocancel": [("yes", "Да"), ("no", "Нет"), ("cancel", "Отмена")],
        "retrycancel": [("retry", "Повторить"), ("cancel", "Отмена")],
        "abortretryignore": [("abort", "Прервать"), ("retry", "Повторить"),
                             ("ignore", "Пропустить")],
    }

    def dialog(title=None, message=None, _icon=None, _type=None, **options):
        parent = options.get("parent") or root
        window = tk.Toplevel(parent)
        window.title(title or "Woonsh Tools")
        window.configure(background=t["bg"])
        window.resizable(False, False)
        window.transient(parent.winfo_toplevel())
        body = ttk.Frame(window, padding=24)
        body.pack(fill="both", expand=True)
        heading = {
            "error": "Ошибка", "warning": "Обратите внимание",
            "question": "Подтверждение", "info": "Информация",
        }.get(_icon, "Woonsh Tools")
        ttk.Label(body, text=heading, style="H.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(body, text=str(message or ""), wraplength=470,
                  justify="left").pack(anchor="w")
        if options.get("detail"):
            ttk.Label(body, text=options["detail"], style="Muted.TLabel",
                      wraplength=470).pack(anchor="w", pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(22, 0))
        choices = layouts.get(_type or "ok", layouts["ok"])
        cancel = next(
            (key for key in ("cancel", "no", "ok", "abort")
             if any(c[0] == key for c in choices)),
            choices[-1][0])
        result = [cancel]

        def finish(value):
            result[0] = value
            window.destroy()

        first = None
        for i, (value, label) in enumerate(choices):
            btn = ttk.Button(
                actions, text=label,
                style="Accent.TButton" if i == 0 else "TButton",
                command=lambda v=value: finish(v))
            btn.pack(side="left", padx=(0, 8))
            if first is None:
                first = btn
        window.protocol("WM_DELETE_WINDOW", lambda: finish(cancel))
        window.bind("<Escape>", lambda e: finish(cancel))
        window.update_idletasks()
        width = max(420, window.winfo_reqwidth())
        height = window.winfo_reqheight()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        previous = window.grab_current()
        window.grab_set()
        first.focus_set()
        window.wait_window()
        if previous and previous.winfo_exists():
            previous.grab_set()
        return result[0]

    messagebox._show = dialog


def make_card(parent, title="", hint=""):
    outer = tk.Frame(parent, bg=COLORS["line"], padx=1, pady=1)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
    inner.pack(fill="both", expand=True)
    inner.columnconfigure(0, weight=1)
    if title:
        ttk.Label(inner, text=title, style="CardH.TLabel").grid(
            row=0, column=0, sticky="w")
    if hint:
        lbl = ttk.Label(inner, text=hint, style="CardMuted.TLabel", justify="left")
        lbl.grid(row=1, column=0, sticky="we", pady=(2, 8))
        lbl.bind("<Configure>",
                 lambda e: lbl.configure(wraplength=max(120, e.width - 8)))
    inner.outer = outer
    return inner
