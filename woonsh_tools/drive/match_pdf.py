"""
Загрузка Google Disk → Сопоставление PDF.
Привязка PDF-файлов к компаниям перед загрузкой на Drive.
Источник: X-File x-file.pyw _build_tab_match (tab 2).
"""
import tkinter as tk
from tkinter import ttk


class MatchPdfPanel(ttk.Frame):
    """Сопоставление PDF с компаниями."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        ttk.Label(self, text="Сопоставление PDF",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(self, text="Сопоставление PDF-файлов с компаниями.\n"
                  "Реализация: перенести из X-File _build_tab_match.",
                  wraplength=600).pack(anchor="w")
