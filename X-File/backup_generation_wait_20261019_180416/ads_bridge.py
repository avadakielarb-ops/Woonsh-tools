"""Profile links to the bundled local Ads generator."""
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import threading
import queue
import time
import re
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse


def csv_basename(item):
    name = (item.get('company') or item.get('name') or 'Компания').strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:120].rstrip(' .') or 'Компания'
    if re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.IGNORECASE):
        name = '_' + name
    return name


class AdsPanel(ttk.Frame):
    def __init__(self, parent, profiles, app_dir):
        super().__init__(parent, padding=12)
        self.profiles = profiles
        spec = importlib.util.spec_from_file_location('vzhuh_ads', Path(__file__).parent / 'ads_generator' / 'app.py')
        self.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.engine)
        self.engine.HISTORY_DIR = Path(app_dir) / 'ads_history'
        self.engine.HISTORY_KEEP = 10000
        legacy = Path.home() / '.ads-csv-generator' / 'history'
        marker = self.engine.HISTORY_DIR / '.legacy_imported'
        if legacy.is_dir() and not marker.exists():
            self.engine.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            for source in legacy.glob('*.json'):
                target = self.engine.HISTORY_DIR / source.name
                if not target.exists():
                    try:
                        shutil.copy2(source, target)
                    except OSError:
                        pass
            marker.write_text('Imported', encoding='utf-8')
        self.events = queue.Queue()
        self.cancel_batch = threading.Event()
        self.batch_running = False
        self.run_path = Path(app_dir) / 'ads_run_status.json'
        try:
            self.run_status = json.loads(self.run_path.read_text(encoding='utf-8'))
            self.run_status = {k:('Прервано при закрытии' if v in ('В очереди', 'Генерация…') else v) for k,v in self.run_status.items()}
        except (OSError, ValueError):
            self.run_status = {}
        self.queue_path = Path(app_dir) / 'ads_queue.json'
        self.queue_lock = threading.Lock()
        try:
            self.saved_queue = json.loads(self.queue_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.saved_queue = []
        self.key_path = Path(app_dir) / 'gemini_key.dpapi'
        self.settings_path = Path(app_dir) / 'ads_settings.json'
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.items = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text='Выберите таблицу и назначьте колонки во вкладке «Профили». Ctrl / Shift — несколько профилей. Настройки и результат открываются внутри приложения.').grid(sticky='w')
        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky='we', pady=8)
        for title, command in [('Обновить', self.refresh), ('Выбрать все', self.select_all), ('Генерировать выбранные', self.generate),
                               ('Остановить очередь', self.cancel), ('Продолжить сохранённую', self.resume),
                               ('Открыть результат', self.open_result), ('Сохранить CSV…', self.export)]:
            ttk.Button(buttons, text=title, command=command).pack(side='left', padx=(0, 6))
        columns = ('profile', 'company', 'site', 'status', 'date')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', selectmode='extended')
        for name, title, width in zip(columns, ['Профиль', 'Компания', 'Сайт', 'Реклама CSV', 'Дата'], [160, 180, 230, 180, 140]):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width)
        self.tree.grid(row=2, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(self, command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.status = tk.StringVar(value='Результаты хранятся локально. Данные карты в генератор не передаются.')
        ttk.Label(self, textvariable=self.status, wraplength=950).grid(row=3, column=0, sticky='w', pady=8)
        self.progress = ttk.Progressbar(self, mode='determinate')
        self.progress.grid(row=4, column=0, sticky='we')
        self._next_refresh = 0
        self.after(250, self.tick)

    def tick(self):
        if not self.winfo_exists():
            return
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'status':
                _, key, label, message, count, total = event
                self.run_status[key] = label
                try:
                    self.run_path.parent.mkdir(parents=True, exist_ok=True)
                    temp = self.run_path.with_suffix('.tmp')
                    temp.write_text(json.dumps(self.run_status, ensure_ascii=False), encoding='utf-8')
                    temp.replace(self.run_path)
                except OSError:
                    pass
                self.status.set(message)
                self.progress.configure(maximum=max(1, total), value=count)
                self._next_refresh = 0
            elif event[0] == 'done':
                self.batch_running = False
                self.status.set(event[1])
                self._next_refresh = 0
        if time.monotonic() >= self._next_refresh:
            self.refresh()
            self._next_refresh = time.monotonic() + 5
        self.after(250, self.tick)

    def identity(self, name):
        source = '\n'.join([(self.profiles.path.get() if self.profiles.path.get().startswith(('http://', 'https://')) else os.path.normcase(os.path.abspath(self.profiles.path.get()))), self.profiles.sheet.get(), name])
        return hashlib.sha256(source.encode('utf-8')).hexdigest()

    def refresh(self):
        from profile_panel import split_information
        history = self.engine.history_list()
        selected = self.tree.selection()
        previous = list(selected)
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for number, row in enumerate(self.profiles.rows, 2):
            name = self.profiles.get_value(row, 'Название профиля')
            if not name:
                continue
            info = split_information(self.profiles.get_value(row, 'Платежная информация'))
            site = info.get('Сайт', '').strip()
            if site and not site.startswith(('https://', 'http://')):
                site = 'https://' + site
            key = self.identity(name)
            matches = [h for h in history if h.get('profile', {}).get('key') == key]
            exact = [h for h in matches if site in h.get('urls', [])]
            ready = next((h for h in exact if h.get('rows', 0) > 0), None)
            legacy_ready = next((h for h in history if not h.get('profile', {}).get('key') and site in h.get('urls', []) and h.get('rows', 0) > 0), None)
            inherited = ready is None and legacy_ready is not None
            ready = ready or legacy_ready
            running = any(getattr(p, 'profile', {}).get('key') == key and getattr(p, 'profile', {}).get('site') == site and not p.finished for p in list(self.engine.JOBS.values()))
            state = ('Нужно исправить' if ready and ready.get('errors') else 'Готово') if ready else ('Ошибка генерации' if exact else ('Сайт изменён' if matches else 'Не создано'))
            if inherited:
                state = 'Есть CSV сайта (архив)'
            if running:
                state = 'Генерация…'
            signature = key + '\n' + site
            if signature in self.run_status:
                state = self.run_status[signature]
            if not site:
                state = 'Нет сайта'
            date = datetime.datetime.fromtimestamp(ready['ts']).strftime('%d.%m.%Y %H:%M') if ready else ''
            iid = str(number)
            self.items[iid] = {'key': key, 'name': name, 'site': site, 'company': info.get('Название фирмы', ''), 'ready': ready}
            self.tree.insert('', 'end', iid=iid, values=(name, info.get('Название фирмы', ''), site, state, date))
        restored = [iid for iid in previous if iid in self.items]
        if restored:
            self.tree.selection_set(restored)

    def selected(self):
        selected = self.tree.selection()
        if not selected:
            self.status.set('Выберите профиль в таблице рекламы.')
            return None
        return self.items.get(selected[0])

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def cancel(self):
        self.cancel_batch.set()
        self.status.set('Очередь остановится после текущего профиля. Текущий запрос Gemini завершится.')

    def generate(self, restored=None):
        if self.batch_running:
            self.status.set('Генерация уже идёт. Дождитесь завершения или остановите очередь.')
            return
        selected = restored if restored is not None else [dict(self.items[i]) for i in self.tree.selection() if i in self.items]
        if not selected:
            self.status.set('Выберите один или несколько профилей (Ctrl / Shift).')
            return
        invalid = [p['name'] for p in selected if urlparse(p['site']).scheme not in ('http','https') or not urlparse(p['site']).hostname]
        if invalid:
            messagebox.showerror('Нет сайта', 'Исправьте сайт у выбранных профилей: ' + ', '.join(invalid), parent=self)
            return
        unique = {}
        for item in selected:
            unique[(item['key'], item['site'])] = item
        selected = list(unique.values())
        from ads_native import Settings
        dialog = Settings(self, self.settings, len(selected), self.engine, self.key_path)
        self.wait_window(dialog)
        if not dialog.result:
            return
        settings, api_key = dialog.result
        self.settings = settings
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix('.tmp')
            temp.write_text(json.dumps(settings, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.settings_path)
        except OSError:
            self.status.set('Настройки не удалось сохранить. Генерация запущена с текущими параметрами.')
        self.saved_queue = [{'item':{k:item[k] for k in ('key','name','site','company')}, 'settings':settings, 'state':'waiting'} for item in selected]
        self.save_queue()
        self.cancel_batch.clear()
        self.batch_running = True
        jobs = []
        for item in selected:
            job_id = os.urandom(8).hex()
            prog = self.engine.Progress()
            prog.profile = {k:item[k] for k in ('key','name','site','company')}
            self.engine.JOBS[job_id] = prog
            self.run_status[item['key'] + '\n' + item['site']] = 'В очереди'
            jobs.append((item, job_id, prog))
        threading.Thread(target=self.worker, args=(jobs, settings, api_key), daemon=True).start()
        self.refresh()

    def save_queue(self):
        with self.queue_lock:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.queue_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.saved_queue,ensure_ascii=False),encoding='utf-8')
            temp.replace(self.queue_path)

    def queue_state(self, item, state):
        for entry in self.saved_queue:
            if entry['item']['key'] == item['key'] and entry['item']['site'] == item['site']:
                entry['state'] = state
        self.save_queue()

    def resume(self):
        pending = [e for e in self.saved_queue if e.get('state') != 'done']
        if not pending:
            self.status.set('Нет незавершённых заданий.')
            return
        self.settings = pending[0]['settings']
        self.generate(restored=[e['item'] for e in pending])

    def worker(self, jobs, settings, api_key):
        total, success, failures, done = len(jobs), 0, 0, 0
        for item, job_id, prog in jobs:
            key = item['key'] + '\n' + item['site']
            if self.cancel_batch.is_set():
                prog.finished = True
                prog.error = 'Очередь остановлена'
                self.events.put(('status', key, 'Отменено', 'Очередь остановлена', done, total))
                continue
            self.queue_state(item, 'running')
            self.events.put(('status', key, 'Генерация…', 'Генерация: ' + item['name'], done, total))
            try:
                payload = {'api_key':api_key, 'urls':[item['site']], 'settings':dict(settings)}
                prog.result = self.engine.generate(payload, prog)
                ready = any(site.get('csv') and not site.get('error') for site in prog.result.get('sites', []))
                if not ready:
                    raise ValueError('Не получен CSV. Проверьте доступ к сайту и настройки Gemini.')
                self.engine.save_history(job_id, prog, [item['site']])
                if not prog.hist_path or not prog.hist_path.exists():
                    raise OSError('Результат создан, но не сохранён на диск.')
                success += 1
                label = 'Нужно исправить' if prog.result.get('errors') else 'Готово'
                self.queue_state(item, 'done')
            except Exception as exc:
                self.queue_state(item, 'failed')
                failures += 1
                # Do not expose provider error text which can contain credentials.
                prog.error = type(exc).__name__
                label = 'Ошибка: ' + type(exc).__name__
            finally:
                if prog.state:
                    prog.state.pop('api_key', None)
                prog.finished = True
                prog.done = prog.total
            done += 1
            self.events.put(('status', key, label, '%s: %s (%d/%d)' % (item['name'], label, done, total), done, total))
        self.events.put(('done', 'Завершено: успешно %d, ошибок %d, отменено %d.' % (success, failures, total-done)))

    def open_result(self):
        selected = [self.items[i] for i in self.tree.selection() if i in self.items]
        if len(selected) != 1:
            self.status.set('Для просмотра выберите один профиль. Несколько CSV можно сохранить одним ZIP.')
            return
        item = selected[0]
        if not item['ready']:
            self.status.set('Для текущего сайта ещё нет готового CSV.')
            return
        try:
            from ads_review import show
            show(self, self.engine, item['ready']['id'], item['name'])
        except Exception:
            messagebox.showerror('Результат', 'Не удалось открыть сохранённый результат.', parent=self)

    def export(self):
        selected = [self.items[i] for i in self.tree.selection() if i in self.items]
        if not selected or any(not item['ready'] for item in selected):
            self.status.set('Выберите профили с готовыми CSV для текущих сайтов.')
            return
        for item in selected:
            result = self.engine.history_load(item['ready']['id'])['result']
            if result.get('errors'):
                self.status.set('Экспорт заблокирован: откройте результат и исправьте ошибки проверки.')
                return
        multiple = len(selected) > 1
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.zip' if multiple else '.csv',
            initialfile='ads.zip' if multiple else csv_basename(selected[0]) + '.csv', filetypes=[('ZIP' if multiple else 'CSV', '*.zip' if multiple else '*.csv')])
        if not path:
            return
        try:
            if multiple:
                with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                    used = set()
                    for item in selected:
                        stem = csv_basename(item)
                        name = stem + '.csv'
                        number = 2
                        while name.casefold() in used:
                            name = '%s (%d).csv' % (stem, number)
                            number += 1
                        used.add(name.casefold())
                        result = self.engine.history_load(item['ready']['id'])['result']
                        archive.writestr(name, ('\ufeff' + result['csv']).encode('utf-8'))
            else:
                result = self.engine.history_load(selected[0]['ready']['id'])['result']
                Path(path).write_text(result['csv'], encoding='utf-8-sig', newline='')
            self.status.set('CSV сохранены.' if multiple else 'CSV сохранён.')
        except Exception:
            messagebox.showerror('CSV', 'Не удалось сохранить файл. Проверьте доступ к папке.', parent=self)
