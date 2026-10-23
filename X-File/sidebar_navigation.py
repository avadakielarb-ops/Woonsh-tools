"""Grouped navigation retaining the Notebook interface used by the app."""
from tkinter import ttk

class SidebarNotebook(ttk.Frame):
    def __init__(self, parent, app_dir=None):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = ttk.Frame(self, padding=(4, 12, 12, 12))
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.pages, self.buttons = [], []
        self.current = 0
        self.profile_page = None
        ttk.Label(self.sidebar,text='ПОИСК ФИРМЫ',style='SidebarGroup.TLabel').pack(anchor='w',pady=(0,8))
        self.search_button=ttk.Button(self.sidebar,text='Поиск фирмы',style='Nav.TButton',command=self.show_search)
        self.search_button.pack(fill='x',pady=3)
        from company_search import CompanySearchPanel
        if app_dir is None:
            import os
            from pathlib import Path
            app_dir=Path(os.environ.get('APPDATA') or Path.home())/'X-File'
        self.search_page=CompanySearchPanel(self,app_dir)

    def add(self, page, text=''):
        index = len(self.pages)
        titles = {0:'Загрузка Google Disk', 3:'Google ADS', 5:'Документация'}
        if index in titles:
            ttk.Label(self.sidebar, text=titles[index], style='SidebarGroup.TLabel').pack(anchor='w', pady=(14, 8))
        button = ttk.Button(self.sidebar, text=text, style='Nav.TButton', command=lambda: self.select(index))
        button.pack(fill='x', pady=3)
        self.buttons.append(button)
        self.pages.append(page)
        if index == 0:
            self.select(0)

    def show_search(self):
        if self.profile_page:self.profile_page.grid_remove();self.profile_button.state(['!disabled']);self.profile_button.configure(style='Nav.TButton')
        for page in self.pages:
            page.grid_remove()
        self.search_page.grid(row=0,column=1,sticky='nsew')
        self.search_button.state(['disabled']);self.search_button.configure(style='NavSelected.TButton')
        for button in self.buttons:
            button.state(['!disabled']);button.configure(style='Nav.TButton')

    def select(self, index=None):
        if index is None:
            return str(self.pages[self.current])
        if not isinstance(index, int):
            index = next(i for i,p in enumerate(self.pages) if str(p) == str(index))
        if self.profile_page:self.profile_page.grid_remove();self.profile_button.state(['!disabled']);self.profile_button.configure(style='Nav.TButton')
        self.search_page.grid_remove()
        self.search_button.state(['!disabled']);self.search_button.configure(style='Nav.TButton')
        for page in self.pages:
            page.grid_remove()
        self.pages[index].grid(row=0, column=1, sticky='nsew')
        self.current = index
        for i,button in enumerate(self.buttons):
            button.state(['disabled'] if i == index else ['!disabled'])
            button.configure(style='NavSelected.TButton' if i==index else 'Nav.TButton')

    def tabs(self):
        return tuple(str(p) for p in self.pages)

    def add_profile(self,app):
        from user_profile import UserProfilePanel
        self.profile_page=UserProfilePanel(self,app)
        ttk.Separator(self.sidebar).pack(fill='x',pady=16)
        self.profile_button=ttk.Button(self.sidebar,text='Мой профиль',style='Nav.TButton',command=self.show_profile)
        self.profile_button.pack(fill='x',pady=4)

    def show_profile(self):
        for page in self.pages:page.grid_remove()
        self.search_page.grid_remove();self.search_button.state(['!disabled']);self.search_button.configure(style='Nav.TButton')
        for button in self.buttons:button.state(['!disabled']);button.configure(style='Nav.TButton')
        self.profile_page.refresh();self.profile_page.grid(row=0,column=1,sticky='nsew')
        self.profile_button.state(['disabled']);self.profile_button.configure(style='NavSelected.TButton')
