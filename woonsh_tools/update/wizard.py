"""
First-run setup wizard — 7 steps, each integration optional.
From X-File setup_wizard.py — adapted for Woonsh Tools.
"""
import json
import math
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from urllib.request import Request, urlopen

from woonsh_tools import VERSION
from woonsh_tools.core.ui_helpers import clipboard_support

FOLDERS = (
    "documents", "profiles", "rclone",
    "ads", "ads_history", "updates",
    "company_search_documents", "document_stock",
)


def prepare(folder):
    for name in FOLDERS:
        (Path(folder) / name).mkdir(parents=True, exist_ok=True)


def show(app):
    current = getattr(app, "setup_window", None)
    if current and current.winfo_exists():
        current.deiconify()
        current.lift()
        return current
    app.setup_window = Wizard(app)
    return app.setup_window


class Wizard(tk.Toplevel):
    titles = [
        "Добро пожаловать", "rclone", "Google Drive",
        "Gemini", "Telegram", "Таблица по ссылке",
        "Добро пожаловать",
    ]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.folder = Path(app.app_data_dir)
        self.title("Первый запуск — Woonsh Tools")
        self.geometry("820x680")
        if app.root.winfo_viewable():
            self.transient(app.root)
        self.step = 0
        self.busy = False
        self.events = queue.Queue()
        self.download_started = False
        self.configure(background="#100c1c")

        self.hero = tk.Canvas(
            self, height=118, bg="#100c1c", highlightthickness=0)
        self.hero.pack(fill="x")
        self.animation_value = 0.0
        self.phase = 0

        self.caption = ttk.Label(self, style="H.TLabel")
        self.caption.pack(anchor="w", padx=24, pady=(4, 8))
        self._animation_job = self.after(30, self._animate)

        self.body = ttk.Frame(self, padding=18)
        self.body.pack(fill="both", expand=True)

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status,
                  wraplength=690).pack(fill="x", padx=18, pady=8)

        bar = ttk.Frame(self, padding=18)
        bar.pack(fill="x")
        self.back = ttk.Button(bar, text="Назад",
                               command=lambda: self._go(-1))
        self.back.pack(side="left")
        ttk.Button(bar, text="Настроить позже",
                   command=self._later).pack(side="left", padx=8)
        self.next = ttk.Button(bar, text="Далее / пропустить",
                               command=lambda: self._go(1))
        self.next.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._later)
        try:
            prepare(self.folder)
        except OSError as exc:
            self.status.set("Не удалось создать папки: " + str(exc))
        self._render()
        self._poll_job = self.after(200, self._poll)

    def destroy(self):
        for name in ("_animation_job", "_poll_job", "_download_job"):
            job = getattr(self, name, None)
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()
        if getattr(self.app, "_onboarding", False):
            self.app._onboarding = False
            self.app.root.deiconify()
            self.app.root.lift()

    def _label(self, text):
        ttk.Label(self.body, text=text, wraplength=680,
                  justify="left").pack(anchor="w", pady=8)

    def _button(self, text, command):
        ttk.Button(self.body, text=text,
                   command=command).pack(anchor="w", pady=6)

    def _entry(self, label, variable, secret=False):
        self._label(label)
        entry = ttk.Entry(self.body, textvariable=variable,
                          show="*" if secret else "")
        entry.pack(fill="x")
        clipboard_support(entry)
        return entry

    def _render(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.caption.configure(
            text=f"{self.step + 1} / 7 · {self.titles[self.step]}")
        self.back.state(["disabled"] if self.step == 0 else ["!disabled"])
        self.next.configure(
            text="Завершить" if self.step == 6 else "Далее / пропустить")
        self.status.set("")
        getattr(self, f"_step{self.step}")()

    def _step0(self):
        self._label(
            "Мастер подготовит программу и поможет подключить ваши "
            "аккаунты. Любой сервис можно пропустить и настроить позже. "
            "Пароли и коды вводите только в окнах входа.")
        self._label(
            "Папки созданы в:\n" + str(self.folder)
            + "\n\nОбновления EXE сохраняют эти данные.")
        self._label(
            "На следующем шаге rclone скачается с официального сайта. "
            "Вход в Google выполняется в браузере; Gemini использует "
            "ваш API-ключ, Telegram — ваш аккаунт.")

    def _step1(self):
        self._label(
            "rclone нужен для Google Drive. Устанавливается только "
            "в папку данных приложения.")
        self.download_progress = ttk.Progressbar(
            self.body, mode="determinate")
        self.download_progress.pack(fill="x", pady=10)
        self._button("Скачать / повторить загрузку", self._download)
        self._button("Выбрать уже скачанный rclone.exe", self._pick_rclone)
        from woonsh_tools.drive.rclone import find_rclone
        exe = find_rclone(self.app.cfg.get("rclone", ""))
        if exe:
            self.status.set("rclone найден: " + exe)
        elif not self.download_started:
            self.download_started = True
            self._download_job = self.after(50, self._download)

    def _step2(self):
        self._label(
            "Нажмите Подключить Google Drive. Откроется rclone и "
            "браузер: выберите свой Google-аккаунт и разрешите доступ.")
        self.drive_var = tk.StringVar(
            value=self.app.cfg.get("drive_folder", ""))
        self._entry(
            "Папка Google Drive — ссылка или ID (необязательно)",
            self.drive_var)
        self._button("Подключить Google Drive", self._drive_connect)
        self._button("Проверить доступ", self._drive_check)

    def _step3(self):
        self._label(
            "Создайте Gemini API-ключ в Google AI Studio, вставьте "
            "и нажмите Сохранить и проверить. Ключ шифруется средствами "
            "Windows. Проверка списка моделей не генерирует рекламу.")
        import webbrowser
        self._button(
            "Открыть Google AI Studio",
            lambda: webbrowser.open("https://aistudio.google.com/api-keys"))
        self.key_var = tk.StringVar(
            value=self.app.cfg.get("gemini_key", ""))
        self._entry("Gemini API-ключ", self.key_var, True)
        self._button("Сохранить и проверить", self._gemini)

    def _step4(self):
        self._label(
            "Создайте приложение Telegram API на my.telegram.org, "
            "затем выберите способ входа в разделе «Поиск фирм».")
        import webbrowser
        self._button(
            "Открыть my.telegram.org",
            lambda: webbrowser.open("https://my.telegram.org"))
        self._label(
            "Вход в Telegram настраивается в панели «Поиск фирм» "
            "через кнопки QR и номер телефона.")

    def _step5(self):
        self._label(
            "Подключите Excel, CSV или Google Sheets по ссылке. "
            "Таблица сохранится локально для следующих запусков.")
        self.table_var = tk.StringVar(
            value=self.app.cfg.get("profile_url", ""))
        self._entry("Ссылка на таблицу", self.table_var)
        self._button("Загрузить таблицу", self._load_table)
        self._label(
            "Назначение колонок выполняется в разделе «Профили». "
            "Обязательно проверьте Название профиля и Платежная информация.")

    def _step6(self):
        ttk.Label(self.body, text="Добро пожаловать\nв Woonsh Tools ✦",
                  style="Title.TLabel", justify="left").pack(
            anchor="w", pady=(6, 16))
        self._label(
            "Основная настройка завершена. Пропущенные сервисы можно "
            "подключить позже через «Настройки».")
        self._label(
            "Таблицы и документы загрузите в соответствующих разделах. "
            "Для обновления используйте кнопку «Обновления».")
        self._label("Сохранённые подключения:\n" + self._summary())

    def _animate(self):
        if not self.winfo_exists():
            return
        self.phase += 0.10
        target = (self.step + 1) / 7
        self.animation_value += (target - self.animation_value) * 0.14
        width = max(700, self.hero.winfo_width())
        self.hero.delete("all")
        self.hero.create_text(
            24, 28, text="WOONSH TOOLS",
            fill="#f2ecff", font=("Segoe UI", 19, "bold"), anchor="w")
        self.hero.create_text(
            24, 56,
            text="Ваше пространство · Ваши подключения · Всё в одном месте",
            fill="#a99bbf", font=("Segoe UI", 10), anchor="w")
        self.hero.create_rectangle(
            24, 87, width - 24, 91, fill="#292038", outline="")
        self.hero.create_rectangle(
            24, 87, 24 + (width - 48) * self.animation_value, 91,
            fill="#8738ef", outline="")
        for i in range(7):
            x = 24 + (width - 48) * ((i + 1) / 7)
            radius = 4 + (math.sin(self.phase) * 1.2 if i == self.step else 0)
            color = "#c697ff" if i <= self.step else "#453458"
            self.hero.create_oval(
                x - radius, 89 - radius, x + radius, 89 + radius,
                fill=color, outline="")
        self._animation_job = self.after(35, self._animate)

    def _summary(self):
        from woonsh_tools.drive.rclone import find_rclone
        lines = [
            "rclone: " + (
                "найден" if find_rclone(self.app.cfg.get("rclone", ""))
                else "не настроен"),
            "Google Drive: " + (
                self.app.cfg.get("drive_folder", "") or "не настроен"),
            "Gemini: " + (
                "ключ сохранён" if self.app.cfg.get("gemini_key")
                else "пропущен"),
            "Таблица: " + (
                self.app.cfg.get("profile_url", "") or "пропущена"),
        ]
        return "\n".join(lines)

    def _active(self):
        return self.busy or self.app.working

    def _go(self, direction):
        if self._active():
            self.status.set("Дождитесь завершения текущей операции.")
            return
        if self.step == 6 and direction == 1:
            self.app.cfg["setup_pending"] = False
            self.app.cfg["setup_complete"] = True
            self.app._save_config()
            self.destroy()
            return
        self.step = max(0, min(6, self.step + direction))
        self._render()

    def _later(self):
        if self._active():
            self.status.set("Операция ещё выполняется.")
            return
        self.app.cfg["setup_pending"] = False
        self.app.cfg["setup_deferred"] = True
        self.app._save_config()
        self.destroy()

    def _run(self, fn):
        if self._active():
            return
        self.busy = True
        self.status.set("Выполняется…")

        def worker():
            try:
                self.events.put(("ok", fn()))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        if not self.winfo_exists():
            return
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "status":
                self.status.set(value)
                continue
            if kind == "progress":
                if self.step == 1 and hasattr(self, "download_progress"):
                    done, total = value
                    self.download_progress.configure(
                        maximum=max(total, done, 1), value=done)
                continue
            self.busy = False
            if kind == "rclone":
                self.app.cfg["rclone"] = value
                self.app._save_config()
                self.status.set(
                    "rclone скачан. Можно перейти к Google Drive.")
            else:
                self.status.set(str(value))
        self._poll_job = self.after(250, self._poll)

    def _download(self):
        if self.step != 1:
            return

        def work():
            from woonsh_tools.drive.rclone import download_rclone
            tools = self.folder / "rclone"
            tools.mkdir(parents=True, exist_ok=True)
            path = download_rclone(
                str(tools),
                lambda done, total: self.events.put(
                    ("progress", (done, total))),
                lambda message: self.events.put(("status", message)))
            self.events.put(("rclone", path))
            return "rclone готов."
        self._run(work)

    def _pick_rclone(self):
        if self._active():
            return
        filename = filedialog.askopenfilename(
            parent=self, title="Выберите rclone.exe",
            filetypes=[("rclone", "rclone.exe")])
        if filename:
            self.app.cfg["rclone"] = filename
            self.app._save_config()
            self.status.set("rclone выбран: " + filename)

    def _drive_connect(self):
        if self._active():
            return
        from woonsh_tools.drive.rclone import find_rclone, drive_folder_id
        exe = find_rclone(self.app.cfg.get("rclone", ""))
        if not exe:
            self.status.set("Сначала скачайте rclone (шаг 2).")
            return
        folder = drive_folder_id(self.drive_var.get())
        if folder:
            self.app.cfg["drive_folder"] = folder
            self.app._save_config()
        self.status.set("Запустите rclone config в терминале для авторизации.")

    def _drive_check(self):
        if self._active():
            return
        from woonsh_tools.drive.rclone import (
            find_rclone, drive_folder_id, check_drive)
        exe = find_rclone(self.app.cfg.get("rclone", ""))
        if not exe:
            self.status.set("rclone не найден.")
            return
        fid = drive_folder_id(self.drive_var.get())

        def work():
            ok, msg = check_drive(exe, fid)
            return msg
        self._run(work)

    def _gemini(self):
        key = self.key_var.get().strip()
        if not key:
            self.status.set("Введите API-ключ.")
            return

        def work():
            self.app.cfg["gemini_key"] = key
            self.app._save_config()
            req = Request(
                "https://generativelanguage.googleapis.com/v1beta/models"
                "?pageSize=1",
                headers={"x-goog-api-key": key})
            try:
                with urlopen(req, timeout=20) as response:
                    data = json.loads(response.read())
                if not data.get("models"):
                    raise ValueError("Список моделей пуст.")
            except Exception:
                return ("Ключ сохранён, но доступ к Gemini не подтверждён. "
                        "Проверьте ключ и интернет.")
            return "Gemini подключён: ключ сохранён, список моделей доступен."
        self._run(work)

    def _load_table(self):
        if self._active():
            return
        url = self.table_var.get().strip()
        if not url.startswith(("https://", "http://")):
            self.status.set("Вставьте ссылку HTTP/HTTPS.")
            return
        self.app.cfg["profile_url"] = url
        self.app._save_config()
        self.status.set("Ссылка сохранена. Загрузите таблицу в «Профилях».")
