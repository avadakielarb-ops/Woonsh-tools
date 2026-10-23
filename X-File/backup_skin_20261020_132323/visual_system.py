"""Shared styling for existing and dynamically-created application windows."""
import tkinter as tk
from tkinter import ttk

def install(root,theme):
    style=ttk.Style(root)
    bg,field,ink,muted=theme['bg'],theme['field'],theme['ink'],theme['muted']
    accent='#8738ef'
    style.configure('TButton',padding=(14,8),font=('Segoe UI',10),borderwidth=0)
    style.configure('TMenubutton',background=field,foreground=ink,padding=(10,7),arrowcolor=muted,relief='flat')
    style.map('TMenubutton',background=[('active','#35234f')],foreground=[('disabled',muted)])
    for name in ('TCheckbutton','TRadiobutton'):
        style.configure(name,background=bg,foreground=ink,padding=(0,5),indicatorcolor=field)
        style.map(name,background=[('active',bg)],foreground=[('disabled',muted)],indicatorcolor=[('selected',accent),('!selected',field)])
    style.configure('TSpinbox',fieldbackground=field,foreground=ink,arrowcolor=muted,padding=6,insertcolor=ink)
    style.map('TSpinbox',fieldbackground=[('readonly',field)])
    style.configure('TLabelframe',background=bg,bordercolor=theme['line'],relief='flat')
    style.configure('TLabelframe.Label',background=bg,foreground=muted,font=('Segoe UI Semibold',10))
    style.configure('Horizontal.TProgressbar',background=accent,troughcolor=theme['surface'],borderwidth=0,thickness=5)
    style.configure('Nav.TButton',background=bg,foreground=muted,font=('Segoe UI Semibold',10),padding=(14,11),anchor='w')
    style.map('Nav.TButton',background=[('active',theme['surface2'])])
    style.configure('NavSelected.TButton',background='#322048',foreground='#f6efff',font=('Segoe UI Semibold',10),padding=(14,11),anchor='w')
    style.map('NavSelected.TButton',background=[('disabled','#322048')],foreground=[('disabled','#f6efff')])
    style.configure('SidebarGroup.TLabel',font=('Segoe UI Semibold',9),foreground='#9c8bb7',padding=(2,5))
    style.configure('Treeview',rowheight=32)
    style.configure('Treeview.Heading',font=('Segoe UI Semibold',10),padding=(10,9))
    root.option_add('*Text.background',field)
    root.option_add('*Text.foreground',ink)
    root.option_add('*Text.insertBackground',ink)
    root.option_add('*Listbox.background',field)
    root.option_add('*Listbox.foreground',ink)
    root.option_add('*Menu.background',theme['surface2'])
    root.option_add('*Menu.foreground',ink)
    root.option_add('*Menu.activeBackground',accent)
    root.option_add('*Menu.activeForeground','#ffffff')
    install_dialogs(root,theme)
    primary=('Генерировать выбранные','Найти через Gemini','Сохранить изменения','Сохранить поля','Установить и продолжить','Завершить','Обновить и перезапустить')
    def skin(widget):
        try:
            if not getattr(widget,'_mtf_skinned',False):
                if isinstance(widget,tk.Toplevel):widget.configure(background=bg)
                elif isinstance(widget,tk.Text):
                    widget.configure(background=field,foreground=ink,insertbackground=ink,selectbackground=accent,
                        selectforeground='white',relief='flat',borderwidth=0,highlightthickness=1,
                        highlightbackground=theme['line'],highlightcolor=accent,padx=10,pady=8,font=('Segoe UI',10))
                elif isinstance(widget,tk.Listbox):
                    widget.configure(background=field,foreground=ink,selectbackground=accent,selectforeground='white',
                        relief='flat',borderwidth=0,highlightthickness=1,highlightbackground=theme['line'],font=('Segoe UI',10))
                elif isinstance(widget,tk.Entry):
                    widget.configure(background=field,foreground=ink,insertbackground=ink,selectbackground=accent,
                        selectforeground='white',relief='flat',highlightthickness=1,highlightbackground=theme['line'],highlightcolor=accent)
                elif isinstance(widget,tk.Button):
                    widget.configure(background=theme['surface2'],foreground=ink,activebackground=accent,activeforeground='white',
                        relief='flat',borderwidth=0,padx=14,pady=7)
                elif isinstance(widget,(tk.Frame,tk.Label)):
                    if str(widget.cget('background')) in ('SystemButtonFace','SystemWindow','#d9d9d9','white','#ffffff'):
                        widget.configure(background=bg)
                        if isinstance(widget,tk.Label):widget.configure(foreground=ink)
                elif isinstance(widget,ttk.Button) and widget.cget('style') in ('','TButton'):
                    text=str(widget.cget('text'))
                    if text.startswith(primary):widget.configure(style='Accent.TButton')
                    elif text.startswith('Удалить'):widget.configure(style='Danger.TButton')
                widget._mtf_skinned=True
            if isinstance(widget,ttk.Treeview):
                widget.tag_configure('mtf_even',background='#1d172c')
                widget.tag_configure('mtf_odd',background='#211a32')
                for i,item in enumerate(widget.get_children()):
                    tags=[t for t in widget.item(item,'tags') if not t.startswith('mtf_')]
                    if not tags:widget.item(item,tags=('mtf_even' if i%2==0 else 'mtf_odd',))
            for child in widget.winfo_children():skin(child)
        except tk.TclError:pass
    def mapped(event):
        try:root.after_idle(lambda:skin(event.widget))
        except tk.TclError:pass
    root.bind_all('<Map>',mapped,add='+')
    def tick():
        if not root.winfo_exists():return
        skin(root)
        root.after(1200,tick)
    root.after_idle(tick)
    return skin

