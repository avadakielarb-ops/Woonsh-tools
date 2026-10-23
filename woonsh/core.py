"""
WoonSh ToolS — ядро: конфиг, хранилище (Excel + Google Sheets), ротация ключей.

Всё, что общее для пяти модулей, живёт здесь. Модули берут отсюда config, Store и
Gemini — им не надо знать, куда именно уходят данные (в таблицу или в Excel) и
какой ключ сейчас живой.
"""

import os
import json
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


# ─────────────────────────── КОНФИГ ───────────────────────────

def load_config():
    """Читает config.json. Нет файла — берём config.example.json как основу."""
    path = CONFIG_PATH
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "config.example.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _col_to_index(letter):
    """A→1, B→2, E→5, I→9 (1-based, как в Excel/Sheets)."""
    n = 0
    for ch in letter.strip().upper():
        n = n * 26 + (ord(ch) - 64)
    return n


# ─────────────────────────── ХРАНИЛИЩЕ ───────────────────────────
# Один лист, деление по колонкам. Каждый модуль пишет в СВОЙ блок колонок, с первой
# пустой строки НЕЗАВИСИМО от других модулей: строки Drop-X и ID Phantom не связаны.
# Пишем в Google-таблицу, если задан sheet_id + сервис-аккаунт; иначе — в Excel.
# Так «автосейв в Excel, если таблицы нет» получается сам собой, без отдельной ветки.

class Store:
    def __init__(self, cfg):
        self.cfg = cfg
        self.columns = cfg.get("columns", {})
        self._lock = threading.Lock()
        self._ws = None          # лист gspread, если получилось подключиться
        self._connect_sheets()

    # — Google Sheets —
    def _connect_sheets(self):
        t = self.cfg.get("table", {})
        sid, creds = t.get("sheet_id", ""), t.get("google_creds_path", "")
        if not sid or not creds or not os.path.exists(creds):
            return
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            gc = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
            sh = gc.open_by_key(sid)
            name = t.get("sheet_name", "WoonSh")
            try:
                self._ws = sh.worksheet(name)
            except Exception:
                self._ws = sh.add_worksheet(title=name, rows=1000, cols=26)
        except Exception as e:
            print(f"[store] Google Sheets недоступны, пишу в Excel: {e}")
            self._ws = None

    def target(self):
        return "Google-таблица" if self._ws else "Excel (" + self.cfg["table"].get("excel_path", "WoonSh_Backup.xlsx") + ")"

    def append(self, module, values):
        """Дописывает одну строку в блок колонок модуля. values — список значений
        по порядку колонок (headers). Возвращает номер строки, куда записали."""
        block = self.columns.get(module)
        if not block:
            raise ValueError(f"нет блока колонок для модуля '{module}'")
        start = _col_to_index(block["start_col"])
        headers = block["headers"]
        vals = (list(values) + [""] * len(headers))[:len(headers)]
        with self._lock:
            return self._ws_append(start, headers, vals) if self._ws else self._excel_append(start, headers, vals)

    # — запись в Sheets —
    def _ws_append(self, start, headers, vals):
        first_col = self._ws.col_values(start)          # значения первой колонки блока
        # шапка
        if len(first_col) == 0:
            self._ws.update_cell(1, start, headers[0])
            for i, h in enumerate(headers):
                self._ws.update_cell(1, start + i, h)
            first_col = [headers[0]]
        row = len(first_col) + 1
        end_col = start + len(headers) - 1
        rng = f"{_a1(start)}{row}:{_a1(end_col)}{row}"
        self._ws.update(rng, [vals], value_input_option="USER_ENTERED")
        return row

    # — запись в Excel —
    def _excel_append(self, start, headers, vals):
        from openpyxl import load_workbook, Workbook
        path = os.path.join(BASE_DIR, self.cfg["table"].get("excel_path", "WoonSh_Backup.xlsx"))
        name = self.cfg["table"].get("sheet_name", "WoonSh")
        if os.path.exists(path):
            wb = load_workbook(path)
            ws = wb[name] if name in wb.sheetnames else wb.create_sheet(name)
        else:
            wb = Workbook(); ws = wb.active; ws.title = name
        # шапка блока
        if ws.cell(row=1, column=start).value in (None, ""):
            for i, h in enumerate(headers):
                ws.cell(row=1, column=start + i, value=h)
        # первая пустая строка В ЭТОМ блоке (по первой колонке блока)
        row = 2
        while ws.cell(row=row, column=start).value not in (None, ""):
            row += 1
        for i, v in enumerate(vals):
            ws.cell(row=row, column=start + i, value=v)
        wb.save(path)
        return row


def _a1(col_index):
    """1→A, 5→E, 9→I."""
    s = ""
    n = col_index
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ─────────────────────────── GEMINI (ротация ключей) ───────────────────────────
# Один ключ уперся в лимит (429) — молча берём следующий. Кончились ключи на этой
# модели — пробуем следующую модель. Так же, как в боте: лимит не должен ронять работу.

class Gemini:
    def __init__(self, cfg):
        self.keys = [k for k in cfg.get("gemini", {}).get("keys", []) if k]
        self.models = cfg.get("gemini", {}).get("models", ["gemini-2.5-flash"])

    def available(self):
        return bool(self.keys)

    def ask(self, parts, system=None, max_tokens=900):
        """parts — список (str и/или PIL.Image). Возвращает текст ответа или кидает."""
        import google.generativeai as genai
        last = "нет ключей Gemini"
        for model_name in self.models:
            for key in self.keys:
                try:
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel(model_name, system_instruction=system) if system \
                        else genai.GenerativeModel(model_name)
                    r = model.generate_content(parts, generation_config={"max_output_tokens": max_tokens})
                    return (r.text or "").strip()
                except Exception as e:
                    last = f"{model_name}/{key[:6]}…: {e}"
                    # 429 / quota — молча к следующему ключу; иначе тоже пробуем дальше
                    continue
        raise RuntimeError(last)
