"""
Загрузчик выписок на Google Drive.

1. Вставляешь платёжные профили → парсер достаёт названия компаний → Excel (колонка A).
2. Выбираешь папку с PDF-выписками → если имя файла совпадает с компанией — ок,
   если нет — открывает PDF, ищет название внутри, переименовывает.
3. Вставляешь ссылку на папку Drive → загружает через rclone → собирает ссылки →
   колонка B в тот же Excel.

Зависимости: tkinter (стандарт), openpyxl (pip install openpyxl), pypdf (pip install pypdf).
Снаружи: rclone.exe (рядом или в PATH).
"""

import os, sys, re, json, shutil, subprocess, threading, queue, io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

BASE_DIR = os.path.dirname(os.path.abspath(
    sys.argv[0] if getattr(sys, "frozen", False) else __file__))

RCLONE_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
REMOTE = "gdrive"
CREATE_NO_WINDOW = 0x08000000

SUFFIXES = re.compile(
    r"\b(LIMITED|LTD\.?|PLC|INC\.?|CORP\.?|LLC|LLP|CO\.?|COMPANY|GROUP|HOLDINGS?|"
    r"SERVICES?|SOLUTIONS?|ENTERPRISES?|PARTNERS?|ASSOCIATES?|"
    r"CONSULTANTS?|INVESTMENTS?|PROPERTIES|ESTATES?|MANAGEMENT|DEVELOPMENTS?|"
    r"CONSTRUCTION|TRADING|PROJECTS?|TEO)\b",
    re.IGNORECASE)

JUNK = re.compile(r"[^a-z0-9 ]")

CONFIG_FILE = os.path.join(BASE_DIR, "x-file_config.json")


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

_CHECK_IMAGES = []
_TICK = [(4, 8), (5, 9), (6, 10), (7, 11),
         (8, 10), (9, 9), (10, 8), (11, 7), (12, 6)]


def _install_check_images(style, t):
    size, gap = 16, 6
    off = tk.PhotoImage(width=size + gap, height=size)
    on = tk.PhotoImage(width=size + gap, height=size)
    for x in range(size + gap):
        for y in range(size):
            if x >= size:
                off.put(t["bg"], to=(x, y))
                on.put(t["bg"], to=(x, y))
                continue
            edge = x in (0, size - 1) or y in (0, size - 1)
            off.put(t["line"] if edge else t["field"], to=(x, y))
            on.put(AURORA[0], to=(x, y))
    for x, y in _TICK:
        on.put("#ffffff", to=(x, y))
        on.put("#ffffff", to=(x, y - 1))
    _CHECK_IMAGES.extend((off, on))
    try:
        style.element_create("Aurora.indicator", "image", on,
                             ("!selected", off), sticky="", border=0)
    except tk.TclError:
        return
    style.layout("TCheckbutton", [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Aurora.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                ("Checkbutton.label", {"sticky": "nswe"})]})]})])


def apply_theme(root, t):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=t["bg"])

    style.configure(".", background=t["bg"], foreground=t["ink"],
                    fieldbackground=t["field"], bordercolor=t["line"],
                    lightcolor=t["line"], darkcolor=t["line"],
                    troughcolor=t["surface"], focuscolor=AURORA[0])
    for widget in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton",
                   "TSeparator", "TLabelframe", "TLabelframe.Label"):
        style.configure(widget, background=t["bg"])
    style.configure("TLabel", foreground=t["ink"])
    style.configure("Muted.TLabel", foreground=t["muted"])
    style.configure("Success.TLabel", foreground=SEMANTIC["success"])
    style.configure("Danger.TLabel", foreground=SEMANTIC["danger"])
    style.configure("Warning.TLabel", foreground=SEMANTIC["warning"])
    style.configure("TSeparator", background=t["line"])
    style.configure("TCheckbutton", foreground=t["ink"], padding=(0, 2))
    style.map("TCheckbutton", background=[("active", t["bg"])])

    style.configure("TButton", background=t["surface2"], foreground=t["ink"],
                    bordercolor=t["line"], relief="flat", padding=(10, 4))
    style.map("TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[0]),
                          ("disabled", t["surface"])],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff"),
                          ("disabled", t["muted"])],
              bordercolor=[("active", AURORA[0])])

    style.configure("Accent.TButton", background=AURORA[0], foreground="#ffffff",
                    bordercolor=AURORA[0], relief="flat", padding=(14, 6))
    style.map("Accent.TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[2]),
                          ("disabled", t["surface"])],
              foreground=[("disabled", t["muted"])])

    style.configure("TEntry", fieldbackground=t["field"], foreground=t["field_ink"],
                    insertcolor=t["field_ink"], bordercolor=t["line"], padding=4)
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

    _install_check_images(style, t)
    return style


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
    except Exception:
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
    menu.add_command(label="Вырезать",
                     command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать",
                     command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить",
                     command=lambda: widget.event_generate("<<Paste>>"))
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


