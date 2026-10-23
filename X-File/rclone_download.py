"""Official rclone download with a GitHub fallback and atomic installation."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import zipfile

PRIMARY='https://downloads.rclone.org/rclone-current-windows-amd64.zip'

def fetch(url,progress=None):
    req=urllib.request.Request(url,headers={'User-Agent':'Multi-Tool-Farmer','Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=60) as response:
        total=int(response.headers.get('Content-Length') or 0)
        buffer=io.BytesIO()
        while True:
            chunk=response.read(262144)
            if not chunk:break
            if buffer.tell()+len(chunk)>100*1024*1024:raise ValueError('Слишком большой архив rclone.')
            buffer.write(chunk)
            if progress:progress(buffer.tell(),total)
        return buffer.getvalue()

def github_asset():
    req=urllib.request.Request('https://api.github.com/repos/rclone/rclone/releases/latest',headers={
        'User-Agent':'Multi-Tool-Farmer','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=20) as response:release=json.loads(response.read(2_000_000))
    asset=next((a for a in release.get('assets',[]) if a['name'].endswith('-windows-amd64.zip')),None)
    if not asset:raise ValueError('В официальном релизе rclone не найден архив Windows x64.')
    url=asset.get('browser_download_url','')
    digest=asset.get('digest','')
    if not url.startswith('https://github.com/rclone/rclone/releases/download/') or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):
        raise ValueError('Не удалось проверить источник архива rclone.')
    return url,digest.split(':')[1].lower()

def install(archive,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names=[n for n in zf.namelist() if n.lower().endswith('/rclone.exe') or n.lower()=='rclone.exe']
        if len(names)!=1:raise ValueError('В архиве не найден единственный rclone.exe.')
        if zf.getinfo(names[0]).file_size>150*1024*1024:raise ValueError('Слишком большой rclone.exe.')
        fd,path=tempfile.mkstemp(prefix='rclone-',suffix='.download',dir=str(folder))
        try:
            with os.fdopen(fd,'wb') as stream,zf.open(names[0]) as source:
                import shutil
                shutil.copyfileobj(source,stream)
            with open(path,'rb') as stream:
                if stream.read(2)!=b'MZ':raise ValueError('Скачанный файл не является Windows EXE.')
            target=folder/'rclone.exe';os.replace(path,target)
            return str(target)
        finally:
            if os.path.exists(path):os.unlink(path)

def download(folder,progress=None,status=None):
    notify=status or (lambda message:None)
    try:
        notify('Скачиваю rclone с downloads.rclone.org…')
        return install(fetch(PRIMARY,progress),folder)
    except Exception:
        notify('Основной источник недоступен. Скачиваю rclone из официального GitHub…')
    try:
        url,digest=github_asset()
        archive=fetch(url,progress)
        if hashlib.sha256(archive).hexdigest()!=digest:raise ValueError('Контрольная сумма rclone не совпала.')
        return install(archive,folder)
    except Exception as exc:
        raise RuntimeError('Не удалось скачать rclone из обоих официальных источников. Нажмите «Выбрать уже скачанный rclone.exe» или повторите позже. Причина: '+type(exc).__name__) from exc
