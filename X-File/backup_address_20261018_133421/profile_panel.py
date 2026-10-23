"""Local table viewer. Only column mappings and source path are persisted."""
import csv
import io
import json
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

FIELDS = ('Название профиля', 'Адрес', 'Название фирмы', 'Сайт', 'Карта', 'ММ/ГГ', 'CVV/CVC', 'Информация')
SOURCES = ('Название профиля', 'Платежная информация', 'Карта', 'Срок карты', 'СVV')
SECRET = {'Карта', 'ММ/ГГ', 'CVV/CVC', 'Информация'}

def header_key(text):
    return ''.join(str(text).lower().split()).replace('ё', 'е').replace('с', 'c').replace('в', 'v')

def split_information(text):
    result = {}
    aliases = {'адрес': 'Адрес', 'address': 'Адрес', 'название фирмы': 'Название фирмы',
               'компания': 'Название фирмы', 'company': 'Название фирмы',
               'сайт': 'Сайт', 'website': 'Сайт', 'веб-сайт': 'Сайт'}
    for line in text.splitlines():
        match = re.match(r'^\s*([^:=]+?)\s*[:=]\s*(.+?)\s*$', line)
        if match:
            field = aliases.get(match.group(1).strip().casefold())
            if field and field not in result:
                result[field] = match.group(2)
    return result



def cell_text(cell):
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fmt = cell.number_format or ''
        if fmt and set(fmt) == {'0'}:
            return str(int(value)).zfill(len(fmt))
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%y')
    return str(value)


def read_tables(path):
    if path.lower().endswith('.csv'):
        for encoding in ('utf-8-sig', 'cp1251'):
            try:
                with open(path, encoding=encoding, newline='') as f:
                    text = f.read()
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError('Не удалось прочитать кодировку CSV')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        return {'CSV': list(csv.reader(io.StringIO(text), dialect))}
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return {s.title: [[cell_text(c) for c in row] for row in s.iter_rows()] for s in book}
    finally:
        book.close()


