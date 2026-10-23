"""Grouped navigation retaining the Notebook interface used by the app."""
from tkinter import ttk

class SidebarNotebook(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = ttk.Frame(self, padding=(4, 12, 12, 12))
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.pages, self.buttons = [], []
        self.current = 0

    def add(self, page, text=''):
        index = len(self.pages)
        titles = {0:'Загрузка в Гугл Диск', 3:'Google ADS', 5:'Документация'}
        if index in titles:
            ttk.Label(self.sidebar, text=titles[index], style='H.TLabel').pack(anchor='w', pady=(14, 8))
        button = ttk.Button(self.sidebar, text=text, command=lambda: self.select(index))
        button.pack(fill='x', pady=3)
        self.buttons.append(button)
        self.pages.append(page)
        if index == 0:
            self.select(0)

    def select(self, index=None):
        if index is None:
            return str(self.pages[self.current])
        if not isinstance(index, int):
            index = next(i for i,p in enumerate(self.pages) if str(p) == str(index))
        for page in self.pages:
            page.grid_remove()
        self.pages[index].grid(row=0, column=1, sticky='nsew')
        self.current = index
        for i,button in enumerate(self.buttons):
            button.state(['disabled'] if i == index else ['!disabled'])

    def tabs(self):
        return tuple(str(p) for p in self.pages)
