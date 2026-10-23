"""Local profile settings, without exposing stored credentials."""
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from profile_store import load

class UserProfilePanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=24)
        self.app=app
        ttk.Label(self,text='Мой профиль',style='Title.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(self,text='Подключения и данные вашего рабочего пространства').pack(anchor='w',pady=6)
        self.name=tk.StringVar(value=app.cfg.get('profile_name',''))
        ttk.Label(self,text='Имя профиля').pack(anchor='w',pady=(14,4))
        ttk.Entry(self,textvariable=self.name,width=45).pack(anchor='w')
        ttk.Button(self,text='Сохранить имя',command=self.save_name).pack(anchor='w',pady=8)
        self.details=tk.StringVar()
        ttk.Label(self,textvariable=self.details,wraplength=850,justify='left').pack(anchor='w',pady=18)
        bar=ttk.Frame(self);bar.pack(anchor='w')
        for title,step in [('Google Drive',2),('Gemini API',3),('Telegram',4),('Таблица',5)]:
            ttk.Button(bar,text=title,command=lambda step=step:self.setup(step)).pack(side='left',padx=(0,8))
        ttk.Button(self,text='Открыть папку данных',command=lambda:os.startfile(self.app.app_data_dir)).pack(anchor='w',pady=14)
        ttk.Button(self,text='Обновить сведения',command=self.refresh).pack(anchor='w')
        self.refresh()

    def save_name(self):
        self.app.cfg['profile_name']=self.name.get().strip();self.app._save_config()

    def setup(self,step):
        from setup_wizard import show
        window=show(self.app)
        if not window.active():window.step=step;window.render()

    def refresh(self):
        lines=['Данные: '+str(self.app.app_data_dir),'Google Drive: '+str(self.app.lbl_drive.cget('text'))]
        for filename,label,field in [('gemini_key.dpapi','Gemini API','api_key'),('telegram_search.dpapi','Telegram','session')]:
            try:
                data=load(Path(self.app.app_data_dir)/filename)
                value=bool(data.get(field))
                text='сохранён, защищён Windows' if value else 'не настроен'
                if label=='Telegram' and value and data.get('phone'):
                    text+=' · номер заканчивается на '+data['phone'][-4:]
            except FileNotFoundError:text='не настроен'
            except Exception:text='не удалось прочитать'
            lines.append(label+': '+text)
        lines.append('Таблица: '+(self.app.profile_panel.path.get() or 'не подключена'))
        lines.append('Секреты вводятся в мастере и повторно используются из защищённого хранилища.')
        self.details.set('\n\n'.join(lines))
