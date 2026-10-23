"""
DPAPI-encrypted profile storage and spreadsheet download.
From X-File profile_store.py — adapted for Woonsh Tools.
"""
import ctypes
from ctypes import wintypes
import csv
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD),
                 ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    """Encrypt/decrypt bytes via Windows DPAPI (user-bound)."""
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
            ctypes.byref(source), "Woonsh profiles", None, None, None, 1,
            ctypes.byref(target))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def save(path, data):
    """Save JSON data encrypted with DPAPI."""
    path = Path(path)
    encrypted = crypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(encrypted)
    temp.replace(path)


def load(path):
    """Load DPAPI-encrypted JSON data."""
    return json.loads(crypt(Path(path).read_bytes(), decrypt=True).decode("utf-8"))


def cell_text(cell):
    """Extract clean text from an openpyxl cell."""
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fmt = cell.number_format or ""
        if fmt and set(fmt) == {"0"}:
            return str(int(value)).zfill(len(fmt))
    if hasattr(value, "strftime"):
        return value.strftime("%m/%y")
    return str(value)


def download(url):
    """Download a spreadsheet from URL (Google Sheets, OneDrive, direct)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
        raise ValueError("Нужна ссылка HTTP/HTTPS на таблицу.")
    if parsed.hostname == "docs.google.com":
        match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            url = ("https://docs.google.com/spreadsheets/d/"
                   + match.group(1) + "/export?format=xlsx")
    elif (parsed.hostname.endswith("sharepoint.com")
          or parsed.hostname.endswith("1drv.ms")
          or parsed.hostname == "onedrive.live.com"):
        url += ("&" if "?" in url else "?") + "download=1"
    with urlopen(Request(url, headers={"User-Agent": "WoonshTools/1.0"}),
                 timeout=30) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("Таблица больше 30 МБ. Откройте локальный файл.")
    if data[:2] == b"PK":
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True,
                                      data_only=True)
        try:
            return {s.title: [[cell_text(c) for c in row]
                              for row in s.iter_rows()] for s in book}
        finally:
            book.close()
    text = data.decode("utf-8-sig")
    if "<html" in text[:2000].lower() or "<!doctype html" in text[:2000].lower():
        raise ValueError("Ссылка требует входа или ведёт на страницу. "
                         "Скачайте Excel и откройте файл.")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        raise ValueError("По ссылке не найдена таблица Excel или CSV.")
    return {"CSV": list(csv.reader(io.StringIO(text), dialect))}


def read_tables(path):
    """Read local Excel/CSV file into {sheet: rows} dict."""
    if path.lower().endswith(".csv"):
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                with open(path, encoding=encoding, newline="") as f:
                    text = f.read()
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Не удалось прочитать кодировку CSV")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return {"CSV": list(csv.reader(io.StringIO(text), dialect))}
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return {s.title: [[cell_text(c) for c in row]
                          for row in s.iter_rows()] for s in book}
    finally:
        book.close()
