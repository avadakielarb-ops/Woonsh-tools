"""Native settings and result views for the existing generator engine."""
import tkinter as tk
from tkinter import ttk, messagebox

DEFAULTS = dict(campaigns=1, ad_groups=1, keywords=10, ads=1, headlines=10,
    descriptions=4, max_cpc=0.5, budget_mode='fixed', budget_fixed=10,
    budget_min=5, budget_max=15, status='Paused', language='', notes='',
    about='', pages=3, policy=True, locations=[], match_types=['phrase'],
    neg_on=True, neg_builtin=True, neg_ai=10, neg_match='phrase', neg_custom='',
    ext_callouts_on=True, ext_callouts=8, ext_sitelinks_on=True, ext_sitelinks=6)


class Settings(tk.Toplevel):
    def __init__(self, parent, initial, count, engine):
        super().__init__(parent)
        self.title('Генерация рекламы — %d профилей' % count)
        self.transient(parent.winfo_toplevel())
        self.result = None
        self.engine = engine
        self.vars = {}
        self.key = tk.StringVar(value='')
        ttk.Label(self, text='Gemini API key (не сохраняется)').pack(anchor='w', padx=12, pady=(12, 0))
        ttk.Entry(self, textvariable=self.key, show='*', width=65).pack(fill='x', padx=12, pady=5)
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=12)
        groups = [
            ('Кампании', [('campaigns','Кампаний'),('ad_groups','Групп'),('keywords','Ключей на группу'),('ads','Объявлений'),('headlines','Заголовков'),('descriptions','Описаний'),('max_cpc','Макс. CPC'),('budget_mode','Бюджет: fixed / random'),('budget_fixed','Бюджет фикс.'),('budget_min','Бюджет мин.'),('budget_max','Бюджет макс.'),('status','Статус: Paused / Enabled')]),
            ('Содержание', [('language','Язык (пусто — авто)'),('locations','География (через запятую)'),('match_types','Типы: broad, phrase, exact'),('pages','Дополнительных страниц'),('about','Описание бизнеса'),('notes','Пожелания')]),
            ('Дополнения', [('policy','Фильтр текстов'),('neg_on','Минус-слова'),('neg_builtin','Встроенные минус-слова'),('neg_ai','Минус-слов от ИИ'),('neg_match','Тип минус-слов'),('neg_custom','Свои минус-слова'),('ext_callouts_on','Уточнения'),('ext_callouts','Число уточнений'),('ext_sitelinks_on','Быстрые ссылки'),('ext_sitelinks','Число быстрых ссылок')])]
        values = {**DEFAULTS, **initial}
        for title, fields in groups:
            frame = ttk.Frame(nb, padding=10)
            frame.columnconfigure(1, weight=1)
            nb.add(frame, text=title)
            for row, (key, label) in enumerate(fields):
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3)
                value = values[key]
                if isinstance(value, bool):
                    var = tk.BooleanVar(value=value)
                    widget = ttk.Checkbutton(frame, variable=var)
                else:
                    var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
                    choices = {'status':['Paused','Enabled'], 'budget_mode':['fixed','random'], 'neg_match':['broad','phrase','exact']}
                    widget = ttk.Combobox(frame, textvariable=var, values=choices[key], state='readonly') if key in choices else ttk.Entry(frame, textvariable=var, width=45)
                widget.grid(row=row, column=1, sticky='we', padx=8, pady=3)
                self.vars[key] = var
        ttk.Button(self, text='Запустить для выбранных', command=self.accept).pack(pady=12)
        self.grab_set()

    def accept(self):
        data = {k:v.get() for k,v in self.vars.items()}
        for field in ('locations','match_types'):
            data[field] = [x.strip() for x in data[field].split(',') if x.strip()]
        try:
            for key, default in DEFAULTS.items():
                if type(default) is int:
                    data[key] = int(data[key])
                elif type(default) is float:
                    data[key] = float(str(data[key]).replace(',', '.'))
            self.engine.parse_settings(data)
        except (ValueError, TypeError, KeyError):
            messagebox.showerror('Настройки', 'Проверьте числовые значения.', parent=self)
            return
        if not self.key.get().strip():
            messagebox.showerror('Ключ', 'Введите Gemini API key.', parent=self)
            return
        self.result = (data, self.key.get().strip())
        self.destroy()


def show_result(parent, name, result):
    window = tk.Toplevel(parent)
    window.title('Реклама — ' + name)
    window.geometry('900x600')
    text = tk.Text(window, wrap='none')
    scroll = ttk.Scrollbar(window, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    text.pack(fill='both', expand=True)
    lines = []
    for site in result.get('sites', []):
        lines.extend([site.get('url',''), site.get('summary',''), str(site.get('stats', {})), ''])
    lines += ['Предупреждения:', *result.get('warnings', []), '', 'CSV:', result.get('csv','')]
    text.insert('1.0', '\n'.join(lines))
    text.configure(state='disabled')
