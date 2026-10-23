"""Build a clean portable EXE using explicit source/data allowlists."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from app_update import VERSION, repository

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repository',default='')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    output=root/'release'/VERSION
    output.mkdir(parents=True,exist_ok=True)
    stage=root/'build_release_work';stage.mkdir(exist_ok=True)
    source=stage/'release_source.json'
    source.write_text(json.dumps({'repository':repository(args.repository) if args.repository else ''}),encoding='utf-8')
    modules=['setup_wizard','ads_bridge','ads_native','ads_review','ads_validation','ads_selectors','app_update','company_search',
        'document_archive','document_archive_review','document_classifier','document_dedup','document_fields',
        'document_reader','document_stock','documents_panel','gemini_document','native_ocr','profile_panel',
        'profile_scroll','profile_store','sidebar_navigation','ui_helpers']
    data=['ads_generator/app.py','ads_generator/index.html','ads_countries.json','windows_ocr.ps1','instrukciya.html']
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
        '--name','MultiToolFarmer','--distpath',str(output),'--workpath',str(stage/'pyinstaller'),
        '--specpath',str(stage),'--paths',str(root)]
    for module in modules:command+=['--hidden-import',module]
    command+=['--collect-all','telethon','--collect-all','pymupdf']
    for name in data:
        file=root/name
        destination=str(Path(name).parent)
        command+=['--add-data',str(file)+';'+destination]
    command+=['--add-data',str(source)+';.',str(root/'x-file.pyw')]
    subprocess.run(command,cwd=root,check=True)
    exe=output/'MultiToolFarmer.exe'
    sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    (output/'SHA256SUMS.txt').write_text(sha+'  MultiToolFarmer.exe\n',encoding='ascii')
    import shutil
    shutil.copy2(root/'instrukciya.html',output/'instrukciya.html')
    (output/'Публикация.txt').write_text('Версия '+VERSION+'\nРелиз GitHub: v'+VERSION+
        '\nПрикрепите MultiToolFarmer.exe. Не загружайте папки AppData, конфиги, сессии, документы или исходную рабочую папку.'
        '\nПеред первой раздачей задайте --repository owner/repo и пересоберите, чтобы пользователям не вводить адрес.'
        '\nКонтрольная сумма: '+sha+'\n',encoding='utf-8')
    print(str(exe))

if __name__=='__main__':main()
