"""Windows user-bound encrypted snapshots and spreadsheet link download."""
import ctypes
from ctypes import wintypes
import io
import json
import re
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.windll.crypt32
    if decrypt:
        ok = dll.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = dll.CryptProtectData(ctypes.byref(source), 'Vzhuh profiles', None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def save(path, data):
    encrypted = crypt(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(encrypted)
    temp.replace(path)


def load(path):
    return json.loads(crypt(path.read_bytes(), decrypt=True).decode('utf-8'))


def download(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ValueError('Нужна ссылка HTTP/HTTPS на таблицу.')
    if parsed.hostname == 'docs.google.com':
        match = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]+)', parsed.path)
        if match:
            url = 'https://docs.google.com/spreadsheets/d/' + match.group(1) + '/export?format=xlsx'
    elif parsed.hostname.endswith('sharepoint.com') or parsed.hostname.endswith('1drv.ms') or parsed.hostname == 'onedrive.live.com':
        url += ('&' if '?' in url else '?') + 'download=1'
    with urlopen(Request(url, headers={'User-Agent':'Vzhuh/2.5'}), timeout=30) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024:
        raise ValueError('Таблица больше 30 МБ. Откройте локальный файл.')
    if data[:2] == b'PK':
        import openpyxl
        from profile_panel import cell_text
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            return {s.title:[[cell_text(c) for c in row] for row in s.iter_rows()] for s in book}
        finally:
            book.close()
    text = data.decode('utf-8-sig')
    if '<html' in text[:2000].lower() or '<!doctype html' in text[:2000].lower():
        raise ValueError('Ссылка требует входа или ведёт на страницу. Скачайте Excel и откройте файл.')
    import csv
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    except csv.Error:
        raise ValueError('По ссылке не найдена таблица Excel или CSV.')
    return {'CSV':list(csv.reader(io.StringIO(text), dialect))}
