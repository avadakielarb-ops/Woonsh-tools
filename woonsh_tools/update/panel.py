"""
Settings panel — Gemini API, Google Drive, Telegram, updates.
Combines configuration UI with the GitHub Releases updater.
"""
import tkinter as tk
from tkinter import ttk
import webbrowser

from woonsh_tools import VERSION
from woonsh_tools.core.theme import make_card
from woonsh_tools.core.ui_helpers import clipboard_support


class SettingsPanel(ttk.Frame):
    """Settings tab: service configuration + update checker."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.columnconfigure(0, weight=1)

        row = 0

        # -- Gemini --
        gemini = make_card(self, "Gemini API")
        gemini.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        gemini.columnconfigure(1, weight=1)

        ttk.Label(gemini, text="API-ключ:").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self.var_key = tk.StringVar(value=app.cfg.get("gemini_key", ""))
        key_entry = ttk.Entry(gemini, textvariable=self.var_key, show="*")
        key_entry.grid(row=0, column=1, sticky="ew")
        clipboard_support(key_entry)
        ttk.Button(gemini, text="Сохранить",
                   command=self._save_key).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(gemini, text="AI Studio",
                   command=lambda: webbrowser.open(
                       "https://aistudio.google.com/api-keys")).grid(
            row=1, column=0, sticky="w", pady=(8, 0))

        row += 1

        # -- Google Drive --
        drive = make_card(self, "Google Drive")
        drive.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        drive.columnconfigure(1, weight=1)

        ttk.Label(drive, text="ID папки:").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self.var_drive = tk.StringVar(
            value=app.cfg.get("drive_folder", ""))
        drive_entry = ttk.Entry(drive, textvariable=self.var_drive)
        drive_entry.grid(row=0, column=1, sticky="ew")
        clipboard_support(drive_entry)
        ttk.Button(drive, text="Сохранить",
                   command=self._save_drive).grid(
            row=0, column=2, padx=(8, 0))

        ttk.Label(drive, text="rclone:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.var_rclone = tk.StringVar(
            value=app.cfg.get("rclone", "не настроен"))
        ttk.Label(drive, textvariable=self.var_rclone).grid(
            row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Button(drive, text="Скачать rclone",
                   command=self._download_rclone).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0))

        row += 1

        # -- Repository --
        repo = make_card(self, "Обновления")
        repo.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        repo.columnconfigure(1, weight=1)

        ttk.Label(repo, text=f"Версия: {VERSION}").grid(
            row=0, column=0, sticky="w", columnspan=2)
        ttk.Label(repo, text="Репозиторий:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.var_repo = tk.StringVar(
            value=app.cfg.get("update_repo", ""))
        repo_entry = ttk.Entry(repo, textvariable=self.var_repo)
        repo_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        clipboard_support(repo_entry)
        ttk.Button(repo, text="Проверить обновления",
                   command=self._check_updates).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0))

        row += 1

        # -- Wizard --
        wizard = make_card(self, "Мастер настройки")
        wizard.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(wizard, text="Запустить мастер настройки",
                   command=self._show_wizard).grid(row=0, column=0, sticky="w")

        row += 1

        # -- Status --
        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(row=row, column=0, sticky="w", pady=8)

    def _save_key(self):
        key = self.var_key.get().strip()
        if not key:
            self.status_var.set("Введите API-ключ.")
            return
        self.app.cfg["gemini_key"] = key
        self.app._save_config()
        self.status_var.set("Ключ Gemini сохранён.")

    def _save_drive(self):
        from woonsh_tools.drive.rclone import drive_folder_id
        fid = drive_folder_id(self.var_drive.get())
        self.app.cfg["drive_folder"] = fid
        self.app._save_config()
        self.status_var.set(
            "ID папки сохранён: " + fid if fid
            else "ID папки очищен.")

    def _download_rclone(self):
        import os
        import threading
        self.status_var.set("Скачиваю rclone…")

        def worker():
            try:
                from woonsh_tools.drive.rclone import download_rclone
                tools_dir = os.path.join(self.app.app_data_dir, "rclone")
                os.makedirs(tools_dir, exist_ok=True)
                path = download_rclone(tools_dir)
                self.app.cfg["rclone"] = path
                self.app._save_config()
                self.var_rclone.set(path)
                self.app.emit("status", "rclone готов: " + path)
            except Exception as exc:
                self.app.emit("status", "Ошибка: " + str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _check_updates(self):
        from woonsh_tools.update.updater import show_update_window
        show_update_window(self.app)

    def _show_wizard(self):
        from woonsh_tools.update.wizard import show
        show(self.app)
