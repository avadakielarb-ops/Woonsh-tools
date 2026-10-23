"""
Sidebar navigation — левая панель с группами вкладок.
Из X-File sidebar_navigation.py, адаптировано для Woonsh Tools.
"""

from tkinter import ttk


class Sidebar(ttk.Frame):
    """Левая панель навигации с группами секций."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, padding=(4, 12, 12, 12))
        self.sidebar.grid(row=0, column=0, sticky="ns")

        self.pages = []
        self.buttons = []
        self.groups = {}
        self.current = 0

    def add_group(self, title):
        if self.groups:
            ttk.Separator(self.sidebar).pack(fill="x", pady=8)
        lbl = ttk.Label(self.sidebar, text=title, style="SidebarGroup.TLabel")
        lbl.pack(anchor="w", pady=(6, 8))
        self.groups[title] = lbl

    def add(self, page, text="", group=None):
        if group and group not in self.groups:
            self.add_group(group)

        index = len(self.pages)
        btn = ttk.Button(
            self.sidebar, text=text, style="Nav.TButton",
            command=lambda: self.select(index))
        btn.pack(fill="x", pady=3)
        self.buttons.append(btn)
        self.pages.append(page)

        if index == 0:
            self.select(0)

    def select(self, index=None):
        if index is None:
            return self.current

        if isinstance(index, str):
            index = next(
                (i for i, p in enumerate(self.pages) if str(p) == index),
                self.current)

        for page in self.pages:
            page.grid_remove()
        self.pages[index].grid(row=0, column=1, sticky="nsew")
        self.current = index

        for i, btn in enumerate(self.buttons):
            if i == index:
                btn.state(["disabled"])
                btn.configure(style="NavSelected.TButton")
            else:
                btn.state(["!disabled"])
                btn.configure(style="Nav.TButton")

    def tabs(self):
        return tuple(str(p) for p in self.pages)