def install_dialogs(root,theme):
    """Keep messagebox return conventions while matching application styling."""
    from tkinter import messagebox
    layouts={
        'ok':[('ok','Понятно')],
        'okcancel':[('ok','Продолжить'),('cancel','Отмена')],
        'yesno':[('yes','Да'),('no','Нет')],
        'yesnocancel':[('yes','Да'),('no','Нет'),('cancel','Отмена')],
        'retrycancel':[('retry','Повторить'),('cancel','Отмена')],
        'abortretryignore':[('abort','Прервать'),('retry','Повторить'),('ignore','Пропустить')]}
    def dialog(title=None,message=None,_icon=None,_type=None,**options):
        parent=options.get('parent') or root
        window=tk.Toplevel(parent);window.title(title or 'Multi-Tool Farmer')
        window.configure(background=theme['bg']);window.resizable(False,False)
        window.transient(parent.winfo_toplevel())
        body=ttk.Frame(window,padding=24);body.pack(fill='both',expand=True)
        heading={'error':'Ошибка','warning':'Обратите внимание','question':'Подтверждение','info':'Информация'}.get(_icon,'Multi-Tool Farmer')
        ttk.Label(body,text=heading,style='H.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(body,text=str(message or ''),wraplength=470,justify='left').pack(anchor='w')
        if options.get('detail'):ttk.Label(body,text=options['detail'],style='Muted.TLabel',wraplength=470).pack(anchor='w',pady=8)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=(22,0))
        choices=layouts.get(_type or 'ok',layouts['ok'])
        cancel=next((key for key in ('cancel','no','ok','abort') if any(c[0]==key for c in choices)),choices[-1][0])
        result=[cancel]
        def finish(value):result[0]=value;window.destroy()
        first=None
        for i,(value,label) in enumerate(choices):
            button=ttk.Button(actions,text=label,style='Accent.TButton' if i==0 else 'TButton',command=lambda value=value:finish(value))
            button.pack(side='left',padx=(0,8))
            if first is None:first=button
        window.protocol('WM_DELETE_WINDOW',lambda:finish(cancel))
        window.bind('<Escape>',lambda event:finish(cancel))
        window.update_idletasks()
        width=max(420,window.winfo_reqwidth());height=window.winfo_reqheight()
        x=max(0,parent.winfo_rootx()+(parent.winfo_width()-width)//2)
        y=max(0,parent.winfo_rooty()+(parent.winfo_height()-height)//2)
        window.geometry(f'{width}x{height}+{x}+{y}')
        previous=window.grab_current();window.grab_set();first.focus_set()
        window.wait_window()
        if previous and previous.winfo_exists():previous.grab_set()
        return result[0]
    messagebox._show=dialog
