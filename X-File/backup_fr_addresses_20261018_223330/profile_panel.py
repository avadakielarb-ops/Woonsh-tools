"""Local table viewer. Only column mappings and source path are persisted."""
import csv
import io
import json
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
import threading
import queue

FIELDS = ('Название профиля', 'Название фирмы', 'Адрес (полный)', 'Улица', 'Почтовый индекс', 'Город', 'Прокси', 'Прокси для карты', 'Сайт', 'Карта', 'ММ/ГГ', 'CVV/CVC', 'Информация')
LABELS = {'Название фирмы':'Название компании', 'Улица':'Адрес: только улица'}
MASKED = {'Информация'}
SOURCES = ('Название профиля', 'Платежная информация', 'Карта', 'Срок карты', 'СVV', 'Прокси', 'Прокси для карты')
SECRET = {'Карта', 'ММ/ГГ', 'CVV/CVC', 'Информация'}

def header_key(text):
    return ''.join(str(text).lower().split()).replace('ё', 'е').replace('с', 'c').replace('в', 'v')

def split_information(text):
    result = {}
    parts = [part.strip() for part in text.split('|')]
    if len(parts) == 3:
        result.update({'Название фирмы': parts[0], 'Адрес': parts[1], 'Сайт': parts[2]})
    else:
        aliases = {'адрес': 'Адрес', 'address': 'Адрес', 'название фирмы': 'Название фирмы',
                   'название': 'Название фирмы', 'компания': 'Название фирмы', 'company': 'Название фирмы',
                   'почтовый индекс': 'Почтовый индекс', 'индекс': 'Почтовый индекс',
                   'postal code': 'Почтовый индекс', 'zip': 'Почтовый индекс',
                   'город': 'Город', 'city': 'Город', 'улица': 'Улица', 'street': 'Улица',
                   'сайт': 'Сайт', 'website': 'Сайт', 'веб-сайт': 'Сайт'}
        for line in text.splitlines():
            match = re.match(r'^\s*([^:=]+?)\s*[:=]\s*(.+?)\s*$', line)
            if match:
                field = aliases.get(match.group(1).strip().casefold())
                if field and field not in result:
                    result[field] = match.group(2)
    website = result.get('Сайт', '')
    link = re.fullmatch(r'\[[^\]]*\]\((https?://[^\s]+)\)', website)
    if link:
        result['Сайт'] = link.group(1)
    address = result.get('Адрес', '').strip()
    result['Адрес (полный)'] = address
    segments = [part.strip() for part in address.split(',') if part.strip()]
    if len(segments) >= 2:
        result['Улица'] = segments[0]
    # A postcode must start a comma-separated city segment; house numbers
    # in the street segment are never treated as postcodes.
    city_matches = []
    for part in segments[1:]:
        match = re.fullmatch(r'(?P<postal>\d{2}-\d{3}|\d{3}\s\d{2}|\d{3,6})\s+(?P<city>[^\d].*)', part)
        if match:
            city_matches.append(match)
    if len(city_matches) == 1:
        match = city_matches[0]
        result['Почтовый индекс'] = result.get('Почтовый индекс') or match.group('postal')
        result['Город'] = match.group('city').strip()
        # Keep the legacy address key for integrations that use it.
        result['Адрес'] = address.replace(match.group(0), match.group('city'), 1)
    elif len(segments) >= 3:
        # With separate street, city and country parts the middle part is city.
        # Do not guess when it contains unparsed digits or multiple parts.
        if len(segments) == 3 and not any(c.isdigit() for c in segments[1]):
            result['Город'] = segments[1]
    if not result.get('Улица') and address and not ',' in address:
        result['Улица'] = address
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
        self.snapshot_path = Path(settings_dir) / 'profiles_snapshot.dpapi'
        self.download_events = queue.Queue()
        self.downloading = False
        self.keep_data = tk.BooleanVar(value=True)
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
        file_buttons = ttk.Frame(self)
        file_buttons.grid(row=0, column=0, sticky='w')
        ttk.Button(file_buttons, text='Excel / CSV…', command=self.open_file).pack(side='left')
        ttk.Button(file_buttons, text='По ссылке…', command=self.open_link).pack(side='left', padx=5)
        ttk.Button(file_buttons, text='Обновить ссылку', command=self.refresh_link).pack(side='left')
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
        from profile_scroll import ScrollFields
        left, right_scroll = ttk.Frame(body), ScrollFields(body)
        right = right_scroll.content
        body.add(left, weight=1)
        body.add(right_scroll, weight=3)
        ttk.Label(left, text='Поиск профиля · Ctrl / Shift — несколько').pack(anchor='w')
        ttk.Entry(left, textvariable=self.query).pack(fill='x', pady=4)
        self.query.trace_add('write', lambda *a: self.filter_rows())
        listing = ttk.Frame(left)
        listing.pack(fill='both', expand=True)
        self.listbox = tk.Listbox(listing, exportselection=False, width=28, selectmode='extended')
        scroll = ttk.Scrollbar(listing, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.listbox.bind('<<ListboxSelect>>', self.select_row)
        ttk.Button(left,text='Показать выбранные',command=self.show_selected).pack(fill='x',pady=5)
        ttk.Button(left,text='Выбрать все',command=self.select_all_profiles).pack(fill='x')
        right.columnconfigure(1, weight=1)
        self.values, self.entries = {}, {}
        for i, name in enumerate(FIELDS):
            ttk.Label(right, text=LABELS.get(name, name)).grid(row=i, column=0, sticky='w', padx=8, pady=5)
            var = tk.StringVar()
            entry = ttk.Entry(right, textvariable=var, state='readonly', show='*' if name in MASKED else '')
            entry.grid(row=i, column=1, sticky='we', pady=5)
            ttk.Button(right, text='Копировать', command=lambda n=name: self.copy(n)).grid(row=i, column=2, padx=5)
            if name in MASKED:
                ttk.Button(right, text='Показать', command=lambda n=name: self.reveal(n)).grid(row=i, column=3)
            self.values[name], self.entries[name] = var, entry
        ttk.Label(self, textvariable=self.status, wraplength=900).grid(row=4, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Checkbutton(self, text='Сохранять профили между запусками (шифрование Windows)', variable=self.keep_data, command=self.persist).grid(row=5, column=0, columnspan=2, sticky='w')
        right_scroll.bind_fields()
        self.restore_snapshot()
        self.after(200, self.poll_download)

    def persist(self):
        if not self.keep_data.get():
            try:
                self.snapshot_path.unlink(missing_ok=True)
                self.settings['keep_data'] = False
                with open(self.settings_path, 'w', encoding='utf-8') as f:
                    json.dump(self.settings, f, ensure_ascii=False)
            except OSError:
                self.status.set('Не удалось удалить сохранённую копию профилей.')
            return
        if not self.headers or not self.rows:
            return
        # Persist only the five chosen columns, not passwords/email/2FA columns.
        indices = [self.headers.index(v.get()) for v in self.maps.values() if v.get() in self.headers]
        rows = [[str(row[i]) if i in indices and i < len(row) else '' for i in range(len(self.headers))] for row in self.rows]
        data = {'version':1, 'path':self.path.get(), 'sheet':self.sheet.get(),
                'header':[h.split(': ',1)[1] for h in self.headers], 'rows':rows,
                'mapping':{k:v.get() for k,v in self.maps.items()}}
        try:
            from profile_store import save
            save(self.snapshot_path, data)
            self.settings.update({'keep_data':True, 'path':self.path.get(), 'sheet':self.sheet.get(), 'mapping':data['mapping']})
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            self.status.set('Не удалось сохранить зашифрованную копию профилей. Исходный файл не изменён.')

    def restore_snapshot(self):
        self.keep_data.set(self.settings.get('keep_data', True))
        if not self.snapshot_path.exists() or not self.keep_data.get():
            return
        try:
            from profile_store import load
            data = load(self.snapshot_path)
            if data.get('version') != 1:
                raise ValueError('Unknown snapshot version')
            self.path.set(data['path'])
            self.tables = {data['sheet']:[data['header']] + data['rows']}
            self.sheet_box.configure(values=list(self.tables))
            self.sheet.set(data['sheet'])
            self.settings['mapping'] = data['mapping']
            self.select_sheet()
            self.status.set('Восстановлена сохранённая таблица. Для актуальных данных нажмите «Обновить ссылку» или откройте файл заново.')
        except Exception:
            self.status.set('Не удалось восстановить профили. Откройте исходную таблицу. Копия сохранена для восстановления.')

    def open_link(self):
        from ui_helpers import LinkDialog
        dialog = LinkDialog(self, self.path.get() if self.path.get().startswith(('http://','https://')) else '')
        self.wait_window(dialog)
        if dialog.result:
            self.fetch_link(dialog.result)

    def refresh_link(self):
        if self.path.get().startswith(('http://','https://')):
            self.fetch_link(self.path.get())
        else:
            self.open_link()

    def fetch_link(self, url):
        if self.downloading:
            self.status.set('Таблица уже загружается.')
            return
        self.downloading = True
        self.status.set('Загружаю таблицу по ссылке…')
        def worker():
            try:
                from profile_store import download
                self.download_events.put((url, download(url), None))
            except Exception:
                self.download_events.put((url, None, 'Не удалось получить Excel/CSV. Проверьте доступ по ссылке; если нужен вход — скачайте файл и откройте локально.'))
        threading.Thread(target=worker, daemon=True).start()

    def poll_download(self):
        if not self.download_events.empty():
            url, tables, error = self.download_events.get_nowait()
            self.downloading = False
            if error:
                self.status.set(error)
            else:
                self.clear_clipboard()
                self.tables = tables
                self.path.set(url)
                self.sheet_box.configure(values=list(tables))
                preferred = self.sheet.get()
                self.sheet.set(preferred if preferred in tables else next(iter(tables)))
                self.select_sheet()
                if self.maps['Название профиля'].get():
                    self.apply_mapping()
        self.after(200, self.poll_download)

    def open_file(self):
        path = filedialog.askopenfilename(parent=self, initialdir=(os.path.dirname(self.path.get()) if not self.path.get().startswith(('http://','https://')) else None) or None,
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
        self.status.set('Выберите пять колонок и нажмите «Применить колонки». Формат информации: Название | Адрес с индексом | Сайт. Также поддерживаются строки с метками.')

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
        self.settings = {'keep_data':self.keep_data.get(), 'path': self.path.get(), 'sheet': self.sheet.get(),
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
        self.persist()

    def filter_rows(self):
        self.clear_clipboard()
        self.current = {}
        for name, var in self.values.items():
            var.set('')
            if name in MASKED:
                self.entries[name].configure(show='*')
        self.listbox.delete(0, 'end')
        self.visible = []
        for number, row in enumerate(self.rows, 2):
            name = self.get_value(row, FIELDS[0])
            if name and self.query.get().casefold() in name.casefold():
                self.visible.append(row)
                self.listbox.insert('end', f'{name}  [строка {number}]')

    def values_for_row(self, row):
        info = self.get_value(row, 'Платежная информация')
        values = {name:'' for name in FIELDS}
        values.update(split_information(info))
        values.update({'Название профиля':self.get_value(row,'Название профиля'),
                       'Информация':info, 'Карта':self.get_value(row,'Карта'),
                       'ММ/ГГ':self.get_value(row,'Срок карты'),
                       'CVV/CVC':self.get_value(row,'СVV'),
                       'Прокси':self.get_value(row,'Прокси'),
                       'Прокси для карты':self.get_value(row,'Прокси для карты')})
        return values

    def select_all_profiles(self):
        self.listbox.selection_set(0,'end')
        self.select_row()

    def select_row(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        self.clear_clipboard()
        active=self.listbox.index('active')
        index=active if active in selection else selection[0]
        self.current=self.values_for_row(self.visible[index])
        for name,var in self.values.items():
            var.set(self.current.get(name,''))
            if name in MASKED:self.entries[name].configure(show='*')
        self.status.set('Выбрано профилей: %d. Справа — %s. Для просмотра всех нажмите «Показать выбранные».' % (len(selection),self.current['Название профиля']))

    def show_selected(self):
        rows=[self.visible[i] for i in self.listbox.curselection()]
        if not rows:
            self.status.set('Выберите профили с Ctrl / Shift, затем нажмите «Показать выбранные».')
            return
        from profile_scroll import ScrollFields
        window=tk.Toplevel(self)
        window.title('Профили для копирования — %d' % len(rows))
        window.geometry('950x700')
        window.transient(self.winfo_toplevel())
        notebook=ttk.Notebook(window)
        notebook.pack(fill='both',expand=True,padx=10,pady=10)
        for number,row in enumerate(rows,1):
            values=self.values_for_row(row)
            pane=ScrollFields(notebook)
            notebook.add(pane,text='%d. %s'%(number,values['Название профиля']))
            pane.content.columnconfigure(1,weight=1)
            for index,name in enumerate(FIELDS):
                ttk.Label(pane.content,text=LABELS.get(name,name)).grid(row=index,column=0,sticky='w',padx=8,pady=6)
                var=tk.StringVar(value=values.get(name,''))
                entry=ttk.Entry(pane.content,textvariable=var,state='readonly',show='*' if name in MASKED else '')
                entry.grid(row=index,column=1,sticky='we',padx=8,pady=6)
                # Entry owns its Tcl variable through the Python reference.
                entry.value_var=var
                ttk.Button(pane.content,text='Копировать',command=lambda n=name,v=values.get(name,''):self.copy_value(n,v)).grid(row=index,column=2,padx=8)
                if name in MASKED:
                    ttk.Button(pane.content,text='Показать',command=lambda e=entry:e.configure(show='' if e.cget('show') else '*')).grid(row=index,column=3,padx=4)
            pane.bind_fields()
        window.protocol('WM_DELETE_WINDOW',lambda:(self.clear_clipboard(),window.destroy()))
        return window

    def reveal(self, name):
        self.entries[name].configure(show='' if self.entries[name].cget('show') else '*')
        self.after(15000, lambda: self.entries[name].configure(show='*'))

    def copy(self, name):
        self.copy_value(name, self.current.get(name, ''))

    def copy_value(self, name, value):
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
