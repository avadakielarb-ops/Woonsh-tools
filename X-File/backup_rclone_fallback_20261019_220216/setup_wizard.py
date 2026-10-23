"""First-run setup; each integration is optional and uses the user's account."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import webbrowser
from profile_store import load, save
from ui_helpers import clipboard_support

FOLDERS=('tools','documents','documents/profiles','document_stock','ads_history','company_search_documents','updates')

def prepare(folder):
    for name in FOLDERS:(Path(folder)/name).mkdir(parents=True,exist_ok=True)

def show(app):
    current=getattr(app,'setup_window',None)
    if current and current.winfo_exists():current.deiconify();current.lift();return current
    app.setup_window=Wizard(app)
    return app.setup_window

class Wizard(tk.Toplevel):
    titles=['Добро пожаловать','rclone','Google Drive','Gemini','Telegram','Таблица по ссылке','Добро пожаловать']
    def __init__(self,app):
        super().__init__(app.root)
        self.app=app;self.folder=Path(app.app_data_dir)
        self.api=app.__class__.__init__.__globals__
        self.title('Первый запуск — Multi-Tool Farmer');self.geometry('820x680')
        self.transient(app.root)
        self.step=0;self.busy=False;self.events=queue.Queue();self.download_started=False
        self.configure(background='#100c1c')
        self.hero=tk.Canvas(self,height=118,bg='#100c1c',highlightthickness=0)
        self.hero.pack(fill='x')
        self.animation_value=0.0
        self.phase=0
        self.caption=ttk.Label(self,style='H.TLabel');self.caption.pack(anchor='w',padx=24,pady=(4,8))
        self._animation_job=self.after(30,self.animate)
        self.body=ttk.Frame(self,padding=18);self.body.pack(fill='both',expand=True)
        self.status=tk.StringVar()
        ttk.Label(self,textvariable=self.status,wraplength=690).pack(fill='x',padx=18,pady=8)
        bar=ttk.Frame(self,padding=18);bar.pack(fill='x')
        self.back=ttk.Button(bar,text='Назад',command=lambda:self.go(-1));self.back.pack(side='left')
        ttk.Button(bar,text='Настроить позже',command=self.later).pack(side='left',padx=8)
        self.next=ttk.Button(bar,text='Далее / пропустить',command=lambda:self.go(1));self.next.pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.later)
        try:prepare(self.folder)
        except OSError as exc:self.status.set('Не удалось создать папки: '+str(exc))
        self.render();self._poll_job=self.after(200,self.poll)

    def destroy(self):
        for name in ('_animation_job','_poll_job','_download_job'):
            job=getattr(self,name,None)
            if job:
                try:self.after_cancel(job)
                except tk.TclError:pass
        super().destroy()

    def label(self,text):
        ttk.Label(self.body,text=text,wraplength=680,justify='left').pack(anchor='w',pady=8)

    def button(self,text,command):
        ttk.Button(self.body,text=text,command=command).pack(anchor='w',pady=6)

    def entry(self,label,variable,secret=False):
        self.label(label)
        entry=ttk.Entry(self.body,textvariable=variable,show='*' if secret else '')
        entry.pack(fill='x');clipboard_support(entry)
        return entry

    def render(self):
        for child in self.body.winfo_children():child.destroy()
        self.caption.configure(text=f'{self.step+1} / 7 · {self.titles[self.step]}')
        self.back.state(['disabled'] if self.step==0 else ['!disabled'])
        self.next.configure(text='Завершить' if self.step==6 else 'Далее / пропустить')
        self.status.set('')
        if self.step==0:
            self.label('Мастер подготовит программу и поможет подключить ваши аккаунты. Любой сервис можно пропустить и настроить позже. Пароли и коды вводите только в окнах входа.')
            self.label('Папки созданы в:\n'+str(self.folder)+'\n\nОбновления EXE сохраняют эти данные.')
            self.label('На следующем шаге rclone скачается с официального сайта. Вход в Google выполняется в браузере; Gemini использует ваш API-ключ, Telegram — ваш аккаунт.')
        elif self.step==1:
            self.label('rclone нужен для Google Drive. Он устанавливается только в папку данных приложения; Python и системный установщик не требуются.')
            self.button('Скачать / повторить загрузку',self.download)
            self.button('Выбрать уже скачанный rclone.exe',self.pick_rclone)
            exe=self.api['find_rclone'](self.app.cfg.get('rclone',''))
            if exe:self.status.set('rclone найден: '+exe)
            elif not self.download_started:
                self.download_started=True;self._download_job=self.after(50,self.download)
        elif self.step==2:
            self.label('Нажмите Подключить Google Drive. Откроется rclone и браузер: выберите свой Google-аккаунт и разрешите доступ. Если rclone спрашивает, продолжать ли со встроенным client_id, ответьте y. Можно указать собственный OAuth-клиент ниже.')
            self.drive=tk.StringVar(value=self.app.var_drive.get())
            self.entry('Папка Google Drive — ссылка или ID (необязательно)',self.drive)
            try:oauth=load(self.folder/'drive_oauth.dpapi')
            except FileNotFoundError:oauth=self.app.cfg
            except Exception:oauth={}
            self.client_id=tk.StringVar(value=oauth.get('drive_client_id',''))
            self.client_secret=tk.StringVar(value=oauth.get('drive_client_secret',''))
            self.entry('Собственный Google client_id (необязательно)',self.client_id)
            self.entry('Google client_secret (если используете собственный client_id)',self.client_secret,True)
            self.button('Подключить Google Drive',self.drive_connect)
            self.button('Проверить доступ',self.drive_check)
        elif self.step==3:
            self.label('Создайте Gemini API-ключ в Google AI Studio, вставьте его и нажмите Сохранить и проверить. Ключ шифруется средствами Windows. Проверка списка моделей не генерирует рекламу.')
            self.button('Открыть Google AI Studio',lambda:webbrowser.open('https://aistudio.google.com/api-keys'))
            try:value=load(self.folder/'gemini_key.dpapi').get('api_key','')
            except Exception:value=''
            self.key=tk.StringVar(value=value)
            self.entry('Gemini API-ключ',self.key,True)
            self.button('Сохранить и проверить',self.gemini)
            self.status.set('Ключ сохранён; можно проверить подключение.' if value else 'Ключ ещё не настроен.')
        elif self.step==4:
            self.label('Для автоматической проверки через Used Companies нужен ваш Telegram-аккаунт. На my.telegram.org откройте API development tools и получите api_id и api_hash. Затем нажмите Войти: программа попросит номер, код Telegram и пароль 2FA, если он включён.')
            self.label('Сессия хранится локально с шифрованием Windows. Мастер не отправляет названия компаний и сообщения боту.')
            self.button('Открыть my.telegram.org',lambda:webbrowser.open('https://my.telegram.org'))
            self.button('Войти в Telegram',self.app.nb.search_page.login)
            self.label('Для смены аккаунта завершите сессию Multi-Tool Farmer в настройках Telegram → Устройства. После этого приложение запросит вход заново.')
        elif self.step==5:
            self.label('Подключите Excel, CSV или Google Sheets по ссылке. Таблица сохранится локально для следующих запусков. Для ссылки нужен доступ на чтение без входа; закрытую таблицу можно загрузить файлом в разделе Профили.')
            self.table_url=tk.StringVar(value=self.app.profile_panel.path.get())
            self.entry('Ссылка на таблицу',self.table_url)
            self.button('Загрузить таблицу',self.load_table)
            self.button('Открыть назначение колонок',self.mapping)
            self.label('Назначение колонок выполняется в разделе Профили. Обязательно проверьте Название профиля и Платежная информация.')
        else:
            ttk.Label(self.body,text='Добро пожаловать\nв Мультитул ✦',style='Title.TLabel',justify='left').pack(anchor='w',pady=(6,16))
            self.label('Основная настройка завершена. Пропущенные сервисы можно подключить позже кнопкой «Мастер настройки» вверху главного окна.')
            self.label('Таблицы и документы загрузите в соответствующих разделах. Для обновления используйте кнопку «Обновления».')
            self.label('Сохранённые подключения:\n'+self.summary())

    def animate(self):
        if not self.winfo_exists():return
        import math
        self.phase+=.10
        target=(self.step+1)/7
        self.animation_value+=(target-self.animation_value)*.14
        width=max(700,self.hero.winfo_width())
        self.hero.delete('all')
        self.hero.create_text(24,28,text='MULTI-TOOL FARMER',fill='#f2ecff',font=('Segoe UI',19,'bold'),anchor='w')
        self.hero.create_text(24,56,text='Ваше пространство · Ваши подключения · Всё в одном месте',fill='#a99bbf',font=('Segoe UI',10),anchor='w')
        self.hero.create_rectangle(24,87,width-24,91,fill='#292038',outline='')
        self.hero.create_rectangle(24,87,24+(width-48)*self.animation_value,91,fill='#8738ef',outline='')
        for i in range(7):
            x=24+(width-48)*((i+1)/7)
            radius=4+(math.sin(self.phase)*1.2 if i==self.step else 0)
            self.hero.create_oval(x-radius,89-radius,x+radius,89+radius,fill='#c697ff' if i<=self.step else '#453458',outline='')
        self._animation_job=self.after(35,self.animate)

    def mapping(self):
        self.app.nb.select(3)
        self.withdraw()
        self.app.lbl_status.configure(text="Назначьте колонки, затем нажмите Мастер настройки, чтобы вернуться.")

    def load_table(self):
        if self.active():return
        url=self.table_url.get().strip()
        if not url.startswith(('https://','http://')):
            self.status.set('Вставьте ссылку HTTP/HTTPS.');return
        self.app.profile_panel.keep_data.set(True)
        self.app.profile_panel.fetch_link(url)

    def summary(self):
        lines=['rclone: '+('найден' if self.api['find_rclone'](self.app.cfg.get('rclone','')) else 'не настроен')]
        lines.append('Google Drive: '+str(self.app.lbl_drive.cget('text')))
        for filename,title,field in [('gemini_key.dpapi','Gemini','api_key'),('telegram_search.dpapi','Telegram','session')]:
            try:configured=bool(load(self.folder/filename).get(field))
            except Exception:configured=False
            lines.append(title+': '+('данные сохранены' if configured else 'пропущен'))
        lines.append('Таблица: '+(self.app.profile_panel.path.get() or 'пропущена'))
        return '\n'.join(lines)

    def active(self):
        return self.busy or self.app.working or self.app.nb.search_page.busy or self.app.profile_panel.downloading

    def go(self,direction):
        if self.active():self.status.set('Дождитесь завершения текущей операции.');return
        if self.step==6 and direction==1:
            self.app.cfg['setup_pending']=False;self.app.cfg['setup_complete']=True
            self.app._save_config();self.destroy();return
        self.step=max(0,min(6,self.step+direction));self.render()

    def later(self):
        if self.active():self.status.set('Операция ещё выполняется. Дождитесь её завершения.');return
        self.app.cfg['setup_pending']=False;self.app.cfg['setup_deferred']=True
        self.app._save_config();self.destroy()

    def run(self,fn):
        if self.active():return
        self.busy=True;self.status.set('Выполняется…')
        def worker():
            try:self.events.put(('ok',fn()))
            except Exception as exc:
                from ads_bridge import safe_error
                self.events.put(('error',safe_error(str(exc),getattr(self,'submitted_key',''))))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        if not self.winfo_exists():return
        while not self.events.empty():
            kind,value=self.events.get();self.busy=False
            if kind=='rclone':
                self.app.cfg['rclone']=value;self.app._save_config();self.app.lbl_rclone.configure(text='rclone найден ✓')
                self.status.set('rclone скачан. Можно перейти к Google Drive.')
            else:self.status.set(str(value))
        if self.step==2 and self.app.working:self.status.set('Подключение Google Drive… Завершите вход в открывшемся окне.')
        elif self.step==2 and not self.busy:self.status.set(str(self.app.lbl_drive.cget('text')))
        if self.step==4:self.status.set(self.app.nb.search_page.status.get())
        if self.step==5:self.status.set(self.app.profile_panel.status.get())
        self._poll_job=self.after(250,self.poll)

    def download(self):
        if self.step!=1:return
        def work():
            tools=self.folder/'tools';tools.mkdir(parents=True,exist_ok=True)
            path=self.api['download_rclone'](str(tools))
            self.events.put(('rclone',path))
            return 'rclone готов.'
        self.run(work)

    def pick_rclone(self):
        if self.active():return
        from tkinter import filedialog
        filename=filedialog.askopenfilename(parent=self,title='Выберите rclone.exe',filetypes=[('rclone','rclone.exe')])
        if filename:
            self.app.cfg['rclone']=filename;self.app._save_config();self.app.lbl_rclone.configure(text='rclone найден ✓')
            self.status.set('rclone выбран: '+filename)

    def drive_values(self):
        self.app.var_drive.set(self.drive.get().strip())
        save(self.folder/'drive_oauth.dpapi',{'drive_client_id':self.client_id.get().strip(),'drive_client_secret':self.client_secret.get().strip()})
        self.app.cfg.pop('drive_client_id',None)
        self.app.cfg.pop('drive_client_secret',None)
        self.app._save_config()

    def drive_connect(self):
        if self.active():return
        self.drive_values();self.app.on_setup_drive()

    def drive_check(self):
        if self.active():return
        self.drive_values();self.app.on_check_drive()

    def gemini(self):
        key=self.key.get().strip()
        if not key:self.status.set('Введите API-ключ.');return
        self.submitted_key=key
        def work():
            save(self.folder/'gemini_key.dpapi',{'api_key':key})
            req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?pageSize=1',headers={'x-goog-api-key':key})
            try:
                with urllib.request.urlopen(req,timeout=20) as response:data=json.loads(response.read())
                if not data.get('models'):raise ValueError('Список моделей пуст.')
            except Exception:
                return 'Ключ сохранён, но доступ к Gemini не подтверждён. Проверьте ключ, интернет и доступность сервиса.'
            return 'Gemini подключён: ключ сохранён, список моделей доступен.'
        self.run(work)
