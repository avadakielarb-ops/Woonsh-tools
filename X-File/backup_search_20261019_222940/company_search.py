"""Grounded company discovery. Candidates never imply registry/PDF verification."""
import asyncio
import csv
import datetime
import importlib.util
import json
from pathlib import Path
import queue
import re
import threading
import urllib.request
from urllib.parse import urlparse
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from profile_store import load, save
from ui_helpers import clipboard_support

BOT = 'usedcompaniesarb_bot'

def now():
    return datetime.datetime.now().astimezone().isoformat()

def bot_status(text):
    text = text.casefold().replace('ё','е')
    if any(s in text for s in ('компания уже есть','уже добавлена','already exists')):
        return 'Уже есть'
    if any(s in text for s in ('компания добавлена','company added')):
        return 'Добавлена'
    return 'Ответ не распознан'

def http_url(value):
    value = str(value or '').strip()
    u = urlparse(value)
    return value if u.scheme in ('http','https') and u.hostname and not u.username else ''

def discover(engine, key, country, topic, count):
    prompt = (f'Use Google Search to find up to {count} real active companies in {country}, sector: {topic}. '
        'Each must have a full street address and its own official website. Exclude parked domains. '
        'Do not invent facts, registry numbers or document URLs. Return JSON only: '
        '{"companies":[{"name":"legal name","address":"full address","site":"https://...",'
        '"source":"source URL","registry":"official registry company URL if found, otherwise empty"}]}. '
        'Unknown means omit the company. These are candidates requiring independent verification.')
    model = engine.model_order(key)[0]
    body = {'contents':[{'parts':[{'text':prompt}]}], 'tools':[{'google_search':{}}],
        'generationConfig':{'temperature':0.2,'maxOutputTokens':8000}}
    req = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'x-goog-api-key':key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:
        data=json.loads(response.read())
    candidate=(data.get('candidates') or [{}])[0]
    chunks=candidate.get('groundingMetadata',{}).get('groundingChunks',[])
    sources=[c['web'] for c in chunks if c.get('web',{}).get('uri')]
    if not sources:
        raise ValueError('Gemini не вернул источники Google Search. Результат не принят; проверьте доступ модели к поиску.')
    text=''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]))
    result=engine.parse_json_loose(text)
    rows=[]
    for item in result.get('companies',[])[:count]:
        if not isinstance(item,dict):continue
        name=str(item.get('name','')).strip()
        address=str(item.get('address','')).strip()
        site=http_url(item.get('site'))
        source=http_url(item.get('source'))
        if not (name and address and site and source):continue
        rows.append({'name':name,'address':address,'site':site,'source':source,'country':country,
            'registry':http_url(item.get('registry')),'website':'Не проверен','bot':'Не проверена',
            'pdf':'Не получена','created':now(),'sources':sources})
    if not rows:raise ValueError('Не найдено полных записей с адресом, сайтом и источником.')
    return rows

