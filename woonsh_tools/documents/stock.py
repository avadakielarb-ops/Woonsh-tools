"""
Склад свободных документов: импорт ZIP/RAR, OCR, назначение профилям.
Из X-File document_stock.py — адаптировано для Woonsh Tools.
"""

import copy
import datetime
from pathlib import Path
import os
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from woonsh_tools.core.secure_store import load, save
from woonsh_tools.core.ui_helpers import enable_clipboard
from woonsh_tools.documents.fields import FIELDS
from woonsh_tools.documents.archive import read_pairs, review_pairs
from woonsh_tools.documents.reader import paired_fields, classify_file
from woonsh_tools.documents.panel import FieldEditor


class AssignmentDialog(tk.Toplevel):
    """Назначение свободных комплектов выбранным профилям."""

    def __init__(self, parent, profiles, free, submit):
        super().__init__(parent)
        self.title('Свободные документы → выбранные профили')
        self.transient(parent.winfo_toplevel())
        self.configure(
            background=ttk.Style(self).lookup('TFrame', 'background')
                       or '#100c1c')
        self.choices = {}
        self.profiles = profiles
        self.free = free
        self.submit = submit

        self.columnconfigure(1, weight=1)
        ttk.Label(
            self,
            text='Выберите комплект для каждого профиля. '
                 'Автоматического распределения нет.'
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=12)

        labels = [''] + [
            '%03d · %s · %s' % (
                i + 1,
                record.get('fields', {}).get('ФИО') or 'ФИО не распознано',
                record['label'])
            for i, record in enumerate(free)]
        self.lookup = dict(zip(labels[1:], free))

        for i, profile in enumerate(profiles, 1):
            ttk.Label(self, text=profile['name']).grid(
                row=i, column=0, sticky='w', padx=12, pady=4)
            var = tk.StringVar()
            ttk.Combobox(
                self, textvariable=var, values=labels,
                state='readonly', width=75
            ).grid(row=i, column=1, sticky='we', padx=12, pady=4)
            self.choices[profile['key']] = var

        ttk.Button(
            self, text='Назначить выбранные комплекты',
            command=self.accept, style='Accent.TButton'
        ).grid(row=len(profiles) + 1, column=1, sticky='e', padx=12, pady=12)
        self.grab_set()

    def accept(self):
        choices = [
            (profile, self.lookup[self.choices[profile['key']].get()])
            for profile in self.profiles
            if self.choices[profile['key']].get()]
        if not choices:
            return
        if len({record['id'] for _, record in choices}) != len(choices):
            messagebox.showerror(
                'Один комплект — один профиль',
                'Один и тот же свободный комплект нельзя назначить '
                'сразу нескольким профилям.',
                parent=self)
            return
        try:
            self.submit(choices)
        except Exception:
            messagebox.showerror(
                'Назначение',
                'Не удалось завершить назначение. Проверьте статусы '
                'на складе и свободное место.',
                parent=self)
            return
        self.destroy()


