"""
Общие UI-утилиты: буфер обмена (Ctrl+A/C/V/X + ПКМ-меню), LinkDialog.
Из X-File ui_helpers.py.
"""

import tkinter as tk
from tkinter import ttk

CTRL_MASK = 0x4
KEYCODE_ACTIONS = {65: "select_all", 67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}


def _select_all(widget):
    try:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
        elif isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            widget.select_range(0, "end")
            widget.icursor(0)
    except tk.TclError:
        pass


def clipboard_support(widget):
    """Ctrl+A/C/V/X и контекстное меню ПКМ для Entry/Text/Combobox."""

    def on_key(event):
        if not (event.state & CTRL_MASK):
            return
        action = KEYCODE_ACTIONS.get(event.keycode)
        if action == "select_all":
            _select_all(event.widget)
            return "break"
        if action:
            event.widget.event_generate(action)
            return "break"

    widget.bind("<KeyPress>", on_key, add="+")

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: _select_all(widget))

    def show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", show_menu)


def enable_clipboard(root):
    """Глобально включает Ctrl+A/C/V/X для всех Entry/Text/Combobox."""

    def on_key(event):
        if not (event.state & CTRL_MASK):
            return
        action = KEYCODE_ACTIONS.get(event.keycode)
        if action == "select_all":
            _select_all(event.widget)
            return "break"
        if action:
            try:
                event.widget.event_generate(action)
            except tk.TclError:
                pass
            return "break"

    root.bind_all("<KeyPress>", on_key, add="+")


class LinkDialog:
    """Диалог ввода URL со вставкой из буфера."""

    def __init__(self, parent, title="Ссылка", prompt="Введите URL:"):
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.transient(parent.winfo_toplevel())
        self.win.resizable(False, False)

        body = ttk.Frame(self.win, padding=20)
        body.pack(fill="both")
        ttk.Label(body, text=prompt).pack(anchor="w", pady=(0, 8))

        self.entry = ttk.Entry(body, width=60)
        self.entry.pack(fill="x")
        clipboard_support(self.entry)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(16, 0))

        def paste():
            try:
                text = self.win.clipboard_get().strip()
                if text:
                    self.entry.delete(0, "end")
                    self.entry.insert(0, text)
            except tk.TclError:
                pass

        ttk.Button(buttons, text="Вставить", command=paste).pack(side="left")
        ttk.Button(buttons, text="OK", style="Accent.TButton",
                   command=self._ok).pack(side="right")
        ttk.Button(buttons, text="Отмена",
                   command=self.win.destroy).pack(side="right", padx=(0, 8))

        self.win.bind("<Return>", lambda e: self._ok())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

        self.win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.win.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.win.winfo_reqheight()) // 2
        self.win.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.win.grab_set()
        self.entry.focus_set()
        self.win.wait_window()

    def _ok(self):
        text = self.entry.get().strip()
        if text:
            self.result = text
        self.win.destroy()
