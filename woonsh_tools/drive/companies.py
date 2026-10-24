"""
Загрузка Google Disk → Компании.
Платёжные профили компаний для загрузки на Drive.
Источник: X-File x-file.pyw _build_tab_companies (tab 1).
"""
import tkinter as tk
from tkinter import ttk


class DriveCompaniesPanel(ttk.Frame):
    """Компании для загрузки на Google Drive."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        ttk.Label(self, text="Компании",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(self, text="Платёжные профили компаний для загрузки.\n"
                  "Реализация: перенести из X-File _build_tab_companies.",
                  wraplength=600).pack(anchor="w")
