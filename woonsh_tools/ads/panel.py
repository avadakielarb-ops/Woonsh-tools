"""
Панели Google Ads: генератор CSV и проверка рекламы.
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path


class AdsPanel(ttk.Frame):
    """Генератор CSV-кампаний Google Ads."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.stop = threading.Event()
        self.working = False
        self.results = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Тема кампании:").grid(
            row=0, column=0, sticky="w")
        self.var_topic = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_topic).grid(
            row=0, column=1, sticky="ew", padx=8)

        ttk.Label(top, text="Страна:").grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self.var_country = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_country).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(4, 0))

        ttk.Label(top, text="Язык:").grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self.var_lang = tk.StringVar(value="English")
        ttk.Entry(top, textvariable=self.var_lang).grid(
            row=2, column=1, sticky="ew", padx=8, pady=(4, 0))

        opts = ttk.Frame(self)
        opts.grid(row=1, column=0, sticky="w", pady=(0, 8))

        ttk.Label(opts, text="Кол-во:").pack(side="left")
        self.var_count = tk.IntVar(value=1)
        ttk.Spinbox(opts, from_=1, to=20, width=4,
                     textvariable=self.var_count).pack(side="left", padx=4)

        ttk.Label(opts, text="Режим:").pack(side="left", padx=(12, 0))
        self.var_mode = tk.StringVar(value="API")
        ttk.Combobox(opts, textvariable=self.var_mode,
                     values=["API", "Браузер (CDP)"],
                     state="readonly", width=16).pack(side="left", padx=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(buttons, text="Генерировать", style="Accent.TButton",
                   command=self._generate).pack(side="left")
        ttk.Button(buttons, text="Стоп",
                   command=self._stop).pack(side="left", padx=8)
        ttk.Button(buttons, text="Экспорт CSV",
                   command=self._export).pack(side="left")
        ttk.Button(buttons, text="Очистить очередь",
                   command=self._clear_queue).pack(side="left", padx=8)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=3, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("topic", "headlines", "status"),
            show="headings", selectmode="browse")
        self.tree.heading("topic", text="Тема")
        self.tree.heading("headlines", text="Заголовки")
        self.tree.heading("status", text="Статус")
        self.tree.column("topic", width=200)
        self.tree.column("headlines", width=500)
        self.tree.column("status", width=100)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(
            row=4, column=0, sticky="w", pady=8)

        self._load_results()

    def _queue_path(self):
        return os.path.join(self.app.app_data_dir, "ads_batch.json")

    def _results_path(self):
        return os.path.join(self.app.app_data_dir, "ads_results.json")

    def _load_results(self):
        try:
            with open(self._results_path(), encoding="utf-8") as f:
                self.results = json.load(f)
        except (OSError, ValueError):
            self.results = []
        self._refresh_tree()

    def _save_results(self):
        tmp = self._results_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._results_path())

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for c in self.results:
            headlines = c.get("headlines", [])
            preview = " | ".join(headlines[:3])
            if len(headlines) > 3:
                preview += f" (+{len(headlines)-3})"
            self.tree.insert("", "end", values=(
                c.get("topic", ""), preview, "✓"))

    def _generate(self):
        topic = self.var_topic.get().strip()
        if not topic:
            self.status_var.set("Введите тему кампании.")
            return
        api_key = self.app.cfg.get("gemini_api_key", "")
        mode = "browser" if "CDP" in self.var_mode.get() else "api"
        if mode == "api" and not api_key:
            self.status_var.set("Нужен Gemini API key в настройках.")
            return
        if self.working:
            self.status_var.set("Генерация уже идёт.")
            return

        self.working = True
        self.stop.clear()
        count = self.var_count.get()
        country = self.var_country.get().strip()
        language = self.var_lang.get().strip() or "English"

        from woonsh_tools.ads.generator import BatchQueue
        queue = BatchQueue(self._queue_path())
        queue.add(topic, country, language, count)
        self.status_var.set(f"В очереди: {queue.pending_count()}")

        def worker():
            try:
                from woonsh_tools.core.gemini import GeminiClient
                client = GeminiClient(keys=[api_key])
                tab = None
                if mode == "browser":
                    from woonsh_tools.core.cdp import (
                        chrome_path, launch_chrome, open_gemini_tab, cdp_alive, Tab)
                    exe = chrome_path(self.app.cfg.get("chrome_path", ""))
                    if not exe:
                        self.app.emit("status", "Chrome не найден.")
                        return
                    if not cdp_alive():
                        launch_chrome(exe)
                    target = open_gemini_tab()
                    tab = Tab(target["webSocketDebuggerUrl"])

                def progress(done, total, msg):
                    self.app.emit("status", f"Генерация: {msg}")

                new = queue.process(
                    client, api_key=api_key, mode=mode,
                    tab=tab, on_progress=progress, stop=self.stop)
                self.results.extend(new)
                self._save_results()

                def update():
                    self._refresh_tree()
                    self.status_var.set(
                        f"Готово: {len(new)} новых кампаний.")
                self.after(0, update)

                if tab:
                    tab.close()
            except Exception as exc:
                self.app.emit("status", f"Ошибка: {exc}")
            finally:
                self.working = False

        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        self.stop.set()
        self.status_var.set("Остановка…")

    def _export(self):
        if not self.results:
            self.status_var.set("Нет кампаний для экспорта.")
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        from woonsh_tools.ads.generator import export_csv
        export_csv(self.results, path)
        self.status_var.set(f"Экспортировано: {path}")

    def _clear_queue(self):
        from woonsh_tools.ads.generator import BatchQueue
        queue = BatchQueue(self._queue_path())
        queue.clear_done()
        self.status_var.set("Очередь очищена.")