def rclone_ask(exe, args):
    proc = subprocess.run([exe] + args, stdin=subprocess.DEVNULL,
                          capture_output=True, creationflags=CREATE_NO_WINDOW,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or ""), (proc.stderr or "")


def rclone_lsjson(exe, folder_id):
    code, out, err = rclone_ask(exe, ["lsjson", remote_of(folder_id),
                                       "--files-only", "--no-modtime"])
    if code != 0:
        raise RuntimeError("rclone lsjson: " + err.strip()[-300:])
    rows = json.loads(out.strip() or "[]")
    return {row["Name"]: row.get("ID", "") for row in rows}


def rclone_upload_file(exe, filepath, folder_id):
    folder = os.path.dirname(filepath)
    name = os.path.basename(filepath)
    cmd = [exe, "copy", "--include", name, folder, remote_of(folder_id),
           "--retries", "3", "--low-level-retries", "10", "--transfers", "1"]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                          creationflags=CREATE_NO_WINDOW,
                          encoding="utf-8", errors="replace")
    return proc.returncode == 0


def rclone_upload_folder(exe, folder, folder_id, on_progress=None, stop=None):
    cmd = [exe, "copy", folder, remote_of(folder_id),
           "--stats", "1s", "--stats-one-line", "--stats-log-level", "NOTICE",
           "--retries", "3", "--low-level-retries", "10",
           "--transfers", "10", "--checkers", "16",
           "--drive-chunk-size", "64M", "--drive-upload-cutoff", "64M"]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=CREATE_NO_WINDOW,
                            encoding="utf-8", errors="replace")
    lines = []
    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                lines.append(line)
                if on_progress:
                    on_progress(line)
            if stop and stop():
                proc.kill()
                break
    except Exception:
        pass
    proc.wait()
    return proc.returncode, lines


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
        inside = next((n for n in zf.namelist()
                       if n.lower().endswith("rclone.exe")), "")
        if not inside:
            raise RuntimeError("в архиве rclone.exe не нашёлся")
        dest = os.path.join(dest_dir, "rclone.exe")
        with zf.open(inside) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return dest


# ══ ПАРСЕР ПРОФИЛЕЙ ══════════════════════════════════════════════════════════

def parse_profiles(text):
    names = []
    seen = set()
    company_suffix = re.compile(
        r"\b(?:GMBH|KG|AG|UG|LIMITED|LTD|PLC|INC|CORP|LLC|LLP)\b",
        re.IGNORECASE)
    for line in text.splitlines():
        line = line.strip().strip('"').strip()
        if not line or line.lower().startswith(("http://", "https://")):
            continue
        upper = sum(1 for c in line if c.isupper())
        lower = sum(1 for c in line if c.islower())
        if company_suffix.search(line) or (
                not re.match(r"^\d", line) and upper > lower and len(line) > 5):
            key = line.casefold()
            if key not in seen:
                seen.add(key)
                names.append(line)
    return names


# ══ СОПОСТАВЛЕНИЕ ФАЙЛОВ И КОМПАНИЙ ══════════════════════════════════════════

def normalize(name):
    s = SUFFIXES.sub("", name)
    s = JUNK.sub(" ", s.lower())
    return " ".join(s.split())


def match_score(a, b):
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 100
    wa, wb = na.split(), nb.split()
    sa, sb = set(wa), set(wb)
    if not sa or not sb:
        return 0
    common = sa & sb
    if not common:
        return 0
    ratio = len(common) / max(len(sa), len(sb))
    len_diff = abs(len(sa) - len(sb))
    return int(90 * ratio - len_diff * 5)


def best_match(filename, companies, threshold=40):
    stem = os.path.splitext(filename)[0]
    best, score = None, 0
    for c in companies:
        s = match_score(stem, c)
        if s > score:
            score, best = s, c
    return (best, score) if score >= threshold else (None, 0)


