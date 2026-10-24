"""
Woonsh Tools — главное приложение.
Sidebar с модулями: Поиск фирм, CSV Ads, Документы, Drive, Профили.
"""

import os
import sys
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk

from woonsh_tools import VERSION
from woonsh_tools.core import theme as aurora
from woonsh_tools.core.sidebar import Sidebar
from woonsh_tools.core.ui_helpers import enable_clipboard

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(os.environ.get("APPDATA") or BASE_DIR, "WoonshTools")


def _ensure_dirs():
    for sub in ("", "documents", "profiles", "rclone", "ads", "updates"):
        os.makedirs(os.path.join(APP_DIR, sub), exist_ok=True)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class App:
    def __init__(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        _ensure_dirs()

        self.app_data_dir = APP_DIR
        self.cfg = load_json(os.path.join(APP_DIR, "config.json"))
        self.q = queue.Queue()
        self.working = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"Woonsh Tools v{VERSION}")
        self.root.geometry(self.cfg.get("geometry", "1120x860"))
        self.root.minsize(800, 600)

        aurora.apply(self.root)
        enable_clipboard(self.root)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll)
        self.root.deiconify()

    def emit(self, *args):
        self.q.put(args)

    def _poll(self):
        while True:
            try:
                kind, *a = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(*a)
            elif kind == "status":
                self.status_var.set(a[0])
        if self.root.winfo_exists():
            self.root.after(100, self._poll)

    def _log(self, text, level="info"):
        self.status_var.set(str(text))

    def _build_ui(self):
        self.nb = Sidebar(self.root)
        self.nb.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Готово")
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom")
        ttk.Label(status_bar, textvariable=self.status_var,
                  style="Muted.TLabel", padding=(12, 6)).pack(side="left")
        ttk.Label(status_bar, text=f"v{VERSION}",
                  style="Muted.TLabel", padding=(12, 6)).pack(side="right")

        # -- Модули --

        from woonsh_tools.companies.panel import CompaniesPanel
        from woonsh_tools.companies.stats import StatsPanel
        from woonsh_tools.drive.panel import DrivePanel
        from woonsh_tools.profiles.panel import ProfilesPanel
        from woonsh_tools.ads.panel import AdsPanel, ReviewPanel
        from woonsh_tools.documents.panel import DocumentsPanel
        from woonsh_tools.documents.stock import StockPanel
        from woonsh_tools.update.panel import SettingsPanel

        # 1. Поиск фирм
        self.companies_panel = CompaniesPanel(self.nb, self)
        self.nb.add(self.companies_panel, text="Поиск фирм",
                    group="ПОИСК ФИРМ")

        # 2. Гео и выдача
        self.geo_panel = StatsPanel(self.nb, self)
        self.nb.add(self.geo_panel, text="Гео и выдача", group="ПОИСК ФИРМ")

        # 3. Генератор CSV
        self.ads_panel = AdsPanel(self.nb, self)
        self.nb.add(self.ads_panel, text="Генератор CSV", group="GOOGLE ADS")

        # 4. Профили
        self.profiles_panel = ProfilesPanel(self.nb, self)
        self.nb.add(self.profiles_panel, text="Профили", group="GOOGLE ADS")

        # 5. Компании (привязка фирм к аккаунтам)
        self.review_panel = ReviewPanel(self.nb, self)
        self.nb.add(self.review_panel, text="Компании", group="GOOGLE ADS")

        # 6. Google Drive — Загрузка PDF
        self.drive_panel = DrivePanel(self.nb, self)
        self.nb.add(self.drive_panel, text="Загрузка", group="GOOGLE DRIVE")

        # 7. Документы
        self.documents_panel = DocumentsPanel(self.nb, self, self.app_data_dir)
        self.nb.add(self.documents_panel, text="Документы",
                    group="ДОКУМЕНТАЦИЯ")

        # 8. Склад документов
        self.stock_panel = StockPanel(self.nb, self, self.app_data_dir)
        self.nb.add(self.stock_panel, text="Склад", group="ДОКУМЕНТАЦИЯ")

        # 9. Настройки
        self.settings_panel = SettingsPanel(self.nb, self)
        self.nb.add(self.settings_panel, text="Настройки", group="СИСТЕМА")

    def _save_config(self):
        self.cfg["geometry"] = self.root.geometry()
        save_json(os.path.join(APP_DIR, "config.json"), self.cfg)

    def on_close(self):
        if self.working:
            from tkinter import messagebox
            if not messagebox.askyesno("Идёт операция",
                                       "Прервать и выйти?", parent=self.root):
                return
        self._save_config()
        self.root.destroy()


def main():
    from woonsh_tools.update.updater import confirm_start
    confirm_start()
    app = App()
    app.root.mainloop()


if __name__ == "__main__":
    main()
