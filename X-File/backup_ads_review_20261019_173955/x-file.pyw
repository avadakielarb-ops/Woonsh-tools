"""
Помощник ИИ Вжух на Google Drive.

Шаг 1. Компании: вставляешь платёжные профили -> названия -> Excel (или открываешь готовый Excel).
Шаг 2. Сопоставление: папка с PDF -> таблица «компания -> PDF -> причина»; спорное выбираешь вручную.
Шаг 3. Drive: проверка доступа -> загрузка ТОЛЬКО подтверждённых PDF -> ссылки в Excel.

Зависимости: tkinter (стандарт), openpyxl, pypdf; необязательно: pymupdf + Tesseract (OCR сканов).
Снаружи: rclone.exe (рядом или в PATH).
"""

import os, sys, re, json, time, shutil, subprocess, threading, queue, io
import tempfile, unicodedata, datetime, platform, traceback
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import webbrowser

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import openpyxl
    from openpyxl.styles import Font
except ImportError:
    openpyxl = None
    Font = None

APP_VERSION = "2.7"

BASE_DIR = os.path.dirname(os.path.abspath(
    sys.argv[0] if getattr(sys, "frozen", False) else __file__))
APP_DIR = os.path.join(os.environ.get("APPDATA") or BASE_DIR, "X-File")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "state.json")
LEGACY_CONFIG = os.path.join(BASE_DIR, "x-file_config.json")
REPORT_FILE = os.path.join(APP_DIR, "error_report.txt")

RCLONE_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
REMOTE = "gdrive"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


# ══ ТЕМА AURORA ══════════════════════════════════════════════════════════════

AURORA = ("#7a34e6", "#d6389e", "#3b74ed")
GOLD = "#e8a531"

THEME = {
    "bg": "#100c1c", "surface": "#1a1430", "surface2": "#20193a",
    "ink": "#f2ecff", "muted": "#a99fc4", "line": "#2c2444",
    "field": "#20193a", "field_ink": "#f2ecff",
}
SEMANTIC = {"success": "#4cc98a", "danger": "#ff6b6b",
            "warning": GOLD, "info": AURORA[2], "gold": GOLD}

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
FONT_H = ("Segoe UI Semibold", 12)
FONT_T = ("Segoe UI Semibold", 17)
MONO = ("Consolas", 9)


