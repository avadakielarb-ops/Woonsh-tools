"""Native settings and result views for the existing generator engine."""
import tkinter as tk
from tkinter import ttk, messagebox
from ui_helpers import clipboard_support

BUDGET_LABELS = {"fixed":"Фиксированный", "random":"От и до"}

DEFAULTS = dict(campaigns=1, ad_groups=1, keywords=10, ads=1, headlines=10,
    descriptions=4, max_cpc=0.5, budget_mode='fixed', budget_fixed=10,
    budget_min=5, budget_max=15, status='Paused', language='', notes='',
    about='', pages=3, policy=True, locations=[], match_types=['phrase'],
    neg_on=True, neg_builtin=True, neg_ai=10, neg_match='phrase', neg_custom='',
    ext_snippets_on=False, ext_callouts_on=True, ext_callouts=8, ext_sitelinks_on=True, ext_sitelinks=6)


class Settings(tk.Toplevel):
    def __init__(self, parent, initial, count, engine, key_path=None):
        super().__init__(parent)
        self.title('Генерация рекламы — %d профилей' % count)
        self.transient(parent.winfo_toplevel())
        self.result = None
        self.engine = engine
        self.vars = {}
        self.widgets = {}
        self.configure(background=ttk.Style(self).lookup("TFrame", "background") or "#100c1c")
        self.key_path = key_path
        saved_key = ''
        if key_path and key_path.exists():
            try:
                from profile_store import load
                saved_key = load(key_path).get('api_key', '')
            except Exception:
                pass
        self.key = tk.StringVar(value=saved_key)
        self.remember_key = tk.BooleanVar(value=True)
        ttk.Label(self, text='Gemini API key').pack(anchor='w', padx=12, pady=(12, 0))
        key_entry = ttk.Entry(self, textvariable=self.key, show='*', width=65)
        key_entry.pack(fill='x', padx=12, pady=5)
        clipboard_support(key_entry)
        key_options = ttk.Frame(self)
        key_options.pack(fill='x', padx=12, pady=(0,5))
        ttk.Checkbutton(key_options, text='Запомнить ключ (шифрование Windows)', variable=self.remember_key).pack(side='left')
        ttk.Button(key_options, text='Удалить сохранённый ключ', command=self.delete_key).pack(side='right')
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=12)
        groups = [
            ('Кампании', [('campaigns','Кампаний'),('ad_groups','Групп'),('keywords','Ключей на группу'),('ads','Объявлений'),('headlines','Заголовков'),('descriptions','Описаний'),('max_cpc','Макс. CPC'),('budget_mode','Режим бюджета'),('budget_fixed','Сумма, $'),('budget_min','От, $'),('budget_max','До, $'),('status','Статус: Paused / Enabled')]),
            ('Содержание', [('language','Язык рекламы'),('locations','География (через запятую)'),('match_types','Типы: broad, phrase, exact'),('pages','Дополнительных страниц'),('about','Описание бизнеса'),('notes','Пожелания')]),
            ('Дополнения', [('ext_snippets_on','Структурированные описания'),('policy','Фильтр текстов'),('neg_on','Минус-слова'),('neg_builtin','Встроенные минус-слова'),('neg_ai','Минус-слов от ИИ'),('neg_match','Тип минус-слов'),('neg_custom','Свои минус-слова'),('ext_callouts_on','Уточнения'),('ext_callouts','Число уточнений'),('ext_sitelinks_on','Быстрые ссылки'),('ext_sitelinks','Число быстрых ссылок')])]
        values = {**DEFAULTS, **initial}
        for title, fields in groups:
            frame = ttk.Frame(nb, padding=10)
            frame.columnconfigure(1, weight=1)
            nb.add(frame, text=title)
            for row, (key, label) in enumerate(fields):
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3)
                value = values[key]
                if key == "budget_mode":
                    value = BUDGET_LABELS.get(value, value)
                if isinstance(value, bool):
                    var = tk.BooleanVar(value=value)
                    widget = ttk.Checkbutton(frame, variable=var)
                else:
                    var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
                    choices = {'status':['Paused','Enabled'], 'budget_mode':list(BUDGET_LABELS.values()), 'neg_match':['broad','phrase','exact']}
                    if key in ('language','locations'):
                        from ads_selectors import SearchPicker
                        widget = SearchPicker(frame,var,key)
                    else:
                        widget = ttk.Combobox(frame, textvariable=var, values=choices[key], state='readonly') if key in choices else ttk.Entry(frame, textvariable=var, width=45)
                widget.grid(row=row, column=1, sticky='we', padx=8, pady=3)
                self.vars[key] = var
                self.widgets[key] = widget
                if isinstance(widget, ttk.Entry):
                    clipboard_support(widget)
        self.vars['budget_mode'].trace_add('write', lambda *args: self.update_budget())
        self.update_budget()
        ttk.Button(self, text='Запустить для выбранных', command=self.accept).pack(pady=12)
        self.grab_set()

    def delete_key(self):
        try:
            if self.key_path:
                self.key_path.unlink(missing_ok=True)
            self.key.set('')
            self.remember_key.set(False)
        except OSError:
            messagebox.showerror('Ключ', 'Не удалось удалить сохранённый ключ.', parent=self)

    def update_budget(self):
        ranged = self.vars['budget_mode'].get() == BUDGET_LABELS['random']
        self.widgets['budget_fixed'].configure(state='disabled' if ranged else 'normal')
        for key in ('budget_min','budget_max'):
            self.widgets[key].configure(state='normal' if ranged else 'disabled')

    def accept(self):
        data = {k:v.get() for k,v in self.vars.items()}
        from ads_selectors import LANGUAGES
        if data['language'] not in LANGUAGES:
            messagebox.showerror('Язык', 'Выберите язык из подсказок или выберите Авто.', parent=self)
            return
        data['budget_mode'] = next((key for key, label in BUDGET_LABELS.items() if label == data['budget_mode']), data['budget_mode'])
        for field in ('locations','match_types'):
            data[field] = [x.strip() for x in data[field].split(',') if x.strip()]
        try:
            for key, default in DEFAULTS.items():
                if type(default) is int:
                    data[key] = int(data[key])
                elif type(default) is float:
                    data[key] = float(str(data[key]).replace(',', '.'))
            import math
            if any(not math.isfinite(data[k]) for k in ('budget_fixed','budget_min','budget_max','max_cpc')):
                raise ValueError('Non-finite budget')
            if data['budget_mode'] == 'random':
                if data['budget_min'] <= 0 or data['budget_max'] < data['budget_min']:
                    messagebox.showerror('Бюджет', 'Укажите положительную сумму «От» и сумму «До», не меньшую «От».', parent=self)
                    return
            elif data['budget_fixed'] <= 0:
                raise ValueError('Budget must be positive')
            self.engine.parse_settings(data)
        except (ValueError, TypeError, KeyError):
            messagebox.showerror('Настройки', 'Проверьте числовые значения.', parent=self)
            return
        if not self.key.get().strip():
            messagebox.showerror('Ключ', 'Введите Gemini API key.', parent=self)
            return
        if self.key_path:
            try:
                if self.remember_key.get():
                    from profile_store import save
                    save(self.key_path, {'api_key':self.key.get().strip()})
                else:
                    self.key_path.unlink(missing_ok=True)
            except Exception:
                messagebox.showerror('Ключ', 'Не удалось обновить сохранённый ключ. Проверьте доступ к папке данных.', parent=self)
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
