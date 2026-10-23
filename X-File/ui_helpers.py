"""Themed input dialogs and layout-independent Windows clipboard shortcuts."""
import tkinter as tk
from tkinter import ttk


def clipboard_support(widget):
    def select_all():
        if isinstance(widget, tk.Text):
            widget.tag_add('sel', '1.0', 'end-1c')
        else:
            widget.selection_range(0, 'end')
            widget.icursor('end')

    def key(event):
        if not event.state & 4:
            return
        action = {65:'all', 67:'<<Copy>>', 86:'<<Paste>>', 88:'<<Cut>>'}.get(event.keycode)
        if action:
            if action == 'all':
                select_all()
            else:
                widget.event_generate(action)
            return 'break'

    widget.bind('<KeyPress>', key, add='+')
    style = ttk.Style(widget)
    menu = tk.Menu(widget, tearoff=False,
                   background=style.lookup('TFrame', 'background') or '#1a1430',
                   foreground=style.lookup('TLabel', 'foreground') or '#f2ecff',
                   activebackground='#7a34e6', activeforeground='white')
    for label, action in [('Вырезать','<<Cut>>'),('Копировать','<<Copy>>'),('Вставить','<<Paste>>')]:
        menu.add_command(label=label, command=lambda a=action: widget.event_generate(a))
    menu.add_separator()
    menu.add_command(label='Выделить всё', command=select_all)

    def popup(event):
        widget.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    widget.bind('<Button-3>', popup)


class LinkDialog(tk.Toplevel):
    def __init__(self, parent, initial=''):
        super().__init__(parent)
        self.withdraw()
        self.title('Таблица по ссылке')
        self.transient(parent.winfo_toplevel())
        self.result = None
        self.configure(background=ttk.Style(self).lookup('TFrame','background') or '#100c1c')
        self.resizable(True, False)
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text='Ссылка на Excel, CSV или Google Sheets', style='H.TLabel').grid(row=0, column=0, sticky='w')
        self.value = tk.StringVar(value=initial)
        self.entry = ttk.Entry(frame, textvariable=self.value, width=75)
        self.entry.grid(row=1, column=0, sticky='we', pady=(12,8))
        clipboard_support(self.entry)
        ttk.Label(frame, text='Ctrl+V или правая кнопка мыши → Вставить', style='Muted.TLabel').grid(row=2,column=0,sticky='w')
        self.error = tk.StringVar()
        ttk.Label(frame, textvariable=self.error, style='Danger.TLabel').grid(row=3,column=0,sticky='w',pady=5)
        buttons=ttk.Frame(frame)
        buttons.grid(row=4,column=0,sticky='e',pady=(8,0))
        ttk.Button(buttons,text='Вставить из буфера',command=self.paste).pack(side='left',padx=5)
        ttk.Button(buttons,text='Отмена',command=self.destroy).pack(side='left',padx=5)
        ttk.Button(buttons,text='Открыть таблицу',command=self.accept,style='Accent.TButton').pack(side='left')
        self.bind('<Return>',lambda e:self.accept())
        self.bind('<Escape>',lambda e:self.destroy())
        self.update_idletasks()
        owner=parent.winfo_toplevel()
        x=max(0,owner.winfo_rootx()+(owner.winfo_width()-self.winfo_reqwidth())//2)
        y=max(0,owner.winfo_rooty()+(owner.winfo_height()-self.winfo_reqheight())//2)
        self.geometry('+%d+%d'%(x,y))
        self.deiconify()
        self.grab_set()
        self.entry.focus_set()
        self.entry.selection_range(0,'end')

    def paste(self):
        try:
            self.value.set(self.clipboard_get().strip())
            self.entry.icursor('end')
            self.error.set('')
        except tk.TclError:
            self.error.set('В буфере нет текста.')

    def accept(self):
        value=self.value.get().strip()
        if not value.startswith(('https://','http://')):
            self.error.set('Вставьте ссылку, начинающуюся с https:// или http://')
            return
        self.result=value
        self.destroy()