class ReviewPanel(ttk.Frame):
    """Проверка и одобрение рекламных кампаний."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.campaigns = []
        self.approved = set()
        self._load_approved()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Button(buttons, text="Загрузить CSV",
                   command=self._load_csv).pack(side="left")
        ttk.Button(buttons, text="Из генератора",
                   command=self._from_generator).pack(side="left", padx=8)
        ttk.Button(buttons, text="Проверить все",
                   command=self._validate_all).pack(side="left")
        ttk.Button(buttons, text="Одобрить выбранное",
                   command=self._approve).pack(side="left", padx=8)
        ttk.Button(buttons, text="Экспорт одобренных",
                   command=self._export_approved).pack(side="left")

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("topic", "headlines", "errors", "status"),
            show="headings", selectmode="extended")
        self.tree.heading("topic", text="Тема")
        self.tree.heading("headlines", text="Заголовки")
        self.tree.heading("errors", text="Ошибки")
        self.tree.heading("status", text="Статус")
        self.tree.column("topic", width=150)
        self.tree.column("headlines", width=350)
        self.tree.column("errors", width=200)
        self.tree.column("status", width=100)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(value="Загрузите кампании для проверки.")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(
            row=2, column=0, sticky="w", pady=8)

    def _approved_path(self):
        return os.path.join(self.app.app_data_dir, "ads_approved.json")

    def _load_approved(self):
        try:
            with open(self._approved_path(), encoding="utf-8") as f:
                self.approved = set(json.load(f))
        except (OSError, ValueError):
            self.approved = set()

    def _save_approved(self):
        tmp = self._approved_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self.approved), f)
        os.replace(tmp, self._approved_path())

    def _load_csv(self):
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        import csv
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            self.campaigns = []
            for row in reader:
                campaign = {
                    "topic": row.get("Campaign", ""),
                    "headlines": [row.get(f"Headline {i}", "")
                                  for i in range(1, 16) if row.get(f"Headline {i}")],
                    "descriptions": [row.get(f"Description {i}", "")
                                     for i in range(1, 5) if row.get(f"Description {i}")],
                    "path1": row.get("Path 1", ""),
                    "path2": row.get("Path 2", ""),
                    "keywords": [k.strip() for k in
                                 row.get("Keywords", "").split(";") if k.strip()],
                }
                self.campaigns.append(campaign)
        self._refresh_tree()
        self.status_var.set(f"Загружено {len(self.campaigns)} кампаний.")

    def _from_generator(self):
        results_path = os.path.join(self.app.app_data_dir, "ads_results.json")
        try:
            with open(results_path, encoding="utf-8") as f:
                self.campaigns = json.load(f)
        except (OSError, ValueError):
            self.status_var.set("Нет сгенерированных кампаний.")
            return
        self._refresh_tree()
        self.status_var.set(f"Загружено {len(self.campaigns)} кампаний.")

    def _refresh_tree(self):
        from woonsh_tools.ads.validation import validate_campaign, approval_hash
        self.tree.delete(*self.tree.get_children())
        for c in self.campaigns:
            headlines = " | ".join(c.get("headlines", [])[:3])
            errors = validate_campaign(c)
            ahash = approval_hash(c)
            if ahash in self.approved:
                status = "✓ Одобрено"
            elif errors:
                status = f"✗ {len(errors)} ош."
            else:
                status = "○ На проверке"
            error_text = "; ".join(errors[:3])
            self.tree.insert("", "end", values=(
                c.get("topic", ""), headlines, error_text, status))

    def _validate_all(self):
        self._refresh_tree()
        from woonsh_tools.ads.validation import validate_campaign
        total_errors = sum(
            len(validate_campaign(c)) for c in self.campaigns)
        self.status_var.set(
            f"Проверено: {len(self.campaigns)} кампаний, "
            f"{total_errors} ошибок.")

    def _approve(self):
        from woonsh_tools.ads.validation import validate_campaign, approval_hash
        selection = self.tree.selection()
        if not selection:
            self.status_var.set("Выберите кампании.")
            return
        approved = 0
        for item in selection:
            index = self.tree.index(item)
            if index < len(self.campaigns):
                c = self.campaigns[index]
                errors = validate_campaign(c)
                if not errors:
                    self.approved.add(approval_hash(c))
                    approved += 1
        self._save_approved()
        self._refresh_tree()
        self.status_var.set(f"Одобрено: {approved}")

    def _export_approved(self):
        from woonsh_tools.ads.validation import approval_hash
        from woonsh_tools.ads.generator import export_csv
        approved = [c for c in self.campaigns
                    if approval_hash(c) in self.approved]
        if not approved:
            self.status_var.set("Нет одобренных кампаний.")
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        export_csv(approved, path)
        self.status_var.set(f"Экспортировано {len(approved)} кампаний.")