class ProfilePanel(ttk.Frame):
    def __init__(self, parent, settings_dir):
        super().__init__(parent, padding=12)
        self.settings_path = os.path.join(settings_dir, 'profile_panel.json')
        try:
            with open(self.settings_path, encoding='utf-8') as f:
                self.settings = json.load(f)
        except (OSError, ValueError):
            self.settings = {}
        self.tables, self.rows, self.visible = {}, [], []
        self.headers, self.current, self.clip_value = [], {}, None
        self.path = tk.StringVar(value=self.settings.get('path', ''))
        self.sheet = tk.StringVar()
        self.query = tk.StringVar()
        self.status = tk.StringVar(value='Откройте таблицу. Первая строка должна содержать заголовки.')
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Button(self, text='Открыть Excel / CSV…', command=self.open_file).grid(row=0, column=0, sticky='w')
        ttk.Label(self, textvariable=self.path).grid(row=0, column=1, sticky='w', padx=8)
        self.sheet_box = ttk.Combobox(self, textvariable=self.sheet, state='readonly', width=24)
        self.sheet_box.grid(row=1, column=0, sticky='w', pady=8)
        self.sheet_box.bind('<<ComboboxSelected>>', lambda e: self.select_sheet())
        ttk.Button(self, text='Применить колонки', command=self.apply_mapping).grid(row=1, column=1, sticky='w')
        mapping = ttk.Frame(self)
        mapping.grid(row=2, column=0, columnspan=2, sticky='we')
        self.maps, self.boxes = {}, {}
        for i, name in enumerate(SOURCES):
            group, slot = i // 4, i % 4
            ttk.Label(mapping, text=name).grid(row=group*2, column=slot, sticky='w', padx=4)
            var = tk.StringVar()
            box = ttk.Combobox(mapping, textvariable=var, state='readonly', width=23)
            box.grid(row=group*2+1, column=slot, sticky='we', padx=4, pady=(0, 8))
            mapping.columnconfigure(slot, weight=1)
            self.maps[name], self.boxes[name] = var, box
        body = ttk.PanedWindow(self, orient='horizontal')
        body.grid(row=3, column=0, columnspan=2, sticky='nsew')
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=3)
        ttk.Label(left, text='Поиск профиля').pack(anchor='w')
        ttk.Entry(left, textvariable=self.query).pack(fill='x', pady=4)
        self.query.trace_add('write', lambda *a: self.filter_rows())
        listing = ttk.Frame(left)
        listing.pack(fill='both', expand=True)
        self.listbox = tk.Listbox(listing, exportselection=False, width=28)
        scroll = ttk.Scrollbar(listing, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.listbox.bind('<<ListboxSelect>>', self.select_row)
        right.columnconfigure(1, weight=1)
        self.values, self.entries = {}, {}
        for i, name in enumerate(FIELDS):
            ttk.Label(right, text=name).grid(row=i, column=0, sticky='w', padx=8, pady=5)
            var = tk.StringVar()
            entry = ttk.Entry(right, textvariable=var, state='readonly', show='*' if name in SECRET else '')
            entry.grid(row=i, column=1, sticky='we', pady=5)
            ttk.Button(right, text='Копировать', command=lambda n=name: self.copy(n)).grid(row=i, column=2, padx=5)
            if name in SECRET:
                ttk.Button(right, text='Показать', command=lambda n=name: self.reveal(n)).grid(row=i, column=3)
            self.values[name], self.entries[name] = var, entry
        ttk.Label(self, textvariable=self.status, wraplength=900).grid(row=4, column=0, columnspan=2, sticky='w', pady=10)

    def open_file(self):
        path = filedialog.askopenfilename(parent=self, initialdir=os.path.dirname(self.path.get()) or None,
            filetypes=[('Таблицы', '*.xlsx *.csv'), ('Excel', '*.xlsx'), ('CSV', '*.csv')])
        if not path:
            return
        try:
            tables = read_tables(path)
        except Exception:
            messagebox.showerror('Таблица', 'Не удалось прочитать файл. Проверьте формат и доступ к файлу.', parent=self)
            return
        self.clear_clipboard()
        self.tables = tables
        self.path.set(path)
        self.sheet_box.configure(values=list(tables))
        preferred = self.settings.get('sheet')
        self.sheet.set(preferred if preferred in tables else next(iter(tables)))
        self.select_sheet()

    def select_sheet(self):
        data = self.tables.get(self.sheet.get(), [])
        self.headers = [f'{i+1}: {str(v).strip() or "Без заголовка"}' for i, v in enumerate(data[0])] if data else []
        self.rows = data[1:]
        saved = self.settings.get('mapping', {})
        for name, box in self.boxes.items():
            box.configure(values=[''] + self.headers)
            choice = saved.get(name, '')
            if choice not in self.headers:
                choice = next((h for h in self.headers if header_key(h.split(': ', 1)[1]) == header_key(name)), '')
            self.maps[name].set(choice)
        self.filter_rows()
        self.status.set('Выберите пять колонок и нажмите «Применить колонки». Адрес, фирма и сайт распознаются по меткам в отдельных строках.')

    def get_value(self, row, name):
        selected = self.maps[name].get()
        if selected not in self.headers:
            return ''
        index = self.headers.index(selected)
        return str(row[index]) if index < len(row) and row[index] is not None else ''

    def apply_mapping(self):
        if not self.maps[FIELDS[0]].get():
            self.status.set('Выберите колонку «Название профиля».')
            return
        self.settings = {'path': self.path.get(), 'sheet': self.sheet.get(),
                         'mapping': {k: v.get() for k, v in self.maps.items()}}
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except OSError:
            self.status.set('Настройки не сохранены; таблица доступна в текущем сеансе.')
            self.filter_rows()
            return
        self.filter_rows()
        self.status.set('Колонки применены. Выберите профиль. Исходный файл не изменяется.')

    def filter_rows(self):
        self.clear_clipboard()
        self.current = {}
        for name, var in self.values.items():
            var.set('')
            if name in SECRET:
                self.entries[name].configure(show='*')
        self.listbox.delete(0, 'end')
        self.visible = []
        for number, row in enumerate(self.rows, 2):
            name = self.get_value(row, FIELDS[0])
            if name and self.query.get().casefold() in name.casefold():
                self.visible.append(row)
                self.listbox.insert('end', f'{name}  [строка {number}]')

    def select_row(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        self.clear_clipboard()
        row = self.visible[selection[0]]
        info = self.get_value(row, 'Платежная информация')
        self.current = {name: '' for name in FIELDS}
        self.current.update(split_information(info))
        self.current.update({'Название профиля': self.get_value(row, 'Название профиля'),
                             'Информация': info, 'Карта': self.get_value(row, 'Карта'),
                             'ММ/ГГ': self.get_value(row, 'Срок карты'),
                             'CVV/CVC': self.get_value(row, 'СVV')})
        for name, var in self.values.items():
            var.set(self.current[name])
            if name in SECRET:
                self.entries[name].configure(show='*')
        self.status.set('Профиль выбран. Проверьте реквизиты перед копированием.')

    def reveal(self, name):
        self.entries[name].configure(show='' if self.entries[name].cget('show') else '*')
        self.after(15000, lambda: self.entries[name].configure(show='*'))

    def copy(self, name):
        value = self.current.get(name, '')
        if not value:
            self.status.set('Поле пустое или профиль не выбран.')
            return
        self.clear_clipboard()
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status.set('Значение скопировано.' + (' Буфер будет очищен через 30 секунд.' if name in SECRET else ''))
        if name in SECRET:
            self.clip_value = value
            self.clip_generation = getattr(self, 'clip_generation', 0) + 1
            generation = self.clip_generation
            self.after(30000, lambda: self.clear_clipboard() if generation == self.clip_generation else None)

    def clear_clipboard(self):
        if self.clip_value is not None:
            try:
                if self.clipboard_get() == self.clip_value:
                    self.clipboard_clear()
            except tk.TclError:
                pass
            self.clip_value = None

    def destroy(self):
        self.clear_clipboard()
        self.tables, self.rows, self.visible, self.current = {}, [], [], {}
        super().destroy()
