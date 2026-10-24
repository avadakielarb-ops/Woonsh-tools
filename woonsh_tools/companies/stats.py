"""
Панель статистики — сводка по странам: компании, сайты, PDF, проверки.
"""

import json
import os
import tkinter as tk
from tkinter import ttk


class StatsPanel(ttk.Frame):
    """Сводная статистика по результатам поиска компаний."""

    COLUMNS = (
        ("country", "Страна", 130),
        ("total", "Всего", 60),
        ("with_site", "С сайтом", 70),
        ("site_pdf", "С PDF", 60),
        ("no_site", "Без сайта", 75),
        ("no_site_pdf", "PDF б/с", 60),
        ("accepted", "Принято", 65),
        ("checked", "Проверено", 80),
        ("unchecked", "Не провер.", 80),
    )

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(top, text="Обновить", style="Accent.TButton",
                   command=self.refresh).pack(side="left")
        self.status_var = tk.StringVar(value="Нажмите «Обновить».")
        ttk.Label(top, textvariable=self.status_var).pack(
            side="left", padx=12)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        col_ids = [c[0] for c in self.COLUMNS]
        self.tree = ttk.Treeview(
            tree_frame, columns=col_ids,
            show="headings", selectmode="browse")
        for cid, heading, width in self.COLUMNS:
            self.tree.heading(cid, text=heading)
            self.tree.column(cid, width=width, anchor="center"
                             if cid != "country" else "w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        totals = ttk.Frame(self)
        totals.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.total_var = tk.StringVar()
        ttk.Label(totals, textvariable=self.total_var,
                  style="Muted.TLabel").pack(anchor="w")

    def _data_path(self):
        return os.path.join(self.app.app_data_dir, "company_search.json")

    def refresh(self):
        path = self._data_path()
        if not os.path.exists(path):
            self.status_var.set("Нет данных поиска.")
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            self.status_var.set("Не удалось прочитать данные.")
            return

        rows = data if isinstance(data, list) else data.get("rows", [])
        if not rows:
            self.status_var.set("Нет записей.")
            return

        from woonsh_tools.companies.search import summarize
        stats = summarize(rows)

        self.tree.delete(*self.tree.get_children())
        grand = [0] * 8
        for item in stats:
            country, *values = item
            self.tree.insert("", "end", values=(country, *values))
            for i, v in enumerate(values):
                grand[i] += v

        self.tree.insert("", "end", values=("ИТОГО", *grand),
                         tags=("total",))
        self.tree.tag_configure("total", font=("Segoe UI Semibold", 10))

        self.total_var.set(
            f"Всего стран: {len(stats)}, записей: {grand[0]}")
        self.status_var.set("Обновлено.")
