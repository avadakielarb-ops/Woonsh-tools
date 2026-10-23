"""Local document archive, linked companies/profiles and reviewed OCR metadata."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import queue
import shutil
import threading
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
import re
from document_fields import FIELDS, extract_fields, valid_date
from document_dedup import consolidate, profile_identity
from profile_store import load, save
from ui_helpers import clipboard_support


def company_id(name):
    return ' '.join(name.casefold().split())


class FieldEditor(tk.Toplevel):
    def __init__(self, parent, record, on_save):
        super().__init__(parent)
        self.title('Проверка документа — ' + record.get('name',''))
        self.transient(parent.winfo_toplevel())
        self.configure(background=ttk.Style(self).lookup('TFrame','background') or '#100c1c')
        self.record, self.on_save = record, on_save
        frame=ttk.Frame(self,padding=16)
        frame.pack(fill='both',expand=True)
        frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text='Проверьте по оригиналу. Нераспознанные поля оставлены пустыми.').grid(row=0,column=0,columnspan=2,pady=(0,12))
        self.values={}
        for row,field in enumerate(FIELDS,1):
            ttk.Label(frame,text=field).grid(row=row,column=0,sticky='w',pady=5)
            var=tk.StringVar(value=record.get('fields',{}).get(field,''))
            entry=ttk.Entry(frame,textvariable=var,width=55)
            entry.grid(row=row,column=1,sticky='we',padx=10,pady=5)
            clipboard_support(entry)
            self.values[field]=var
        ttk.Label(frame,text='Даты: ДД.ММ.ГГГГ. Страна — страна выдачи документа.').grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
        self.checked=tk.BooleanVar(value=record.get('checked',False))
        ttk.Checkbutton(frame,text='Я проверил(а) данные по оригиналу',variable=self.checked).grid(row=7,column=0,columnspan=2,sticky='w')
        ttk.Button(frame,text='Сохранить поля',command=self.accept,style='Accent.TButton').grid(row=8,column=1,sticky='e',pady=12)
        self.grab_set()

    def accept(self):
        values={key:var.get().strip() for key,var in self.values.items()}
        for field in ('Дата рождения','Действителен до'):
            if values[field]:
                value=valid_date(values[field])
                if not value:
                    messagebox.showerror('Дата','Проверьте поле «%s»: нужна дата ДД.ММ.ГГГГ.'%field,parent=self)
                    return
                values[field]=value
        if values['Дата рождения'] and dt.datetime.strptime(values['Дата рождения'],'%d.%m.%Y').date()>dt.date.today():
            messagebox.showerror('Дата','Дата рождения не может быть в будущем.',parent=self)
            return
        old=dict(self.record)
        self.record.update(fields=values,checked=self.checked.get())
        try:
            self.on_save()
        except Exception:
            self.record.clear();self.record.update(old)
            messagebox.showerror('Сохранение','Не удалось сохранить поля документа.',parent=self)
            return
        self.destroy()


class DocumentsPanel(ttk.Frame):
    def __init__(self,parent,app,app_dir):
        super().__init__(parent,padding=12)
        self.app=app
        self.root_dir=Path(app_dir)/'documents'
        self.registry=Path(app_dir)/'documents_registry.dpapi'
        self.events=queue.Queue()
        self.busy=False
        self.data={'version':1,'identity_version':2,'profiles':{},'companies':{}}
        self.load_error=False
        if self.registry.exists():
            try:
                self.data=load(self.registry)
                if self.data.get('version')!=1 or not isinstance(self.data.get('profiles'),dict) or not isinstance(self.data.get('companies'),dict):
                    raise ValueError('Unknown version')
                self.data['companies']={company_id(value['name']):value for value in self.data['companies'].values()}
                self.data, self.merge_report = consolidate(self.data,self.registry,self.root_dir)
            except Exception:
                self.data={'version':1,'identity_version':2,'profiles':{},'companies':{}}
                self.load_error=True
        self.items={}
        self.records=[]
        self.query=tk.StringVar()
        self.columnconfigure(0,weight=1)
        self.rowconfigure(3,weight=1)
        self.rowconfigure(5,weight=1)
        ttk.Label(self,text='Локальные копии документов закреплены за компанией и профилем. Распознанные поля нужно проверить.').grid(sticky='w')
        bar=ttk.Frame(self);bar.grid(row=1,column=0,sticky='we',pady=8)
        for label,command in [('Обновить',self.refresh),('Папка профиля',self.open_profile_folder),('Со склада',self.assign_from_stock),('Выписки из истории',self.import_history),
                               ('Добавить выписку',lambda:self.attach('Выписка')),
                               ('Добавить физ. документ',lambda:self.attach('Физ. документ'))]:
            ttk.Button(bar,text=label,command=command).pack(side='left',padx=(0,6))
        search=ttk.Frame(self)
        search.grid(row=2,column=0,sticky='we',pady=(0,8))
        search.columnconfigure(1,weight=1)
        ttk.Label(search,text='Поиск профиля или компании').grid(row=0,column=0,padx=(0,8))
        search_entry=ttk.Entry(search,textvariable=self.query)
        search_entry.grid(row=0,column=1,sticky='we')
        clipboard_support(search_entry)
        ttk.Button(search,text='Очистить',command=lambda:self.query.set('')).grid(row=0,column=2,padx=(8,0))
        self.query.trace_add('write',lambda *args:self.refresh())
        self.tree=ttk.Treeview(self,columns=('profile','company','statement','personal'),show='headings',selectmode='extended',height=5)
        for key,title in [('profile','Профиль'),('company','Компания'),('statement','Выписки'),('personal','Физ. документы')]:
            self.tree.heading(key,text=title);self.tree.column(key,width=190)
        self.tree.grid(row=3,column=0,sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.show_documents())
        actions=ttk.Frame(self);actions.grid(row=4,column=0,sticky='we',pady=8)
        for label,command in [('Открыть файл',self.open_file),('Распознать поля',self.recognize),('Проверить / изменить',self.edit),('Удалить привязку',self.detach)]:
            ttk.Button(actions,text=label,command=command).pack(side='left',padx=(0,6))
        columns=('kind','name','fio','birth','expiry','country','type','review')
        self.files=ttk.Treeview(self,columns=columns,show='headings',selectmode='browse',height=6)
        for key,title in zip(columns,['Категория','Файл','ФИО','Рождение','Действителен до','Страна выдачи','Вид','Проверка']):
            self.files.heading(key,text=title);self.files.column(key,width=125,stretch=True)
        self.files.grid(row=5,column=0,sticky='nsew')
        self.files.bind('<ButtonRelease-1>',self.copy_fio_cell,add='+')
        horizontal=ttk.Scrollbar(self,orient='horizontal',command=self.files.xview)
        horizontal.grid(row=6,column=0,sticky='we');self.files.configure(xscrollcommand=horizontal.set)
        self.status=tk.StringVar(value='Исходные файлы не изменяются. Прикреплённые файлы копируются в локальное хранилище.')
        if self.load_error:self.status.set('Архив недоступен для расшифровки. Реестр сохранён; запись заблокирована, чтобы не потерять старые данные.')
        ttk.Label(self,textvariable=self.status,wraplength=1000).grid(row=7,column=0,sticky='w',pady=8)
        self.after(300,self.poll)
        self.after(1000,self.startup_import)

    def persist(self):
        if self.load_error:raise OSError('Registry locked')
        save(self.registry,self.data)

    def profile(self):
        selection=self.tree.selection()
        return self.items.get(selection[0]) if len(selection)==1 else None

    def selected_file(self):
        selection=self.files.selection()
        return next((record for record in self.records if record['id']==selection[0]),None) if selection else None

    def refresh(self):
        from profile_panel import split_information
        selection=self.tree.selection()
        self.items={key:dict(value,key=key) for key,value in self.data['profiles'].items()}
        for row in self.app.profile_panel.rows:
            name=self.app.profile_panel.get_value(row,'Название профиля')
            if not name:continue
            info=split_information(self.app.profile_panel.get_value(row,'Платежная информация'))
            key=profile_identity(name,info.get('Название фирмы',''))
            self.items[key]={'key':key,'name':name,'company':info.get('Название фирмы',''),'docs':self.data['profiles'].get(key,{}).get('docs',[])}
        represented={company_id(item['company']) for item in self.items.values()}
        for key,value in self.data['companies'].items():
            if key not in represented:
                self.items['company:'+key]={'key':'company:'+key,'name':'— (история выписок)','company':value['name'],'docs':[]}
        try:self.sync_profile_folders()
        except Exception:self.status.set('Не удалось создать часть папок профилей. Старые копии файлов сохранены.')
        self.tree.delete(*self.tree.get_children())
        for key,item in self.items.items():
            if self.query.get().strip().casefold() not in (item['name']+' '+item['company']).casefold():continue
            statement=self.data['companies'].get(company_id(item['company']),{}).get('docs',[])
            personal=item.get('docs',[])
            self.tree.insert('','end',iid=key,values=(item['name'],item['company'],len(statement),len({r.get('pair_id') or r['id'] for r in personal})))
        restored=[key for key in selection if self.tree.exists(key)]
        if restored:self.tree.selection_set(restored)
        self.show_documents()

    def assign_from_stock(self):
        self.app.stock_panel.assign_selected_profiles()

    def sync_profile_folders(self):
        if self.load_error:return
        changed=False
        for key,item in self.items.items():
            if key.startswith('company:'):continue
            owner=self.data['profiles'].setdefault(key,{'name':item['name'],'company':item['company'],'docs':[]})
            folder=owner.get('folder')
            if not folder:
                name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',item['name']).strip(' .')[:100] or 'Профиль'
                if re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.I):name='_'+name
                target=self.root_dir/'profiles'/name
                occupied={v.get('folder','').casefold() for k,v in self.data['profiles'].items() if k!=key}
                if str(target).casefold() in occupied:target=target.with_name(name+'_'+key[-8:])
                folder=str(target);owner['folder']=folder;changed=True
            target=Path(folder)
            statement=self.data['companies'].get(company_id(item['company']),{}).get('docs',[])
            for record in statement+owner.get('docs',[]):
                source=Path(record['path'])
                if not source.is_file():continue
                destination=record.get('profile_paths',{}).get(key)
                if destination and Path(destination).is_file():continue
                group=target/('Выписки' if record['kind']=='Выписка' else 'Физ документы')
                group.mkdir(parents=True,exist_ok=True)
                name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(record['name']).name).strip(' .') or 'document'+source.suffix
                candidate=group/name
                number=2
                while candidate.exists():
                    if hashlib.sha256(candidate.read_bytes()).hexdigest()==record['sha256']:break
                    candidate=group/('%s (%d)%s'%(Path(name).stem,number,Path(name).suffix));number+=1
                if not candidate.exists():
                    temp=candidate.with_suffix(candidate.suffix+'.tmp')
                    shutil.copy2(source,temp);temp.replace(candidate)
                record.setdefault('profile_paths',{})[key]=str(candidate)
                if record['kind']=='Физ. документ':record['path']=str(candidate)
                changed=True
            target.mkdir(parents=True,exist_ok=True)
        if changed:self.persist()

    def open_profile_folder(self):
        item=self.profile()
        if not item or item['key'].startswith('company:'):
            self.status.set('Выберите конкретный профиль, чтобы открыть его папку.');return
        try:
            self.sync_profile_folders()
            folder=self.data['profiles'][item['key']]['folder']
            os.startfile(folder)
        except Exception:messagebox.showerror('Папка','Не удалось открыть папку профиля.',parent=self)

    def document_path(self,record):
        item=self.profile()
        if item:
            path=record.get('profile_paths',{}).get(item['key'])
            if path and Path(path).exists():return path
        return record['path']

    def show_documents(self):
        selected=self.files.selection()
        self.files.delete(*self.files.get_children())
        item=self.profile()
        self.records=[]
        if item:
            self.records=list(self.data['companies'].get(company_id(item['company']),{}).get('docs',[]))+list(self.data['profiles'].get(item['key'],{}).get('docs',[]))
        for record in self.records:
            f=record.get('fields',{})
            status='Проверено' if record.get('checked') else 'Нужно проверить'
            expiry=f.get('Действителен до','')
            if expiry and valid_date(expiry):
                if dt.datetime.strptime(expiry,'%d.%m.%Y').date()<dt.date.today():status+='; срок истёк'
            if not Path(record['path']).is_file():status='Файл не найден'
            self.files.insert('','end',iid=record['id'],values=(record['kind'],record['name'],f.get('ФИО',''),f.get('Дата рождения',''),expiry,f.get('Страна выдачи',''),f.get('Вид документа',''),status))
        if selected and any(r['id']==selected[0] for r in self.records):self.files.selection_set(selected[0])

    def archive(self,source,company,kind,profile=None):
        if self.load_error:raise OSError('Registry locked')
        source=Path(source)
        if source.suffix.lower() not in ('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp'):
            raise ValueError('Unsupported document type')
        digest=hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        hexdigest=digest.hexdigest()
        self.root_dir.mkdir(parents=True,exist_ok=True)
        dest=self.root_dir/(hexdigest+source.suffix.lower())
        if kind=='Выписка':
            owner=self.data['companies'].setdefault(company_id(company),{'name':company,'docs':[]})
        else:
            owner=self.data['profiles'].setdefault(profile['key'],{'name':profile['name'],'company':company,'docs':[]})
        existing=next((r for r in owner['docs'] if r['sha256']==hexdigest),None)
        if not dest.exists():
            temp=dest.with_suffix(dest.suffix+'.tmp')
            shutil.copy2(source,temp);temp.replace(dest)
        if existing:return existing
        record={'id':uuid.uuid4().hex,'kind':kind,'name':source.name,'path':str(dest),'sha256':hexdigest,'fields':{},'checked':False}
        owner['docs'].append(record)
        try:self.persist()
        except Exception:
            owner['docs'].remove(record)
            raise
        return record

    def archive_jobs(self,jobs):
        for company,source,_ in jobs:self.archive(source,company,'Выписка')
        self.refresh()

    def startup_import(self):
        self.import_history(quiet=True)
        self.refresh()

    def import_history(self,quiet=False):
        if self.load_error:return
        count=0;missing=0
        tables=list(self.app.tables.values())+[self.app._snapshot()]
        try:
            for table in tables:
                for company,row in table.get('rows',{}).items():
                    if row.get('status') not in ('auto','manual','confirmed') or not row.get('file'):continue
                    source=Path(table.get('folder',''))/row['file']
                    if source.is_file():
                        self.archive(source,company,'Выписка');count+=1
                    else:missing+=1
            self.refresh()
            if not quiet:self.status.set('Обработано выписок: %d. Недоступны локально: %d. Уже прикреплённые файлы не дублируются.'%(count,missing))
        except Exception:self.status.set('Не удалось сохранить часть выписок. Исходные файлы не изменены.')

    def attach(self,kind):
        item=self.profile()
        if not item:
            self.status.set('Выберите профиль или компанию. Если список пуст — откройте таблицу во вкладке «Профили».');return
        if kind=='Физ. документ' and item['key'].startswith('company:'):
            self.status.set('Сначала откройте таблицу профилей и выберите конкретный профиль для документа физлица.');return
        if not item['company']:
            self.status.set('Для профиля не распознано название фирмы. Проверьте платежную информацию.');return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Документы','*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if not path:return
        try:record=self.archive(path,item['company'],kind,item)
        except Exception:
            messagebox.showerror('Архив','Не удалось сохранить копию документа. Проверьте папку данных.',parent=self);return
        self.refresh();self.tree.selection_set(item['key']);self.show_documents();self.files.selection_set(record['id'])
        if kind=='Физ. документ':self.recognize()
        else:self.status.set('Локальная копия выписки закреплена за компанией.')

    def copy_document_name(self, record_id):
        record=next((r for r in self.records if r['id']==record_id),None)
        value=record.get('fields',{}).get('ФИО','').strip() if record else ''
        if not value:
            self.status.set('В этой строке ФИО пока не распознано.')
            return False
        self.app.profile_panel.clear_clipboard()
        self.clipboard_clear();self.clipboard_append(value)
        self.status.set('ФИО скопировано в буфер обмена.')
        return True

    def copy_fio_cell(self, event):
        if self.files.identify_region(event.x,event.y)!='cell':return
        column=self.files.identify_column(event.x)
        if not column or self.files.column(column,'id')!='fio':return
        record_id=self.files.identify_row(event.y)
        if record_id:self.copy_document_name(record_id)

    def open_file(self):
        record=self.selected_file()
        if record:
            try:os.startfile(self.document_path(record))
            except OSError:messagebox.showerror('Документ','Не удалось открыть локальную копию файла.',parent=self)

    def recognize(self):
        record=self.selected_file()
        if not record:return
        if self.busy:
            self.status.set('Распознавание уже идёт. Дождитесь завершения.');return
        self.busy=True
        self.status.set('Локальное распознавание документа…')
        path=self.document_path(record);record_id=record['id']
        paths=[path]
        if record.get('pair_id'):
            paired=[r for r in self.records if r.get('pair_id')==record['pair_id']]
            paired.sort(key=lambda r:0 if r.get('side')=='front' else 1)
            paths=[self.document_path(r) for r in paired]
        def worker():
            try:
                from document_reader import paired_fields
                fields=paired_fields(self.app,paths)
                note='Прочитаны обе стороны документа.' if len(paths)>1 else 'Локальное распознавание завершено.'
                self.events.put((record_id,fields,note))
            except Exception:self.events.put((record_id,{field:'' for field in FIELDS},'Не удалось прочитать документ. Поля можно заполнить вручную.'))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        if not self.events.empty():
            record_id,fields,note=self.events.get_nowait();self.busy=False
            record=None
            for owner in list(self.data['profiles'].values())+list(self.data['companies'].values()):
                record=next((r for r in owner['docs'] if r['id']==record_id),None)
                if record:break
            if record:
                # Keep manually confirmed values; OCR only fills missing fields.
                previous=dict(record.get('fields',{}))
                record['fields']={field:previous.get(field) or fields.get(field,'') for field in FIELDS}
                if record['fields']!=previous:record['checked']=False
                try:self.persist()
                except Exception:self.status.set('Не удалось сохранить результаты распознавания.')
                else:
                    self.status.set((note+' ' if note else '') + ('Поля распознаны. Проверьте по оригиналу.' if any(record['fields'].values()) else 'Текст прочитан, но поля не определены. Заполните их вручную или используйте более чёткое фото.'))
                    self.show_documents();FieldEditor(self,record,lambda r=record:self.save_editor(r))
        self.after(300,self.poll)

    def save_editor(self, record=None):
        if record and record.get('pair_id'):
            for owner in self.data['profiles'].values():
                for other in owner['docs']:
                    if other.get('pair_id')==record['pair_id'] and other is not record:
                        other['fields']=dict(record['fields']);other['checked']=record.get('checked',False)
        self.persist();self.show_documents()

    def edit(self):
        record=self.selected_file()
        if record:FieldEditor(self,record,lambda r=record:self.save_editor(r))

    def detach(self):
        record=self.selected_file()
        if not record:return
        if not messagebox.askyesno('Удалить привязку','Удалить привязку документа? Локальная копия файла останется в архиве.',parent=self):return
        for owner in list(self.data['profiles'].values())+list(self.data['companies'].values()):
            if record in owner['docs']:
                owner['docs'].remove(record)
                try:self.persist()
                except Exception:
                    owner['docs'].append(record);messagebox.showerror('Архив','Не удалось удалить привязку.',parent=self)
                break
        self.refresh()
