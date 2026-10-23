"""Local Telegram login dialogs; codes and QR tokens are never saved."""
import time
import tkinter as tk
from tkinter import ttk
from ui_helpers import clipboard_support

def delivery(sent):
    name=type(getattr(sent,'type',None)).__name__
    if name=='SentCodeTypeApp':return 'Откройте служебный чат «Telegram» на устройстве, где этот аккаунт уже авторизован.'
    if name in ('SentCodeTypeSms','SentCodeTypeSmsWord','SentCodeTypeSmsPhrase'):return 'Telegram выбрал SMS. Проверьте сообщения на телефоне с этим номером.'
    if name in ('SentCodeTypeCall','SentCodeTypeFlashCall','SentCodeTypeMissedCall'):return 'Telegram выбрал звонок. Проверьте входящие вызовы на телефоне с этим номером.'
    if name=='SentCodeTypeEmailCode':return 'Telegram выбрал почту: '+str(getattr(sent.type,'email_pattern','проверьте привязанную почту'))
    return 'Telegram выбрал способ '+name+'. Если код не приходит, отмените ввод и используйте вход по QR.'

class CodeDialog(tk.Toplevel):
    def __init__(self,parent,phone,sent,signal,box):
        super().__init__(parent)
        self.title('Вход Telegram — код');self.geometry('600x370')
        if parent.winfo_viewable():self.transient(parent.winfo_toplevel())
        self.signal,self.box=signal,box
        frame=ttk.Frame(self,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Подтвердите вход в Telegram',style='H.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Номер: '+phone).pack(anchor='w',pady=8)
        ttk.Label(frame,text=delivery(sent),wraplength=540,justify='left').pack(anchor='w',pady=8)
        self.code=tk.StringVar();entry=ttk.Entry(frame,textvariable=self.code,show='*');entry.pack(fill='x',pady=8);clipboard_support(entry)
        ttk.Label(frame,text='Код вводите только здесь. Если его нет, отмените и выберите QR-вход.',wraplength=540,style='Muted.TLabel').pack(anchor='w')
        self.note=tk.StringVar();ttk.Label(frame,textvariable=self.note).pack(anchor='w',pady=8)
        actions=ttk.Frame(frame);actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='Войти',style='Accent.TButton',command=self.submit).pack(side='left')
        self.resend=ttk.Button(actions,text='Запросить повторно',command=lambda:self.finish(('resend','')));self.resend.pack(side='left',padx=8)
        ttk.Button(actions,text='Отмена',command=lambda:self.finish(('cancel',''))).pack(side='left')
        self.ready=time.monotonic()+max(0,getattr(sent,'timeout',None) or 0)
        self.expires=time.monotonic()+290;self.can_resend=bool(getattr(sent,'next_type',None))
        self.protocol('WM_DELETE_WINDOW',lambda:self.finish(('cancel','')))
        entry.bind('<Return>',lambda event:self.submit());entry.focus_set();self.tick()

    def submit(self):
        code=self.code.get().strip()
        if code:self.finish(('code',code))

    def tick(self):
        if not self.winfo_exists():return
        seconds=max(0,int(self.ready-time.monotonic())+1)
        self.resend.state(['!disabled'] if self.can_resend and seconds==0 else ['disabled'])
        self.note.set(('Повторный запрос через '+str(seconds)+' с') if self.can_resend and seconds else ('Можно запросить повторно.' if self.can_resend else 'Telegram не предложил повторный способ доставки. Доступен QR-вход.'))
        if time.monotonic()>self.expires:self.finish(('cancel',''));return
        self.timer=self.after(500,self.tick)

    def finish(self,value):
        if not self.signal.is_set():self.box.append(value);self.signal.set()
        self.destroy()

    def destroy(self):
        if hasattr(self,'timer'):
            try:self.after_cancel(self.timer)
            except tk.TclError:pass
        super().destroy()

class QRDialog(tk.Toplevel):
    def __init__(self,parent,url,cancel):
        super().__init__(parent)
        self.title('Telegram — вход по QR');self.geometry('500x540')
        if parent.winfo_viewable():self.transient(parent.winfo_toplevel())
        frame=ttk.Frame(self,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Войдите через телефон',style='H.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Telegram → Настройки → Устройства → Подключить устройство. Отсканируйте этот QR и подтвердите вход.',wraplength=440).pack(anchor='w',pady=12)
        import qrcode
        from PIL import ImageTk
        qr=qrcode.QRCode(box_size=6,border=4);qr.add_data(url);qr.make(fit=True)
        self.image=ImageTk.PhotoImage(qr.make_image(fill_color='black',back_color='white').convert('RGB'))
        ttk.Label(frame,image=self.image).pack(pady=8)
        ttk.Label(frame,text='QR действует ограниченное время. После истечения запросите новый.',wraplength=440,style='Muted.TLabel').pack(anchor='w',pady=8)
        def close():cancel.set();self.destroy()
        ttk.Button(frame,text='Отмена',command=close).pack(anchor='e')
        self.protocol('WM_DELETE_WINDOW',close)
