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

        # 1. Поиск фирм
        companies_page = self._placeholder("Поиск фирм",
            "Поиск компаний по стране и направлению.\n"
            "19 гео-драйверов, DnB, реестры, Gemini, Telegram-бот.")
        self.nb.add(companies_page, text="Поиск фирм", group="ПОИСК ФИРМ")

        # 2. Статистика
        stats_page = self._placeholder("Статистика",
            "Сводные показатели по странам:\n"
            "компании с сайтом, без сайта, PDF, проверки.")
        self.nb.add(stats_page, text="Статистика", group="ПОИСК ФИРМ")

        # 3. Google Drive
        drive_page = self._placeholder("Загрузка на Drive",
            "Сопоставление PDF с компаниями.\n"
            "Загрузка через rclone, SHA-256 проверка, ссылки в Excel.")
        self.nb.add(drive_page, text="Загрузка", group="GOOGLE DRIVE")

        # 4. Профили
        profiles_page = self._placeholder("Профили",
            "Таблицы профилей, копирование реквизитов.\n"
            "DPAPI-шифрование, 30с авто-очистка буфера.")
        self.nb.add(profiles_page, text="Профили", group="GOOGLE DRIVE")

        # 5. CSV Генератор
        ads_page = self._placeholder("Генератор CSV",
            "Google Ads кампании через Gemini API.\n"
            "ThreadPoolExecutor(4), MODEL_CHAIN, CDP браузер-режим,\n"
            "batch queue, авторемонт, DKI, бан-категории.")
        self.nb.add(ads_page, text="Генератор CSV", group="GOOGLE ADS")

        # 6. Проверка рекламы
        review_page = self._placeholder("Проверка рекламы",
            "Валидация структуры, длин, повторов.\n"
            "SHA-256 manual approval, редактор.")
        self.nb.add(review_page, text="Проверка", group="GOOGLE ADS")

        # 7. Документы
        docs_page = self._placeholder("Документы",
            "MRZ-парсинг (TD3/TD1), OCR, Gemini распознавание.\n"
            "SHA-256 дедуп, DPAPI, front/back пары.")
        self.nb.add(docs_page, text="Документы", group="ДОКУМЕНТАЦИЯ")

        # 8. Склад документов
        stock_page = self._placeholder("Склад",
            "Предварительная загрузка комплектов документов.\n"
            "ZIP/RAR, path traversal protection, назначение профилям.")
        self.nb.add(stock_page, text="Склад", group="ДОКУМЕНТАЦИЯ")

        # 9. Настройки
        settings_page = self._placeholder("Настройки",
            "Gemini API, Google Drive, Telegram, таблицы.\n"
            "Обновления через GitHub Releases.")
        self.nb.add(settings_page, text="Настройки", group="СИСТЕМА")

    def _placeholder(self, title, description):
        """Страница-заглушка для ещё не подключённого модуля."""
        frame = ttk.Frame(self.nb)
        inner = ttk.Frame(frame, padding=40)
        inner.pack(fill="both", expand=True)

        ttk.Label(inner, text=title, style="Title.TLabel").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(inner, text=description, style="Muted.TLabel",
                  justify="left", wraplength=500).pack(anchor="w", pady=(0, 20))

        badge = ttk.Frame(inner)
        badge.pack(anchor="w")
        tk.Label(badge, text=" В РАЗРАБОТКЕ ", bg="#4a1f2e", fg="#ffd7d7",
                 font=("Segoe UI Semibold", 9), padx=8, pady=4).pack()

        return frame

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
    app = App()
    app.root.mainloop()


if __name__ == "__main__":
    main()
