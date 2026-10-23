"""Per-user installation location; legacy users retain their existing data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog

def marker_path():
    return Path(os.environ.get('APPDATA') or Path.home())/'MultiToolFarmer'/'installation.json'

def settings():
    try:
        data=json.loads(marker_path().read_text(encoding='utf-8'))
        root=Path(data['install_dir'])
        if root.is_absolute() and (root/'data').is_dir():return data
    except (OSError,ValueError,KeyError):pass
    return None

def data_dir(legacy):
    config=settings()
    return str(Path(config['install_dir'])/'data') if config else legacy

def write_settings(data):
    marker=marker_path();marker.parent.mkdir(parents=True,exist_ok=True)
    temp=marker.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8');temp.replace(marker)

def redirect():
    if not getattr(sys,'frozen',False):return False
    config=settings()
    if not config:return False
    from app_update import VERSION, version
    target=Path(config['install_dir'])/'MultiToolFarmer.exe'
    source=Path(sys.executable).resolve()
    try:installed_version=version(config.get('version','0.0.0'))
    except ValueError:installed_version=(0,0,0)
    if target.is_file() and target.resolve()!=source:
        if installed_version<version(VERSION):
            # A freshly downloaded fix must not redirect back into an older broken EXE.
            staging=target.with_suffix('.launcher-update')
            shutil.copy2(source,staging)
            try:os.replace(staging,target)
            except OSError:
                staging.unlink(missing_ok=True)
                # Run the newer download itself if another instance locks the installed EXE.
                return False
            config['version']=VERSION;write_settings(config)
        subprocess.Popen([str(target)],cwd=str(target.parent))
        return True
    if target.resolve()==source and installed_version<version(VERSION):
        config['version']=VERSION;write_settings(config)
    return False


def install_to(folder,source):
    root=Path(folder).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    target=root/'MultiToolFarmer.exe';source=Path(source).resolve()
    if target!=source:
        if target.exists():
            if hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(source.read_bytes()).digest():
                raise ValueError('В папке уже есть другая версия MultiToolFarmer.exe. Выберите новую папку.')
        else:
            stage=root/'MultiToolFarmer.installing'
            shutil.copy2(source,stage);stage.replace(target)
    from setup_wizard import prepare
    prepare(root/'data')
    from app_update import VERSION
    write_settings({'install_dir':str(root),'version':VERSION})
    return str(root/'data')

def choose(root):
    root.title('Установка — Multi-Tool Farmer');root.geometry('740x430')
    frame=ttk.Frame(root,padding=30);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='MULTI-TOOL FARMER',style='Title.TLabel').pack(anchor='w',pady=(4,12))
    ttk.Label(frame,text='Ваше рабочее пространство',style='H.TLabel').pack(anchor='w',pady=8)
    ttk.Label(frame,text='Выберите папку для программы и всех её данных.\nПосле установки мастер поможет подключить сервисы.',wraplength=650).pack(anchor='w',pady=12)
    chosen=tk.StringVar(value=str(Path(os.environ.get('LOCALAPPDATA') or Path.home())/'Programs'/'MultiToolFarmer'))
    entry=ttk.Entry(frame,textvariable=chosen);entry.pack(fill='x',pady=8)
    from ui_helpers import clipboard_support
    clipboard_support(entry)
    ttk.Button(frame,text='Выбрать папку…',command=lambda:pick()).pack(anchor='w')
    status=tk.StringVar();ttk.Label(frame,textvariable=status,wraplength=650).pack(anchor='w',pady=12)
    progress=ttk.Progressbar(frame,mode='indeterminate');progress.pack(fill='x',pady=8)
    done=tk.BooleanVar(value=False);result=[];install_busy=[False]
    def pick():
        folder=filedialog.askdirectory(parent=root,title='Папка Multi-Tool Farmer')
        if folder:chosen.set(folder)
    def finish():
        if install_busy[0]:return
        if not chosen.get().strip():status.set('Выберите папку.');return
        import queue,threading
        events=queue.Queue();install_busy[0]=True
        progress.start(12);button.state(['disabled']);status.set('Создаём ваше рабочее пространство…')
        selected=chosen.get()
        def worker():
            try:events.put((True,install_to(selected,sys.executable)))
            except Exception as exc:events.put((False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            if events.empty():root.after(60,poll);return
            ok,value=events.get();progress.stop();install_busy[0]=False
            if ok:result.append(value);done.set(True)
            else:status.set(value);button.state(['!disabled'])
        root.after(60,poll)
    button=ttk.Button(frame,text='Установить и продолжить →',command=finish);button.pack(anchor='e',pady=8)
    root.protocol('WM_DELETE_WINDOW',lambda:None if install_busy[0] else done.set(True))
    root.wait_variable(done);frame.destroy()
    return result[0] if result else None
