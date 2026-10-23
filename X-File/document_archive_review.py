"""Explicit selection of the only two files retained from each archive folder."""
from pathlib import Path
import os
import tkinter as tk
from tkinter import ttk,messagebox
from document_archive import sha
import hashlib
from profile_scroll import ScrollFields


class ArchiveReview(tk.Toplevel):
    def __init__(self,parent,groups):
        super().__init__(parent)
        self.title('Отбор документов из архива')
        self.geometry('1100x650')
        self.transient(parent.winfo_toplevel())
        self.result=None
        self.groups=groups
        self.choices=[]
        ttk.Label(self,text='Проверьте фронт и бэк для каждой папки. Только два выбранных файла попадут на склад; остальные фотографии не сохраняются.',wraplength=1050).pack(anchor='w',padx=12,pady=12)
        pane=ScrollFields(self);pane.pack(fill='both',expand=True,padx=12)
        pane.content.columnconfigure(1,weight=1)
        for index,group in enumerate(groups):
            start=index*4
            ttk.Label(pane.content,text=group['label'],style='H.TLabel').grid(row=start,column=0,columnspan=3,sticky='w',pady=(12,5))
            candidates=group.get('candidates') or [
                {'path':group['front'],'name':Path(group['front']).name,'side':'front','score':99,'reason':'Имя front'},
                {'path':group['back'],'name':Path(group['back']).name,'side':'back','score':99,'reason':'Имя back'}]
            labels=['Пропустить']+['%s — %s'%(candidate['name'],candidate.get('reason','Проверьте')) for candidate in candidates]
            lookup=dict(zip(labels[1:],candidates))
            values={}
            for offset,side,title in [(1,'front','Фронт'),(2,'back','Бэк')]:
                ttk.Label(pane.content,text=title).grid(row=start+offset,column=0,sticky='w',padx=8)
                var=tk.StringVar(value='Пропустить')
                suggested=group.get(side)
                for label,candidate in lookup.items():
                    if candidate['path']==suggested:var.set(label);break
                ttk.Combobox(pane.content,textvariable=var,values=labels,state='readonly',width=85).grid(row=start+offset,column=1,sticky='we',padx=8,pady=4)
                def open_choice(v=var,l=lookup):
                    if v.get() in l:os.startfile(l[v.get()]['path'])
                ttk.Button(pane.content,text='Открыть файл',command=open_choice).grid(row=start+offset,column=2,padx=8)
                values[side]=var
            self.choices.append((group,values,lookup))
        pane.bind_fields()
        bar=ttk.Frame(self);bar.pack(fill='x',padx=12,pady=12)
        ttk.Button(bar,text='Отмена',command=self.destroy).pack(side='right')
        ttk.Button(bar,text='Забрать только выбранные документы',command=self.accept,style='Accent.TButton').pack(side='right',padx=8)
        self.grab_set()

    def accept(self):
        selected=[]
        for group,values,lookup in self.choices:
            front=lookup.get(values['front'].get());back=lookup.get(values['back'].get())
            if not front and not back:continue
            if not front or not back or front['path']==back['path']:
                messagebox.showerror('Проверьте пару','Выберите два разных файла — фронт и бэк — либо пропустите обе стороны папки.',parent=self)
                return
            result={'label':group['label'],'front':front['path'],'back':back['path']}
            result['front_sha']=sha(result['front']);result['back_sha']=sha(result['back'])
            result['id']=hashlib.sha256((result['front_sha']+'\n'+result['back_sha']).encode()).hexdigest()
            selected.append(result)
        self.result=selected;self.destroy()


def review_pairs(parent,groups):
    dialog=ArchiveReview(parent,groups)
    parent.wait_window(dialog)
    return dialog.result
