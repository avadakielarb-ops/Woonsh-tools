"""Read documents without trusting archive paths; rank unnamed image groups."""
import hashlib
from pathlib import Path,PurePosixPath
import os
import subprocess
import zipfile

LIMIT=20*1024*1024
EXTENSIONS={'.jpg','.jpeg','.png','.pdf','.tif','.tiff','.bmp'}


def safe_name(name):
    name=name.replace('\\','/')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:raise ValueError('Unsafe archive entry')
    return name


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def read_pairs(archives,target,classifier=None):
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    groups=[];skipped=0;total=0
    for archive_index,archive in enumerate(archives):
        archive=Path(archive);z=None
        if archive.suffix.lower()=='.zip':
            z=zipfile.ZipFile(archive)
            names=[info.filename for info in z.infolist() if not info.is_dir()]
        elif archive.suffix.lower()=='.rar':
            tar=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/tar.exe'
            process=subprocess.run([str(tar),'-tf',str(archive)],stdin=subprocess.DEVNULL,capture_output=True,timeout=60,creationflags=0x08000000)
            if process.returncode:raise ValueError('Cannot read archive')
            try:names=process.stdout.decode('utf-8').splitlines()
            except UnicodeDecodeError:names=process.stdout.decode('cp1251').splitlines()
        else:raise ValueError('Only ZIP/RAR supported')
        try:
            if len(names)>2000 or len(set(names))!=len(names):raise ValueError('Archive entry limit or duplicate names')
            folders={}
            for raw in names:
                member=PurePosixPath(safe_name(raw))
                if member.suffix.lower() in EXTENSIONS:folders.setdefault(str(member.parent),[]).append(raw)

            def extract(member,number):
                nonlocal total
                if z:
                    info=z.getinfo(member)
                    if info.file_size>LIMIT:raise ValueError('Document too large')
                    with z.open(info) as stream:data=stream.read(LIMIT+1)
                else:
                    proc=subprocess.Popen([str(tar),'-xOf',str(archive),'--',member],stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                    try:
                        data=proc.stdout.read(LIMIT+1)
                        if len(data)>LIMIT:proc.kill();raise ValueError('Document too large')
                        if proc.wait(timeout=60):raise ValueError('Cannot extract document')
                    finally:
                        if proc.poll() is None:proc.kill();proc.wait()
                        proc.stdout.close()
                total+=len(data)
                if not data or len(data)>LIMIT or total>300*1024*1024:raise ValueError('Document size limit')
                path=target/('%d_%d_%d%s'%(archive_index,group_index,number,PurePosixPath(member.replace('\\','/')).suffix.lower()))
                path.write_bytes(data)
                return str(path)

            for group_index,(folder,members) in enumerate(sorted(folders.items())):
                conventional={}
                for raw in members:
                    stem=PurePosixPath(safe_name(raw)).stem.casefold().strip()
                    side={'фронт':'front','фронд':'front','бэк':'back','бек':'back'}.get(stem,stem)
                    if side in ('front','back'):
                        if side in conventional:raise ValueError('Ambiguous named side')
                        conventional[side]=raw
                result={'label':archive.name+' / '+folder}
                if set(conventional)=={'front','back'}:
                    for number,(side,raw) in enumerate(conventional.items()):result[side]=extract(raw,number)
                elif classifier:
                    if len(members)>30:raise ValueError('Too many candidates in one folder')
                    candidates=[]
                    for number,raw in enumerate(members):
                        path=extract(raw,number)
                        try:classification=classifier(path)
                        except Exception:classification={'side':'unknown','score':0,'reason':'Не прочитан'}
                        candidates.append(dict(classification,path=path,name=PurePosixPath(safe_name(raw)).name))
                    result['candidates']=candidates;result['needs_review']=True
                    for side in ('front','back'):
                        ranked=sorted((c for c in candidates if c.get('side')==side),key=lambda c:c.get('score',0),reverse=True)
                        if ranked and ranked[0].get('score',0)>=3 and (len(ranked)==1 or ranked[0]['score']>ranked[1]['score']):result[side]=ranked[0]['path']
                else:skipped+=1;continue
                if result.get('front') and result.get('back'):
                    result['front_sha']=sha(result['front']);result['back_sha']=sha(result['back'])
                    result['id']=hashlib.sha256((result['front_sha']+'\n'+result['back_sha']).encode()).hexdigest()
                groups.append(result)
        finally:
            if z:z.close()
    return groups,skipped
