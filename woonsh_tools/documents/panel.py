"""
Панель «Документы» — локальный архив документов с привязкой к профилям.
Из X-File documents_panel.py — адаптировано для Woonsh Tools.
"""

import datetime as dt
import hashlib
import os
from pathlib import Path
import queue
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid

from woonsh_tools.documents.fields import FIELDS, extract_fields, valid_date
from woonsh_tools.documents.dedup import consolidate, profile_identity
from woonsh_tools.core.secure_store import load, save
from woonsh_tools.core.ui_helpers import clipboard_support


def company_id(name):
    return ' '.join(name.casefold().split())


class FieldEditor(tk.Toplevel):
    """Диалог проверки полей документа по оригиналу."""

    def __init__(self, parent, record, on_save):
        super().__init__(parent)
        self.title('Проверка документа — ' + record.get('name', ''))
        self.transient(parent.winfo_toplevel())
        self.configure(
            background=ttk.Style(self).lookup('TFrame', 'background')
                       or '#100c1c')
        self.record = record
        self.on_save = on_save

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text='Проверьте по оригиналу. Нераспознанные поля оставлены пустыми.'
        ).grid(row=0, column=0, columnspan=2, pady=(0, 12))

        self.values = {}
        for row, field in enumerate(FIELDS, 1):
            ttk.Label(frame, text=field).grid(row=row, column=0,
                                               sticky='w', pady=5)
            var = tk.StringVar(
                value=record.get('fields', {}).get(field, ''))
            entry = ttk.Entry(frame, textvariable=var, width=55)
            entry.grid(row=row, column=1, sticky='we', padx=10, pady=5)
            clipboard_support(entry)
            self.values[field] = var

        ttk.Label(
            frame,
            text='Даты: ДД.ММ.ГГГГ. Страна — страна выдачи документа.'
        ).grid(row=6, column=0, columnspan=2, sticky='w', pady=8)

        self.checked = tk.BooleanVar(value=record.get('checked', False))
        ttk.Checkbutton(
            frame, text='Я проверил(а) данные по оригиналу',
            variable=self.checked).grid(
            row=7, column=0, columnspan=2, sticky='w')

        ttk.Button(
            frame, text='Сохранить поля', command=self.accept,
            style='Accent.TButton').grid(
            row=8, column=1, sticky='e', pady=12)

        self.grab_set()

    def accept(self):
        values = {key: var.get().strip() for key, var in self.values.items()}
        for field in ('Дата рождения', 'Действителен до'):
            if values[field]:
                value = valid_date(values[field])
                if not value:
                    messagebox.showerror(
                        'Дата',
                        'Проверьте поле «%s»: нужна дата ДД.ММ.ГГГГ.' % field,
                        parent=self)
                    return
                values[field] = value
        if values['Дата рождения']:
            if dt.datetime.strptime(values['Дата рождения'],
                                     '%d.%m.%Y').date() > dt.date.today():
                messagebox.showerror(
                    'Дата', 'Дата рождения не может быть в будущем.',
                    parent=self)
                return

        old = dict(self.record)
        self.record.update(fields=values, checked=self.checked.get())
        try:
            self.on_save()
        except Exception:
            self.record.clear()
            self.record.update(old)
            messagebox.showerror(
                'Сохранение', 'Не удалось сохранить поля документа.',
                parent=self)
            return
        self.destroy()


