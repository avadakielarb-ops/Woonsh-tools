"""Profile links to the bundled local Ads generator."""
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import quote, urlparse
import webbrowser


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
        self.server = None
        self.items = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text='Выберите таблицу и назначьте колонки во вкладке «Профили». Генератор откроется в браузере.').grid(sticky='w')
        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky='we', pady=8)
        for title, command in [('Обновить', self.refresh), ('Сгенерировать CSV', self.generate),
                               ('Открыть результат', self.open_result), ('Сохранить CSV…', self.export)]:
            ttk.Button(buttons, text=title, command=command).pack(side='left', padx=(0, 6))
        columns = ('profile', 'company', 'site', 'status', 'date')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', selectmode='browse')
        for name, title, width in zip(columns, ['Профиль', 'Компания', 'Сайт', 'Реклама CSV', 'Дата'], [160, 180, 230, 180, 140]):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width)
        self.tree.grid(row=2, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(self, command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.status = tk.StringVar(value='Результаты хранятся локально. Данные карты в генератор не передаются.')
        ttk.Label(self, textvariable=self.status, wraplength=950).grid(row=3, column=0, sticky='w', pady=8)
        self.after(1000, self.tick)

    def tick(self):
        if self.winfo_exists():
            self.refresh()
            self.after(5000, self.tick)

    def identity(self, name):
        source = '\n'.join([os.path.normcase(os.path.abspath(self.profiles.path.get())), self.profiles.sheet.get(), name])
        return hashlib.sha256(source.encode('utf-8')).hexdigest()

    def refresh(self):
        from profile_panel import split_information
        history = self.engine.history_list()
        selected = self.tree.selection()
        previous = selected[0] if selected else None
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
            running = any(getattr(p, 'profile', {}).get('key') == key and not p.finished for p in self.engine.JOBS.values())
            state = 'Готово' if ready else ('Ошибка генерации' if exact else ('Сайт изменён' if matches else 'Не создано'))
            if inherited:
                state = 'Есть CSV сайта (архив)'
            if running:
                state = 'Генерация…'
            if not site:
                state = 'Нет сайта'
            date = datetime.datetime.fromtimestamp(ready['ts']).strftime('%d.%m.%Y %H:%M') if ready else ''
            iid = str(number)
            self.items[iid] = {'key': key, 'name': name, 'site': site, 'company': info.get('Название фирмы', ''), 'ready': ready}
            self.tree.insert('', 'end', iid=iid, values=(name, info.get('Название фирмы', ''), site, state, date))
        if previous in self.items:
            self.tree.selection_set(previous)

    def selected(self):
        selected = self.tree.selection()
        if not selected:
            self.status.set('Выберите профиль в таблице рекламы.')
            return None
        return self.items.get(selected[0])

    def url(self):
        if self.server is None:
            self.server = self.engine.ThreadingHTTPServer(('127.0.0.1', 0), self.engine.Handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return 'http://127.0.0.1:%d/' % self.server.server_address[1]

    def generate(self):
        item = self.selected()
        if not item:
            return
        parsed = urlparse(item['site'])
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            self.status.set('В платежной информации не найден корректный сайт.')
            return
        profile = {k: item[k] for k in ('key', 'name', 'site', 'company')}
        webbrowser.open(self.url() + '#profile=' + quote(json.dumps(profile, ensure_ascii=False)))
        self.status.set('Открыты настройки генерации для выбранного профиля. Укажите Gemini API key и нажмите «Сгенерировать CSV».')

    def open_result(self):
        item = self.selected()
        if item and item['ready']:
            webbrowser.open(self.url() + '#history=' + item['ready']['id'])
        elif item:
            self.status.set('Для текущего сайта ещё нет готового CSV.')

    def export(self):
        item = self.selected()
        if not item or not item['ready']:
            self.status.set('Выберите профиль с готовым CSV для текущего сайта.')
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', initialfile='ads.csv', filetypes=[('CSV', '*.csv')])
        if path:
            try:
                result = self.engine.history_load(item['ready']['id'])['result']
                Path(path).write_text(result['csv'], encoding='utf-8-sig', newline='')
                self.status.set('CSV сохранён.')
            except Exception:
                messagebox.showerror('CSV', 'Не удалось сохранить CSV. Проверьте доступ к файлу.', parent=self)
