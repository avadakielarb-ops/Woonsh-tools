"""Read front/back pairs from ZIP/RAR without extracting archive paths."""
import hashlib
from pathlib import Path, PurePosixPath
import os
import subprocess
import zipfile

LIMIT=20*1024*1024
EXTENSIONS={'.jpg','.jpeg','.png','.pdf','.tif','.tiff','.bmp'}


def safe_name(name):
    name=name.replace('\\','/')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
        raise ValueError('Unsafe archive entry')
    return name


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def read_pairs(archives, target):
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    groups=[];skipped=0;total=0
    for archive_index,archive in enumerate(archives):
        archive=Path(archive)
        z=None
        if archive.suffix.lower()=='.zip':
            z=zipfile.ZipFile(archive)
            names=[info.filename for info in z.infolist() if not info.is_dir()]
        elif archive.suffix.lower()=='.rar':
            tar=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/tar.exe'
            process=subprocess.run([str(tar),'-tf',str(archive)],capture_output=True,timeout=60,creationflags=0x08000000)
            if process.returncode:raise ValueError('Cannot read archive')
            try:names=process.stdout.decode('utf-8').splitlines()
            except UnicodeDecodeError:names=process.stdout.decode('cp1251').splitlines()
        else:raise ValueError('Only ZIP/RAR supported')
        try:
            if len(names)>2000 or len(set(names))!=len(names):raise ValueError('Archive entry limit or duplicate names')
            pairs={}
            for raw in names:
                name=safe_name(raw)
                member=PurePosixPath(name)
                if member.suffix.lower() not in EXTENSIONS:continue
                side=member.stem.casefold().strip()
                side={'фронт':'front','фронд':'front','бэк':'back','бек':'back'}.get(side,side)
                if side not in ('front','back'):continue
                group=pairs.setdefault(str(member.parent),{})
                if side in group:raise ValueError('Ambiguous front/back files in one folder')
                group[side]=raw
            for group_index,(folder,members) in enumerate(sorted(pairs.items())):
                if set(members)!= {'front','back'}:
                    skipped+=1;continue
                result={'label':archive.name+' / '+folder}
                for side,member in members.items():
                    if z:
                        info=z.getinfo(member)
                        if info.file_size>LIMIT:raise ValueError('Document too large')
                        with z.open(info) as stream:data=stream.read(LIMIT+1)
                    else:
                        proc=subprocess.Popen([str(tar),'-xOf',str(archive),'--',member],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                        try:
                            data=proc.stdout.read(LIMIT+1)
                            if len(data)>LIMIT:proc.kill();raise ValueError('Document too large')
                            if proc.wait(timeout=60):raise ValueError('Cannot extract document')
                        finally:
                            if proc.poll() is None:proc.kill();proc.wait()
                            proc.stdout.close()
                    total+=len(data)
                    if not data or len(data)>LIMIT or total>300*1024*1024:raise ValueError('Document size limit')
                    path=target/('%d_%d_%s%s'%(archive_index,group_index,side,PurePosixPath(member.replace('\\','/')).suffix.lower()))
                    path.write_bytes(data);result[side]=str(path)
                    result[side+'_sha']=sha(path)
                result['id']=hashlib.sha256((result['front_sha']+'\n'+result['back_sha']).encode()).hexdigest()
                groups.append(result)
        finally:
            if z:z.close()
    return groups,skipped
