"""
Ads CSV panel — UI for batch generation, queue, export.
From X-File ads_bridge.py, adapted for woonsh_tools.
"""

import json
import os
import re
import threading
import time
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from urllib.parse import urlparse
import queue as queuemod


def csv_basename(item):
    name = (item.get("company") or item.get("name") or "Компания").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:120]
    name = name.rstrip(" .") or "Компания"
    if re.fullmatch(
            r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",
            name, re.IGNORECASE):
        name = "_" + name
    return name


def safe_error(message, api_key=""):
    text = str(message)
    if api_key:
        text = text.replace(api_key, "[скрыто]")
    text = re.sub(r"AIza[\w-]+", "[скрыто]", text)
    text = re.sub(
        r"(?i)(key|token|authorization)([=:\s]+)[^\s,;]+",
        r"\1\2[скрыто]", text)
    return text[:1200]


class AdsPanel(ttk.Frame):
    """Генератор CSV-кампаний Google Ads."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.app_dir = Path(app.app_data_dir)

        from woonsh_tools.ads import generator as engine
        self.engine = engine
        self.engine.HISTORY_DIR = self.app_dir / "ads_history"
        self.engine.HISTORY_KEEP = 10000

        self.events = queuemod.Queue()
        self.cancel_batch = threading.Event()
        self.batch_running = False

        self.queue_path = self.app_dir / "ads_queue.json"
        self.queue_lock = threading.Lock()
        try:
            self.saved_queue = json.loads(
                self.queue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.saved_queue = []

        self.key_path = self.app_dir / "gemini_key.dpapi"
        self.settings_path = self.app_dir / "ads_settings.json"
        try:
            self.settings = json.loads(
                self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="URL сайта:").grid(
            row=0, column=0, sticky="w")
        self.var_url = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_url).grid(
            row=0, column=1, sticky="ew", padx=8)

        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky="w", pady=(0, 8))
        for title, command in [
            ("Генерировать", self._generate),
            ("Остановить", self._cancel),
            ("Продолжить очередь", self._resume),
            ("Экспорт CSV…", self._export),
        ]:
            ttk.Button(buttons, text=title, command=command).pack(
                side="left", padx=(0, 6))

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        columns = ("site", "topic", "status")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            selectmode="extended")
        for name, title, width in zip(
                columns,
                ["Сайт", "Тематика", "Статус"],
                [300, 250, 200]):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(
            row=3, column=0, sticky="w", pady=8)
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.grid(row=4, column=0, sticky="we")

        self._next_refresh = 0
        self._refresh_history()
        self.after(250, self._tick)

    def _tick(self):
        if not self.winfo_exists():
            return
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == "status":
                _, key, label, message, count, total = event
                self.status_var.set(message)
                self.progress.configure(maximum=max(1, total), value=count)
                self._next_refresh = 0
            elif event[0] == "done":
                self.batch_running = False
                self.status_var.set(event[1])
                self._next_refresh = 0
        if time.monotonic() >= self._next_refresh:
            self._refresh_history()
            self._next_refresh = time.monotonic() + 5
        self.after(250, self._tick)

    def _refresh_history(self):
        self.tree.delete(*self.tree.get_children())
        try:
            history = self.engine.history_list()
        except Exception:
            history = []
        for h in history[:50]:
            urls = ", ".join(h.get("urls", []))
            topics = ", ".join(h.get("topics", []))
            status = ("Ошибки" if h.get("errors")
                      else ("Проверено" if h.get("manual_approved")
                            else "Готово"))
            self.tree.insert("", "end", iid=h["id"],
                             values=(urls, topics, status))

    def _generate(self):
        if self.batch_running:
            self.status_var.set("Генерация уже идёт.")
            return
        url = self.var_url.get().strip()
        if not url:
            self.status_var.set("Введите URL сайта.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        from woonsh_tools.ads.settings import Settings
        dialog = Settings(
            self, self.settings, 1, self.engine, self.key_path)
        self.wait_window(dialog)
        if not dialog.result:
            return
        settings, api_key = dialog.result
        self.settings = settings
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(settings, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.settings_path)
        except OSError:
            pass

        self.cancel_batch.clear()
        self.batch_running = True
        job_id = os.urandom(8).hex()
        prog = self.engine.Progress()
        self.engine.JOBS[job_id] = prog

        def worker():
            try:
                payload = {
                    "api_key": api_key,
                    "urls": [url],
                    "settings": dict(settings),
                }
                prog.result = self.engine.generate(payload, prog)
                ready = any(
                    site.get("csv") and not site.get("error")
                    for site in prog.result.get("sites", []))
                if not ready:
                    details = "; ".join(
                        safe_error(st.get("error", ""), api_key)
                        for st in prog.result.get("sites", [])
                        if st.get("error"))
                    raise ValueError(details or "Модель не создала кампанию.")
                self.engine.save_history(job_id, prog, [url])
                label = ("Нужно исправить" if prog.result.get("errors")
                         else "Готово")
                self.events.put((
                    "status", url, label,
                    f"{url}: {label}", 1, 1))
            except Exception as exc:
                prog.error = safe_error(str(exc), api_key)
                if prog.state:
                    for site in prog.state.get("sites", []):
                        if site.get("error"):
                            site["error"] = safe_error(
                                site["error"], api_key)
                    self.engine.save_history(job_id, prog, [url])
                self.events.put((
                    "status", url, "Ошибка",
                    f"Ошибка: {prog.error[:160]}", 1, 1))
            finally:
                if prog.state:
                    prog.state.pop("api_key", None)
                prog.finished = True
            self.events.put(("done", "Генерация завершена."))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel(self):
        self.cancel_batch.set()
        self.status_var.set("Остановка после текущего запроса…")

    def _resume(self):
        pending = [e for e in self.saved_queue if e.get("state") != "done"]
        if not pending:
            self.status_var.set("Нет незавершённых заданий.")
            return
        self.status_var.set(f"Найдено {len(pending)} незавершённых.")

    def _export(self):
        selection = self.tree.selection()
        if not selection:
            history = self.engine.history_list()
            ready = [h for h in history if h.get("rows", 0) > 0]
        else:
            ready = []
            for hid in selection:
                try:
                    data = self.engine.history_load(hid)
                    if data["result"].get("rows"):
                        ready.append({"id": hid})
                except Exception:
                    pass
        if not ready:
            self.status_var.set("Нет готовых CSV для экспорта.")
            return

        if len(ready) == 1:
            result = self.engine.history_load(ready[0]["id"])["result"]
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".csv",
                initialfile="ads.csv",
                filetypes=[("CSV", "*.csv")])
            if path:
                Path(path).write_text(
                    result["csv"], encoding="utf-8-sig", newline="")
                self.status_var.set("CSV сохранён.")
        else:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".zip",
                initialfile="ads.zip",
                filetypes=[("ZIP", "*.zip")])
            if path:
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                    used = set()
                    for h in ready:
                        result = self.engine.history_load(h["id"])["result"]
                        name = "ads"
                        base, n = name, 2
                        while name in used:
                            name, n = f"{base}_{n}", n + 1
                        used.add(name)
                        zf.writestr(
                            name + ".csv",
                            ("﻿" + result["csv"]).encode("utf-8"))
                self.status_var.set("ZIP сохранён.")


class ReviewPanel(ttk.Frame):
    """Проверка и одобрение рекламных кампаний."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Button(buttons, text="Загрузить результат",
                   command=self._load).pack(side="left")
        ttk.Button(buttons, text="Проверить",
                   command=self._validate).pack(side="left", padx=8)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(tree_frame, wrap="word")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(
            value="Загрузите результат генерации для проверки.")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(
            row=2, column=0, sticky="w", pady=8)
        self._result = None

    def _load(self):
        from woonsh_tools.ads import generator as engine
        history = engine.history_list()
        if not history:
            self.status_var.set("Нет истории генерации.")
            return
        latest = history[0]
        data = engine.history_load(latest["id"])
        self._result = data["result"]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for site in self._result.get("sites", []):
            self.text.insert("end",
                             f"URL: {site.get('url', '')}\n"
                             f"Тематика: {site.get('topic', '')}\n"
                             f"Статистика: {site.get('stats', {})}\n\n")
        if self._result.get("errors"):
            self.text.insert("end", "ОШИБКИ:\n")
            for e in self._result["errors"]:
                self.text.insert("end", f"  • {e}\n")
        if self._result.get("warnings"):
            self.text.insert("end", "\nПРЕДУПРЕЖДЕНИЯ:\n")
            for w in self._result["warnings"]:
                self.text.insert("end", f"  • {w}\n")
        self.text.configure(state="disabled")
        self.status_var.set(f"Загружен результат: {latest['id']}")

    def _validate(self):
        if not self._result:
            self.status_var.set("Сначала загрузите результат.")
            return
        errors = self._result.get("errors", [])
        warnings = self._result.get("warnings", [])
        self.status_var.set(
            f"Ошибок: {len(errors)}, предупреждений: {len(warnings)}")
