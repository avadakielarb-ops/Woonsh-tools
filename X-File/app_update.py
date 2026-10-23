"""Public GitHub Releases updater for the single-file Windows build."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox

VERSION='2.9.9'
ASSET='MultiToolFarmer.exe'

def version(value):
    if not re.fullmatch(r'v?\d+\.\d+(?:\.\d+)?',value):raise ValueError('Нужна версия вида v2.8.1.')
    parts=tuple(map(int,value.lstrip('v').split('.')))
    return parts+(0,)*(3-len(parts))

def repository(value):
    value=value.strip().removeprefix('https://github.com/').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value):
        raise ValueError('Укажите публичный репозиторий: owner/repository или ссылку GitHub.')
    return value

def release(repo):
    repo=repository(repo)
    req=urllib.request.Request('https://api.github.com/repos/'+repo+'/releases/latest',headers={
        'User-Agent':'Multi-Tool-Farmer/'+VERSION,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=20) as response:result=json.loads(response.read(2_000_000))
    if result.get('draft') or result.get('prerelease'):raise ValueError('Это предварительный релиз.')
    version(result['tag_name'])
    asset=next((a for a in result.get('assets',[]) if a['name']==ASSET),None)
    if not asset:raise ValueError('В релизе отсутствует '+ASSET)
    digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):raise ValueError('GitHub не вернул SHA-256 файла; установка заблокирована.')
    url=asset.get('browser_download_url','')
    if not url.startswith('https://github.com/'+repo+'/releases/download/'):
        raise ValueError('Адрес загрузки не относится к выбранному репозиторию.')
    size=asset.get('size',0)
    if not isinstance(size,int) or not 0<size<500_000_000:raise ValueError('Некорректный размер обновления.')
    return {'version':result['tag_name'],'notes':result.get('body') or 'Описание отсутствует.',
        'url':url,'sha256':digest.split(':')[1].lower(),'size':size}

def download(info,folder):
    target=Path(folder)/'download.exe'
    h=hashlib.sha256();size=0
    req=urllib.request.Request(info['url'],headers={'User-Agent':'Multi-Tool-Farmer/'+VERSION})
    try:
        with urllib.request.urlopen(req,timeout=30) as response, target.open('wb') as stream:
            if urlparse(response.geturl()).scheme!='https':raise ValueError('Небезопасное перенаправление.')
            while True:
                chunk=response.read(256*1024)
                if not chunk:break
                size+=len(chunk)
                if size>info['size']:raise ValueError('Размер файла не совпадает.')
                stream.write(chunk);h.update(chunk)
        if size!=info['size'] or h.hexdigest()!=info['sha256']:raise ValueError('Контрольная сумма обновления не совпала.')
        with target.open('rb') as stream:magic=stream.read(2)
        if magic!=b'MZ':raise ValueError('Файл не является Windows EXE.')
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise

HELPER=r'''param([string]$Config)
$ErrorActionPreference='Stop'
$task=Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$copied=$false
$child=$null
$phase='wait'
# A restarted onefile application must unpack into its own temporary directory.
# The old bootloader removes its directory after the parent exits.
$env:PYINSTALLER_RESET_ENVIRONMENT='1'
try {
  $parent=Get-Process -Id $task.parent -ErrorAction SilentlyContinue
  if ($parent -and -not $parent.WaitForExit(120000)) { throw 'Application did not exit' }
  $phase='verify'
  $hasher=[System.Security.Cryptography.SHA256]::Create()
  $inputStream=[System.IO.File]::OpenRead($task.staged)
  try { $actual=[System.BitConverter]::ToString($hasher.ComputeHash($inputStream)).Replace('-','').ToLower() }
  finally { $inputStream.Dispose(); $hasher.Dispose() }
  if ($actual -ne $task.sha256) { throw 'Hash mismatch' }
  $phase='replace'
  $lastFailure=''
  for ($attempt=0;$attempt -lt 60;$attempt++) {
    try {
      [System.IO.File]::Replace($task.staged,$task.target,$task.backup,$true)
      $copied=$true
      break
    } catch { $lastFailure=$_.Exception.Message; Start-Sleep -Milliseconds 500 }
  }
  if (-not $copied) { throw ('Cannot replace executable: '+$lastFailure) }
  $phase='restart'
  $env:MTF_UPDATE_ACK=$task.ack
  $env:MTF_UPDATE_TOKEN=$task.token
  $child=Start-Process -FilePath $task.target -WorkingDirectory ([System.IO.Path]::GetDirectoryName($task.target)) -PassThru
  $ready=$false
  for ($attempt=0;$attempt -lt 120;$attempt++) {
    if (Test-Path -LiteralPath $task.ack) {
      $reply=Get-Content -LiteralPath $task.ack -Raw -Encoding UTF8
      if ($reply.Trim() -eq $task.token) { $ready=$true; break }
    }
    if ($child.HasExited) { throw ('New executable exited before startup: '+$child.ExitCode) }
    Start-Sleep -Milliseconds 500
  }
  if (-not $ready) { throw 'New executable did not confirm startup within 60 seconds' }
  @{ok=$true;phase='complete';version=$task.version;target=$task.target;processId=$child.Id} | ConvertTo-Json | Set-Content -LiteralPath $task.result -Encoding UTF8
  foreach ($item in @($task.backup,$task.ack,$task.log)) {
    try { if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force } } catch { }
  }
} catch {
  $failure=$_.Exception.Message
  ('Phase: '+$phase+[Environment]::NewLine+'Target: '+$task.target+[Environment]::NewLine+$failure) | Set-Content -LiteralPath $task.log -Encoding UTF8
  $env:MTF_UPDATE_ACK=$null
  $env:MTF_UPDATE_TOKEN=$null
  $restored=$false
  if ($copied -and (Test-Path -LiteralPath $task.backup)) {
    if ($child -and -not $child.HasExited) {
      & taskkill.exe /PID $child.Id /T /F 2>$null | Out-Null
    }
    for ($attempt=0;$attempt -lt 30;$attempt++) {
      try {
        [System.IO.File]::Replace($task.backup,$task.target,$task.staged,$true)
        $restored=$true
        break
      } catch { Start-Sleep -Milliseconds 500 }
    }
  }
  @{ok=$false;phase=$phase;error=$failure;restored=$restored;target=$task.target} | ConvertTo-Json | Set-Content -LiteralPath $task.result -Encoding UTF8
  if ($restored -or (-not $copied -and $phase -ne 'wait')) {
    if (Test-Path -LiteralPath $task.staged) { Remove-Item -LiteralPath $task.staged -Force }
    Start-Process -FilePath $task.target -WorkingDirectory ([System.IO.Path]::GetDirectoryName($task.target))
  }
}
'''


def confirm_start():
    """Acknowledge only after App initialization, never from the bootloader."""
    ack=os.environ.pop('MTF_UPDATE_ACK', '')
    token=os.environ.pop('MTF_UPDATE_TOKEN', '')
    if ack and token:
        Path(ack).write_text(token,encoding='utf-8')


def launch_helper(staged,target,info,folder):
    staged,target=Path(staged).resolve(),Path(target).resolve()
    if staged.parent!=target.parent or target.suffix.lower()!='.exe' or staged==target:
        raise ValueError('Некорректные пути установки.')
    if not target.is_file():raise ValueError('Основной EXE не найден: '+str(target))
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    config=folder/'install.json';script=folder/'install.ps1'
    import uuid
    config.write_text(json.dumps({'staged':str(staged),'target':str(target),'sha256':info['sha256'],
        'backup':str(target.with_name('.'+target.name+'.rollback')),'ack':str(folder/'startup.ok'),'token':uuid.uuid4().hex,
        'result':str(folder/'install-result.json'),'version':info['version'],
        'parent':os.getpid(),'log':str(folder/'install-error.txt')}),encoding='utf-8')
    script.write_text(HELPER,encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden',
        '-ExecutionPolicy','Bypass','-File',str(script),'-Config',str(config)],env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'},creationflags=0x08000000)

def show(app):
    win=tk.Toplevel(app.root);win.title('Обновления — Multi-Tool Farmer');win.geometry('650x430')
    folder=Path(app_update_dir(app));config=folder/'source.json'
    try:settings=json.loads(config.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        try:settings=json.loads(Path(__file__).with_name('release_source.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):settings={}
    repo=tk.StringVar(value=settings.get('repository',''))
    ttk.Label(win,text='Версия '+VERSION+' · Публичный GitHub-репозиторий').pack(anchor='w',padx=12,pady=10)
    entry=ttk.Entry(win,textvariable=repo);entry.pack(fill='x',padx=12)
    from ui_helpers import clipboard_support
    clipboard_support(entry)
    text=tk.Text(win,wrap='word',height=10,bg='#211936',fg='#eee9ff',insertbackground='white');text.pack(fill='both',expand=True,padx=12,pady=10)
    text.insert('1.0','Адрес можно указать позже. Для обновлений нужен опубликованный релиз с файлом '+ASSET+'.\nПрофили, ключи и документы остаются в AppData.\n')
    try:
        previous=json.loads((folder/'install-result.json').read_text(encoding='utf-8-sig'))
        previous_status=('Предыдущее обновление установлено: '+previous.get('version','')) if previous.get('ok') else ('Ошибка обновления ('+previous.get('phase','')+'): '+previous.get('error','')+'; подробности: '+str(folder/'install-error.txt'))
    except (OSError,ValueError):previous_status=''
    status=tk.StringVar(value=previous_status);ttk.Label(win,textvariable=status,wraplength=620).pack(anchor='w',padx=12)
    events=queue.Queue();state={'release':None,'busy':False}
    def busy(fn):
        if state['busy']:return
        state['busy']=True;check_button.state(['disabled']);install_button.state(['disabled']);status.set('Выполняется…')
        def worker():
            try:events.put(('ok',fn()))
            except Exception as exc:events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def check():
        try:
            normalized=repository(repo.get())
            folder.mkdir(parents=True,exist_ok=True)
            tmp=config.with_suffix('.tmp');tmp.write_text(json.dumps({'repository':normalized}),encoding='utf-8');tmp.replace(config)
        except Exception as exc:status.set(str(exc));return
        state['release']=None
        busy(lambda:('release',release(normalized)))
    def running():
        return getattr(getattr(app,'setup_window',None),'busy',False) or app.working or app.stock_panel.busy or app.ads_panel.batch_running or app.nb.search_page.busy
    def install():
        if not getattr(sys,'frozen',False):status.set('Установка кнопкой доступна в собранной EXE-версии.');return
        if running():status.set('Завершите загрузку, генерацию и поиск перед обновлением.');return
        if not messagebox.askyesno('Обновление','Скачать обновление, закрыть программу и установить? Источник: '+repo.get(),parent=win):return
        info=state['release']
        def work():
            import shutil
            staging=folder/'download';staging.mkdir(parents=True,exist_ok=True)
            path=download(info,staging)
            from installation import settings as installation_settings
            installed=installation_settings()
            target=(Path(installed['install_dir'])/'MultiToolFarmer.exe') if installed else Path(sys.executable).resolve()
            sibling=target.with_name(target.name+'.update')
            shutil.move(str(path),str(sibling))
            return ('install',(sibling,target))
        busy(work)
    def poll():
        if not win.winfo_exists():return
        while not events.empty():
            kind,value=events.get();state['busy']=False;check_button.state(['!disabled'])
            if kind=='error':status.set(value);continue
            action,value=value
            if action=='release':
                state['release']=value;text.delete('1.0','end');text.insert('1.0',value['version']+'\n\n'+value['notes'])
                newer=version(value['version'])>version(VERSION)
                status.set('Доступно обновление.' if newer else 'Установлена актуальная версия.')
                if newer:install_button.state(['!disabled'])
            else:
                if running():status.set('Появилась активная операция. Завершите её и повторите установку.');continue
                try:
                    app._save_state();app.profile_panel.persist();app.profile_panel.clear_clipboard()
                    launch_helper(value[0],value[1],state['release'],folder)
                    app.root.destroy();return
                except Exception as exc:status.set(str(exc))
        win.after(200,poll)
    buttons=ttk.Frame(win);buttons.pack(fill='x',padx=12,pady=10)
    check_button=ttk.Button(buttons,text='Проверить обновления',command=check);check_button.pack(side='left')
    install_button=ttk.Button(buttons,text='Обновить и перезапустить',command=install,state='disabled');install_button.pack(side='left',padx=8)
    win.protocol('WM_DELETE_WINDOW',lambda:None if state['busy'] else win.destroy())
    poll()

def app_update_dir(app):
    return Path(app.app_data_dir)/'updates'