def pdf_text_first_page(filepath):
    if not PdfReader:
        return ""
    try:
        reader = PdfReader(filepath)
        if reader.pages:
            return reader.pages[0].extract_text() or ""
    except Exception:
        pass
    return ""


def match_from_pdf(filepath, companies, threshold=40):
    text = pdf_text_first_page(filepath)
    if not text:
        return None, 0
    best, score = None, 0
    for c in companies:
        s = match_score(text, c)
        nc = normalize(c)
        if nc and nc in normalize(text):
            s = max(s, 85)
        if s > score:
            score, best = s, c
    return (best, score) if score >= threshold else (None, 0)


# ══ EXCEL ════════════════════════════════════════════════════════════════════

def create_excel(path, companies):
    if not openpyxl:
        raise RuntimeError("openpyxl не установлен: pip install openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Выписки"
    ws["A1"] = "Компания"
    ws["B1"] = "Ссылка на выписку"
    ws["A1"].font = openpyxl.styles.Font(bold=True)
    ws["B1"].font = openpyxl.styles.Font(bold=True)
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 70
    for i, name in enumerate(companies, start=2):
        ws.cell(row=i, column=1, value=name)
    wb.save(path)
    return path


def write_links_to_excel(path, mapping):
    if not openpyxl:
        raise RuntimeError("openpyxl не установлен")
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    name_to_row = {}
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=1).value
        if val:
            name_to_row[normalize(val)] = row
    written = 0
    for company, link in mapping.items():
        nc = normalize(company)
        r = name_to_row.get(nc)
        if r:
            ws.cell(row=r, column=2, value=link)
            written += 1
    wb.save(path)
    return written


