"""Searchable inline pickers; stored values stay compatible with the engine."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from ui_helpers import clipboard_support

LANGUAGES = {'':'Авто — по содержимому сайта', 'en':'Английский', 'ru':'Русский', 'uk':'Украинский', 'fi':'Финский', 'sv':'Шведский', 'fr':'Французский', 'de':'Немецкий', 'es':'Испанский', 'it':'Итальянский', 'pt':'Португальский', 'pl':'Польский', 'cs':'Чешский', 'sk':'Словацкий', 'da':'Датский', 'no':'Норвежский', 'nl':'Нидерландский', 'is':'Исландский', 'et':'Эстонский', 'lv':'Латышский', 'lt':'Литовский', 'ro':'Румынский', 'hu':'Венгерский', 'bg':'Болгарский', 'hr':'Хорватский', 'sr':'Сербский', 'sl':'Словенский', 'el':'Греческий', 'tr':'Турецкий', 'ar':'Арабский', 'he':'Иврит', 'hi':'Хинди', 'ja':'Японский', 'ko':'Корейский', 'zh-CN':'Китайский упрощённый', 'zh-TW':'Китайский традиционный', 'th':'Тайский', 'vi':'Вьетнамский', 'id':'Индонезийский', 'ms':'Малайский', 'bn':'Бенгальский', 'ta':'Тамильский', 'te':'Телугу', 'ur':'Урду', 'fa':'Персидский', 'ca':'Каталанский'}
ALIASES = dict(zip('Finland|France|Germany|United Kingdom|United States|Ukraine|Poland|Spain|Italy|Sweden|Norway|Denmark|Netherlands|Belgium|Switzerland|Austria|Portugal|Czechia|Iceland|Estonia|Latvia|Lithuania|Canada|Australia|Ireland|Romania|Greece|Turkey'.split('|'), 'Финляндия|Франция|Германия|Великобритания Англия|США Америка|Украина|Польша|Испания|Италия|Швеция|Норвегия|Дания|Нидерланды Голландия|Бельгия|Швейцария|Австрия|Португалия|Чехия|Исландия|Эстония|Латвия|Литва|Канада|Австралия|Ирландия|Румыния|Греция|Турция'.split('|')))

class SearchPicker(ttk.Frame):
    def __init__(self,parent,variable,kind):
        super().__init__(parent)
        self.variable,self.kind = variable,kind
        self.options = [(code, label+(' ('+code+')' if code else ''),label+' '+code) for code,label in LANGUAGES.items()] if kind=='language' else [(c,c,c+' '+ALIASES.get(c,'')) for c in json.loads(Path(__file__).with_name('ads_countries.json').read_text(encoding='utf-8'))]
        self.query=tk.StringVar(value=self.display(variable.get()))
        self.entry=ttk.Entry(self,textvariable=self.query,width=45)
        self.entry.pack(fill='x')
        clipboard_support(self.entry)
        style=ttk.Style(self)
        bg=style.lookup('TEntry','fieldbackground') or '#211936'
        fg=style.lookup('TEntry','foreground') or '#eee9ff'
        self.list= tk.Listbox(self.winfo_toplevel(),height=4,exportselection=False,
            background=bg,foreground=fg,selectbackground='#7c2fe5',selectforeground='#ffffff',
            relief='flat',borderwidth=0,highlightthickness=1,highlightbackground='#7440b7',
            highlightcolor='#9b60ff',font=self.entry.cget('font'))
        self.list.bind('<ButtonRelease-1>',self.choose)
        self.entry.bind('<KeyRelease>',self.filter)
        self.entry.bind('<Down>',self.down)
        self.entry.bind('<Return>',self.choose)
        self.entry.bind('<Escape>',lambda e:self.list.place_forget())
        self.entry.bind('<FocusIn>',self.filter)
        self.entry.bind('<FocusOut>',lambda e:self.after(150,self.blur))

    def show_list(self):
        top=self.winfo_toplevel()
        self.update_idletasks()
        height=min(6,max(1,len(self.matches)))
        self.list.configure(height=height)
        x=self.entry.winfo_rootx()-top.winfo_rootx()
        y=self.entry.winfo_rooty()-top.winfo_rooty()+self.entry.winfo_height()
        self.list.place(x=x,y=y,width=self.entry.winfo_width())
        self.list.lift()

    def display(self,value):
        if self.kind=='language':
            return LANGUAGES.get(value,value)+(' ('+value+')' if value in LANGUAGES and value else '')
        return value

    def filter(self,event=None):
        if event and event.keysym in ('Return','Escape','Down','Up'):
            return
        text=self.query.get()
        term=(text.split(',')[-1] if self.kind=='locations' else text).strip().casefold()
        self.matches=[o for o in self.options if not term or term in o[2].casefold() or term==o[1].casefold()]
        self.list.delete(0,'end')
        for o in self.matches:self.list.insert('end',o[1])
        if self.matches:self.show_list()
        else:self.list.place_forget()
        if self.kind=='locations':self.variable.set(text)
        else:
            match=next((o for o in self.options if text.casefold() in (o[0].casefold(),o[1].casefold(),LANGUAGES[o[0]].casefold())),None)
            self.variable.set(match[0] if match else text)

    def down(self,event):
        if self.list.size():self.list.selection_clear(0,'end');self.list.selection_set(0)
        return 'break'

    def choose(self,event=None):
        selected=self.list.curselection()
        if not selected:
            if self.list.size()!=1:return 'break'
            selected=(0,)
        option=self.matches[selected[0]]
        if self.kind=='locations':
            parts=self.query.get().split(',')[:-1]
            value=', '.join([p.strip() for p in parts if p.strip()]+[option[0]])
            self.variable.set(value);self.query.set(value)
        else:self.variable.set(option[0]);self.query.set(option[1])
        self.list.place_forget()
        return 'break'

    def blur(self):
        if self.focus_get()!=self.list:self.list.place_forget()


class MatchPicker(ttk.Menubutton):
    def __init__(self,parent,variable):
        super().__init__(parent)
        self.variable=variable
        style=ttk.Style(self)
        self.menu=tk.Menu(self,tearoff=False,
            background=style.lookup('TEntry','fieldbackground') or '#211936',
            foreground=style.lookup('TEntry','foreground') or '#eee9ff',
            activebackground='#7c2fe5',activeforeground='white',selectcolor='#211936',
            relief='flat',borderwidth=1)
        self.configure(menu=self.menu)
        chosen={v.strip() for v in variable.get().split(',')}
        self.flags={}
        for key,label in [('broad','broad — широкое'),('phrase','phrase — фразовое'),('exact','exact — точное')]:
            flag=tk.BooleanVar(value=key in chosen)
            self.flags[key]=flag
            self.menu.add_checkbutton(label=label,variable=flag,command=self.changed)
        self.changed()

    def changed(self):
        values=[key for key,flag in self.flags.items() if flag.get()]
        self.variable.set(', '.join(values))
        self.configure(text=', '.join(values) if values else 'Выберите тип соответствия')
