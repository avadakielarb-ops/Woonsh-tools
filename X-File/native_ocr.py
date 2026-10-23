"""Offline Windows OCR fallback; only local paths are passed to PowerShell."""
import os
from pathlib import Path
import subprocess


def image_text(path, regions=False):
    shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script=Path(__file__).with_name('windows_ocr.ps1')
    command=[str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                           '-File',str(script),'-ImagePath',str(Path(path).resolve())]
    if regions:command.append('-Regions')
    result=subprocess.run(command,
                          stdin=subprocess.DEVNULL,capture_output=True,encoding='utf-8',errors='replace',
                          creationflags=0x08000000,timeout=90)
    if result.returncode:
        raise RuntimeError('Windows OCR unavailable')
    return result.stdout.strip()
