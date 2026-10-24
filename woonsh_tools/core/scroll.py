"""
Прокручиваемый контейнер для полей.
Из X-File profile_scroll.py.
"""

import tkinter as tk
from tkinter import ttk


class ScrollFields(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self, highlightthickness=0,
            background=ttk.Style(self).lookup('TFrame', 'background')
                       or '#100c1c')
        self.canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar = ttk.Scrollbar(self, command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(
            (0, 0), window=self.content, anchor='nw')

        self.content.bind('<Configure>', lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(
            self.window, width=e.width))
        self.canvas.bind('<MouseWheel>', self.wheel)

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), 'units')
        return 'break'

    def bind_fields(self):
        def walk(widget):
            widget.bind('<MouseWheel>', self.wheel, add='+')
            for child in widget.winfo_children():
                walk(child)
        walk(self.content)