class StockPanel(ttk.Frame):
    """Вкладка «Склад» — импорт, распознавание, назначение документов."""

    def __init__(self, parent, app, app_dir):
        super().__init__(parent, padding=12)
        self.app = app
        self.root_dir = Path(app_dir) / 'document_stock'
        self.registry = Path(app_dir) / 'document_stock.dpapi'
        self.data = {'version': 1, 'pairs': {}}
        self.locked = False

        if self.registry.exists():
            try:
                self.data = load(self.registry)
                if (self.data.get('version') != 1
                        or not isinstance(self.data.get('pairs'), dict)):
                    raise ValueError()
            except Exception:
                self.data = {'version': 1, 'pairs': {}}
                self.locked = True

        self.events = queue.Queue()
        self.busy = False
        self.query = tk.StringVar()
        self.only_free = tk.BooleanVar(value=True)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky='we', pady=8)
        for label, command in [
            ('Загрузить архивы…', self.import_archives),
            ('Распознать выбранные', self.recognize_selected),
            ('Распознать через Gemini…', self.recognize_gemini),
            ('Проверить поля', self.edit),
            ('Завершить назначения', self.resume_pending),
            ('Открыть папку', self.open_folder),
        ]:
            ttk.Button(bar, text=label, command=command).pack(
                side='left', padx=(0, 6))

        search = ttk.Frame(self)
        search.grid(row=1, column=0, sticky='we', pady=8)
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text='Поиск комплекта / ФИО').grid(
            row=0, column=0, padx=(0, 8))
        entry = ttk.Entry(search, textvariable=self.query)
        entry.grid(row=0, column=1, sticky='we')
        enable_clipboard(entry)
        ttk.Checkbutton(
            search, text='Только свободные',
            variable=self.only_free, command=self.refresh
        ).grid(row=0, column=2, padx=8)
        self.query.trace_add('write', lambda *_: self.refresh())

        columns = ('label', 'fio', 'birth', 'expiry',
                   'country', 'type', 'state', 'profile')
        self.tree = ttk.Treeview(
            self, columns=columns, show='headings', selectmode='extended')
        for key, title, width in zip(columns, [
            'Комплект', 'ФИО', 'Рождение', 'Действителен до',
            'Страна', 'Вид', 'Статус', 'Профиль',
        ], [250, 200, 110, 120, 100, 140, 140, 220]):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width)
        self.tree.grid(row=2, column=0, sticky='nsew')

        vertical = ttk.Scrollbar(self, command=self.tree.yview)
        vertical.grid(row=2, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(
            self, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=3, column=0, sticky='we')
        self.tree.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        self.status = tk.StringVar(
            value='Загрузите ZIP / RAR с папками front/back. '
                  'До назначения комплекты остаются свободными.')
        if self.locked:
            self.status.set(
                'Не удалось расшифровать склад. Запись заблокирована; '
                'исходный реестр сохранён.')
        ttk.Label(self, textvariable=self.status, wraplength=1050).grid(
            row=4, column=0, sticky='w', pady=8)

        self.refresh()
        self.after(250, self.poll)

    def persist(self):
        if self.locked:
            raise OSError('Stock registry locked')
        save(self.registry, self.data)

    def refresh(self):
        selection = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for key, record in self.data['pairs'].items():
            if (self.only_free.get()
                    and record.get('state', 'free') != 'free'):
                continue
            fields = record.get('fields', {})
            text = (record['label'] + ' ' + fields.get('ФИО', '')).casefold()
            if self.query.get().strip().casefold() not in text:
                continue
            state = {
                'free': 'Свободен',
                'assigned': 'Назначен',
                'pending': 'Назначение не завершено',
            }.get(record.get('state', 'free'), 'Неизвестно')
            if not record.get('checked'):
                state += ' · проверить'
            self.tree.insert('', 'end', iid=key, values=(
                record['label'],
                fields.get('ФИО', ''),
                fields.get('Дата рождения', ''),
                fields.get('Действителен до', ''),
                fields.get('Страна выдачи', ''),
                fields.get('Вид документа', ''),
                state,
                record.get('assignment', {}).get('profile_name', '')))
        restore = [k for k in selection if self.tree.exists(k)]
        if restore:
            self.tree.selection_set(restore)

    def add_pairs(self, pairs):
        if self.locked:
            raise OSError('Stock registry locked')
        count = 0
        for pair in pairs:
            if pair['id'] in self.data['pairs']:
                continue
            folder = self.root_dir / pair['id']
            folder.mkdir(parents=True, exist_ok=True)
            record = {k: pair[k] for k in ('id', 'label', 'front_sha', 'back_sha')}
            record.update(name=pair['label'], fields={},
                          checked=False, state='free')
            for side in ('front', 'back'):
                source = Path(pair[side])
                target = folder / (side + source.suffix.lower())
                temp = target.with_suffix(target.suffix + '.tmp')
                shutil.copy2(source, temp)
                temp.replace(target)
                record[side] = str(target)

            matched = []
            for key, owner in self.app.documents_panel.data['profiles'].items():
                if any(doc.get('sha256') in (pair['front_sha'], pair['back_sha'])
                       for doc in owner.get('docs', [])):
                    matched.append((key, owner))
            if matched:
                key, owner = matched[0]
                attached = {doc.get('sha256') for doc in owner.get('docs', [])}
                state = ('assigned'
                         if {pair['front_sha'], pair['back_sha']} <= attached
                         else 'pending')
                record.update(
                    state=state,
                    assignment={
                        'profile_key': key,
                        'profile_name': owner['name'],
                        'company': owner['company']})

            self.data['pairs'][record['id']] = record
            try:
                self.persist()
            except Exception:
                self.data['pairs'].pop(record['id'], None)
                raise
            count += 1
        return count

    # ------------------------------------------------------------------
    # Импорт архивов
    # ------------------------------------------------------------------

    def import_archives(self):
        if self.busy or self.locked:
            self.status.set(
                'Дождитесь текущей операции или проверьте доступ к складу.')
            return
        paths = filedialog.askopenfilenames(
            parent=self, title='Архивы front/back',
            filetypes=[('Архивы', '*.rar *.zip')])
        if not paths:
            return
        self._start_import(paths)

    def _start_import(self, paths):
        self.busy = True
        self.status.set('Читаю архивы…')

        def worker():
            workspace = self.root_dir / 'work'
            workspace.mkdir(parents=True, exist_ok=True)
            session = tempfile.TemporaryDirectory(
                prefix='import_', dir=workspace)
            try:
                pairs, skipped = read_pairs(
                    paths, session.name,
                    classifier=lambda path: classify_file(self.app, path))
                self.events.put(('import', session, pairs, skipped))
            except Exception:
                session.cleanup()
                self.events.put((
                    'error',
                    'Не удалось прочитать архивы. Проверьте формат ZIP/RAR, '
                    'отсутствие пароля и пары front/back.'))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # OCR / Gemini
    # ------------------------------------------------------------------

    def _start_ocr(self, records, gemini_key=None):
        if not records:
            self.busy = False
            return
        self.busy = True

        def worker():
            for index, record in enumerate(records, 1):
                try:
                    if gemini_key:
                        from woonsh_tools.documents.reader import extract_with_gemini
                        fields = extract_with_gemini(
                            gemini_key,
                            [record['front'], record['back']],
                            self.app.gemini_engine)
                    else:
                        fields = paired_fields(
                            self.app, [record['front'], record['back']])
                except Exception:
                    self.events.put(('ocr_failed', record['id'],
                                     index, len(records)))
                    continue
                self.events.put(('ocr', record['id'], fields,
                                 index, len(records)))
            self.events.put(('done',))

        threading.Thread(target=worker, daemon=True).start()

    def recognize_selected(self):
        if self.busy:
            return
        records = [self.data['pairs'][k] for k in self.tree.selection()]
        self._start_ocr(records)

    def recognize_gemini(self):
        if self.busy:
            return
        records = [self.data['pairs'][k] for k in self.tree.selection()]
        if not records:
            self.status.set(
                'Выберите комплекты для распознавания через Gemini.')
            return
        key_path = self.registry.parent / 'gemini_key.dpapi'
        try:
            key = load(key_path).get('api_key', '')
        except Exception:
            key = ''
        if not key:
            self.status.set(
                'Сначала сохраните Gemini API key в настройках '
                'генерации рекламы.')
            return
        if not messagebox.askyesno(
                'Отправка документов в Google Gemini',
                'Фронт и бэк выбранных комплектов (%d) будут отправлены '
                'в Google Gemini для извлечения полей. Это внешний сервис; '
                'запросы используют ваш API-ключ и могут оплачиваться '
                'по его тарифу. Продолжить?' % len(records),
                parent=self):
            return
        self._start_ocr(records, gemini_key=key)
        self.status.set(
            'Распознавание через Gemini запущено по вашему подтверждению.')

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    def poll(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'error':
                self.busy = False
                self.status.set(event[1])

            elif event[0] == 'import':
                _, session, pairs, skipped = event
                try:
                    if any(pair.get('needs_review') for pair in pairs):
                        pairs = review_pairs(self, pairs)
                        if pairs is None:
                            self.busy = False
                            self.status.set(
                                'Импорт отменён. Файлы на склад '
                                'не добавлены.')
                            continue
                    if not pairs:
                        self.busy = False
                        self.status.set(
                            'Документы не выбраны. На склад ничего '
                            'не добавлено.')
                        continue
                    count = self.add_pairs(pairs)
                    records = [
                        self.data['pairs'][pair['id']]
                        for pair in pairs
                        if pair['id'] in self.data['pairs']]
                    records = list({r['id']: r for r in records}.values())
                    self.status.set(
                        'Добавлено комплектов: %d. Пропущено неполных '
                        'папок: %d. Распознаю…' % (count, skipped))
                    self.refresh()
                    self._start_ocr(records)
                except Exception:
                    self.busy = False
                    self.status.set(
                        'Не удалось сохранить все комплекты. '
                        'Уже сохранённые доступны на складе.')
                finally:
                    try:
                        session.cleanup()
                    except OSError:
                        self.status.set(
                            'Импорт завершён, но временный файл открыт '
                            'в просмотрщике. Закройте просмотрщик.')

            elif event[0] == 'ocr_failed':
                self.status.set(
                    'Не удалось распознать комплект %d / %d. '
                    'Сохранённые поля не изменены.' % (event[2], event[3]))

            elif event[0] == 'ocr':
                _, key, fields, index, total = event
                record = self.data['pairs'].get(key)
                if record:
                    if not record.get('checked') and any(fields.values()):
                        record['fields'] = fields
                    try:
                        self.persist()
                    except Exception:
                        self.status.set(
                            'Не удалось сохранить поля распознавания.')
                        continue
                self.status.set(
                    'Распознано комплектов: %d / %d. '
                    'Поля требуют проверки.' % (index, total))
                self.refresh()

            elif event[0] == 'done':
                self.busy = False
                self.status.set(
                    'Распознавание завершено. Проверьте поля; назначение '
                    'профилям выполняется во вкладке «Документы».')

        self.after(250, self.poll)

    # ------------------------------------------------------------------
    # Editing / assignment
    # ------------------------------------------------------------------

    def edit(self):
        selection = self.tree.selection()
        if len(selection) != 1:
            self.status.set('Выберите один комплект для проверки полей.')
            return
        record = self.data['pairs'][selection[0]]
        FieldEditor(self, record, lambda: (self.persist(), self.refresh()))

    def open_folder(self):
        selection = self.tree.selection()
        if len(selection) == 1:
            folder = Path(self.data['pairs'][selection[0]]['front']).parent
            if hasattr(os, 'startfile'):
                os.startfile(str(folder))

    def assign_selected_profiles(self):
        docs = self.app.documents_panel
        profiles = [
            docs.items[k] for k in docs.tree.selection()
            if k in docs.items and not k.startswith('company:')]
        if not profiles:
            docs.status.set(
                'Выберите конкретные профили в «Документах» '
                'через Ctrl / Shift.')
            return
        free = [r for r in self.data['pairs'].values()
                if r.get('state') == 'free']
        if not free:
            docs.status.set(
                'На складе нет свободных комплектов. '
                'Добавьте архивы во вкладке «Склад».')
            return
        AssignmentDialog(docs, profiles, free, self.assign)

    def resume_pending(self):
        if self.busy:
            self.status.set(
                'Дождитесь завершения импорта или распознавания.')
            return
        pending = [
            self.data['pairs'][k] for k in self.tree.selection()
            if self.data['pairs'][k].get('state') == 'pending']
        if not pending:
            self.status.set(
                'Отключите «Только свободные» и выберите '
                'незавершённые назначения.')
            return
        for record in pending:
            assignment = record.get('assignment', {})
            owner = self.app.documents_panel.data['profiles'].get(
                assignment.get('profile_key'))
            if not owner:
                self.status.set(
                    'Связанный профиль не найден. Назначение '
                    'сохранено для ручной проверки.')
                continue
            profile = dict(owner, key=assignment['profile_key'])
            record['state'] = 'free'
            try:
                self.assign([(profile, record)])
            except Exception:
                record['state'] = 'pending'
                self.status.set(
                    'Не удалось завершить назначение. '
                    'Комплект остаётся зарезервированным.')
        self.refresh()

    def assign(self, choices):
        if self.locked:
            raise OSError('Stock locked')
        if any(record.get('state') != 'free' for _, record in choices):
            raise ValueError('Pair no longer free')
        if len({record['id'] for _, record in choices}) != len(choices):
            raise ValueError('Duplicate pair assignment')
        docs = self.app.documents_panel
        for profile, record in choices:
            if not profile.get('company'):
                raise ValueError('Company required')
            record.update(
                state='pending',
                assignment={
                    'profile_key': profile['key'],
                    'profile_name': profile['name'],
                    'company': profile['company'],
                    'time': datetime.datetime.now().isoformat(
                        timespec='seconds')})
            self.persist()
            try:
                for side in ('front', 'back'):
                    attached = docs.archive(
                        record[side], profile['company'],
                        'Физ. документ', profile)
                    attached.update(
                        pair_id=record['id'], side=side,
                        stock_id=record['id'],
                        fields=copy.deepcopy(record.get('fields', {})),
                        checked=record.get('checked', False))
                docs.persist()
                docs.refresh()
                record['state'] = 'assigned'
                self.persist()
            except Exception:
                self.persist()
                self.refresh()
                raise
        self.refresh()
        docs.refresh()
        docs.status.set(
            'Комплекты со склада назначены выбранным профилям. '
            'Фронт и бэк сохранены в их папках.')