# ══ КОНФИГ ═══════════════════════════════════════════════════════════════════

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ══ ПРИЛОЖЕНИЕ ═══════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Загрузчик выписок")
        self.root.geometry("820x700")
        self.root.minsize(600, 500)

        self.cfg = load_config()
        self.style = apply_theme(self.root, THEME)
        self.q = queue.Queue()
        self.stop_flag = False
        self.companies = []
        self.file_map = {}  # company -> filename
        self.excel_path = ""
        self.working = False

        self._build_ui()
        self._check_deps()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll)

    def _poll(self):
        while not self.q.empty():
            try:
                kind, *args = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(*args)
            elif kind == "status":
                self.lbl_status.configure(text=args[0])
            elif kind == "bar":
                self.bar["value"] = args[0]
                self.bar["maximum"] = args[1]
            elif kind == "done":
                self._log(args[0] if args else "Готово", "success")
                self._set_working(False)
            elif kind == "error":
                self._log(args[0], "danger")
                self._set_working(False)
            elif kind == "companies":
                self.companies = args[0]
                self._log("Компаний: %d" % len(self.companies), "success")
            elif kind == "file_map":
                self.file_map = args[0]
            elif kind == "excel_done":
                self.excel_path = args[0]
                self._log("Excel: " + args[0], "success")
                self.btn_open_excel.pack(side="right", padx=(6, 0))
        self.root.after(100, self._poll)

    def emit(self, *args):
        self.q.put(args)

    def _build_ui(self):
        t = THEME
        pad = {"padx": 12, "pady": (4, 0)}
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # ── 1. Профили ──
        ttk.Label(main, text="1. Платёжные профили", font=("Segoe UI", 11, "bold")
                  ).pack(anchor="w", **pad)
        ttk.Label(main, text="Вставь текст с профилями — вытащу названия компаний",
                  style="Muted.TLabel").pack(anchor="w", padx=12)

        tf = ttk.Frame(main)
        tf.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        self.txt_profiles = tk.Text(tf, height=8, wrap="word",
                                    bg=t["field"], fg=t["field_ink"],
                                    insertbackground=t["field_ink"],
                                    selectbackground=AURORA[0],
                                    relief="flat", font=("Consolas", 9))
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.txt_profiles.yview)
        self.txt_profiles.configure(yscrollcommand=sb.set)
        self.txt_profiles.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        enable_clipboard(self.txt_profiles)

        bf = ttk.Frame(main)
        bf.pack(fill="x", padx=12, pady=(6, 0))
        ttk.Button(bf, text="Распознать и создать Excel",
                   command=self.on_parse).pack(side="left")
        self.lbl_companies = ttk.Label(bf, text="", style="Muted.TLabel")
        self.lbl_companies.pack(side="left", padx=(12, 0))

        ttk.Separator(main).pack(fill="x", padx=12, pady=(12, 4))

        # ── 2. Папка с выписками ──
        ttk.Label(main, text="2. Папка с выписками", font=("Segoe UI", 11, "bold")
                  ).pack(anchor="w", **pad)

        ff = ttk.Frame(main)
        ff.pack(fill="x", padx=12, pady=(4, 0))
        self.var_folder = tk.StringVar(value=self.cfg.get("last_folder", ""))
        ttk.Entry(ff, textvariable=self.var_folder).pack(side="left", fill="x", expand=True)
        ttk.Button(ff, text="Обзор…", width=10, command=self.on_browse).pack(side="left", padx=(6, 0))

        bf2 = ttk.Frame(main)
        bf2.pack(fill="x", padx=12, pady=(6, 0))
        ttk.Button(bf2, text="Сопоставить файлы",
                   command=self.on_match).pack(side="left")
        self.lbl_matched = ttk.Label(bf2, text="", style="Muted.TLabel")
        self.lbl_matched.pack(side="left", padx=(12, 0))

        ttk.Separator(main).pack(fill="x", padx=12, pady=(12, 4))

        # ── 3. Google Drive ──
        ttk.Label(main, text="3. Google Drive", font=("Segoe UI", 11, "bold")
                  ).pack(anchor="w", **pad)

        df = ttk.Frame(main)
        df.pack(fill="x", padx=12, pady=(4, 0))
        ttk.Label(df, text="Ссылка на папку:").pack(side="left")
        self.var_drive = tk.StringVar(value=self.cfg.get("last_drive", ""))
        e_drive = ttk.Entry(df, textvariable=self.var_drive)
        e_drive.pack(side="left", fill="x", expand=True, padx=(6, 0))
        enable_clipboard(e_drive)

        bf3 = ttk.Frame(main)
        bf3.pack(fill="x", padx=12, pady=(6, 0))
        ttk.Button(bf3, text="Загрузить и заполнить Excel",
                   style="Accent.TButton",
                   command=self.on_upload).pack(side="left")

        # ── rclone ──
        rf = ttk.Frame(main)
        rf.pack(fill="x", padx=12, pady=(8, 0))
        self.lbl_rclone = ttk.Label(rf, text="", style="Muted.TLabel")
        self.lbl_rclone.pack(side="left")
        self.b_get_rclone = ttk.Button(rf, text="Скачать rclone", width=16,
                                       command=self.on_get_rclone)
        self.b_get_rclone.pack(side="left", padx=(8, 0))

        ttk.Separator(main).pack(fill="x", padx=12, pady=(12, 4))

        # ── Лог ──
        lf = ttk.Frame(main)
        lf.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.log = tk.Text(lf, height=6, wrap="word", state="disabled",
                           bg=t["surface"], fg=t["ink"],
                           insertbackground=t["field_ink"],
                           selectbackground=AURORA[0],
                           relief="flat", font=("Consolas", 9))
        sb2 = ttk.Scrollbar(lf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb2.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

        for tag, color in SEMANTIC.items():
            self.log.tag_configure(tag, foreground=color)
        self.log.tag_configure("muted", foreground=t["muted"])

        # ── Статус + прогресс + Открыть Excel ──
        sf = ttk.Frame(main)
        sf.pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_status = ttk.Label(sf, text="", style="Muted.TLabel")
        self.lbl_status.pack(side="left")
        self.btn_open_excel = ttk.Button(sf, text="Открыть Excel",
                                         command=self.on_open_excel)
        self.bar = ttk.Progressbar(sf, length=200, mode="determinate",
                                   style="Aurora.Horizontal.TProgressbar")
        self.bar.pack(side="right")

    def _log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_working(self, v):
        self.working = v
        state = "disabled" if v else "normal"
        for w in self.root.winfo_children():
            try:
                for c in w.winfo_children():
                    if isinstance(c, (ttk.Button,)):
                        c.configure(state=state)
            except Exception:
                pass

    def _check_deps(self):
        ok = True
        if not PdfReader:
            self._log("pypdf не найден — чтение PDF недоступно. pip install pypdf", "warning")
            ok = False
        if not openpyxl:
            self._log("openpyxl не найден — Excel недоступен. pip install openpyxl", "danger")
            ok = False
        exe = find_rclone(self.cfg.get("rclone", ""))
        if exe:
            self.cfg["rclone"] = exe
            self.lbl_rclone.configure(text="rclone: " + exe)
        else:
            self.lbl_rclone.configure(text="rclone не найден")
            self._log("rclone не найден — скачай кнопкой или положи rclone.exe рядом", "warning")
        return ok

    # ── Действия ──

    def on_open_excel(self):
        if self.excel_path and os.path.isfile(self.excel_path):
            os.startfile(self.excel_path)

    def on_parse(self):
        text = self.txt_profiles.get("1.0", "end")
        names = parse_profiles(text)
        if not names:
            self._log("Не нашёл названий компаний в тексте", "danger")
            return
        self.companies = names
        self.lbl_companies.configure(text="Найдено: %d" % len(names))
        self._log("Компании (%d):" % len(names), "info")
        for n in names:
            self._log("  • " + n, "muted")

        path = filedialog.asksaveasfilename(
            title="Сохранить Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialdir=self.cfg.get("last_excel_dir", BASE_DIR),
            initialfile="выписки_%s.xlsx" % __import__("datetime").date.today().strftime("%d-%m-%Y"))
        if not path:
            return
        self.cfg["last_excel_dir"] = os.path.dirname(path)
        save_config(self.cfg)
        try:
            create_excel(path, names)
            self.excel_path = path
            self._log("Excel создан: " + path, "success")
        except Exception as e:
            self._log("Ошибка Excel: " + str(e), "danger")

    def on_browse(self):
        d = filedialog.askdirectory(
            title="Папка с выписками",
            initialdir=self.var_folder.get() or BASE_DIR)
        if d:
            self.var_folder.set(d)
            self.cfg["last_folder"] = d
            save_config(self.cfg)

    def on_match(self):
        folder = self.var_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log("Выбери папку с выписками", "danger")
            return
        if not self.companies:
            self._log("Сначала распознай профили (шаг 1)", "danger")
            return
        self._set_working(True)
        threading.Thread(target=self._match_worker, args=(folder,), daemon=True).start()

    def _match_worker(self, folder):
        try:
            files = [f for f in os.listdir(folder)
                     if os.path.isfile(os.path.join(folder, f))
                     and f.lower().endswith(".pdf")]
            if not files:
                self.emit("error", "В папке нет PDF файлов")
                return
            self.emit("log", "PDF файлов: %d" % len(files), "info")
            self.emit("bar", 0, len(files))

            matched = {}
            unmatched = []
            used = set()
            renamed = 0

            for i, f in enumerate(files):
                self.emit("status", "Сопоставляю: %s" % f)
                self.emit("bar", i + 1, len(files))
                fp = os.path.join(folder, f)

                company, score = best_match(f, self.companies)
                source = "имя файла"

                if not company and PdfReader:
                    company, score = match_from_pdf(fp, self.companies)
                    source = "текст PDF"

                if company and company not in used:
                    used.add(company)
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', company) + ".pdf"
                    if safe_name != f:
                        new_path = os.path.join(folder, safe_name)
                        if not os.path.exists(new_path):
                            os.rename(fp, new_path)
                            self.emit("log", "  ✓ %s → %s (%s, %d%%)" %
                                      (f, safe_name, source, score), "success")
                            renamed += 1
                        else:
                            self.emit("log", "  ⚠ %s → %s уже есть" % (f, safe_name), "warning")
                            safe_name = f
                    else:
                        self.emit("log", "  ✓ %s (%s, %d%%)" % (f, source, score), "success")
                    matched[company] = safe_name
                elif company and company in used:
                    self.emit("log", "  ⚠ %s → %s уже занят" % (f, company), "warning")
                    unmatched.append(f)
                else:
                    self.emit("log", "  ✗ %s — не опознан" % f, "danger")
                    unmatched.append(f)

            self.emit("file_map", matched)
            self.emit("status", "")
            self.lbl_matched.configure(
                text="Совпало: %d из %d, переименовано: %d" % (len(matched), len(files), renamed))

            if unmatched:
                self.emit("log", "\nНе опознаны (%d):" % len(unmatched), "warning")
                for f in unmatched:
                    self.emit("log", "  • " + f, "muted")
            self.emit("done", "Сопоставление завершено")
        except Exception as e:
            self.emit("error", "Ошибка: " + str(e))

    def on_upload(self):
        exe = find_rclone(self.cfg.get("rclone", ""))
        if not exe:
            self._log("rclone не найден — скачай кнопкой", "danger")
            return
        folder = self.var_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log("Выбери папку с выписками", "danger")
            return
        drive_url = self.var_drive.get().strip()
        fid = drive_folder_id(drive_url)
        if not fid:
            self._log("Не могу достать ID папки из ссылки", "danger")
            return
        if not self.excel_path or not os.path.isfile(self.excel_path):
            self._log("Сначала создай Excel (шаг 1)", "danger")
            return
        if not self.companies:
            self._log("Сначала распознай профили", "danger")
            return

        self.cfg["last_drive"] = drive_url
        save_config(self.cfg)

        self._set_working(True)
        threading.Thread(target=self._upload_worker,
                         args=(exe, folder, fid), daemon=True).start()

    def _upload_worker(self, exe, folder, fid):
        try:
            self.emit("log", "Загружаю папку на Drive…", "info")
            self.emit("status", "Загрузка…")

            def on_line(line):
                pct = re.search(r"(\d+)%", line)
                if pct:
                    self.emit("bar", int(pct.group(1)), 100)
                    self.emit("status", "Загрузка… %s%%" % pct.group(1))

            code, lines = rclone_upload_folder(exe, folder, fid, on_progress=on_line)
            if code != 0:
                self.emit("error", "rclone завершился с ошибкой. Последние строки:\n" +
                          "\n".join(lines[-5:]))
                return
            self.emit("log", "Загрузка завершена", "success")

            self.emit("status", "Получаю ссылки…")
            name_to_id = rclone_lsjson(exe, fid)
            self.emit("log", "Файлов на Drive: %d" % len(name_to_id), "info")

            mapping = {}
            filled = 0
            for company in self.companies:
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', company) + ".pdf"
                fid_file = name_to_id.get(safe_name, "")
                if fid_file:
                    link = "https://drive.google.com/file/d/%s/view" % fid_file
                    mapping[company] = link
                    filled += 1

            not_matched = [c for c in self.companies if c not in mapping]
            if not_matched:
                stems = {normalize(os.path.splitext(n)[0]): n for n in name_to_id}
                for company in not_matched:
                    nc = normalize(company)
                    best_s, best_fname = 0, None
                    for sn, fname in stems.items():
                        s = match_score(nc, sn)
                        if s > best_s:
                            best_s, best_fname = s, fname
                    if best_s >= 40 and best_fname:
                        fid_file = name_to_id.get(best_fname, "")
                        if fid_file:
                            link = "https://drive.google.com/file/d/%s/view" % fid_file
                            mapping[company] = link
                            filled += 1

            if mapping:
                written = write_links_to_excel(self.excel_path, mapping)
                self.emit("log", "Записано ссылок в Excel: %d" % written, "success")
            else:
                self.emit("log", "Не удалось сопоставить ни одного файла со ссылкой", "warning")

            not_found = [c for c in self.companies if c not in mapping]
            if not_found:
                self.emit("log", "Без ссылки (%d):" % len(not_found), "warning")
                for c in not_found[:20]:
                    self.emit("log", "  • " + c, "muted")

            self.emit("status", "")
            self.emit("done", "Готово: %d из %d компаний со ссылками" %
                      (filled, len(self.companies)))
        except Exception as e:
            self.emit("error", "Ошибка: " + str(e))

    def on_get_rclone(self):
        if os.path.isfile(os.path.join(BASE_DIR, "rclone.exe")):
            if not messagebox.askyesno("rclone уже есть",
                                       "rclone.exe уже лежит рядом. Скачать заново?",
                                       parent=self.root):
                return
        self._set_working(True)
        threading.Thread(target=self._download_rclone, daemon=True).start()

    def _download_rclone(self):
        try:
            self.emit("log", "Качаю rclone…", "info")
            self.emit("status", "Качаю rclone…")

            def progress(done, total):
                self.emit("bar", done, total or 1)

            path = download_rclone(BASE_DIR, progress)
            self.cfg["rclone"] = path
            save_config(self.cfg)
            self.emit("log", "rclone скачан: " + path, "success")
            self.lbl_rclone.configure(text="rclone: " + path)
            self.emit("done", "rclone готов")
        except Exception as e:
            self.emit("error", "Не скачалось: " + str(e))

    def on_close(self):
        self.stop_flag = True
        save_config(self.cfg)
        self.root.destroy()


if __name__ == "__main__":
    app = App()
    app.root.mainloop()
