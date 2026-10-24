"""
Шифрованное хранилище на основе Windows DPAPI.
Из X-File profile_store.py — адаптировано для Woonsh Tools.

На не-Windows платформах данные хранятся в открытом JSON (fallback).
"""

import json
from pathlib import Path


def _dpapi_available():
    try:
        import ctypes
        ctypes.windll.crypt32
        return True
    except (AttributeError, OSError):
        return False


def _crypt(data, decrypt=False):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD),
                     ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.windll.crypt32

    if decrypt:
        ok = dll.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1,
            ctypes.byref(target))
    else:
        ok = dll.CryptProtectData(
            ctypes.byref(source), 'Woonsh Tools', None, None, None, 1,
            ctypes.byref(target))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def save(path, data):
    """Сохранение данных с DPAPI-шифрованием (или JSON fallback)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False).encode('utf-8')

    if _dpapi_available():
        raw = _crypt(raw)

    temp = path.with_suffix('.tmp')
    temp.write_bytes(raw)
    temp.replace(path)


def load(path):
    """Загрузка данных с DPAPI-расшифровкой (или JSON fallback)."""
    path = Path(path)
    raw = path.read_bytes()

    if _dpapi_available():
        try:
            raw = _crypt(raw, decrypt=True)
        except OSError:
            pass

    return json.loads(raw.decode('utf-8'))
