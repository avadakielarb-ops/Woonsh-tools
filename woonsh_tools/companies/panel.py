"""
Панель «Поиск фирм» — CompaniesPanel для Sidebar.

Объединяет:
- X-File CompanySearchPanel: форма поиска, Treeview результатов,
  DnB/реестр/Gemini провайдеры, Telegram, PDF, экспорт
- Фирмы: очередь заданий, мультигео, человек-в-цикле

Хранение: company_search.json в APP_DIR (без DPAPI для кроссплатформенности).
"""

import asyncio
import json
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog

from woonsh_tools.companies.search import (
    LANGUAGES, PROVIDERS, bot_status, country_languages, discover_gemini,
    export_csv, grounded_request, http_url, now, summarize,
    translate_keyword, verify_website,
)


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(path))


class CompaniesPanel(ttk.Frame):
    """Панель поиска фирм для Sidebar."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=14)
        self.app = app
        self.folder = Path(app.app_data_dir)
        self.path = self.folder / "company_search.json"
        self.telegram_path = self.folder / "telegram.json"
        self.data = _load(self.path)
        if "rows" not in self.data:
            self.data["rows"] = []
        if "checks" not in self.data:
            self.data["checks"] = {}
        self.events = queue.Queue()
        self.busy = False
        self.stop = threading.Event()
        self.diagnostics = ""

        self._build_ui()
        self.refresh()
        self.after(200, self.poll)

    # ------------------------------------------------------------------
    #  UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Заголовок
        ttk.Label(self, text="Поиск фирм", style="Title.TLabel").pack(
            anchor="w", pady=(0, 8))

        # Форма
        form = ttk.Frame(self)
        form.pack(fill="x", pady=8)
        form.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(form, text="Страна").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.country = tk.StringVar(value=self.data.get("country", "Finland"))
        countries = sorted(LANGUAGES.keys())
        self.cmb_country = ttk.Combobox(
            form, textvariable=self.country, values=countries, state="readonly")
        self.cmb_country.grid(row=row, column=1, sticky="ew")

        row += 1
        ttk.Label(form, text="Ключевое слово").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.topic = tk.StringVar(value=self.data.get("topic", ""))
        entry = ttk.Entry(form, textvariable=self.topic)
        entry.grid(row=row, column=1, sticky="ew")

        row += 1
        ttk.Label(form, text="Количество (1–20)").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.count = tk.StringVar(value="5")
        ttk.Spinbox(form, from_=1, to=20, textvariable=self.count, width=8).grid(
            row=row, column=1, sticky="w")

        row += 1
        ttk.Label(form, text="Источник поиска").grid(row=row, column=0, sticky="w", padx=(0, 8))
        remembered = self.data.get("provider", PROVIDERS[0])
        if remembered not in PROVIDERS:
            remembered = PROVIDERS[0]
        self.provider = tk.StringVar(value=remembered)
        ttk.Combobox(form, textvariable=self.provider, values=list(PROVIDERS),
                      state="readonly").grid(row=row, column=1, sticky="ew")

        row += 1
        ttk.Label(form, text="Язык поиска").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.search_language = tk.StringVar()
        self.lang_box = ttk.Combobox(
            form, textvariable=self.search_language, state="readonly")
        self.lang_box.grid(row=row, column=1, sticky="ew")

        def update_languages(*_):
            options = country_languages(self.country.get())
            self.lang_box.configure(values=options)
            self.search_language.set(options[0])
        self.country.trace_add("write", update_languages)
        update_languages()

        row += 1
        ttk.Label(form, text="Язык ключевых слов").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.keyword_source = tk.StringVar(value="Русский")
        ttk.Combobox(form, textvariable=self.keyword_source,
                      values=["Русский", "Українська", "Уже на языке поиска"],
                      state="readonly").grid(row=row, column=1, sticky="ew")

        row += 1
        ttk.Label(form, text="Перевод: MyMemory (онлайн, без Gemini).",
                  style="Muted.TLabel").grid(row=row, column=0, columnspan=2, sticky="w")

        # Опции
        opts = ttk.Frame(self)
        opts.pack(fill="x")
        self.ai_sites = tk.BooleanVar(value=self.data.get("ai_sites", True))
        ttk.Checkbutton(opts,
                        text="Проверять сайты через ИИ",
                        variable=self.ai_sites).pack(anchor="w")
        self.auto_bot = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts,
                        text="Автопроверка через Telegram после поиска",
                        variable=self.auto_bot).pack(anchor="w")

        # Кнопки
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8)
        buttons = [
            ("Найти фирмы", self.search),
            ("Войти в Telegram", self.login),
            ("Проверить выбранные", self.verify),
            ("Остановить", self.stop.set),
            ("Прикрепить PDF", self.attach_pdf),
            ("Копировать", self.copy),
            ("Экспорт CSV", self.export),
        ]
        for text, cmd in buttons:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        # Пояснение
        ttk.Label(self, text="Найденные — кандидаты. Проверка: сайт → Used Companies.",
                  style="Muted.TLabel", wraplength=900).pack(anchor="w")

        # Таблица результатов
        columns = ("name", "address", "site", "website", "bot", "pdf")
        self.tree = ttk.Treeview(
            self, columns=columns, show="headings", selectmode="extended")
        for key, label in zip(columns,
            ["Компания", "Адрес", "Сайт", "Доступность", "Used Companies", "Выписка"]):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=160)
        self.tree.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<Double-1>", lambda e: self.open_source())

        # Статус
        self.status = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status, wraplength=1000).pack(anchor="w")

    # ------------------------------------------------------------------
    #  Данные
    # ------------------------------------------------------------------

    def persist(self):
        _save(self.path, self.data)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.data["rows"]):
            self.tree.insert("", "end", iid=str(i), values=tuple(
                row.get(k, "") for k in ("name", "address", "site", "website", "bot", "pdf")))

    def selected(self):
        return [self.data["rows"][int(i)] for i in self.tree.selection()]

    # ------------------------------------------------------------------
    #  Фоновые операции
    # ------------------------------------------------------------------

    def run_bg(self, fn):
        if self.busy:
            self.status.set("Дождитесь завершения текущей операции.")
            return
        self.busy = True
        self.stop.clear()
        self.status.set("Выполняется…")

        def worker():
            try:
                result = fn()
                self.events.put(("done", result or "Операция завершена."))
            except Exception as exc:
                self.events.put(("done", str(exc)[:500]))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            event = self.events.get()
            if event[0] == "status":
                self.status.set(event[1])
            elif event[0] == "refresh":
                self.refresh()
            elif event[0] == "done":
                self.busy = False
                self.status.set(event[1])
                self.refresh()
        self.after(200, self.poll)

    # ------------------------------------------------------------------
    #  Поиск
    # ------------------------------------------------------------------

    def search(self):
        try:
            count = int(self.count.get())
            if not 1 <= count <= 20:
                raise ValueError()
            if not self.country.get().strip() or not self.topic.get().strip():
                raise ValueError()
        except ValueError:
            self.status.set("Укажите страну, тематику и количество от 1 до 20.")
            return

        country = self.country.get().strip()
        topic = self.topic.get().strip()
        provider = self.provider.get()
        search_language = self.search_language.get()
        keyword_source = self.keyword_source.get()

        def work():
            existing = {
                (r["country"].casefold(), r["name"].casefold())
                for r in self.data["rows"]}
            added = []
            self.data.update(country=country, topic=topic, provider=provider,
                             ai_sites=self.ai_sites.get())
            self.persist()

            def accept(row):
                identity = (row["country"].casefold(), row["name"].casefold())
                if identity not in existing:
                    self.data["rows"].append(row)
                    existing.add(identity)
                    added.append(row)
                    self.persist()
                    self.events.put(("refresh",))

            log = lambda text: self.events.put(("status", text))

            search_topic = topic
            if keyword_source != "Уже на языке поиска":
                src = "uk" if keyword_source == "Українська" else "ru"
                search_topic = translate_keyword(
                    topic, search_language, stop=self.stop, source=src)
            log(f"Запрос: {topic} → {search_topic} [{search_language}]")

            if self.stop.is_set():
                return "Поиск остановлен."

            if provider == "Gemini + Google Search":
                cfg = _load(self.folder / "config.json")
                api_key = cfg.get("gemini_key", "")
                if not api_key:
                    raise ValueError("Gemini API ключ не задан в настройках.")
                models = [
                    "gemini-2.5-flash", "gemini-2.0-flash",
                    "gemini-1.5-flash", "gemini-1.5-pro",
                ]
                rows = discover_gemini(
                    api_key, models, country, search_topic, count,
                    notify=log, stop=self.stop)
                for row in rows:
                    accept(row)
            else:
                log(f"Провайдер {provider}: требуется company_directory.")
                log("DnB и реестр-драйверы подключаются из X-File company_directory.")

            if self.auto_bot.get() and not self.stop.is_set() and added:
                tg = _load(self.telegram_path)
                if not tg.get("session"):
                    raise ValueError("Для автопроверки сначала войдите в Telegram.")
                for row in added:
                    verify_website(row)
                    self.persist()
                asyncio.run(_telegram_check_wrap(tg, added, self.stop, log))
                self.persist()

            prefix = "Поиск остановлен. " if self.stop.is_set() else "Поиск завершён. "
            return prefix + f"Новых фирм: {len(added)}."

        self.run_bg(work)

    # ------------------------------------------------------------------
    #  Telegram
    # ------------------------------------------------------------------

    def login(self):
        if self.busy:
            return
        tg = _load(self.telegram_path)
        if not tg.get("api_id") or not tg.get("api_hash"):
            api_id = simpledialog.askinteger(
                "Telegram API", "Введите api_id из my.telegram.org:", parent=self, minvalue=1)
            if not api_id:
                return
            api_hash = simpledialog.askstring(
                "Telegram API", "Введите api_hash (32 символа):", parent=self, show="*")
            if not api_hash or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash.strip()):
                self.status.set("api_hash должен содержать 32 шестнадцатеричных символа.")
                return
            tg.update(api_id=api_id, api_hash=api_hash.strip())

        if not tg.get("session"):
            phone = simpledialog.askstring(
                "Telegram", "Номер телефона (+380…):",
                initialvalue=tg.get("phone", ""), parent=self)
            if not phone:
                return
            phone = re.sub(r"[\s()-]", "", phone)
            if not re.fullmatch(r"\+[0-9]{7,15}", phone):
                self.status.set("Укажите номер с + и кодом страны.")
                return
            tg["phone"] = phone
        _save(self.telegram_path, tg)

        def work():
            return asyncio.run(_telegram_login(tg, self.telegram_path, self.stop))
        self.run_bg(work)

    def verify(self):
        rows = self.selected()
        if not rows:
            self.status.set("Выберите фирмы для проверки.")
            return
        tg = _load(self.telegram_path)
        if not tg.get("session"):
            self.status.set("Сначала войдите в Telegram.")
            return

        def work():
            for row in rows:
                if self.stop.is_set():
                    break
                verify_website(row)
                self.persist()
            accessible = [r for r in rows if r["website"].startswith("Доступен")]
            if accessible:
                log = lambda text: self.events.put(("status", text))
                asyncio.run(_telegram_check_wrap(tg, accessible, self.stop, log))
                self.persist()
            return f"Проверено фирм: {len(rows)}."
        self.run_bg(work)

    # ------------------------------------------------------------------
    #  PDF, копирование, экспорт
    # ------------------------------------------------------------------

    def attach_pdf(self):
        if self.busy:
            return
        rows = self.selected()
        if len(rows) != 1:
            self.status.set("Выберите одну фирму.")
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        data = Path(path).read_bytes()
        if not data.startswith(b"%PDF-"):
            self.status.set("Файл не является PDF.")
            return
        import hashlib
        row = rows[0]
        target = self.folder / "company_documents" / hashlib.sha256(
            (row["country"] + row["name"]).encode()).hexdigest()
        target.mkdir(parents=True, exist_ok=True)
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", row["name"]).strip(" .")[:100] or "Company"
        dest = target / (name + ".pdf")
        if dest.exists():
            self.status.set("PDF уже прикреплён.")
            return
        dest.write_bytes(data)
        row["pdf"] = "Прикреплена"
        row["pdf_path"] = str(dest)
        self.persist()
        self.refresh()

    def copy(self):
        text = "\n".join(
            f"{r['name']} | {r['address']} | {r['site']}"
            for r in self.selected())
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def export(self):
        rows = self.selected() or self.data["rows"]
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        export_csv(rows, path)
        self.status.set(f"Экспортировано {len(rows)} записей.")

    def open_source(self):
        import webbrowser
        rows = self.selected()
        if rows:
            url = rows[0].get("registry") or rows[0].get("source", "")
            if url:
                webbrowser.open(url)


# ---------------------------------------------------------------------------
#  Telegram helpers
# ---------------------------------------------------------------------------

async def _telegram_login(config, save_path, stop):
    try:
        from telethon import TelegramClient, errors
        from telethon.sessions import StringSession
    except ImportError:
        raise RuntimeError('Установите Telethon: pip install "Telethon<2"')

    client = TelegramClient(
        StringSession(config.get("session", "")),
        config["api_id"], config["api_hash"],
        request_retries=0, connection_retries=1,
        flood_sleep_threshold=0, timeout=15,
        device_model="Woonsh Tools", app_version="0.1")
    try:
        await asyncio.wait_for(client.connect(), 30)
        if not await asyncio.wait_for(client.is_user_authorized(), 20):
            phone = config.get("phone", "")
            if not phone:
                raise ValueError("Номер телефона не задан.")
            sent = await asyncio.wait_for(client.send_code_request(phone), 30)
            # В headless-режиме код вводится через диалог, который уже на UI
            raise ValueError(
                "Telegram запросил код подтверждения. "
                "Полный вход через GUI пока не реализован в Woonsh Tools. "
                "Используйте X-File для первичного входа.")
        config["session"] = client.session.save()
        _save(save_path, config)
        me = await asyncio.wait_for(client.get_me(), 20)
        if getattr(me, "phone", None):
            config["phone"] = "+" + me.phone.lstrip("+")
            _save(save_path, config)
        return "Telegram подключён. Сессия сохранена."
    finally:
        await client.disconnect()


async def _telegram_check_wrap(config, rows, stop, on_status=None):
    from woonsh_tools.companies.search import telegram_check
    return await telegram_check(config, rows, stop, on_status)