def apply_theme(root, t):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=t["bg"])
    root.option_add("*Font", FONT)

    style.configure(".", background=t["bg"], foreground=t["ink"], font=FONT,
                    fieldbackground=t["field"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"],
                    troughcolor=t["surface"], focuscolor=AURORA[0])
    style.configure("TFrame", background=t["bg"])
    style.configure("TLabel", background=t["bg"], foreground=t["ink"])
    style.configure("Muted.TLabel", foreground=t["muted"])
    style.configure("Title.TLabel", font=FONT_T)
    style.configure("H.TLabel", font=FONT_H)
    for name, color in (("Success", SEMANTIC["success"]), ("Danger", SEMANTIC["danger"]),
                        ("Warning", SEMANTIC["warning"])):
        style.configure("%s.TLabel" % name, foreground=color)

    # карточки (поверхность светлее фона)
    style.configure("Card.TFrame", background=t["surface"])
    style.configure("Card.TLabel", background=t["surface"], foreground=t["ink"])
    style.configure("CardMuted.TLabel", background=t["surface"], foreground=t["muted"])
    style.configure("CardH.TLabel", background=t["surface"], font=FONT_H)
    for name, color in (("Success", SEMANTIC["success"]), ("Danger", SEMANTIC["danger"]),
                        ("Warning", SEMANTIC["warning"])):
        style.configure("Card%s.TLabel" % name, background=t["surface"], foreground=color)

    style.configure("TSeparator", background=t["line"])
    style.configure("TCombobox", fieldbackground=t["field"], background=t["surface2"],
                    foreground=t["field_ink"], arrowcolor=t["muted"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"], padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", t["field"]), ("disabled", t["surface"])],
              foreground=[("readonly", t["field_ink"]), ("disabled", t["muted"])],
              selectbackground=[("readonly", t["field"])], selectforeground=[("readonly", t["field_ink"])],
              bordercolor=[("focus", AURORA[0])])
    root.option_add("*TCombobox*Listbox.background", t["field"])
    root.option_add("*TCombobox*Listbox.foreground", t["field_ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", AURORA[0])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    style.configure("Card.TCheckbutton", background=t["surface"], foreground=t["ink"], padding=(0, 4))
    style.map("Card.TCheckbutton", background=[("active", t["surface"])],
              indicatorcolor=[("selected", AURORA[0]), ("!selected", t["field"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TButton", background=t["surface2"], foreground=t["ink"],
                    bordercolor=t["line"], relief="flat", padding=(12, 6))
    style.map("TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[0]),
                          ("disabled", t["surface"])],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff"),
                          ("disabled", t["muted"])],
              bordercolor=[("active", AURORA[0])])
    style.configure("Accent.TButton", background=AURORA[0], foreground="#ffffff",
                    bordercolor=AURORA[0], relief="flat", padding=(16, 8),
                    font=FONT_B)
    style.map("Accent.TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[2]),
                          ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])
    style.configure("Danger.TButton", background="#4a1f2e", foreground="#ffd7d7",
                    bordercolor="#6b2c40", relief="flat", padding=(12, 6))
    style.map("Danger.TButton",
              background=[("active", "#a43a52"), ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TEntry", fieldbackground=t["field"], foreground=t["field_ink"],
                    insertcolor=t["field_ink"], bordercolor=t["line"], padding=6)
    style.map("TEntry", bordercolor=[("focus", AURORA[0])],
              fieldbackground=[("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("Aurora.Horizontal.TProgressbar", background=AURORA[0],
                    troughcolor=t["surface"], bordercolor=t["line"],
                    lightcolor=AURORA[0], darkcolor=AURORA[0])

    for bar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(bar, background=t["surface2"], troughcolor=t["bg"],
                        bordercolor=t["bg"], arrowcolor=t["muted"], relief="flat")
        style.map(bar, background=[("active", AURORA[0])])

    style.configure("TNotebook", background=t["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=t["bg"], foreground=t["muted"],
                    padding=(20, 10), borderwidth=0, font=FONT_B, focuscolor=t["bg"],
                    lightcolor=t["bg"], darkcolor=t["bg"], bordercolor=t["bg"])
    style.map("TNotebook.Tab",
              background=[("selected", t["surface"]), ("active", t["surface2"])],
              foreground=[("selected", t["ink"]), ("active", t["ink"])],
              focuscolor=[("selected", t["surface"])],
              lightcolor=[("selected", t["surface"])], darkcolor=[("selected", t["surface"])],
              bordercolor=[("selected", t["surface"])])

    style.configure("Treeview", background=t["field"], fieldbackground=t["field"],
                    foreground=t["ink"], rowheight=28, borderwidth=0,
                    bordercolor=t["line"])
    style.map("Treeview", background=[("selected", AURORA[0])],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=t["surface2"], foreground=t["muted"],
                    relief="flat", padding=(8, 6), font=FONT_B)
    style.map("Treeview.Heading", background=[("active", t["line"])])

    style.configure("TPanedwindow", background=t["bg"])
    style.configure("Sash", sashthickness=6, background=t["bg"])
    return style


def make_card(parent, title="", hint=""):
    """Карточка с рамкой. Возвращает внутренний фрейм (style Card.TFrame)."""
    outer = tk.Frame(parent, bg=THEME["line"], padx=1, pady=1)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
    inner.pack(fill="both", expand=True)
    inner.columnconfigure(0, weight=1)
    if title:
        ttk.Label(inner, text=title, style="CardH.TLabel").grid(row=0, column=0, sticky="w")
    if hint:
        lbl = ttk.Label(inner, text=hint, style="CardMuted.TLabel", justify="left")
        lbl.grid(row=1, column=0, sticky="we", pady=(2, 8))
        wrap_on_resize(lbl)
    inner.outer = outer
    return inner


def wrap_on_resize(label, pad=8):
    """Перенос текста подписи по ширине окна."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(120, e.width - pad)))


# ── Буфер обмена ──────────────────────────────────────────────────────────────

CTRL_MASK = 0x4
KEYCODE_ACTIONS = {65: "select_all", 67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}


def _select_all(widget):
    try:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
        else:
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
    except tk.TclError:
        pass


def _on_ctrl_key(event):
    if not (event.state & CTRL_MASK):
        return None
    action = KEYCODE_ACTIONS.get(event.keycode)
    if not action:
        return None
    if action == "select_all":
        _select_all(event.widget)
    else:
        event.widget.event_generate(action)
    return "break"


def attach_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: _select_all(widget))

    def popup(event):
        widget.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    widget.bind("<Button-3>", popup)


def enable_clipboard(*widgets):
    for w in widgets:
        w.bind("<Key>", _on_ctrl_key)
        attach_context_menu(w)


# ══ ХРАНИЛИЩЕ (config + state) ═══════════════════════════════════════════════

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ══ RCLONE ═══════════════════════════════════════════════════════════════════

ID_RE = re.compile(r"[A-Za-z0-9_-]{15,}")


def find_rclone(saved=""):
    for path in (saved, os.path.join(BASE_DIR, "rclone.exe"),
                 shutil.which("rclone.exe") or ""):
        if path and os.path.isfile(path):
            return path
    return ""


def drive_folder_id(url):
    url = (url or "").strip()
    if ID_RE.fullmatch(url):
        return url
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = ID_RE.search(url)
    return m.group(0) if m else ""


def remote_of(folder_id):
    return "%s,root_folder_id=%s:" % (REMOTE, folder_id)


class Procs:
    """Запуск rclone с возможностью отмены: cancel() убивает все активные процессы."""

    def __init__(self, cancel_event):
        self.cancel_event = cancel_event
        self.lock = threading.Lock()
        self.active = set()
        self.last_err = ""

    def run(self, args, timeout=None):
        if self.cancel_event.is_set():
            return -1, "", "cancelled"
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW,
                             encoding="utf-8", errors="replace")
        with self.lock:
            self.active.add(p)
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            return -2, "", "i/o timeout"
        finally:
            with self.lock:
                self.active.discard(p)
        if p.returncode != 0:
            self.last_err = (err or "").strip()[-600:]
        return p.returncode, out or "", err or ""

    def cancel(self):
        self.cancel_event.set()
        with self.lock:
            procs = list(self.active)
        for p in procs:
            try:
                p.kill()
            except OSError:
                pass


REPORT_HINT = " Нажмите «Сообщить об ошибке» внизу окна и отправьте отчёт разработчику."


def E(code, text, report=False):
    """Единый вид сообщения об ошибке: код + понятный текст (+ просьба написать разработчику)."""
    return "Ошибка %s: %s%s" % (code, text, REPORT_HINT if report else "")


def explain_rclone_error(text):
    """Техническая ошибка rclone -> (понятное сообщение с кодом, действие: config|reconnect|None)."""
    low = (text or "").lower()

    def has(*keys):
        return any(k in low for k in keys)

    if has("didn't find section in config", "didn\u2019t find section in config"):
        return (E("E110", "Google Drive ещё не подключён. Нажмите «Настроить Drive» и войдите "
                          "в аккаунт Google в браузере."), "config")
    if has("invalid_grant", "oauth2", "token has been expired", "unauthorized",
           "invalid credentials", "failed to get token", "autherror"):
        return (E("E111", "доступ к Google Drive истёк или отозван. Нажмите «Настроить Drive» "
                          "и войдите в аккаунт заново."), "reconnect")
    if has("storagequotaexceeded", "storage quota"):
        return (E("E112", "на Google Drive закончилось свободное место. Освободите место "
                          "или выберите другой аккаунт."), None)
    if has("ratelimit", "rate limit"):
        return (E("E113", "Google временно ограничил число запросов к Drive (так бывает с общим ключом rclone). "
                          "Подождите 5–10 минут и повторите. Если ошибка повторяется постоянно, нажмите "
                          "«Сообщить об ошибке» внизу окна и отправьте отчёт разработчику: возможно, "
                          "понадобится собственный ключ Google API."), None)
    if has("couldn't find root directory", "directory not found", "notfound",
           "file not found", "error 404", "object not found"):
        return (E("E114", "папка не найдена или у аккаунта нет к ней доступа. Проверьте ссылку "
                          "и откройте доступ аккаунту, под которым вы вошли в Drive."), None)
    if has("403", "forbidden", "insufficient", "permission", "cannotadd"):
        return (E("E115", "нет прав на запись в эту папку. Попросите владельца выдать "
                          "доступ «Редактор»."), None)
    if has("no such host", "dial tcp", "i/o timeout", "connection refused",
           "network is unreachable", "timed out", "deadline exceeded", "tls handshake"):
        return (E("E116", "нет соединения с Google. Проверьте интернет и повторите."), None)
    return (E("E199", "неизвестная ошибка при работе с Google Drive.", True), None)


def recycle_file(path):
    """Переместить файл в Корзину Windows (можно восстановить). True — файл убран."""
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

        op = SHFILEOPSTRUCTW()
        op.wFunc = 3                                  # FO_DELETE
        op.pFrom = os.path.abspath(path) + "\0"
        op.fFlags = 0x40 | 0x10 | 0x400 | 0x4         # в Корзину, без вопросов и окон
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return res == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)
    except Exception:
        return False


def check_drive(procs, exe, folder_id):
    """Возвращает (ok, сообщение, действие)."""
    if not exe:
        return False, E("E101", "не найден rclone. Нажмите «Скачать rclone» или положите rclone.exe рядом с программой."), "get_rclone"
    code, out, err = procs.run([exe, "listremotes"], timeout=30)
    if procs.cancel_event.is_set():
        return False, "Отменено пользователем", None
    if code != 0:
        return False, E("E102", "rclone не запускается (файл повреждён или заблокирован антивирусом). "
                        "Скачайте rclone заново кнопкой «Скачать rclone».", True), "get_rclone"
    if (REMOTE + ":") not in out.split():
        msg, fix = explain_rclone_error("didn't find section in config")
        return False, msg, fix
    if folder_id:
        code, out, err = procs.run([exe, "lsjson", remote_of(folder_id), "--max-depth", "1",
                                    "--files-only", "--no-modtime", "--retries", "2",
                                    "--low-level-retries", "6"], timeout=150)
        if code != 0:
            msg, fix = explain_rclone_error(err)
            return False, msg, fix
        try:
            n = len(json.loads(out.strip() or "[]"))
        except ValueError:
            n = 0
        return True, "Google Drive доступен, папка открывается (файлов внутри: %d)." % n, None
    code, out, err = procs.run([exe, "about", REMOTE + ":"], timeout=60)
    if code != 0:
        msg, fix = explain_rclone_error(err)
        return False, msg, fix
    return True, "Google Drive подключён. Вставьте ссылку на папку и проверьте доступ.", None


def download_rclone(dest_dir, progress=None):
    import urllib.request, zipfile
    buf = io.BytesIO()
    with urllib.request.urlopen(RCLONE_URL, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            buf.write(chunk)
            if progress:
                progress(buf.tell(), total)
    with zipfile.ZipFile(buf) as zf:
        inside = next((n for n in zf.namelist() if n.lower().endswith("rclone.exe")), "")
        if not inside:
            raise RuntimeError("в архиве rclone.exe не нашёлся")
        dest = os.path.join(dest_dir, "rclone.exe")
        with zf.open(inside) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return dest


# ══ ПАРСЕР ПРОФИЛЕЙ ══════════════════════════════════════════════════════════

def parse_profiles(text):
    names = []
    for line in text.splitlines():
        line = line.strip().strip('"').strip()
        if not line:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            continue
        if "|" in line:  # формат «Название | адрес | сайт» — название до первого «|»
            name = line.split("|")[0].strip().strip('"').strip()
            if len(name) >= 2 and name not in names:
                names.append(name)
            continue
        if re.match(r"^\d", line):
            continue
        upper = sum(1 for c in line if c.isupper())
        lower = sum(1 for c in line if c.islower())
        if upper > lower and len(line) > 5 and line not in names:
            names.append(line)
    return names


# ══ СРАВНЕНИЕ НАЗВАНИЙ ═══════════════════════════════════════════════════════

# Организационно-правовые формы: в сравнении не участвуют (GmbH, GmbH & Co. KG, Ltd ...)
LEGAL = frozenset("""
gmbh mbh ag kg kgaa ug ohg se ek ev eg gbr co und and haftungsbeschrankt
haftungsbeschraenkt ltd limited plc inc corp corporation llc llp lp sa srl sarl
bv nv oy sas spa zoo sro kft the
""".split())

# Слова, которые бывают в имени файла выписки, но не в названии компании
FILE_NOISE = frozenset("""
kontoauszug kontoauszuge auszug statement statements bank konto account copy kopie
final scan januar februar maerz marz april mai juni juli august september oktober
november dezember january february march may june july october december
""".split())

_TRANS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "œ": "oe",
          "ø": "o", "đ": "d", "ł": "l"}
_ABBR = re.compile(r"\b(?:[^\W\d_]\.\s?){2,}")
_LOOSE = re.compile(r"ae|oe|ue")

Key = namedtuple("Key", "tokens compact loose")


def _fold(s):
    s = s.casefold()
    for k, v in _TRANS.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens_of(s):
    s = _fold(s)
    s = _ABBR.sub(lambda m: re.sub(r"[.\s]", "", m.group(0)) + " ", s)  # e.K. -> ek
    s = s.replace("&", " ")
    return re.findall(r"[^\W_]+", s)


def _loose(compact):
    return _LOOSE.sub(lambda m: m.group(0)[0], compact)


def make_key(tokens):
    core = [t for t in tokens if t not in LEGAL] or list(tokens)
    compact = "".join(core)
    return Key(tuple(core), compact, _loose(compact))


def company_key(name):
    return make_key(tokens_of(name))


def name_score(ck, file_tokens):
    """Сравнение названия компании (ключ) с токенами имени файла -> (балл, причина)."""
    cleaned = [t for t in file_tokens
               if t not in FILE_NOISE and not (t.isdigit() and t not in ck.tokens)]
    fk = make_key(cleaned)
    if not fk.tokens or not ck.tokens:
        return 0, ""
    if fk.tokens == ck.tokens:
        return 100, "название совпадает"
    if fk.compact == ck.compact:
        return 98, "совпадает без учёта пробелов и знаков"
    if fk.loose == ck.loose:
        return 95, "совпадает с учётом умлаутов (ä = ae)"
    # Похожесть в процентах: лучшее из «посимвольного сходства» и «сходства по словам»
    # (слова сравниваются с допуском на опечатки; лишние/недостающие слова снижают процент).
    sm = SequenceMatcher(None, ck.loose, fk.loose)
    if sm.real_quick_ratio() < SUGGEST_MIN / 100 or sm.quick_ratio() < SUGGEST_MIN / 100:
        return 0, ""
    sim = max(sm.ratio(), _token_sim(ck.tokens, fk.tokens))
    pct = min(int(sim * 100), 94)
    if pct < SUGGEST_MIN:
        return 0, ""
    return pct, "похожее название"


def _token_sim(ct, ft):
    """Сходство наборов слов 0..1 (F-мера с учётом длины слов, допуск на опечатки)."""
    if not ct or not ft:
        return 0.0
    used, matched = set(), 0.0
    for a in ct:
        bi, br = None, 0.0
        for j, b in enumerate(ft):
            if j in used:
                continue
            r = 1.0 if a == b else SequenceMatcher(None, _loose(a), _loose(b)).ratio()
            if r > br:
                bi, br = j, r
        if bi is not None and br >= 0.8:
            used.add(bi)
            matched += br * len(a)
    cov = matched / sum(len(a) for a in ct)
    prec = matched / sum(len(b) for b in ft)
    return 2 * cov * prec / (cov + prec) if cov + prec else 0.0


def text_hits(pages, ckeys):
    """Поиск названий компаний в тексте страниц PDF -> {компания: (балл, причина)}."""
    prepared = []
    for p in pages:
        toks = [t for t in tokens_of(p) if t not in LEGAL]
        compact = "".join(toks)
        prepared.append((" " + " ".join(toks) + " ", compact, _loose(compact)))
    exact, loose_hits = {}, {}
    for c, ck in ckeys.items():
        if len(ck.compact) < 4 or not ck.tokens:
            continue
        phrase = " " + " ".join(ck.tokens) + " "
        for pi, (padded, compact, loose) in enumerate(prepared):
            if phrase in padded:
                exact[c] = (pi, phrase)
                break
        if c not in exact and len(ck.compact) >= 6:
            for pi, (padded, compact, loose) in enumerate(prepared):
                if ck.compact in compact or ck.loose in loose:
                    loose_hits[c] = pi
                    break
    result = {}
    # более длинное название «поглощает» короткое (Alpha vs Alpha Services)
    exact = {c: v for c, v in exact.items()
             if not any(c2 != c and v[1] != v2[1] and v[1] in v2[1] for c2, v2 in exact.items())}
    if exact:
        first = min(pi for pi, _ in exact.values())
        top = [c for c, (pi, _) in exact.items() if pi == first]
        for c in top:
            if len(top) == 1:
                score = 95 if first == 0 else 89
                why = "единственное совпадение в тексте PDF, стр. %d" % (first + 1)
            else:
                score = 88
                why = "название есть в тексте PDF (стр. %d), но подходят несколько компаний" % (first + 1)
            result[c] = (score, why)
    for c, pi in loose_hits.items():
        if c not in result:
            result[c] = (85, "найдено в тексте PDF (стр. %d), без учёта пробелов" % (pi + 1))
    return result


# ══ ЧТЕНИЕ PDF И OCR ═════════════════════════════════════════════════════════

MAX_TEXT_PAGES = 5
MAX_OCR_PAGES = 3
_TEXT_CACHE = {}
_TESS = {"exe": None, "checked": False, "lang": "deu+eng"}


def find_tesseract():
    if not _TESS["checked"]:
        _TESS["checked"] = True
        cands = [shutil.which("tesseract") or "",
                 r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                              "Tesseract-OCR", "tesseract.exe")]
        _TESS["exe"] = next((c for c in cands if c and os.path.isfile(c)), None)
    return _TESS["exe"]


def _ocr_png(exe, png):
    for lang in (_TESS["lang"], "eng"):
        proc = subprocess.run([exe, png, "stdout", "-l", lang, "--psm", "3"],
                              stdin=subprocess.DEVNULL, capture_output=True,
                              creationflags=CREATE_NO_WINDOW, encoding="utf-8",
                              errors="replace", timeout=180)
        if proc.returncode == 0:
            _TESS["lang"] = lang
            return proc.stdout or ""
        if "language" not in (proc.stderr or "").lower() and "data file" not in (proc.stderr or "").lower():
            break
    return ""


def ocr_document(doc, stop):
    exe = find_tesseract()
    if not fitz or not exe:
        return [], "скан без текста — для распознавания установите Tesseract OCR и pymupdf"
    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(min(len(doc), MAX_OCR_PAGES)):
            if stop():
                break
            png = os.path.join(tmp, "p%d.png" % i)
            doc[i].get_pixmap(matrix=fitz.Matrix(2.5, 2.5)).save(png)
            pages.append(_ocr_png(exe, png))
    if not any(p.strip() for p in pages):
        return [], "E303: OCR не смог прочитать текст скана — выберите файл вручную"
    return pages, "текст получен через OCR"


def read_pdf_pages(path, stop=lambda: False):
    """-> (список текстов страниц, заметка). Кэшируется по пути/размеру/mtime."""
    try:
        st = os.stat(path)
        key = (path, st.st_size, st.st_mtime_ns)
    except OSError:
        return [], "E302: файл недоступен (удалён или занят другой программой)"
    if key in _TEXT_CACHE:
        return _TEXT_CACHE[key]
    pages, note = [], ""
    try:
        if fitz:
            doc = fitz.open(path)
            try:
                pages = [doc[i].get_text() or "" for i in range(min(len(doc), MAX_TEXT_PAGES))]
                if sum(len(p.strip()) for p in pages) < 30 and len(doc):
                    pages, note = ocr_document(doc, stop)
            finally:
                doc.close()
        elif PdfReader:
            reader = PdfReader(path)
            pages = [(reader.pages[i].extract_text() or "")
                     for i in range(min(len(reader.pages), MAX_TEXT_PAGES))]
            if sum(len(p.strip()) for p in pages) < 30:
                pages, note = [], "скан без текста — для распознавания установите pymupdf и Tesseract OCR"
        else:
            note = E("E003", "не установлены библиотеки для чтения PDF. Запустите ІНСТРУКЦІЯ.bat.")
    except Exception as e:
        pages, note = [], "E302: PDF не читается (повреждён или защищён паролем)"
    if not stop():
        _TEXT_CACHE[key] = (pages, note)
    return pages, note


# ══ СОПОСТАВЛЕНИЕ ФАЙЛОВ И КОМПАНИЙ ══════════════════════════════════════════

AUTO_MIN = 90       # от этого процента совпадение подтверждается автоматически
SUGGEST_MIN = 50    # ниже — «нет файла»; между 50 и 90 — человек подтверждает или выбирает сам
GAP = 5             # отрыв от второго кандидата, иначе «неоднозначно»


def new_row(status="none", file="", reason="", suggest="", score=0):
    return {"status": status, "file": file, "reason": reason, "suggest": suggest, "score": score}


def list_pdfs(folder):
    try:
        return sorted(f for f in os.listdir(folder)
                      if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(folder, f)))
    except OSError:
        return []


def compute_matches(companies, files, folder, locked, stop=None, progress=None):
    """locked: {компания: файл} — подтверждено вручную, не трогаем.
    -> {"rows": {...}, "notes": {файл: заметка}, "unused": [файлы]}"""
    stop = stop or (lambda: False)
    ckeys = {c: company_key(c) for c in companies}
    locked_files = set(locked.values())
    free_c = [c for c in companies if c not in locked]
    free_f = [f for f in files if f not in locked_files]
    cand = {f: {} for f in free_f}
    notes = {}

    def put(f, c, s, why):
        if s >= SUGGEST_MIN and (c not in cand[f] or s > cand[f][c][0]):
            cand[f][c] = (s, why)

    for f in free_f:
        toks = tokens_of(os.path.splitext(f)[0])
        for c in free_c:
            s, why = name_score(ckeys[c], toks)
            if s:
                put(f, c, s, "имя файла: " + why)

    def confident(f):
        v = sorted((s for s, _ in cand[f].values()), reverse=True)
        return bool(v) and v[0] >= AUTO_MIN and (len(v) == 1 or v[0] - v[1] >= GAP)

    todo = [f for f in free_f if not confident(f)]
    sub = {c: ckeys[c] for c in free_c}
    for i, f in enumerate(todo):
        if stop():
            break
        if progress:
            progress(i, len(todo), f)
        pages, note = read_pdf_pages(os.path.join(folder, f), stop)
        if note:
            notes[f] = note
        for c, (s, why) in text_hits(pages, sub).items():
            put(f, c, s, why)

    def file_scores(f, pool):
        return sorted(((cand[f][c][0], c) for c in cand[f] if c in pool), reverse=True)

    def company_scores(c, taken=()):
        return sorted(((cand[f][c][0], f) for f in cand if c in cand[f] and f not in taken),
                      reverse=True)

    rows = {c: new_row("manual", f, "выбрано вручную") for c, f in locked.items()}
    taken_f, done_c = set(), set()
    pool = set(free_c)

    for f in free_f:                                   # 1) автоподтверждение
        fs = file_scores(f, pool)
        if not fs or fs[0][0] < AUTO_MIN:
            continue
        s, c = fs[0]
        cs = company_scores(c)
        if (len(fs) > 1 and s - fs[1][0] < GAP) or (len(cs) > 1 and s - cs[1][0] < GAP):
            continue
        if c in done_c or f in taken_f:
            continue
        rows[c] = new_row("auto", f, "%s (%d%%)" % (cand[f][c][1], s), "", s)
        done_c.add(c)
        taken_f.add(f)

    rest = [c for c in free_c if c not in done_c]
    rest_set = set(rest)
    suggested_files = set()
    for c in rest:                                     # 2) предложения / неоднозначные
        opts = company_scores(c, taken_f)
        if not opts:
            rows[c] = new_row("none", "", "подходящий PDF не найден")
            continue
        s, f = opts[0]
        ok = s >= SUGGEST_MIN and (len(opts) == 1 or s - opts[1][0] >= GAP)
        if ok:
            rivals = [sc for sc, cc in file_scores(f, rest_set) if cc != c]
            ok = not rivals or s - rivals[0] >= GAP
        if ok:
            rows[c] = new_row("suggest", "", "%s (%d%%) — подтвердите или выберите другой файл" % (cand[f][c][1], s), f, s)
            suggested_files.add(f)
        else:
            names = ", ".join("%s (%d%%)" % (ff, ss) for ss, ff in opts[:3])
            rows[c] = new_row("ambiguous", "", "неоднозначно, подходят: " + names)
    unused = [f for f in free_f if f not in taken_f and f not in suggested_files]
    return {"rows": rows, "notes": notes, "unused": unused}


# ══ EXCEL ════════════════════════════════════════════════════════════════════

def _need_openpyxl():
    if not openpyxl:
        raise RuntimeError("openpyxl не установлен: pip install openpyxl")


def create_excel(path, companies):
    _need_openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Выписки"
    for col, title, width in (("A", "Компания", 50), ("B", "Ссылка на выписку", 70), ("C", "Файл", 40)):
        ws[col + "1"] = title
        ws[col + "1"].font = Font(bold=True)
        ws.column_dimensions[col].width = width
    for i, name in enumerate(companies, start=2):
        ws.cell(row=i, column=1, value=name)
    wb.save(path)


def read_excel_companies(path):
    _need_openpyxl()
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        ws = wb.active
        names = []
        for (val,) in ws.iter_rows(min_row=2, max_col=1, values_only=True):
            val = str(val).strip() if val is not None else ""
            if val and val not in names:
                names.append(val)
        return names
    finally:
        wb.close()


def write_links_to_excel(path, links):
    """links: {компания: (ссылка, имя файла на Drive)}. -> (записано, добавлено новых строк)."""
    _need_openpyxl()
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    by_name, by_key = {}, {}
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v:
            s = str(v).strip()
            by_name.setdefault(s, r)
            by_key.setdefault(company_key(s).tokens, []).append(r)
    if ws["C1"].value is None:
        ws["C1"] = "Файл"
        ws["C1"].font = Font(bold=True)
        ws.column_dimensions["C"].width = 40
    written = added = 0
    for company, (link, dest) in links.items():
        r = by_name.get(company.strip())
        if not r:
            lst = by_key.get(company_key(company).tokens, [])
            r = lst[0] if len(lst) == 1 else None
        if not r:
            r = ws.max_row + 1
            ws.cell(row=r, column=1, value=company)
            added += 1
        cell = ws.cell(row=r, column=2, value=link)
        cell.hyperlink = link
        cell.style = "Hyperlink"
        ws.cell(row=r, column=3, value=dest)
        written += 1
    wb.save(path)
    return written, added


# ══ ДИАЛОГ ВЫБОРА PDF ════════════════════════════════════════════════════════

class PickDialog(tk.Toplevel):
    """result: None — отмена, "" — без файла, иначе имя файла."""

    def __init__(self, parent, company, folder, items, preselect):
        super().__init__(parent)
        t = THEME
        self.title("Выбор PDF")
        self.configure(bg=t["bg"], padx=16, pady=14)
        self.transient(parent)
        self.minsize(520, 380)
        self.geometry("680x480+%d+%d" % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 60))
        self.result = None
        self.folder = folder
        self.items = items          # [(файл, подпись)]
        self.shown = []
        self.preselect = preselect

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        lbl = ttk.Label(self, text=company, style="H.TLabel", justify="left")
        lbl.grid(row=0, column=0, sticky="we")
        wrap_on_resize(lbl)
        self.var_q = tk.StringVar()
        self.var_q.trace_add("write", lambda *a: self._fill())
        e = ttk.Entry(self, textvariable=self.var_q)
        e.grid(row=1, column=0, sticky="we", pady=(8, 8))
        enable_clipboard(e)

        lf = ttk.Frame(self)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.lb = tk.Listbox(lf, bg=t["field"], fg=t["field_ink"], relief="flat",
                             selectbackground=AURORA[0], selectforeground="#ffffff",
                             activestyle="none", exportselection=False, font=FONT,
                             highlightthickness=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.lb.bind("<Double-Button-1>", lambda e: self._ok())
        self.lb.bind("<Return>", lambda e: self._ok())

        bf = ttk.Frame(self)
        bf.grid(row=3, column=0, sticky="we", pady=(10, 0))
        ttk.Button(bf, text="Открыть PDF", command=self._open).pack(side="left")
        ttk.Button(bf, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(bf, text="Без файла", command=self._none).pack(side="right", padx=6)
        ttk.Button(bf, text="Выбрать", style="Accent.TButton", command=self._ok).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self._fill()
        e.focus_set()
        self.grab_set()

    def _fill(self):
        q = self.var_q.get().strip().lower()
        self.shown = [(f, lbl) for f, lbl in self.items if q in f.lower()]
        self.lb.delete(0, "end")
        for f, lbl in self.shown:
            self.lb.insert("end", f + lbl)
        idx = 0
        for i, (f, _) in enumerate(self.shown):
            if f == self.preselect:
                idx = i
                break
        if self.shown:
            self.lb.selection_set(idx)
            self.lb.see(idx)

    def _current(self):
        sel = self.lb.curselection()
        return self.shown[sel[0]][0] if sel else None

    def _ok(self):
        f = self._current()
        if f:
            self.result = f
            self.destroy()

    def _none(self):
        self.result = ""
        self.destroy()

    def _open(self):
        f = self._current()
        if f:
            try:
                os.startfile(os.path.join(self.folder, f))
            except OSError:
                pass


# ══ ПРИЛОЖЕНИЕ ═══════════════════════════════════════════════════════════════

STATE_TEXT = {"auto": "✓ авто", "manual": "✓ подтверждено", "suggest": "? подтвердить",
              "ambiguous": "⚠ выбрать", "none": "✗ нет файла"}
STATE_TAG = {"auto": "ok", "manual": "ok", "suggest": "warn", "ambiguous": "warn", "none": "bad"}
CONFIRMED = ("auto", "manual")
DEFAULT_TABLE = "Таблица 1"


class App:
    def __init__(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.title("Помощник ИИ Вжух")

        legacy = load_json(LEGACY_CONFIG)
        self.cfg = {**legacy, **load_json(CONFIG_FILE)}
        self.root.geometry(self.cfg.get("geometry") or "1080x840")
        self.root.minsize(720, 700)
        apply_theme(self.root, THEME)

        self.q = queue.Queue()
        self.cancel_event = threading.Event()
        self.procs = Procs(self.cancel_event)
        self.working = False
        self.work_buttons = []
        self.save_warned = False
        self.last_error = None

        self.companies = []
        self.rows = {}         # компания -> new_row(...)
        self.links = {}        # компания -> {"link":..., "dest":...}
        self.excel_path = ""
        self.pdf_files = []
        self.tables = {}       # название -> данные таблицы
        self.current = DEFAULT_TABLE

        self.root.report_callback_exception = self._on_tk_exception
        threading.excepthook = lambda a: self.emit("error", E("E901", "неожиданный сбой в фоновой операции.", True),
                                                    "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
        self._build_ui()
        self._restore_state()
        self._check_deps()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll)

    # ── очередь событий из потоков ──

    def emit(self, *args):
        self.q.put(args)

    def _poll(self):
        while True:
            try:
                kind, *a = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(*a)
            elif kind == "status":
                self.lbl_status.configure(text=a[0])
            elif kind == "bar":
                self.bar["maximum"] = max(a[1], 1)
                self.bar["value"] = a[0]
            elif kind == "done":
                self._log(a[0] if a else "Готово", "success")
                self._finish()
            elif kind == "error":
                self._remember_error(a[0], a[1] if len(a) > 1 else "")
                self._log(a[0], "danger")
                self._finish()
            elif kind == "cancelled":
                self._log("Операция отменена", "warning")
                self._finish()
            elif kind == "match_result":
                self._apply_match(a[0])
            elif kind == "deleted":
                self._scan_folder()
                for c in a[0]:
                    if c in self.rows:
                        self.rows[c]["reason"] = "загружено на Drive, файл убран из папки"
                self._refresh_table()
                self._save_state()
            elif kind == "links":
                self.links.update(a[0])
                self._refresh_table()
                self._save_state()
            elif kind == "drive_status":
                self._set_drive_status(a[0], a[1])
            elif kind == "rclone_path":
                self.cfg["rclone"] = a[0]
                self._save_config()
                self.lbl_rclone.configure(text="rclone найден ✓")
            elif kind == "call":
                a[0]()
        self.root.after(100, self._poll)

    def _finish(self):
        self.lbl_status.configure(text="")
        self.bar["value"] = 0
        self._set_working(False)

    # ── интерфейс ──

    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        head = ttk.Frame(root, padding=(20, 14, 20, 6))
        head.grid(row=0, column=0, sticky="we")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Помощник ИИ Вжух", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_hint = ttk.Label(head, style="Muted.TLabel",
                                  text="Компании  →  сопоставление PDF  →  загрузка на Google Drive. Ссылки хранятся в таблицах прямо в программе.")
        self.lbl_hint.grid(row=1, column=0, sticky="w")
        tbl = ttk.Frame(head)
        tbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(tbl, text="Таблица:", style="H.TLabel").pack(side="left", padx=(0, 8))
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(tbl, textvariable=self.var_table, state="readonly", width=24)
        self.cmb_table.pack(side="left")
        self.cmb_table.bind("<<ComboboxSelected>>", self.on_switch_table)
        self._btn(tbl, "Новая…", self.on_new_table).pack(side="left", padx=(8, 0))
        self._btn(tbl, "Переименовать", self.on_rename_table).pack(side="left", padx=(6, 0))
        self._btn(tbl, "Удалить", self.on_delete_table).pack(side="left", padx=(6, 0))

        paned = ttk.PanedWindow(root, orient="vertical")
        paned.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 6))

        self.nb = ttk.Notebook(paned)
        paned.add(self.nb, weight=5)
        self._build_tab_companies()
        self._build_tab_match()
        self._build_tab_drive()
        from profile_panel import ProfilePanel
        self.profile_panel = ProfilePanel(self.nb, APP_DIR)
        self.nb.add(self.profile_panel, text="4  Профили")
        from ads_bridge import AdsPanel
        self.ads_panel = AdsPanel(self.nb, self.profile_panel, APP_DIR)
        self.nb.add(self.ads_panel, text="5  Реклама")
        from documents_panel import DocumentsPanel
        self.read_document_pdf = read_pdf_pages
        self.find_document_ocr = find_tesseract
        self.ocr_document_image = _ocr_png
        self.document_fitz = fitz
        self.documents_panel = DocumentsPanel(self.nb, self, APP_DIR)
        self.nb.add(self.documents_panel, text="6  Документы")
        from document_stock import StockPanel
        self.stock_panel = StockPanel(self.nb, self, APP_DIR)
        self.nb.add(self.stock_panel, text="7  Склад")

        logf = ttk.Frame(paned)
        paned.add(logf, weight=1)
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        t = THEME
        self.log = tk.Text(logf, height=4, wrap="word", state="disabled", bg=t["surface"],
                           fg=t["ink"], relief="flat", font=MONO, padx=10, pady=8,
                           selectbackground=AURORA[0], highlightthickness=0)
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        for tag, color in SEMANTIC.items():
            self.log.tag_configure(tag, foreground=color)
        self.log.tag_configure("muted", foreground=t["muted"])
        attach_context_menu(self.log)

        bar = ttk.Frame(root, padding=(20, 4, 20, 12))
        bar.grid(row=2, column=0, sticky="we")
        bar.columnconfigure(0, weight=1)
        self.lbl_status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.lbl_status.grid(row=0, column=0, sticky="we")
        self.bar = ttk.Progressbar(bar, length=180, mode="determinate",
                                   style="Aurora.Horizontal.TProgressbar")
        self.bar.grid(row=0, column=1, padx=(8, 8))
        self.btn_cancel = ttk.Button(bar, text="Отмена", style="Danger.TButton",
                                     command=self.on_cancel, state="disabled")
        self.btn_cancel.grid(row=0, column=2)
        self.btn_open_excel = ttk.Button(bar, text="Открыть Excel", command=self.on_open_excel)
        self.btn_open_excel.grid(row=0, column=3, padx=(8, 0))
        ttk.Button(bar, text="Сообщить об ошибке", command=self.on_report).grid(row=0, column=4, padx=(8, 0))

    def _tab(self, title):
        f = ttk.Frame(self.nb, style="Card.TFrame", padding=14)
        f.columnconfigure(0, weight=1)
        self.nb.add(f, text=title)
        return f

    def _btn(self, parent, text, cmd, style="TButton"):
        b = ttk.Button(parent, text=text, command=cmd, style=style)
        self.work_buttons.append(b)
        return b

    def _build_tab_companies(self):
        tab = self._tab("1  Компании")
        tab.rowconfigure(0, weight=1)
        card = make_card(tab, "Платёжные профили",
                         "Вставьте текст профилей — программа вытащит названия компаний. Excel не обязателен: "
                         "ссылки будут храниться в таблице внутри программы. Excel можно создать или подключить по желанию.")
        card.outer.grid(row=0, column=0, sticky="nsew")
        card.rowconfigure(2, weight=1)

        tf = ttk.Frame(card, style="Card.TFrame")
        tf.grid(row=2, column=0, sticky="nsew")
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)
        t = THEME
        self.txt_profiles = tk.Text(tf, height=8, wrap="word", bg=t["field"], fg=t["field_ink"],
                                    insertbackground=t["field_ink"], selectbackground=AURORA[0],
                                    relief="flat", font=MONO, padx=8, pady=8, highlightthickness=0)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.txt_profiles.yview)
        self.txt_profiles.configure(yscrollcommand=sb.set)
        self.txt_profiles.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        enable_clipboard(self.txt_profiles)

        bf = ttk.Frame(card, style="Card.TFrame")
        bf.grid(row=3, column=0, sticky="we", pady=(10, 0))
        self._btn(bf, "Распознать компании", lambda: self.on_parse(False), "Accent.TButton").pack(side="left")
        self._btn(bf, "…и создать Excel", lambda: self.on_parse(True)).pack(side="left", padx=8)
        self._btn(bf, "Открыть готовый Excel…", self.on_pick_excel).pack(side="left")

        self.lbl_companies = ttk.Label(card, text="", style="CardMuted.TLabel", justify="left")
        self.lbl_companies.grid(row=4, column=0, sticky="we", pady=(10, 0))
        wrap_on_resize(self.lbl_companies)

    def _build_tab_match(self):
        tab = self._tab("2  Сопоставление PDF")
        tab.rowconfigure(2, weight=1)

        ff = ttk.Frame(tab, style="Card.TFrame")
        ff.grid(row=0, column=0, sticky="we")
        ff.columnconfigure(1, weight=1)
        ttk.Label(ff, text="Папка с PDF:", style="Card.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.var_folder = tk.StringVar(value=self.cfg.get("last_folder", ""))
        e = ttk.Entry(ff, textvariable=self.var_folder)
        e.grid(row=0, column=1, sticky="we")
        enable_clipboard(e)
        self._btn(ff, "Обзор…", self.on_browse).grid(row=0, column=2, padx=(8, 0))

        tb = ttk.Frame(tab, style="Card.TFrame")
        tb.grid(row=1, column=0, sticky="we", pady=(10, 8))
        self._btn(tb, "Сопоставить", self.on_match, "Accent.TButton").pack(side="left")
        self._btn(tb, "Принять все предложения", self.on_accept_all).pack(side="left", padx=8)
        self._btn(tb, "Выбрать PDF вручную", self.on_pick_selected).pack(side="left")

        tf = ttk.Frame(tab, style="Card.TFrame")
        tf.grid(row=2, column=0, sticky="nsew")
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)
        cols = ("company", "pdf", "reason", "state", "link")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for col, title, w, mn, stretch in (
                ("company", "Компания", 240, 140, True), ("pdf", "PDF", 210, 120, True),
                ("reason", "Причина совпадения", 300, 140, True),
                ("state", "Статус", 120, 100, False), ("link", "Ссылка на Drive", 200, 90, True)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, minwidth=mn, stretch=stretch)
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="we")
        self.tree.tag_configure("ok", foreground=SEMANTIC["success"])
        self.tree.tag_configure("warn", foreground=SEMANTIC["warning"])
        self.tree.tag_configure("bad", foreground=SEMANTIC["danger"])
        self.tree.bind("<Double-Button-1>", lambda e: self.on_pick_selected())
        self.tree.bind("<Return>", lambda e: self.on_pick_selected())
        self.tree.bind("<Button-3>", self._tree_menu)
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.tree.bind("<Control-A>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.tree.bind("<Control-c>", lambda e: (self.on_copy_selected(), "break")[1])
        self.tree.bind("<Control-C>", lambda e: (self.on_copy_selected(), "break")[1])

        self.lbl_match = ttk.Label(tab, text="", style="CardMuted.TLabel", justify="left")
        self.lbl_match.grid(row=3, column=0, sticky="we", pady=(8, 0))
        wrap_on_resize(self.lbl_match)
        xb = ttk.Frame(tab, style="Card.TFrame")
        xb.grid(row=4, column=0, sticky="we", pady=(8, 0))
        self._btn(xb, "Копировать только ссылки", self.on_copy_only_links).pack(side="left")
        self._btn(xb, "Копировать «компания — ссылка»", self.on_copy_links).pack(side="left", padx=8)
        self._btn(xb, "Экспорт таблицы в Excel…", self.on_export_excel).pack(side="left", padx=8)

    def _build_tab_drive(self):
        tab = self._tab("3  Загрузка на Drive")
        card = make_card(tab, "Google Drive",
                         "Вставьте ссылку на папку. Подключение и доступ проверяются автоматически.")
        card.outer.grid(row=0, column=0, sticky="we")
        df = ttk.Frame(card, style="Card.TFrame")
        df.grid(row=2, column=0, sticky="we")
        df.columnconfigure(1, weight=1)
        ttk.Label(df, text="Ссылка на папку:", style="Card.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.var_drive = tk.StringVar(value=self.cfg.get("last_drive", ""))
        e = ttk.Entry(df, textvariable=self.var_drive)
        e.grid(row=0, column=1, sticky="we")
        enable_clipboard(e)

        bf = ttk.Frame(card, style="Card.TFrame")
        bf.grid(row=3, column=0, sticky="we", pady=(8, 0))
        self._btn(bf, "Проверить доступ", self.on_check_drive).pack(side="left")
        self._btn(bf, "Настроить Drive", self.on_setup_drive).pack(side="left", padx=8)
        self.b_get_rclone = self._btn(bf, "Скачать rclone", self.on_get_rclone)
        self.b_get_rclone.pack(side="left")

        self.lbl_drive = ttk.Label(card, text="Доступ ещё не проверялся", style="CardMuted.TLabel",
                                   justify="left")
        self.lbl_drive.grid(row=4, column=0, sticky="we", pady=(8, 0))
        wrap_on_resize(self.lbl_drive)
        self.lbl_rclone = ttk.Label(card, text="", style="CardMuted.TLabel", justify="left")
        self.lbl_rclone.grid(row=5, column=0, sticky="we", pady=(2, 0))
        wrap_on_resize(self.lbl_rclone)

        up = make_card(tab, "Загрузка")
        up.outer.grid(row=1, column=0, sticky="we", pady=(10, 0))
        self.lbl_upload = ttk.Label(up, text="", style="Card.TLabel", justify="left")
        self.lbl_upload.grid(row=2, column=0, sticky="we")
        wrap_on_resize(self.lbl_upload)
        ttk.Label(up, style="CardMuted.TLabel", justify="left",
                  text="Уходят только подтверждённые PDF (✓). Остальные файлы папки не отправляются."
                  ).grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.var_delete = tk.BooleanVar(value=bool(self.cfg.get("delete_after_upload", False)))
        self.chk_delete = ttk.Checkbutton(
            up, style="Card.TCheckbutton", variable=self.var_delete,
            text="После успешной загрузки убрать PDF из папки (в Корзину Windows)")
        self.chk_delete.grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.work_buttons.append(self.chk_delete)
        self.btn_upload = self._btn(up, "Загрузить на Drive и сохранить ссылки", self.on_upload, "Accent.TButton")
        self.btn_upload.grid(row=5, column=0, sticky="w", pady=(10, 0))

    # ── служебное ──

    # ── ошибки и отчёт разработчикам ──

    def _remember_error(self, text, detail=""):
        self.last_error = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "text": text, "detail": detail}

    def _fail(self, code, text, exc=None, report=False):
        """Показать понятную ошибку с кодом; технические детали уходят только в отчёт."""
        msg = E(code, text, report)
        self._remember_error(msg, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else "")
        self._log(msg, "danger")

    def _on_tk_exception(self, exc_type, exc, tb):
        self._fail("E901", "в программе произошёл неожиданный сбой. Можно продолжить работу.", exc, True)

    def build_report(self):
        def have(x):
            return "да" if x else "нет"
        st = {s: sum(1 for c in self.companies if self.rows.get(c, {}).get("status") == s) for s in STATE_TEXT}
        try:
            log_tail = self.log.get("1.0", "end").strip().splitlines()[-25:]
        except tk.TclError:
            log_tail = []
        err = self.last_error or {}
        lines = [
            "ОТЧЁТ ОБ ОШИБКЕ — Помощник ИИ Вжух v%s" % APP_VERSION,
            "Время: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Система: %s, Python %s" % (platform.platform(), platform.python_version()),
            "openpyxl: %s, pymupdf: %s, pypdf: %s, Tesseract: %s, rclone: %s" % (
                have(openpyxl), have(fitz), have(PdfReader), have(find_tesseract()),
                have(find_rclone(self.cfg.get("rclone", "")))),
            "Компаний: %d, PDF в папке: %d, статусы: %s" % (len(self.companies), len(self.pdf_files), st),
            "",
            "ПОСЛЕДНЯЯ ОШИБКА: " + (err.get("text") or "ошибок не было"),
            "Время ошибки: " + (err.get("time") or "—"),
            "Технические детали:", (err.get("detail") or "—").strip(),
            "",
            "ПОСЛЕДНИЕ СТРОКИ ЖУРНАЛА:"] + log_tail + [
            "",
            "(В отчёте могут быть названия компаний и файлов. Ссылка на Drive и пароли в него не попадают.)"]
        return "\n".join(lines)

    def on_report(self):
        text = self.build_report()
        saved = ""
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            with open(REPORT_FILE, "w", encoding="utf-8") as f:
                f.write(text)
            saved = "\nФайл с отчётом: " + REPORT_FILE
        except OSError:
            pass
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            msg = "Отчёт скопирован в буфер обмена.\nВставьте его (Ctrl+V) в сообщение разработчику." + saved
        except tk.TclError:
            msg = "Не удалось скопировать в буфер обмена." + (saved or "\nСделайте скриншот журнала внизу окна.")
        messagebox.showinfo("Отчёт для разработчиков", msg, parent=self.root)

    def _log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_working(self, v):
        self.working = v
        for b in self.work_buttons:
            b.configure(state="disabled" if v else "normal")
        self.btn_cancel.configure(state="normal" if v else "disabled")
        self.cmb_table.configure(state="disabled" if v else "readonly")

    def _begin(self, status=""):
        self.cancel_event.clear()
        self._set_working(True)
        self.lbl_status.configure(text=status)

    def _set_drive_status(self, text, style):
        names = {"success": "CardSuccess.TLabel", "danger": "CardDanger.TLabel",
                 "warning": "CardWarning.TLabel"}
        self.lbl_drive.configure(text=text, style=names.get(style, "CardMuted.TLabel"))

    def _check_deps(self):
        if not openpyxl:
            self._log(E("E001", "не установлена библиотека для Excel (openpyxl). Запустите ІНСТРУКЦІЯ.bat."), "danger")
        if not fitz and not PdfReader:
            self._log(E("E003", "не установлены библиотеки для чтения PDF. Запустите ІНСТРУКЦІЯ.bat."), "danger")
        elif not fitz:
            self._log("pymupdf не найден — OCR сканов недоступен (pip install pymupdf).", "warning")
        elif not find_tesseract():
            self._log("Tesseract OCR не найден — сканы без текста распознаны не будут.", "warning")
        exe = find_rclone(self.cfg.get("rclone", ""))
        if exe:
            self.cfg["rclone"] = exe
            self.lbl_rclone.configure(text="rclone найден ✓")
        else:
            self.lbl_rclone.configure(text="rclone не найден")
            self._log("rclone не найден — скачайте кнопкой или положите rclone.exe рядом", "warning")

    # ── сохранение / восстановление ──

    def _save_config(self):
        self.cfg["last_folder"] = self.var_folder.get().strip()
        self.cfg["last_drive"] = self.var_drive.get().strip()
        self.cfg["delete_after_upload"] = bool(self.var_delete.get())
        try:
            self.cfg["geometry"] = self.root.winfo_geometry()
        except tk.TclError:
            pass
        self._safe_save(CONFIG_FILE, self.cfg)

    def _safe_save(self, path, data):
        try:
            save_json(path, data)
        except OSError as e:
            if not self.save_warned:
                self.save_warned = True
                self._fail("E902", "не удалось сохранить настройки и сделанную работу. После перезапуска они не восстановятся. "
                           "Проверьте, что диск не заполнен и папка %APPDATA% доступна.", e, True)

    def _snapshot(self):
        return {"profiles": self.txt_profiles.get("1.0", "end").rstrip(),
                "companies": self.companies, "excel": self.excel_path,
                "rows": self.rows, "links": self.links,
                "folder": self.var_folder.get().strip(), "drive": self.var_drive.get().strip()}

    def _save_state(self):
        self.tables[self.current] = self._snapshot()
        self._safe_save(STATE_FILE, {"version": 2, "current": self.current, "tables": self.tables})
        self._save_config()

    def _load_table(self, data):
        self.txt_profiles.delete("1.0", "end")
        if data.get("profiles"):
            self.txt_profiles.insert("1.0", data["profiles"])
        self.companies = [c for c in data.get("companies", []) if isinstance(c, str)]
        self.excel_path = data.get("excel", "") if os.path.isfile(data.get("excel", "") or "") else ""
        self.links = {c: v for c, v in data.get("links", {}).items() if c in self.companies and isinstance(v, dict)}
        self.var_folder.set(data.get("folder", ""))
        self.var_drive.set(data.get("drive", ""))
        self._scan_folder()
        saved = data.get("rows", {})
        self.rows = {}
        for c in self.companies:
            r = saved.get(c)
            if isinstance(r, dict) and r.get("status") in STATE_TEXT:
                r = {**new_row(), **r}
                for key in ("file", "suggest"):
                    if c in self.links and key == "file":
                        continue                      # загружено: файл мог быть убран из папки
                    if r[key] and r[key] not in self.pdf_files:
                        r[key] = ""
                        if r["status"] in CONFIRMED + ("suggest",):
                            r["status"], r["reason"] = "none", "файл не найден в папке — выберите заново"
                self.rows[c] = r
            else:
                self.rows[c] = new_row("none", "", "ещё не сопоставлено")
        self._refresh_table()

    def _refresh_table_list(self):
        self.cmb_table.configure(values=list(self.tables))
        self.var_table.set(self.current)

    def _restore_state(self):
        st = load_json(STATE_FILE)
        if isinstance(st.get("tables"), dict) and st["tables"]:
            self.tables = {k: v for k, v in st["tables"].items() if isinstance(v, dict)} or {DEFAULT_TABLE: {}}
            self.current = st.get("current") if st.get("current") in self.tables else next(iter(self.tables))
        else:                                         # старый формат (до таблиц)
            legacy = {**(st if st.get("companies") else {}),
                      "folder": self.cfg.get("last_folder", ""), "drive": self.cfg.get("last_drive", "")}
            self.tables = {DEFAULT_TABLE: legacy}
            self.current = DEFAULT_TABLE
        self._load_table(self.tables[self.current])
        self._refresh_table_list()
        if self.companies:
            self._log("Восстановлена таблица «%s»: компаний %d." % (self.current, len(self.companies)), "info")

    # ── таблицы (проекты) ──

    def _switch_to(self, name):
        self.current = name
        self._load_table(self.tables[name])
        self._refresh_table_list()
        self._save_state()

    def on_switch_table(self, event=None):
        name = self.var_table.get()
        if name == self.current or name not in self.tables:
            return
        self.tables[self.current] = self._snapshot()
        self._switch_to(name)
        self._log("Открыта таблица «%s»" % name, "info")

    def _ask_table_name(self, title, initial=""):
        name = simpledialog.askstring(title, "Название таблицы:", initialvalue=initial, parent=self.root)
        name = (name or "").strip()
        if not name:
            return None
        if name in self.tables and name != self.current:
            messagebox.showwarning("Такое название уже есть", "Таблица «%s» уже существует." % name, parent=self.root)
            return None
        return name

    def on_new_table(self):
        name = self._ask_table_name("Новая таблица")
        if not name:
            return
        self.tables[self.current] = self._snapshot()
        self.tables[name] = {"drive": self.var_drive.get().strip()}
        self._switch_to(name)
        self._log("Создана таблица «%s». Вставьте профили на вкладке «Компании»." % name, "success")
        self.nb.select(0)

    def on_rename_table(self):
        name = self._ask_table_name("Переименовать таблицу", self.current)
        if not name or name == self.current:
            return
        self.tables[self.current] = self._snapshot()
        self.tables = {(name if k == self.current else k): v for k, v in self.tables.items()}
        self.current = name
        self._refresh_table_list()
        self._save_state()

    def on_delete_table(self):
        if not messagebox.askyesno("Удалить таблицу",
                                   "Удалить таблицу «%s» вместе со списком компаний, сопоставлениями и сохранёнными "
                                   "ссылками?\n\nФайлы на диске и на Google Drive не удаляются." % self.current,
                                   parent=self.root):
            return
        del self.tables[self.current]
        if not self.tables:
            self.tables[DEFAULT_TABLE] = {}
        self._switch_to(next(iter(self.tables)))

    # ── общие операции ──

    def _scan_folder(self):
        folder = self.var_folder.get().strip()
        self.pdf_files = list_pdfs(folder) if folder and os.path.isdir(folder) else []

    def _set_companies(self, names):
        self.companies = list(names)
        old = self.rows
        self.rows = {c: old.get(c) or new_row("none", "", "ещё не сопоставлено") for c in names}
        self.links = {c: v for c, v in self.links.items() if c in self.rows}
        self._refresh_table()

    def _drop_link(self, company):
        self.links.pop(company, None)

    def _refresh_table(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(self.companies):
            r = self.rows.get(c) or new_row()
            if r["status"] in CONFIRMED:
                pdf = r["file"]
            elif r["suggest"]:
                pdf = "≈ " + r["suggest"]
            else:
                pdf = "—"
            self.tree.insert("", "end", iid=str(i), tags=(STATE_TAG[r["status"]],),
                             values=(c, pdf, r["reason"], STATE_TEXT[r["status"]],
                                     self.links[c]["link"] if c in self.links else ""))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        self._update_summary()

    def _count(self, status):
        return sum(1 for c in self.companies if self.rows.get(c, {}).get("status") == status)

    def _update_summary(self):
        n = len(self.companies)
        ok = sum(self._count(s) for s in CONFIRMED)
        sug, amb = self._count("suggest"), self._count("ambiguous")
        none = self._count("none")
        if n:
            self.lbl_match.configure(text="Подтверждено %d из %d  ·  предложений: %d  ·  нужен выбор: %d  ·  без файла: %d.   "
                                          "Двойной клик по строке — выбрать PDF вручную." % (ok, n, sug, amb, none))
            self.lbl_companies.configure(text="Таблица «%s»: компаний %d.%s" % (
                self.current, n, ("  Подключён Excel: " + self.excel_path) if self.excel_path
                else "  Excel не подключён — ссылки хранятся в таблице программы."))
            self.lbl_upload.configure(text="К загрузке: %d PDF из %d компаний.  Без подтверждённого файла: %d.\n%s" % (
                ok, n, n - ok, ("Ссылки сохранятся в таблице программы и в Excel: " + self.excel_path)
                if self.excel_path else "Ссылки сохранятся в таблице программы «%s»." % self.current))
        else:
            self.lbl_match.configure(text="Сначала получите список компаний на шаге 1.")
            self.lbl_companies.configure(text="Таблица «%s»: список компаний пуст." % self.current)
            self.lbl_upload.configure(text="Пока нечего загружать.")

    # ── шаг 1 ──

    def on_parse(self, make_excel=False):
        names = parse_profiles(self.txt_profiles.get("1.0", "end"))
        if not names:
            self._log(E("E201", "в тексте не найдено ни одной компании. Нужен формат «Название | адрес | сайт» или название заглавными буквами."), "danger")
            return
        if not make_excel:
            self.excel_path = ""
            self._set_companies(names)
            self.links = {}
            self._log("Найдено компаний: %d. Ссылки будут храниться в таблице «%s» внутри программы." % (len(names), self.current), "success")
            self._save_state()
            self.nb.select(1)
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить Excel", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialdir=self.cfg.get("last_excel_dir", BASE_DIR),
            initialfile="выписки_%s.xlsx" % datetime.date.today().strftime("%d-%m-%Y"))
        if not path:
            return
        try:
            create_excel(path, names)
        except PermissionError:
            self._log(E("E202", "не могу записать файл Excel — он открыт в другой программе или папка защищена. "
                                "Закройте файл и повторите."), "danger")
            return
        except Exception as e:
            self._fail("E203", "не удалось создать файл Excel.", e, True)
            return
        self.cfg["last_excel_dir"] = os.path.dirname(path)
        self.excel_path = path
        self._set_companies(names)
        self.links = {}
        self._log("Найдено компаний: %d. Excel создан: %s" % (len(names), path), "success")
        self._save_state()
        self.nb.select(1)

    def on_pick_excel(self):
        path = filedialog.askopenfilename(
            title="Выберите Excel", filetypes=[("Excel", "*.xlsx *.xlsm")],
            initialdir=self.cfg.get("last_excel_dir", BASE_DIR))
        if not path:
            return
        try:
            names = read_excel_companies(path)
        except Exception as e:
            self._fail("E204", "не удалось открыть Excel (файл повреждён, защищён паролем или занят).", e, True)
            return
        if not names:
            self._log(E("E205", "в колонке A (со 2-й строки) нет названий компаний."), "danger")
            return
        self.cfg["last_excel_dir"] = os.path.dirname(path)
        self.excel_path = path
        self._set_companies(names)
        self._log("Открыт Excel: компаний %d." % len(names), "success")
        self._save_state()
        self.nb.select(1)

    def _links_list(self):
        return [(c, self.links[c]) for c in self.companies if c in self.links]

    def on_copy_only_links(self):
        links = [v["link"] for c, v in self._links_list()]
        if not links:
            self._log("В таблице пока нет ссылок — сначала загрузите PDF на Drive (шаг 3).", "warning")
            return
        self._to_clipboard("\n".join(links))
        self._log("Скопировано ссылок: %d (по одной в строке). Вставьте куда нужно через Ctrl+V." % len(links), "success")

    def on_copy_selected(self):
        """Ctrl+C в таблице: выделенные строки со ссылками -> «компания<Tab>ссылка»."""
        rows = []
        for iid in self.tree.selection():
            c = self.companies[int(iid)]
            if c in self.links:
                rows.append("%s\t%s" % (c, self.links[c]["link"]))
        if rows:
            self._to_clipboard("\n".join(rows))
            self._log("Скопировано строк со ссылками: %d" % len(rows), "success")
        else:
            self._log("В выделенных строках нет ссылок.", "warning")

    def on_copy_links(self):
        items = self._links_list()
        if not items:
            self._log("В таблице пока нет ссылок — сначала загрузите PDF на Drive (шаг 3).", "warning")
            return
        text = "\n".join("%s\t%s" % (c, v["link"]) for c, v in items)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._log("Скопировано строк «компания — ссылка»: %d. Вставьте в Excel или Google Таблицы (Ctrl+V)." % len(items), "success")

    def on_export_excel(self):
        if not self.companies:
            self._log("Таблица пуста — нечего экспортировать.", "warning")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт таблицы в Excel", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialdir=self.cfg.get("last_excel_dir", BASE_DIR),
            initialfile="%s_%s.xlsx" % (re.sub(r'[<>:"/\\|?*]', "_", self.current), datetime.date.today().strftime("%d-%m-%Y")))
        if not path:
            return
        try:
            create_excel(path, self.companies)
            if self.links:
                write_links_to_excel(path, {c: (v["link"], v.get("dest", "")) for c, v in self._links_list()})
        except PermissionError:
            self._log(E("E202", "не могу записать файл Excel — он открыт в другой программе или папка защищена. Закройте файл и повторите."), "danger")
            return
        except Exception as e:
            self._fail("E203", "не удалось создать файл Excel.", e, True)
            return
        self.cfg["last_excel_dir"] = os.path.dirname(path)
        self._log("Таблица экспортирована в Excel: " + path, "success")

    def _tree_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return "break"
        self.tree.selection_set(iid)
        company = self.companies[int(iid)]
        link = self.links.get(company, {}).get("link", "")
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(label="Выбрать PDF…", command=self.on_pick_selected)
        menu.add_separator()
        menu.add_command(label="Копировать название", command=lambda: self._to_clipboard(company))
        menu.add_command(label="Копировать ссылку", state="normal" if link else "disabled",
                         command=lambda: self._to_clipboard(link))
        menu.add_command(label="Открыть ссылку в браузере", state="normal" if link else "disabled",
                         command=lambda: webbrowser.open(link))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def on_open_excel(self):
        if self.excel_path and os.path.isfile(self.excel_path):
            os.startfile(self.excel_path)
        else:
            self._log("К этой таблице Excel не подключён. Ссылки хранятся в программе; кнопка «Экспорт таблицы в Excel…» на шаге 2.", "warning")

    # ── шаг 2 ──

    def on_browse(self):
        d = filedialog.askdirectory(title="Папка с выписками",
                                    initialdir=self.var_folder.get() or BASE_DIR)
        if d:
            self.var_folder.set(d)
            self._scan_folder()
            self._log("PDF в папке: %d" % len(self.pdf_files), "info")
            self._save_config()

    def on_match(self):
        folder = self.var_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log("Выберите папку с выписками", "danger")
            return
        if not self.companies:
            self._log("Сначала получите список компаний (шаг 1)", "danger")
            return
        self._scan_folder()
        if not self.pdf_files:
            self._log("В папке нет PDF-файлов", "danger")
            return
        locked = {c: r["file"] for c, r in self.rows.items()
                  if r["file"] and ((r["status"] == "manual" and r["file"] in self.pdf_files)
                                    or (c in self.links and r["status"] in CONFIRMED))}
        self._begin("Сопоставляю…")
        self._log("Сопоставляю: PDF %d, компаний %d (вручную подтверждено: %d)…"
                  % (len(self.pdf_files), len(self.companies), len(locked)), "info")
        threading.Thread(target=self._match_worker,
                         args=(folder, list(self.pdf_files), list(self.companies), locked),
                         daemon=True).start()

    def _match_worker(self, folder, files, companies, locked):
        try:
            def prog(i, n, name):
                self.emit("bar", i, n)
                self.emit("status", "Читаю PDF %d из %d: %s" % (i + 1, n, name))

            res = compute_matches(companies, files, folder, locked, self.cancel_event.is_set, prog)
            if self.cancel_event.is_set():
                self.emit("cancelled")
                return
            self.emit("match_result", res)
            self.emit("done", "Сопоставление завершено — проверьте таблицу на шаге 2")
        except Exception as e:
            self.emit("error", E("E301", "сбой при сопоставлении PDF.", True), traceback.format_exc())

    def _apply_match(self, res):
        for c, r in res["rows"].items():
            if c in self.rows:
                old = self.rows[c]
                if c in self.links and old["status"] in CONFIRMED and r["file"] == old["file"]:
                    continue                          # уже загружено — не трогаем
                if r["status"] not in CONFIRMED or r["file"] != old.get("file"):
                    self._drop_link(c)
                self.rows[c] = r
        for f, note in res["notes"].items():
            self._log("  %s — %s" % (f, note), "warning")
        if res["unused"]:
            self._log("PDF без пары: %d (например: %s)" % (len(res["unused"]), ", ".join(res["unused"][:3])), "muted")
        self._refresh_table()
        self._save_state()

    def _selected_company(self):
        sel = self.tree.selection()
        if not sel:
            return None
        i = int(sel[0])
        return self.companies[i] if i < len(self.companies) else None

    def _set_confirmed(self, company, filename, reason):
        self.rows[company] = new_row("manual", filename, reason)
        self._drop_link(company)

    def on_accept_all(self):
        n = 0
        used = {r["file"] for r in self.rows.values() if r["status"] in CONFIRMED}
        for c in self.companies:
            r = self.rows[c]
            if r["status"] == "suggest" and r["suggest"] and r["suggest"] not in used and r.get("score", 0) >= 75:
                used.add(r["suggest"])
                self._set_confirmed(c, r["suggest"], r["reason"] + " · подтверждено")
                n += 1
        self._refresh_table()
        self._save_state()
        self._log("Подтверждено предложений: %d" % n if n else "Нет предложений для подтверждения", "success" if n else "muted")

    def on_pick_selected(self):
        if self.working:
            return
        company = self._selected_company()
        if not company:
            self._log("Выберите строку в таблице", "warning")
            return
        folder = self.var_folder.get().strip()
        self._scan_folder()
        if not self.pdf_files:
            self._log("Сначала выберите папку с PDF", "danger")
            return
        owner = {r["file"]: c for c, r in self.rows.items() if r["status"] in CONFIRMED and r["file"]}
        ck = company_key(company)
        scored = sorted(self.pdf_files, key=lambda f: (-name_score(ck, tokens_of(os.path.splitext(f)[0]))[0], f.lower()))
        cur = self.rows[company]
        items = []
        for f in scored:
            lbl = ""
            if owner.get(f) == company:
                lbl = "   ← сейчас"
            elif f in owner:
                lbl = "   (занят: %s)" % owner[f]
            items.append((f, lbl))
        pre = cur["file"] or cur["suggest"] or (scored[0] if scored else "")
        dlg = PickDialog(self.root, company, folder, items, pre)
        self.root.wait_window(dlg)
        res = dlg.result
        if res is None:
            return
        if res == "":
            self.rows[company] = new_row("none", "", "файл не выбран")
            self._drop_link(company)
        else:
            other = owner.get(res)
            if other and other != company:
                if not messagebox.askyesno("Файл уже занят",
                                           "Файл «%s» сейчас назначен компании\n%s.\nПереназначить?" % (res, other),
                                           parent=self.root):
                    return
                self.rows[other] = new_row("none", "", "файл передан другой компании")
                self._drop_link(other)
            self._set_confirmed(company, res, "выбрано вручную")
        self._refresh_table()
        self._save_state()

    # ── шаг 3: Drive ──

    def _rclone_or_log(self):
        exe = find_rclone(self.cfg.get("rclone", ""))
        if not exe:
            self._set_drive_status(E("E101", "не найден rclone. Нажмите «Скачать rclone»."), "danger")
            self._log(E("E101", "не найден rclone. Нажмите «Скачать rclone» на шаге 3."), "danger")
        return exe

    def on_check_drive(self):
        exe = self._rclone_or_log()
        if not exe:
            return
        fid = drive_folder_id(self.var_drive.get())
        self._begin("Проверяю доступ к Drive…")
        self._set_drive_status("Проверяю…", "muted")
        threading.Thread(target=self._check_worker, args=(exe, fid), daemon=True).start()

    def _check_worker(self, exe, fid):
        try:
            ok, msg, fix = check_drive(self.procs, exe, fid)
            if self.cancel_event.is_set():
                self.emit("cancelled")
                return
            self.emit("drive_status", ("✓ " if ok else "✗ ") + msg, "success" if ok else "danger")
            if ok:
                self.emit("done", msg)
            else:
                self.emit("error", msg, self.procs.last_err)
        except Exception as e:
            self.emit("error", E("E401", "сбой при проверке Google Drive.", True), traceback.format_exc())

    def on_setup_drive(self):
        exe = self._rclone_or_log()
        if not exe:
            return
        self._begin("Настройка Drive…")
        threading.Thread(target=self._setup_worker, args=(exe, drive_folder_id(self.var_drive.get())),
                         daemon=True).start()

    def _setup_worker(self, exe, fid):
        try:
            code, out, err = self.procs.run([exe, "listremotes"], timeout=30)
            exists = (REMOTE + ":") in out.split()
            args = ([exe, "config", "reconnect", REMOTE + ":"] if exists else
                    [exe, "config", "create", REMOTE, "drive", "scope=drive"]
                    + (["client_id=" + self.cfg["drive_client_id"], "client_secret=" + self.cfg["drive_client_secret"]]
                       if self.cfg.get("drive_client_id") and self.cfg.get("drive_client_secret") else []))
            self.emit("log", "Открылось окно rclone и браузер — войдите в аккаунт Google и разрешите доступ. "
                             "Окно закроется само.", "info")
            p = subprocess.Popen(args, creationflags=CREATE_NEW_CONSOLE)
            while p.poll() is None:
                if self.cancel_event.is_set():
                    p.kill()
                    self.emit("cancelled")
                    return
                time.sleep(0.4)
            ok, msg, fix = check_drive(self.procs, exe, fid)
            self.emit("drive_status", ("✓ " if ok else "✗ ") + msg, "success" if ok else "danger")
            if ok:
                self.emit("done", msg)
            else:
                self.emit("error", msg, self.procs.last_err)
        except Exception as e:
            self.emit("error", E("E402", "не удалось настроить вход в Google Drive.", True), traceback.format_exc())

    def on_get_rclone(self):
        if os.path.isfile(os.path.join(BASE_DIR, "rclone.exe")):
            if not messagebox.askyesno("rclone уже есть", "rclone.exe уже лежит рядом. Скачать заново?",
                                       parent=self.root):
                return
        self._begin("Качаю rclone…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            self.emit("log", "Качаю rclone…", "info")
            path = download_rclone(BASE_DIR, lambda d, t: self.emit("bar", d, t or 1))
            self.emit("rclone_path", path)
            self.emit("done", "rclone готов: " + path)
        except Exception as e:
            self.emit("error", E("E403", "не удалось скачать rclone. Проверьте интернет или положите rclone.exe рядом с программой вручную.", True), traceback.format_exc())

    # ── шаг 3: загрузка ──

    def _build_jobs(self):
        folder = self.var_folder.get().strip()
        jobs, used = [], set()
        for c in self.companies:
            r = self.rows.get(c)
            if not r or r["status"] not in CONFIRMED or not r["file"]:
                continue
            src = os.path.join(folder, r["file"])
            if not os.path.isfile(src):
                continue
            base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", c).strip(" .")[:150] or "file"
            dest, k = base + ".pdf", 2
            while dest.lower() in used:
                dest = "%s (%d).pdf" % (base, k)
                k += 1
            used.add(dest.lower())
            jobs.append((c, src, dest))
        return jobs

    def on_upload(self):
        exe = self._rclone_or_log()
        if not exe:
            return
        fid = drive_folder_id(self.var_drive.get())
        if not fid:
            msg = E("E404", "в ссылке не найден ID папки. Откройте папку в Google Drive и скопируйте адрес из браузера.")
            self._set_drive_status(msg, "danger")
            self._log(msg, "danger")
            return
        jobs = self._build_jobs()
        if not jobs:
            self._log(E("E406", "нет подтверждённых PDF для загрузки. Проверьте статусы на шаге 2."), "danger")
            return
        skipped = len(self.companies) - len(jobs)
        delete_after = bool(self.var_delete.get())
        text = ("Загрузить на Google Drive %d PDF?\n\nКомпаний без подтверждённого файла: %d (они не загрузятся)."
                % (len(jobs), skipped))
        if delete_after:
            text += ("\n\nПосле проверки, что файл на Drive такого же размера, загруженные PDF будут "
                     "перемещены из папки в Корзину Windows (их можно восстановить).")
        if not messagebox.askyesno("Подтвердите загрузку", text, parent=self.root):
            return
        try:
            self.documents_panel.archive_jobs(jobs)
        except Exception:
            messagebox.showerror("Локальный архив", "Не удалось сохранить локальные копии выписок. Загрузка не запущена: проверьте свободное место и папку данных.", parent=self.root)
            return
        self._save_state()
        self._begin("Проверяю Drive…")
        threading.Thread(target=self._upload_worker, args=(exe, fid, jobs, self.excel_path if (self.excel_path and os.path.isfile(self.excel_path)) else "", delete_after),
                         daemon=True).start()

    def _upload_worker(self, exe, fid, jobs, excel_path, delete_after=False):
        try:
            ok, msg, fix = check_drive(self.procs, exe, fid)
            if self.cancel_event.is_set():
                self.emit("cancelled")
                return
            if not ok:
                self.emit("drive_status", "✗ " + msg, "danger")
                self.emit("error", msg, self.procs.last_err)
                return
            self.emit("drive_status", "✓ " + msg, "success")
            total = len(jobs)
            self.emit("log", "Загружаю %d PDF…" % total, "info")
            self.emit("bar", 0, total)
            done_names, errors = {}, []
            counter = {"n": 0}
            lock = threading.Lock()

            def one(job):
                company, src, dest = job
                if self.cancel_event.is_set():
                    return
                code, out, err = self.procs.run(
                    [exe, "copyto", src, remote_of(fid) + dest, "--retries", "3",
                     "--low-level-retries", "10", "--drive-chunk-size", "64M"])
                with lock:
                    counter["n"] += 1
                    n = counter["n"]
                if code == 0:
                    done_names[company] = dest
                elif not self.cancel_event.is_set():
                    errors.append((company, explain_rclone_error(err)[0]))
                    self.procs.last_err = (err or "").strip()[-600:]
                self.emit("bar", n, total)
                self.emit("status", "Загружено %d из %d" % (n, total))

            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(one, jobs))

            if self.cancel_event.is_set():
                self.emit("log", "Отменено: успело загрузиться %d из %d. Ссылки не записаны — "
                                 "запустите загрузку снова, готовые файлы пропустятся." % (len(done_names), total),
                          "warning")
                self.emit("cancelled")
                return
            for company, why in errors[:10]:
                self.emit("log", "  ✗ %s — %s" % (company, why), "danger")
            if not done_names:
                self.emit("error", E("E407", "ни один файл не загрузился. Причины — в строках выше.", True), self.procs.last_err)
                return

            self.emit("status", "Получаю ссылки…")
            code, out, err = self.procs.run([exe, "lsjson", remote_of(fid), "--files-only", "--no-modtime"], timeout=120)
            if code != 0:
                self.emit("error", explain_rclone_error(err)[0], err.strip()[-600:])
                return
            rows = json.loads(out.strip() or "[]")
            ids, dup = {}, set()
            for row in rows:
                if row["Name"] in ids:
                    dup.add(row["Name"])
                ids[row["Name"]] = row.get("ID", "")
            links = {}
            for company, dest in done_names.items():
                fid_file = ids.get(dest)
                if fid_file:
                    links[company] = (("https://drive.google.com/file/d/%s/view" % fid_file), dest)
            if dup & set(done_names.values()):
                self.emit("log", "В папке Drive есть файлы с одинаковыми именами — проверьте ссылки вручную.", "warning")
            self.emit("links", {c: {"link": v[0], "dest": v[1]} for c, v in links.items()})
            written = added = 0
            if excel_path:
                try:
                    written, added = write_links_to_excel(excel_path, links)
                except PermissionError:
                    self.emit("error", E("E408", "файлы загружены и ссылки сохранены в таблице программы, но Excel открыт в другой "
                                       "программе. Закройте его и нажмите «Загрузить» ещё раз (повторно файлы не грузятся)."))
                    return
            msg = "Готово: загружено %d, ссылок в таблице программы %d" % (len(done_names), len(links))
            if excel_path:
                msg += ", в Excel %d" % written
            if added:
                msg += " (новых строк в Excel: %d)" % added
            if errors:
                msg += ", с ошибкой: %d" % len(errors)
            if delete_after:
                sizes = {r["Name"]: r.get("Size") for r in rows}
                removed, kept = [], []
                for company, src, dest in jobs:
                    if company not in links or dest in dup:
                        continue
                    try:
                        same = sizes.get(dest) == os.path.getsize(src)
                    except OSError:
                        continue                      # файла уже нет
                    if same and recycle_file(src):
                        removed.append(company)
                    else:
                        kept.append(os.path.basename(src))
                self.emit("deleted", removed)
                msg += ", убрано из папки: %d" % len(removed)
                if kept:
                    self.emit("log", E("E410", "не удалось убрать из папки %d PDF (размер на Drive не совпал или файл занят). "
                                       "Они остались на месте: %s." % (len(kept), ", ".join(kept[:3]))), "warning")
            self.emit("done", msg)
        except Exception as e:
            self.emit("error", E("E409", "сбой при загрузке на Google Drive.", True), traceback.format_exc())

    # ── отмена / выход ──

    def on_cancel(self):
        if self.working:
            self.procs.cancel()
            self.lbl_status.configure(text="Отменяю…")

    def on_close(self):
        if self.stock_panel.busy:
            if not messagebox.askyesno("Склад обрабатывает документы", "Импорт или распознавание ещё идёт. Закрытие прервёт обработку. Уже сохранённые комплекты останутся. Выйти?", parent=self.root):
                return
        if any(not job.finished for job in self.ads_panel.engine.JOBS.values()):
            if not messagebox.askyesno("Идёт генерация", "Генерация рекламы ещё идёт. Закрытие прервёт её. Выйти?", parent=self.root):
                return
        if self.working:
            if not messagebox.askyesno("Идёт операция", "Прервать операцию и выйти?", parent=self.root):
                return
            self.procs.cancel()
        self._save_state()
        self.profile_panel.persist()
        self.profile_panel.clear_clipboard()
        self.root.destroy()


if __name__ == "__main__":
    App().root.mainloop()
