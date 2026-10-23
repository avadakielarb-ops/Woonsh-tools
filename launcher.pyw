"""
Launcher — единая точка входа.
Показывает экран выбора: Multi-Tool Farmer или Woonsh Tools.
Farmer запускается как есть (X-File/x-file.pyw), обновляется через GitHub Releases.
Woonsh Tools — новое ядро со слитыми модулями.
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk

BASE_DIR = os.path.dirname(os.path.abspath(
    sys.argv[0] if getattr(sys, "frozen", False) else __file__))

LAUNCHER_CFG = os.path.join(
    os.environ.get("APPDATA") or BASE_DIR, "WoonshLauncher", "launcher.json")

# ── Тема Aurora (общая) ─────────────────────────────────────────────────────

AURORA = ("#7a34e6", "#d6389e", "#3b74ed")
THEME = {
    "bg": "#100c1c", "surface": "#1a1430", "surface2": "#20193a",
    "ink": "#f2ecff", "muted": "#a99fc4", "line": "#2c2444",
    "field": "#20193a", "field_ink": "#f2ecff",
}
FONT = ("Segoe UI", 11)
FONT_H = ("Segoe UI Semibold", 22)
FONT_SUB = ("Segoe UI", 10)
FONT_BTN = ("Segoe UI Semibold", 13)


def load_preference():
    try:
        with open(LAUNCHER_CFG, "r", encoding="utf-8") as f:
            return json.load(f).get("last_mode")
    except (OSError, ValueError):
        return None


def save_preference(mode):
    os.makedirs(os.path.dirname(LAUNCHER_CFG), exist_ok=True)
    tmp = LAUNCHER_CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_mode": mode}, f)
    os.replace(tmp, LAUNCHER_CFG)


def launch_farmer():
    """Запуск Multi-Tool Farmer (X-File) в текущем процессе."""
    save_preference("farmer")
    xfile = os.path.join(BASE_DIR, "X-File", "x-file.pyw")
    sys.path.insert(0, os.path.join(BASE_DIR, "X-File"))
    os.chdir(os.path.join(BASE_DIR, "X-File"))
    with open(xfile, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, xfile, "exec"), {"__name__": "__main__", "__file__": xfile})


def launch_woonsh():
    """Запуск Woonsh Tools."""
    save_preference("woonsh")
    sys.path.insert(0, BASE_DIR)
    from woonsh_tools.app import main
    main()


class LauncherWindow:
    def __init__(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.root = tk.Tk()
        self.root.title("Woonsh — Выбор режима")
        self.root.configure(bg=THEME["bg"])
        self.root.geometry("620x480")
        self.root.minsize(500, 400)
        self.root.resizable(False, False)

        self._apply_style()
        self._build_ui()

        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _apply_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=THEME["bg"], foreground=THEME["ink"], font=FONT)
        style.configure("TFrame", background=THEME["bg"])
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["ink"])

        style.configure("Title.TLabel", font=FONT_H, foreground=THEME["ink"])
        style.configure("Sub.TLabel", font=FONT_SUB, foreground=THEME["muted"])

        for name, color, hover in [
            ("Farmer", AURORA[0], AURORA[1]),
            ("Woonsh", AURORA[2], "#5590ff"),
        ]:
            style.configure(
                f"{name}.TButton",
                background=color, foreground="#ffffff",
                font=FONT_BTN, padding=(24, 16), relief="flat", borderwidth=0)
            style.map(
                f"{name}.TButton",
                background=[("active", hover), ("pressed", AURORA[1])],
                foreground=[("disabled", THEME["muted"])])

        style.configure("Muted.TButton",
                        background=THEME["surface2"], foreground=THEME["muted"],
                        font=FONT_SUB, padding=(10, 6), relief="flat", borderwidth=0)
        style.map("Muted.TButton",
                  background=[("active", THEME["line"])],
                  foreground=[("active", THEME["ink"])])

    def _build_ui(self):
        body = ttk.Frame(self.root, padding=40)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Woonsh", style="Title.TLabel").pack(pady=(10, 4))
        ttk.Label(body, text="Выберите режим работы", style="Sub.TLabel").pack(pady=(0, 30))

        cards = ttk.Frame(body)
        cards.pack(fill="x")
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        # -- Farmer card --
        farmer = self._card(cards, row=0, col=0,
                            title="Multi-Tool Farmer",
                            desc="Загрузка выписок на Drive,\nтаблицы, сопоставление PDF",
                            version="v2.9.9",
                            btn_style="Farmer.TButton",
                            command=self._start_farmer)

        # -- Woonsh Tools card --
        woonsh = self._card(cards, row=0, col=1,
                            title="Woonsh Tools",
                            desc="Поиск фирм, CSV Ads,\nдокументы, Drive, профили",
                            version="v0.1.0",
                            btn_style="Woonsh.TButton",
                            command=self._start_woonsh)

        # -- Remember checkbox --
        self.remember = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body, text="Запоминать выбор (для сброса: удалить launcher.json)",
            variable=self.remember,
            style="TCheckbutton"
        ).pack(pady=(30, 0))

    def _card(self, parent, row, col, title, desc, version, btn_style, command):
        outer = tk.Frame(parent, bg=THEME["line"], padx=1, pady=1)
        outer.grid(row=row, column=col, padx=8, sticky="nsew")

        inner = tk.Frame(outer, bg=THEME["surface"], padx=20, pady=20)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text=title, bg=THEME["surface"], fg=THEME["ink"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(inner, text=desc, bg=THEME["surface"], fg=THEME["muted"],
                 font=FONT_SUB, justify="left").pack(anchor="w", pady=(6, 12))
        tk.Label(inner, text=version, bg=THEME["surface"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 12))

        btn = ttk.Button(inner, text="Запустить", style=btn_style, command=command)
        btn.pack(fill="x")
        return inner

    def _start_farmer(self):
        if self.remember.get():
            save_preference("farmer")
        self.root.destroy()
        launch_farmer()

    def _start_woonsh(self):
        if self.remember.get():
            save_preference("woonsh")
        self.root.destroy()
        launch_woonsh()

    def run(self):
        self.root.mainloop()


def main():
    if "--farmer" in sys.argv:
        launch_farmer()
        return
    if "--woonsh" in sys.argv:
        launch_woonsh()
        return

    pref = load_preference()
    if pref == "farmer":
        launch_farmer()
        return
    if pref == "woonsh":
        launch_woonsh()
        return

    win = LauncherWindow()
    win.run()


if __name__ == "__main__":
    main()