class CompanySearchPanel(ttk.Frame):
    def __init__(self,parent,app_dir):
        super().__init__(parent,padding=14)
        self.folder=Path(app_dir)
        self.path=self.folder/'company_search.dpapi'
        self.telegram_path=self.folder/'telegram_search.dpapi'
        try:self.data=load(self.path)
        except FileNotFoundError:self.data={'rows':[],'checks':{}}
        except Exception:
            self.data={'rows':[],'checks':{}}
            messagebox.showerror('Поиск фирмы','Не удалось прочитать сохранённый поиск. Новые записи не будут сохраняться поверх него.',parent=self)
            self.read_only=True
        self.events=queue.Queue();self.busy=False
        self.stop=threading.Event()
        ttk.Label(self,text='Поиск фирмы',style='H.TLabel').pack(anchor='w')
        form=ttk.Frame(self);form.pack(fill='x',pady=8)
        self.country=tk.StringVar(value=self.data.get('country','Finland'))
        self.topic=tk.StringVar(value=self.data.get('topic',''))
        self.count=tk.StringVar(value='5')
        from ads_selectors import SearchPicker
        ttk.Label(form,text='Страна').grid(row=0,column=0,sticky='w')
        SearchPicker(form,self.country,'locations').grid(row=0,column=1,sticky='ew')
        ttk.Label(form,text='Тематика').grid(row=1,column=0,sticky='w')
        entry=ttk.Entry(form,textvariable=self.topic);entry.grid(row=1,column=1,sticky='ew');clipboard_support(entry)
        ttk.Label(form,text='Количество (1–20)').grid(row=2,column=0,sticky='w')
        ttk.Spinbox(form,from_=1,to=20,textvariable=self.count,width=8).grid(row=2,column=1,sticky='w')
        form.columnconfigure(1,weight=1)
        self.auto_bot=tk.BooleanVar(value=True)
        ttk.Checkbutton(self,text='После поиска автоматически проверять новые фирмы через Telegram',variable=self.auto_bot).pack(anchor='w')
        bar=ttk.Frame(self);bar.pack(fill='x',pady=8)
        for title,command in [('Найти через Gemini',self.search),('Войти в Telegram',self.login),('Проверить выбранные',self.verify),('Остановить',self.stop.set),('Открыть источник',self.source),('Прикрепить PDF',self.attach_pdf),('Копировать',self.copy),('Экспорт CSV',self.export)]:
            ttk.Button(bar,text=title,command=command).pack(side='left',padx=2)
        ttk.Label(self,text='Найденные фирмы — кандидаты. Проверка выбранных: доступность сайта → Used Companies. Реестр и PDF подтверждаются отдельно.',wraplength=900).pack(anchor='w')
        columns=('name','address','site','website','bot','pdf')
        self.tree=ttk.Treeview(self,columns=columns,show='headings',selectmode='extended')
        for key,label in zip(columns,['Компания','Полный адрес','Сайт','Доступность сайта','Used Companies','Выписка']):
            self.tree.heading(key,text=label);self.tree.column(key,width=160)
        self.tree.pack(fill='both',expand=True,pady=8)
        self.tree.bind('<Double-1>',lambda e:self.source())
        self.status=tk.StringVar(value='Сохранённый Gemini-ключ используется автоматически. Статус бота хранится между запусками.')
        ttk.Label(self,textvariable=self.status,wraplength=1000).pack(anchor='w')
        self.refresh();self.after(200,self.poll)

    def persist(self):
        if getattr(self,'read_only',False):raise OSError('Сохранение заблокировано: исходное хранилище не прочитано.')
        save(self.path,self.data)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.data['rows']):
            self.tree.insert('','end',iid=str(i),values=tuple(row.get(k,'') for k in ('name','address','site','website','bot','pdf')))

    def run(self,fn):
        if self.busy:self.status.set('Дождитесь завершения текущей операции.');return
        self.busy=True;self.stop.clear();self.status.set('Выполняется…')
        def worker():
            try:
                result=fn();self.events.put(('done',result or 'Операция завершена.'))
            except Exception as exc:
                from ads_bridge import safe_error
                text=safe_error(str(exc),getattr(self,'api_key',''))
                if type(exc).__name__=='FloodWaitError':text='Telegram ограничил частоту запросов. Повторите через '+str(getattr(exc,'seconds','несколько'))+' секунд.'
                elif type(exc).__name__=='PhoneCodeExpiredError':text='Код истёк. Запросите новый вход или используйте QR.'
                elif type(exc).__name__=='ApiIdInvalidError':text='Telegram отклонил api_id/api_hash. Проверьте API development tools.'
                elif type(exc).__name__=='PasswordHashInvalidError':text='Неверный пароль двухэтапной проверки Telegram.'
                self.events.put(('done',text or type(exc).__name__))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        while not self.events.empty():
            event=self.events.get()
            if event[0]=='prompt':
                _,title,signal,box=event
                box.append(simpledialog.askstring('Telegram',title,parent=self,show='*'));signal.set()
            elif event[0]=='code':
                from telegram_auth import CodeDialog
                _,phone,sent,signal,box=event
                self.auth_window=CodeDialog(self,phone,sent,signal,box)
            elif event[0]=='qr':
                from telegram_auth import QRDialog
                self.auth_window=QRDialog(self,event[1],self.stop)
            elif event[0]=='auth_close':
                window=getattr(self,'auth_window',None)
                if window and window.winfo_exists():window.destroy()
            elif event[0]=='status_message':
                self.status.set(event[1])
            elif event[0]=='done':
                self.busy=False;self.status.set(event[1]);self.refresh()
        self.after(200,self.poll)

    def prompt(self,title):
        signal=threading.Event();box=[]
        self.events.put(('prompt',title,signal,box))
        if not signal.wait(300) or not box or not box[0]:raise ValueError('Вход отменён или истекло время ожидания.')
        return box[0]

    def ask_code(self,phone,sent):
        signal=threading.Event();box=[]
        self.events.put(('code',phone,sent,signal,box))
        if not signal.wait(300) or not box:raise ValueError('Время ввода кода истекло. Попробуйте QR-вход.')
        return box[0]

    async def qr_auth(self,client):
        qr=await asyncio.wait_for(client.qr_login(),30)
        self.events.put(('qr',qr.url))
        task=asyncio.create_task(qr.wait(timeout=60))
        try:
            while not task.done():
                if self.stop.is_set():raise ValueError('QR-вход отменён.')
                await asyncio.wait({task},timeout=.25)
            return await task
        except asyncio.TimeoutError:
            raise ValueError('Срок QR истёк. Нажмите Войти по QR ещё раз.')
        finally:
            if not task.done():
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
            self.events.put(('auth_close',))

    def search(self):
        try:
            count=int(self.count.get())
            if not 1<=count<=20 or not self.country.get().strip() or not self.topic.get().strip():raise ValueError()
        except ValueError:self.status.set('Укажите страну, тематику и количество от 1 до 20.');return
        country,topic=self.country.get().strip(),self.topic.get().strip()
        automatic=self.auto_bot.get()
        def work():
            self.api_key=load(self.folder/'gemini_key.dpapi')['api_key']
            spec=importlib.util.spec_from_file_location('company_ads_engine',Path(__file__).parent/'ads_generator/app.py')
            engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
            rows=discover(engine,self.api_key,country,topic,count)
            existing={(r['country'].casefold(),r['name'].casefold()) for r in self.data['rows']}
            added=[]
            for row in rows:
                identity=(row['country'].casefold(),row['name'].casefold())
                if identity not in existing:self.data['rows'].append(row);existing.add(identity);added.append(row)
            self.data.update(country=country,topic=topic);self.persist()
            if automatic:
                if not self.telegram_path.exists():
                    raise ValueError('Фирмы сохранены. Для автоматической проверки сначала войдите в Telegram.')
                self.verify_rows(added)
        self.run(work)

    def login(self,qr=False):
        if self.busy:return
        try:config=load(self.telegram_path)
        except FileNotFoundError:config={}
        except Exception:self.status.set('Не удалось прочитать настройки Telegram.');return
        if not config.get('api_id') or not config.get('api_hash'):
            api_id=simpledialog.askinteger('Telegram API','Введите api_id из my.telegram.org → API development tools:',parent=self,minvalue=1)
            if not api_id:return
            api_hash=simpledialog.askstring('Telegram API','Введите api_hash (32 символа):',parent=self,show='*')
            if not api_hash:return
            if not re.fullmatch(r'[0-9a-fA-F]{32}',api_hash.strip()):
                self.status.set('api_hash должен содержать 32 шестнадцатеричных символа.');return
            config.update(api_id=api_id,api_hash=api_hash.strip())
        if not config.get('session') and not qr:
            phone=simpledialog.askstring('Telegram','Номер телефона в формате +380… / +7…:',initialvalue=config.get('phone',''),parent=self)
            if not phone:return
            phone=re.sub(r'[\s()-]','',phone)
            if not re.fullmatch(r'\+[0-9]{7,15}',phone):
                self.status.set('Укажите номер с + и кодом страны.');return
            config['phone']=phone
        save(self.telegram_path,config)
        self.run(lambda:asyncio.run(self.telegram(config,login=True,qr=qr)))

    async def telegram(self,config,login=False,rows=None,qr=False):
        try:
            from telethon import TelegramClient, errors
            from telethon.sessions import StringSession
        except ImportError:raise RuntimeError('Установите Telethon для Python, которым запускается приложение: python -m pip install "Telethon<2"')
        client=TelegramClient(StringSession(config.get('session','')),config['api_id'],config['api_hash'],
            request_retries=0,connection_retries=1,flood_sleep_threshold=0,timeout=15,device_model='Multi-Tool Farmer',app_version='2.9.3')
        try:
            await asyncio.wait_for(client.connect(),30)
            if not await asyncio.wait_for(client.is_user_authorized(),20):
                if not login:raise ValueError('Сначала нажмите Войти в Telegram.')
                try:
                    if qr:
                        await self.qr_auth(client)
                    else:
                        from telethon import functions
                        sent=await asyncio.wait_for(client.send_code_request(config['phone']),30)
                        for attempt in range(4):
                            if not hasattr(sent,'phone_code_hash'):
                                if await client.is_user_authorized():break
                                raise ValueError('Telegram не вернул обычный код входа. Попробуйте вход по QR.')
                            action,code=self.ask_code(config['phone'],sent)
                            if action=='cancel':raise ValueError('Ввод отменён. Если код не пришёл, выберите вход по QR.')
                            if action=='resend':
                                sent=await asyncio.wait_for(client(functions.auth.ResendCodeRequest(config['phone'],sent.phone_code_hash)),30)
                                continue
                            try:
                                await asyncio.wait_for(client.sign_in(config['phone'],(re.sub(r'\s+','',code) if re.sub(r'\s+','',code).isdigit() else code.strip()),phone_code_hash=sent.phone_code_hash),30)
                                break
                            except errors.PhoneCodeInvalidError:
                                if attempt==3:raise ValueError('Код неверный. Проверьте последние сообщения Telegram.')
                        else:raise ValueError('Лимит попыток ввода достигнут. Повторите вход позже.')
                except errors.SessionPasswordNeededError:
                    password=self.prompt('Пароль двухэтапной проверки Telegram:')
                    await asyncio.wait_for(client.sign_in(password=password),30)
            if not await asyncio.wait_for(client.is_user_authorized(),20):
                raise ValueError('Telegram не подтвердил вход. Сессия не сохранена.')
            config['session']=client.session.save();save(self.telegram_path,config)
            if login:
                me=await asyncio.wait_for(client.get_me(),20)
                if getattr(me,'phone',None):
                    config['phone']='+'+me.phone.lstrip('+');save(self.telegram_path,config)
                return 'Telegram подключён. Сессия сохранена.'
            bot=await asyncio.wait_for(client.get_entity(BOT),20)
            if not getattr(bot,'bot',False):raise ValueError('Адрес Used Companies не является ботом.')
            for row in rows or []:
                if self.stop.is_set():break
                key=BOT+'|'+re.sub(r'\s+',' ',row['name']).strip().casefold()
                cached=self.data['checks'].get(key)
                if cached:
                    row['bot']=cached['status'];self.persist();continue
                try:
                    async with client.conversation(bot,timeout=45,exclusive=True) as conv:
                        self.data['checks'][key]={'status':'Отправка начата — проверьте чат','at':now()};self.persist()
                        await conv.send_message(row['name'])
                        reply=await conv.get_response()
                        status=bot_status(reply.raw_text)
                        self.data['checks'][key]={'status':status,'reply':reply.raw_text,'at':now()}
                        row['bot']=status;self.persist()
                except asyncio.TimeoutError:
                    row['bot']='Нет ответа — проверьте чат';self.persist();break
                await asyncio.sleep(3)
        finally:
            self.events.put(('auth_close',))
            await client.disconnect()

    def selected(self):
        return [self.data['rows'][int(i)] for i in self.tree.selection()]

    def verify(self):
        rows=self.selected()
        if not rows:self.status.set('Выберите фирмы для проверки (Ctrl / Shift).');return
        self.run(lambda:self.verify_rows(rows))

    def verify_rows(self,rows):
        config=load(self.telegram_path)
        if not config.get('session'):raise ValueError('Сначала войдите в Telegram.')
        for row in rows:
            if self.stop.is_set():break
            try:
                req=urllib.request.Request(row['site'],headers={'User-Agent':'Multi-Tool Farmer'})
                with urllib.request.urlopen(req,timeout=20) as response:response.read(2048)
                row['website']='Доступен; принадлежность не подтверждена'
            except Exception:row['website']='Не удалось открыть'
            self.persist()
        asyncio.run(self.telegram(config,rows=[r for r in rows if r['website'].startswith('Доступен')]))

    def source(self):
        rows=self.selected()
        if rows:webbrowser.open(rows[0].get('registry') or rows[0]['source'])

    def attach_pdf(self):
        if self.busy:return
        rows=self.selected()
        if len(rows)!=1:self.status.set('Выберите одну фирму.');return
        path=filedialog.askopenfilename(parent=self,filetypes=[('PDF','*.pdf')])
        if not path:return
        data=Path(path).read_bytes()
        if not data.startswith(b'%PDF-'):self.status.set('Файл не является PDF.');return
        import hashlib
        row=rows[0]
        target=self.folder/'company_search_documents'/hashlib.sha256((row['country']+row['name']).encode()).hexdigest()
        target.mkdir(parents=True,exist_ok=True)
        name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',row['name']).strip(' .')[:100] or 'Компания'
        dest=target/(name+'.pdf')
        if dest.exists():self.status.set('PDF уже прикреплён; существующий файл сохранён.');return
        dest.write_bytes(data);row['pdf']='Прикреплена, не проверена';row['pdf_path']=str(dest)
        self.persist();self.refresh()

    def copy(self):
        text='\n'.join(f"{r['name']} | {r['address']} | {r['site']}" for r in self.selected())
        if text:self.clipboard_clear();self.clipboard_append(text)

    def export(self):
        rows=self.selected() or self.data['rows']
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        with open(path,'w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['Название | Адрес | Сайт','Страна','Used Companies','Выписка','Источник'])
            for r in rows:writer.writerow([f"{r['name']} | {r['address']} | {r['site']}",r['country'],r['bot'],r['pdf'],r['source']])