class DocumentsPanel(ttk.Frame):
    """Панель управления документами: привязка к профилям, OCR, ревью."""

    def __init__(self, parent, app, app_dir):
        super().__init__(parent, padding=12)
        self.app = app
        self.root_dir = Path(app_dir) / 'documents'
        self.registry = Path(app_dir) / 'documents_registry.dpapi'
        self.events = queue.Queue()
        self.busy = False
        self.data = {
            'version': 1, 'identity_version': 2,
            'profiles': {}, 'companies': {},
        }
        self.load_error = False
        self.merge_report = None

        if self.registry.exists():
            try:
                self.data = load(self.registry)
                if (self.data.get('version') != 1
                        or not isinstance(self.data.get('profiles'), dict)
                        or not isinstance(self.data.get('companies'), dict)):
                    raise ValueError('Unknown version')
                self.data['companies'] = {
                    company_id(v['name']): v
                    for v in self.data['companies'].values()}
                self.data, self.merge_report = consolidate(
                    self.data, self.registry, self.root_dir,
                    save_fn=save)
            except Exception:
                self.data = {
                    'version': 1, 'identity_version': 2,
                    'profiles': {}, 'companies': {},
                }
                self.load_error = True

        self.items = {}
        self.records = []
        self.query = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(5, weight=1)

        ttk.Label(
            self,
            text='Локальные копии документов закреплены за компанией и профилем. '
                 'Распознанные поля нужно проверить.'
        ).grid(sticky='w')

        # Кнопки
        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky='we', pady=8)
        for label, command in [
            ('Обновить', self.refresh),
            ('Папка профиля', self.open_profile_folder),
            ('Добавить выписку', lambda: self.attach('Выписка')),
            ('Добавить физ. документ', lambda: self.attach('Физ. документ')),
        ]:
            ttk.Button(bar, text=label, command=command).pack(
                side='left', padx=(0, 6))

        # Поиск
        search = ttk.Frame(self)
        search.grid(row=2, column=0, sticky='we', pady=(0, 8))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text='Поиск профиля или компании').grid(
            row=0, column=0, padx=(0, 8))
        search_entry = ttk.Entry(search, textvariable=self.query)
        search_entry.grid(row=0, column=1, sticky='we')
        clipboard_support(search_entry)
        ttk.Button(search, text='Очистить',
                   command=lambda: self.query.set('')).grid(
            row=0, column=2, padx=(8, 0))
        self.query.trace_add('write', lambda *a: self.refresh())

        # Таблица профилей
        self.tree = ttk.Treeview(
            self, columns=('profile', 'company', 'statement', 'personal'),
            show='headings', selectmode='extended', height=5)
        for key, title in [('profile', 'Профиль'), ('company', 'Компания'),
                           ('statement', 'Выписки'), ('personal', 'Физ. документы')]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=190)
        self.tree.grid(row=3, column=0, sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.show_documents())

        # Кнопки файлов
        actions = ttk.Frame(self)
        actions.grid(row=4, column=0, sticky='we', pady=8)
        for label, command in [
            ('Открыть файл', self.open_file),
            ('Распознать поля', self.recognize),
            ('Проверить / изменить', self.edit),
            ('Удалить привязку', self.detach),
        ]:
            ttk.Button(actions, text=label, command=command).pack(
                side='left', padx=(0, 6))

        # Таблица файлов
        columns = ('kind', 'name', 'fio', 'birth', 'expiry',
                   'country', 'type', 'review')
        self.files = ttk.Treeview(
            self, columns=columns, show='headings',
            selectmode='browse', height=6)
        for key, title in zip(columns, [
            'Категория', 'Файл', 'ФИО', 'Рождение', 'Действителен до',
            'Страна выдачи', 'Вид', 'Проверка',
        ]):
            self.files.heading(key, text=title)
            self.files.column(key, width=125, stretch=True)
        self.files.grid(row=5, column=0, sticky='nsew')

        horizontal = ttk.Scrollbar(
            self, orient='horizontal', command=self.files.xview)
        horizontal.grid(row=6, column=0, sticky='we')
        self.files.configure(xscrollcommand=horizontal.set)

        self.status = tk.StringVar(
            value='Исходные файлы не изменяются. '
                  'Прикреплённые файлы копируются в локальное хранилище.')
        if self.load_error:
            self.status.set(
                'Архив недоступен для расшифровки. Запись заблокирована.')
        ttk.Label(self, textvariable=self.status,
                  wraplength=1000).grid(row=7, column=0, sticky='w', pady=8)

        self.after(300, self.poll)
        self.after(1000, lambda: self.refresh())

    def persist(self):
        if self.load_error:
            raise OSError('Registry locked')
        save(self.registry, self.data)

    def profile(self):
        selection = self.tree.selection()
        return self.items.get(selection[0]) if len(selection) == 1 else None

    def selected_file(self):
        selection = self.files.selection()
        if not selection:
            return None
        return next(
            (r for r in self.records if r['id'] == selection[0]), None)

    def refresh(self):
        selection = self.tree.selection()
        self.items = {key: dict(value, key=key)
                      for key, value in self.data['profiles'].items()}

        represented = {company_id(item['company'])
                       for item in self.items.values()}
        for key, value in self.data['companies'].items():
            if key not in represented:
                self.items['company:' + key] = {
                    'key': 'company:' + key,
                    'name': '— (история выписок)',
                    'company': value['name'],
                    'docs': [],
                }

        self.tree.delete(*self.tree.get_children())
        for key, item in self.items.items():
            if (self.query.get().strip().casefold()
                    not in (item['name'] + ' ' + item['company']).casefold()):
                continue
            statement = self.data['companies'].get(
                company_id(item['company']), {}).get('docs', [])
            personal = item.get('docs', [])
            self.tree.insert('', 'end', iid=key, values=(
                item['name'], item['company'],
                len(statement),
                len({r.get('pair_id') or r['id'] for r in personal})))

        restored = [key for key in selection if self.tree.exists(key)]
        if restored:
            self.tree.selection_set(restored)
        self.show_documents()

    def open_profile_folder(self):
        item = self.profile()
        if not item or item['key'].startswith('company:'):
            self.status.set(
                'Выберите конкретный профиль, чтобы открыть его папку.')
            return
        try:
            folder = self.data['profiles'][item['key']].get('folder')
            if folder:
                os.startfile(folder)
        except Exception:
            messagebox.showerror(
                'Папка', 'Не удалось открыть папку профиля.',
                parent=self)

    def document_path(self, record):
        item = self.profile()
        if item:
            path = record.get('profile_paths', {}).get(item['key'])
            if path and Path(path).exists():
                return path
        return record['path']

    def show_documents(self):
        selected = self.files.selection()
        self.files.delete(*self.files.get_children())
        item = self.profile()
        self.records = []
        if item:
            self.records = (
                list(self.data['companies'].get(
                    company_id(item['company']), {}).get('docs', []))
                + list(self.data['profiles'].get(
                    item['key'], {}).get('docs', [])))
        for record in self.records:
            f = record.get('fields', {})
            status = 'Проверено' if record.get('checked') else 'Нужно проверить'
            expiry = f.get('Действителен до', '')
            if expiry and valid_date(expiry):
                if dt.datetime.strptime(expiry, '%d.%m.%Y').date() < dt.date.today():
                    status += '; срок истёк'
            if not Path(record['path']).is_file():
                status = 'Файл не найден'
            self.files.insert('', 'end', iid=record['id'], values=(
                record['kind'], record['name'],
                f.get('ФИО', ''), f.get('Дата рождения', ''),
                expiry, f.get('Страна выдачи', ''),
                f.get('Вид документа', ''), status))
        if selected and any(r['id'] == selected[0] for r in self.records):
            self.files.selection_set(selected[0])

    def archive(self, source, company, kind, profile=None):
        """Архивация документа с SHA-256 дедупликацией."""
        if self.load_error:
            raise OSError('Registry locked')
        source = Path(source)
        if source.suffix.lower() not in (
                '.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
            raise ValueError('Unsupported document type')

        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        hexdigest = digest.hexdigest()

        self.root_dir.mkdir(parents=True, exist_ok=True)
        dest = self.root_dir / (hexdigest + source.suffix.lower())

        if kind == 'Выписка':
            owner = self.data['companies'].setdefault(
                company_id(company), {'name': company, 'docs': []})
        else:
            owner = self.data['profiles'].setdefault(
                profile['key'],
                {'name': profile['name'], 'company': company, 'docs': []})

        existing = next(
            (r for r in owner['docs'] if r['sha256'] == hexdigest), None)
        if not dest.exists():
            temp = dest.with_suffix(dest.suffix + '.tmp')
            shutil.copy2(source, temp)
            temp.replace(dest)
        if existing:
            return existing

        record = {
            'id': uuid.uuid4().hex, 'kind': kind,
            'name': source.name, 'path': str(dest),
            'sha256': hexdigest, 'fields': {}, 'checked': False,
        }
        owner['docs'].append(record)
        try:
            self.persist()
        except Exception:
            owner['docs'].remove(record)
            raise
        return record

    def attach(self, kind):
        item = self.profile()
        if not item:
            self.status.set(
                'Выберите профиль или компанию.')
            return
        if kind == 'Физ. документ' and item['key'].startswith('company:'):
            self.status.set(
                'Выберите конкретный профиль для документа физлица.')
            return
        if not item.get('company'):
            self.status.set(
                'Для профиля не распознано название фирмы.')
            return

        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[('Документы',
                        '*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if not path:
            return
        try:
            record = self.archive(path, item['company'], kind, item)
        except Exception:
            messagebox.showerror(
                'Архив',
                'Не удалось сохранить копию документа.',
                parent=self)
            return

        self.refresh()
        self.tree.selection_set(item['key'])
        self.show_documents()
        self.files.selection_set(record['id'])

        if kind == 'Физ. документ':
            self.recognize()
        else:
            self.status.set('Локальная копия выписки закреплена за компанией.')

    def open_file(self):
        record = self.selected_file()
        if record:
            try:
                os.startfile(self.document_path(record))
            except OSError:
                messagebox.showerror(
                    'Документ',
                    'Не удалось открыть локальную копию файла.',
                    parent=self)

    def recognize(self):
        record = self.selected_file()
        if not record:
            return
        if self.busy:
            self.status.set('Распознавание уже идёт. Дождитесь завершения.')
            return

        self.busy = True
        self.status.set('Локальное распознавание документа…')
        path = self.document_path(record)
        record_id = record['id']

        paths = [path]
        if record.get('pair_id'):
            paired = [r for r in self.records
                      if r.get('pair_id') == record['pair_id']]
            paired.sort(key=lambda r: 0 if r.get('side') == 'front' else 1)
            paths = [self.document_path(r) for r in paired]

        def worker():
            try:
                from woonsh_tools.documents.reader import paired_fields
                fields = paired_fields(self.app, paths)
                note = ('Прочитаны обе стороны документа.' if len(paths) > 1
                        else 'Локальное распознавание завершено.')
                self.events.put((record_id, fields, note))
            except Exception:
                self.events.put((
                    record_id,
                    {field: '' for field in FIELDS},
                    'Не удалось прочитать документ. '
                    'Поля можно заполнить вручную.'))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        if not self.events.empty():
            record_id, fields, note = self.events.get_nowait()
            self.busy = False
            record = None
            for owner in (list(self.data['profiles'].values())
                          + list(self.data['companies'].values())):
                record = next(
                    (r for r in owner['docs'] if r['id'] == record_id), None)
                if record:
                    break
            if record:
                previous = dict(record.get('fields', {}))
                record['fields'] = {
                    field: previous.get(field) or fields.get(field, '')
                    for field in FIELDS}
                if record['fields'] != previous:
                    record['checked'] = False
                try:
                    self.persist()
                except Exception:
                    self.status.set(
                        'Не удалось сохранить результаты распознавания.')
                else:
                    msg = note + ' ' if note else ''
                    if any(record['fields'].values()):
                        msg += 'Поля распознаны. Проверьте по оригиналу.'
                    else:
                        msg += ('Текст прочитан, но поля не определены. '
                                'Заполните вручную.')
                    self.status.set(msg)
                    self.show_documents()
                    FieldEditor(self, record,
                                lambda r=record: self.save_editor(r))
        self.after(300, self.poll)

    def save_editor(self, record=None):
        if record and record.get('pair_id'):
            for owner in self.data['profiles'].values():
                for other in owner['docs']:
                    if (other.get('pair_id') == record['pair_id']
                            and other is not record):
                        other['fields'] = dict(record['fields'])
                        other['checked'] = record.get('checked', False)
        self.persist()
        self.show_documents()

    def edit(self):
        record = self.selected_file()
        if record:
            FieldEditor(self, record,
                        lambda r=record: self.save_editor(r))

    def detach(self):
        record = self.selected_file()
        if not record:
            return
        if not messagebox.askyesno(
                'Удалить привязку',
                'Удалить привязку документа? '
                'Локальная копия файла останется в архиве.',
                parent=self):
            return
        for owner in (list(self.data['profiles'].values())
                      + list(self.data['companies'].values())):
            if record in owner['docs']:
                owner['docs'].remove(record)
                try:
                    self.persist()
                except Exception:
                    owner['docs'].append(record)
                    messagebox.showerror(
                        'Архив', 'Не удалось удалить привязку.',
                        parent=self)
                break
        self.refresh()
