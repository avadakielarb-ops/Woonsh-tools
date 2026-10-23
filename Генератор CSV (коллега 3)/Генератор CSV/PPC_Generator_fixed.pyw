import csv
import ctypes
from datetime import datetime, timedelta
import json
import os
import random
import re
import time
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.error
import urllib.parse
import urllib.request

# ── ТВОЙ ПОСТОЯННЫЙ API-КЛЮЧ ────────────────────────────────────────────────
API_KEY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gemini_api_key.txt"
)
MY_FIXED_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not MY_FIXED_API_KEY and os.path.isfile(API_KEY_FILE):
  try:
    with open(API_KEY_FILE, "r", encoding="utf-8") as _key_file:
      MY_FIXED_API_KEY = _key_file.read().strip()
  except OSError:
    MY_FIXED_API_KEY = ""

# ── HIGH DPI ДЛЯ WINDOWS ──────────────────────────────────────────────────────
try:
  ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
  try:
    ctypes.windll.user32.SetProcessDPIAware()
  except Exception:
    pass

# --- Пути ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")
BRANDS_FILE = os.path.join(BASE_DIR, "brands.txt")
GEO_MAP = os.path.join(BASE_DIR, "geo_map.txt")
LANG_FILE = os.path.join(BASE_DIR, "languages.txt")
NEG_DIR = os.path.join(BASE_DIR, "Мінус-слова")
OUTPUT_BASE_DIR = os.path.join(BASE_DIR, "Готові РК")
YOUTUBE_OUTPUT_DIR = os.path.join(BASE_DIR, "Готові РК YouTube")
LOGOS_DB_FILE = os.path.join(BASE_DIR, "logos_db.json")
YT_SETTINGS_FILE = os.path.join(BASE_DIR, "yt_settings.json")

os.makedirs(NEG_DIR, exist_ok=True)
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
os.makedirs(YOUTUBE_OUTPUT_DIR, exist_ok=True)

memory_storage = {}
is_paused = False
is_running = False


# ── Работа с локальной базой Logo ID ─────────────────────────────────────────
def load_logos_db():
  if os.path.exists(LOGOS_DB_FILE):
    try:
      with open(LOGOS_DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def save_logo_to_db(ident, logo_id):
  if not logo_id or not ident:
    return
  db = load_logos_db()
  db[ident.strip()] = logo_id.strip()
  try:
    with open(LOGOS_DB_FILE, "w", encoding="utf-8") as f:
      json.dump(db, f, indent=4, ensure_ascii=False)
  except Exception:
    pass


# ── Работа с настройками YouTube ────────────────────────────────────────────
def load_yt_settings():
  defaults = {
      "budget": "0.01",
      "cpv": "0.05",
      "location": "Australia",
      "language": "All languages",
      "cta": "Learn more",
  }
  if os.path.exists(YT_SETTINGS_FILE):
    try:
      with open(YT_SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        defaults.update(data)
    except Exception:
      pass
  return defaults


def save_yt_settings(budget, cpv, location, language, cta):
  data = {
      "budget": budget,
      "cpv": cpv,
      "location": location,
      "language": language,
      "cta": cta,
  }
  try:
    with open(YT_SETTINGS_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=4, ensure_ascii=False)
  except Exception:
    pass


TLD_COUNTRY_LANG = {
    "fr": {"country": "France", "lang": "fr"},
    "de": {"country": "Germany", "lang": "de"},
    "at": {"country": "Austria", "lang": "de"},
    "ch": {"country": "Switzerland", "lang": "de;fr;it"},
    "it": {"country": "Italy", "lang": "it"},
    "es": {"country": "Spain", "lang": "es"},
    "pt": {"country": "Portugal", "lang": "pt"},
    "nl": {"country": "Netherlands", "lang": "nl"},
    "cz": {"country": "Czechia", "lang": "cs"},
    "sk": {"country": "Slovakia", "lang": "sk"},
    "pl": {"country": "Poland", "lang": "pl"},
    "ua": {"country": "Ukraine", "lang": "uk"},
    "uk": {"country": "United Kingdom", "lang": "en"},
    "us": {"country": "United States", "lang": "en"},
    "ca": {"country": "Canada", "lang": "en;fr"},
    "au": {"country": "Australia", "lang": "en"},
}

COUNTRIES_LIST = sorted(
    list(set(info["country"] for info in TLD_COUNTRY_LANG.values()))
)
LANGS_LIST = ["All languages"] + sorted(
    list(set(info["lang"] for info in TLD_COUNTRY_LANG.values()))
)

# ── Вспомогательные функции ───────────────────────────────────────────────────

TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
ANY_TAG_RE = re.compile(r"<[^>]+>")


def page_text(html, limit=15000):
  text = TAG_RE.sub(" ", html or "")
  text = ANY_TAG_RE.sub(" ", text)
  text = (
      text.replace("&nbsp;", " ")
      .replace("&amp;", "&")
      .replace("&quot;", '"')
      .replace("&#39;", "'")
  )
  return re.sub(r"\s+", " ", text).strip()[:limit]


def clean_url(raw_url):
  raw_url = (raw_url or "").strip()
  match = re.search(r"(https?://[^\s)\]]+)", raw_url)
  if match:
    return match.group(1)
  if raw_url.lower().startswith("www."):
    return "https://" + raw_url
  if "." in raw_url and " " not in raw_url and not raw_url.startswith("http"):
    return "https://" + raw_url
  return raw_url


def fetch_landing(url, timeout=10):
  url = clean_url(url)
  out = {"ok": False, "status": 0, "text": "", "error": ""}
  if not (url or "").startswith("http"):
    out["error"] = "посилання не починається з http"
    return out

  req = urllib.request.Request(
      url,
      headers={
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              " (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
          ),
          "Accept-Language": "en;q=0.9",
      },
  )
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read(300000)
      out["status"] = resp.status
    charset = "utf-8"
    head = raw[:2000].decode("latin-1", "ignore").lower()
    found = re.search(r"charset=[^A-Za-z0-9_-]*([A-Za-z0-9_-]+)", head)
    if found:
      charset = found.group(1)
    out["text"] = page_text(raw.decode(charset, "ignore"))
    out["ok"] = 200 <= out["status"] < 300 and len(out["text"]) > 30
  except Exception as e:
    out["error"] = str(e)
  return out


def parse_url_meta(url):
  url = clean_url(url)
  host = re.sub(r"^https?://", "", (url or "").strip().lower())
  host = host.split("/")[0].split("?")[0].split(":")[0].strip(".")
  parts = host.split(".")
  if len(parts) < 2:
    return "Australia", "en"
  tld = parts[-1]
  info = TLD_COUNTRY_LANG.get(tld, {"country": "Australia", "lang": "en"})
  return info["country"], info["lang"]


def load_geo_map():
  result = {}
  if os.path.exists(GEO_MAP):
    for line in open(GEO_MAP, encoding="utf-8"):
      line = line.strip()
      if "|" in line:
        city, loc = line.split("|", 1)
        result[city.strip()] = loc.strip()
  return result


def normalize_location(raw_location, url=""):
  raw_location = (raw_location or "").strip()
  address_keywords = [
      "impasse",
      "street",
      "st.",
      "avenue",
      "ave",
      "boulevard",
      "blvd",
      "route",
      "road",
      "rd.",
  ]
  is_detailed_address = any(
      kw in raw_location.lower() for kw in address_keywords
  ) or bool(re.search(r"\d{4,5}", raw_location))

  if is_detailed_address or "," in raw_location:
    parts = [p.strip() for p in raw_location.split(",")]
    if parts:
      auto_country, _ = parse_url_meta(url)
      if auto_country:
        return auto_country
      return parts[-1]

  if not raw_location or is_detailed_address:
    auto_country, _ = parse_url_meta(url)
    return auto_country

  return raw_location


def get_negative_files_list():
  files = ["Автоматично (за гео)"]
  if os.path.exists(NEG_DIR):
    for f_name in os.listdir(NEG_DIR):
      if f_name.endswith(".txt"):
        files.append(f_name)
  return files


def load_negatives(
    is_ua=True, selected_neg_file="Автоматично (за гео)", ai_negatives=None
):
  negatives = []
  if not os.path.exists(NEG_DIR):
    return [n.strip() for n in (ai_negatives or []) if n and n.strip()]

  if selected_neg_file and selected_neg_file != "Автоматично (за гео)":
    f_path = os.path.join(NEG_DIR, selected_neg_file)
    if os.path.exists(f_path):
      with open(f_path, "r", encoding="utf-8") as nf:
        negatives.extend([line.strip() for line in nf if line.strip()])
  else:
    if ai_negatives:
      negatives.extend([n.strip() for n in ai_negatives if n and n.strip()])

    for f_name in os.listdir(NEG_DIR):
      if not f_name.endswith(".txt"):
        continue
      f_lower = f_name.lower()
      is_world_file = (
          "world" in f_lower
          or "word" in f_lower
          or "eng" in f_lower
          or "ворд" in f_lower
      )
      if is_ua and is_world_file:
        continue
      if not is_ua and not is_world_file:
        continue
      with open(os.path.join(NEG_DIR, f_name), "r", encoding="utf-8") as nf:
        negatives.extend([line.strip() for line in nf if line.strip()])

  return list(set(negatives))


def call_gemini_api(api_key, prompt_text, model_name="gemini-3.5-flash-lite"):
  url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
  payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
  data = json.dumps(payload).encode("utf-8")
  req = urllib.request.Request(url, data=data, method="POST")
  req.add_header("x-goog-api-key", api_key)
  req.add_header("Content-Type", "application/json")

  try:
    with urllib.request.urlopen(req, timeout=90) as resp:
      res_data = json.loads(resp.read().decode("utf-8"))
      return res_data["candidates"][0]["content"]["parts"][0]["text"]
  except urllib.error.HTTPError as e:
    error_body = e.read().decode("utf-8", errors="ignore")
    raise Exception(f"HTTP Error {e.code}: {error_body}")
  except Exception as e:
    raise Exception(f"Connection Error: {str(e)}")


def validate_and_correct_response(
    api_key, original_prompt, raw_content, model_name
):
  if "[GROUP]" in raw_content and "[H]" in raw_content and "[K]" in raw_content:
    return raw_content

  correction_prompt = (
      "У попередній відповіді ти порушив структуру виводу і не додав мітки"
      " [GROUP], [H] або [K]. Перероби результат суворо за схемою з промпта,"
      " використовуючи обов'язкові мітки [GROUP], [H], [D], [K]. Ось початкове"
      f" завдання:\n\n{original_prompt}"
  )
  return call_gemini_api(api_key, correction_prompt, model_name)


def _write_editor_csv(file_path, headers, rows):
  os.makedirs(os.path.dirname(file_path), exist_ok=True)
  with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def _keyword_text_and_match(raw_keyword):
  value = (raw_keyword or "").strip()
  if len(value) >= 2 and value.startswith("[") and value.endswith("]"):
    return value[1:-1].strip(), "Exact"
  if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
    return value[1:-1].strip(), "Phrase"
  return value.strip('[]" '), "Broad"


def generate_and_save_csv(
    ident,
    url,
    product_val,
    geo_val,
    budget,
    cpc,
    raw_content,
    use_callouts,
    use_sitelinks,
    use_negatives,
    selected_neg_file,
):
  if not ident or not ident.strip():
    raise ValueError("Вкажи Ідентифікатор проекту/фірми!")
  if not raw_content or not raw_content.strip():
    raise ValueError("Вміст для генерації порожній!")

  url = clean_url(url)
  if not url.startswith(("http://", "https://")):
    raise ValueError("Final URL має починатися з http:// або https://")

  lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
  _, final_lang_code = parse_url_meta(url)
  geo_map = load_geo_map()
  resolved_geo = geo_map.get(geo_val, geo_val)
  location = normalize_location(resolved_geo, url)

  ua_cities = [
      "україна",
      "украина",
      "ukraine",
      "київ",
      "одеса",
      "львів",
      "харків",
      "дніпро",
      "запоріжжя",
  ]
  is_ua = any(city in (geo_val or "").lower() for city in ua_cities)

  ai_negatives_extracted = []
  groups, group_order, callouts, sitelinks = {}, [], [], []
  current_group = None

  for line in lines:
    if line.startswith("[GROUP]"):
      current_group = line[7:].strip()
      if current_group not in groups:
        groups[current_group] = {"h": [], "d": [], "k": []}
        group_order.append(current_group)
    elif line.startswith("[H]") and current_group:
      groups[current_group]["h"].append(line[3:].strip())
    elif line.startswith("[D]") and current_group:
      groups[current_group]["d"].append(line[3:].strip())
    elif line.startswith("[K]") and current_group:
      groups[current_group]["k"].append(line[3:].strip())
    elif line.startswith(("[NEG]", "[NEGATIVE]")):
      neg_val = line.split("]", 1)[-1].strip()
      if neg_val:
        ai_negatives_extracted.append(neg_val)
    elif line.startswith("[CALLOUT]") and use_callouts:
      value = line[len("[CALLOUT]") :].strip()
      if value:
        callouts.append(value)
    elif line.startswith("[SITELINK]") and use_sitelinks:
      parts = line[len("[SITELINK]") :].strip().split("|", 1)
      txt = parts[0].strip() if parts else ""
      sl_url = (
          clean_url(parts[1].strip())
          if len(parts) > 1 and parts[1].strip()
          else url
      )
      if txt:
        sitelinks.append((txt, sl_url))

  if not groups:
    raise ValueError(f"Для '{ident}' не знайдено міток [GROUP]!")

  def fix(value):
    value = value or ""
    return (
        value.replace("{product}", product_val or "")
        .replace("{geo}", location or "")
        .replace("{url}", url.rstrip("/"))
        .strip()
    )

  fixed_groups = {}
  fixed_order = []
  for group_name in group_order:
    fixed_name = fix(group_name)
    data = groups[group_name]
    fixed_groups[fixed_name] = {
        "h": [fix(x) for x in data["h"] if fix(x)],
        "d": [fix(x) for x in data["d"] if fix(x)],
        "k": [fix(x) for x in data["k"] if fix(x)],
    }
    fixed_order.append(fixed_name)
  groups = fixed_groups
  group_order = fixed_order
  callouts = list(dict.fromkeys(fix(x) for x in callouts if fix(x)))
  sitelinks = [(fix(t), clean_url(u)) for t, u in sitelinks if fix(t)]

  for g_name, data in groups.items():
    if len(data["h"]) < 3 or len(data["d"]) < 2:
      raise ValueError(
          f"Група '{g_name}': для адаптивного пошукового оголошення потрібно"
          " мінімум 3 заголовки [H] і 2 описи [D]."
      )
    too_long_h = [i + 1 for i, h in enumerate(data["h"][:15]) if len(h) > 30]
    too_long_d = [i + 1 for i, d in enumerate(data["d"][:4]) if len(d) > 90]
    if too_long_h or too_long_d:
      details = []
      if too_long_h:
        details.append(
            "заголовки понад 30 символів: " + ", ".join(map(str, too_long_h))
        )
      if too_long_d:
        details.append(
            "описи понад 90 символів: " + ", ".join(map(str, too_long_d))
        )
      raise ValueError(f"Група '{g_name}': " + "; ".join(details) + ".")

  negatives = (
      load_negatives(is_ua, selected_neg_file, ai_negatives_extracted)
      if use_negatives
      else []
  )
  personal_dir = os.path.join(OUTPUT_BASE_DIR, ident.strip())
  os.makedirs(personal_dir, exist_ok=True)
  camp_name = f"Search | {location} | {product_val}".strip()

  headers = [
      "Campaign",
      "Campaign type",
      "Campaign status",
      "Budget",
      "Budget period",
      "Bid strategy type",
      "Networks",
      "Location",
      "Language",
      "Ad group",
      "Ad group status",
      "Max CPC",
      "Keyword",
      "Type",
      "Status",
      "Final URL",
      *[f"Headline {i}" for i in range(1, 16)],
      *[f"Description {i}" for i in range(1, 5)],
      "Link text",
      "Callout text",
  ]
  rows = [{
      "Campaign": camp_name,
      "Campaign type": "Search",
      "Campaign status": "Paused",
      "Budget": budget,
      "Budget period": "Daily",
      "Bid strategy type": "Manual CPC",
      "Networks": "Google search",
      "Location": location,
      "Language": final_lang_code,
  }]

  for g_name in group_order:
    data = groups[g_name]
    rows.append({
        "Campaign": camp_name,
        "Ad group": g_name,
        "Ad group status": "Paused",
        "Max CPC": cpc,
    })
    for raw_kw in data["k"]:
      keyword, match_type = _keyword_text_and_match(raw_kw)
      if keyword:
        rows.append({
            "Campaign": camp_name,
            "Ad group": g_name,
            "Keyword": keyword,
            "Type": match_type,
            "Status": "Paused",
        })
    ad_row = {
        "Campaign": camp_name,
        "Ad group": g_name,
        "Final URL": url,
        "Status": "Paused",
    }
    for i, headline in enumerate(data["h"][:15], 1):
      ad_row[f"Headline {i}"] = headline
    for i, description in enumerate(data["d"][:4], 1):
      ad_row[f"Description {i}"] = description
    rows.append(ad_row)

  if use_negatives:
    for negative in negatives:
      if not (negative or "").strip():
        continue
      raw_neg = negative.strip()
      keyword, match_type = _keyword_text_and_match(raw_neg)
      if not keyword:
        continue
      formatted_keyword = (
          f"[{keyword}]"
          if match_type == "Exact"
          else f'"{keyword}"'
          if match_type == "Phrase"
          else keyword
      )
      rows.append({
          "Campaign": camp_name,
          "Keyword": formatted_keyword,
          "Type": "Campaign negative",
          "Status": "Enabled",
      })

  if use_sitelinks:
    for text, sitelink_url in sitelinks:
      if sitelink_url.startswith(("http://", "https://")):
        rows.append(
            {"Campaign": camp_name, "Link text": text, "Final URL": sitelink_url}
        )

  file_path = os.path.join(personal_dir, f"import_{ident.strip()}.csv")
  _write_editor_csv(file_path, headers, rows)

  if use_callouts and callouts:
    callout_path = os.path.join(personal_dir, f"callouts_{ident.strip()}.csv")
    _write_editor_csv(
        callout_path,
        ["Callout text"],
        [{"Callout text": text} for text in callouts[:20]],
    )

  return file_path


# ── ИНТЕРФЕЙС И ВКЛАДКИ ──────────────────────────────────────────────────────
root = tk.Tk()
root.title("PPC Generator Pro — Search + YouTube")
root.geometry("1150x950")
default_font = ("Segoe UI", 10)
root.option_add("*Font", default_font)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=5, pady=5)

# ==============================================================================
# ВКЛАДКА 1: ПОИСК (SEARCH)
# ==============================================================================
tab_search = ttk.Frame(notebook)
notebook.add(tab_search, text="🔍 Пошук (Google Search)")

main_frame = ttk.Frame(tab_search, padding=12)
main_frame.pack(fill="both", expand=True)

frame_settings = ttk.LabelFrame(
    main_frame,
    text=" ЕТАП 1: Налаштування параметрів кампаній та розширень ",
    padding=10,
)
frame_settings.pack(fill="x", pady=(0, 10))

ttk.Label(frame_settings, text="Бюджет Від ($):").grid(
    row=0, column=0, sticky="w"
)
entry_budget_from = ttk.Entry(frame_settings, width=6)
entry_budget_from.insert(0, "2")
entry_budget_from.grid(row=0, column=1, padx=(5, 10), sticky="w")

ttk.Label(frame_settings, text="До ($):").grid(row=0, column=2, sticky="w")
entry_budget_to = ttk.Entry(frame_settings, width=6)
entry_budget_to.insert(0, "5")
entry_budget_to.grid(row=0, column=3, padx=(5, 15), sticky="w")

ttk.Label(frame_settings, text="Max CPC ($):").grid(row=0, column=4, sticky="w")
entry_cpc = ttk.Entry(frame_settings, width=6)
entry_cpc.insert(0, "0.35")
entry_cpc.grid(row=0, column=5, padx=(5, 15), sticky="w")

ttk.Label(frame_settings, text="Модель ШІ:").grid(row=0, column=6, sticky="w")
combo_model = ttk.Combobox(
    frame_settings,
    values=["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-4-argon"],
    width=20,
    state="readonly",
)
combo_model.set("gemini-3.5-flash-lite")
combo_model.grid(row=0, column=7, padx=(5, 0), sticky="w")

frame_options = ttk.Frame(frame_settings)
frame_options.grid(row=1, column=0, columnspan=8, sticky="w", pady=(10, 0))

var_callouts = tk.BooleanVar(value=True)
chk_callouts = ttk.Checkbutton(
    frame_options, text="Callouts", variable=var_callouts
)
chk_callouts.pack(side="left", padx=(0, 15))

var_sitelinks = tk.BooleanVar(value=True)
chk_sitelinks = ttk.Checkbutton(
    frame_options, text="Sitelinks", variable=var_sitelinks
)
chk_sitelinks.pack(side="left", padx=(0, 15))

var_negatives = tk.BooleanVar(value=True)
chk_negatives = ttk.Checkbutton(
    frame_options, text="Мінус-слова", variable=var_negatives
)
chk_negatives.pack(side="left", padx=(0, 10))

ttk.Label(frame_options, text="Джерело:").pack(side="left", padx=(5, 3))
combo_neg_files = ttk.Combobox(
    frame_options,
    values=get_negative_files_list(),
    width=22,
    state="readonly",
)
combo_neg_files.set("Автоматично (за гео)")
combo_neg_files.pack(side="left", padx=(0, 10))

frame_table_area = ttk.LabelFrame(
    main_frame,
    text=(
        " ЕТАП 2: Таблиця даних (№ | Ідентифікатор | Фірма | Адреса | Сайт |"
        " Статус) "
    ),
    padding=10,
)
frame_table_area.pack(fill="both", expand=True, pady=(0, 10))

ctrl_frame = ttk.Frame(frame_table_area)
ctrl_frame.pack(fill="x", pady=(0, 6))


def check_status(ident, firm, address, url):
  if ident.strip() and firm.strip() and address.strip() and url.strip():
    return "⏳ Очікування"
  else:
    return "❌ Не готово"


def update_row_info():
  for idx, item in enumerate(tree.get_children(), 1):
    vals = list(tree.item(item, "values"))
    ident, firm, address, url = vals[1], vals[2], vals[3], vals[4]
    status = vals[5]

    if status not in [
        "✅ Проаналізовано",
        "💾 Створено CSV",
        "❌ Сайт не працює",
    ]:
      status = check_status(ident, firm, address, url)

    vals[0] = str(idx)
    vals[5] = status
    tree.item(item, values=vals)


def add_rows():
  try:
    count = int(entry_count.get().strip())
  except ValueError:
    count = 1

  for _ in range(max(1, count)):
    tree.insert("", "end", values=("", "", "", "", "", "❌ Не готово"))
  update_row_info()


def parse_clipboard_lines(clipboard_text):
  return [line.strip() for line in clipboard_text.splitlines() if line.strip()]


def paste_ident_only():
  try:
    clipboard_data = root.clipboard_get()
    if not clipboard_data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return
    lines = parse_clipboard_lines(clipboard_data)
    items = tree.get_children()

    while len(items) < len(lines):
      tree.insert("", "end", values=("", "", "", "", "", "❌ Не готово"))
      items = tree.get_children()

    updated = 0
    for idx, val in enumerate(lines):
      item_id = items[idx]
      vals = list(tree.item(item_id, "values"))
      vals[1] = val
      vals[5] = check_status(vals[1], vals[2], vals[3], vals[4])
      tree.item(item_id, values=vals)
      updated += 1

    update_row_info()
    messagebox.showinfo("Успіх", f"Вставлено ідентифікаторів: {updated}")
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити:\n{e}")


def paste_firm_address():
  try:
    clipboard_data = root.clipboard_get()
    if not clipboard_data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return

    lines = parse_clipboard_lines(clipboard_data)
    items = tree.get_children()

    needed_rows = (len(lines) + 1) // 2
    while len(items) < needed_rows:
      tree.insert("", "end", values=("", "", "", "", "", "❌ Не готово"))
      items = tree.get_children()

    updated = 0
    line_idx = 0
    for i in range(len(items)):
      if line_idx >= len(lines):
        break

      item_id = items[i]
      vals = list(tree.item(item_id, "values"))

      vals[2] = lines[line_idx].strip('"')
      line_idx += 1

      if line_idx < len(lines):
        vals[3] = lines[line_idx].strip('"')
        line_idx += 1

      vals[5] = check_status(vals[1], vals[2], vals[3], vals[4])
      tree.item(item_id, values=vals)
      updated += 1

    update_row_info()
    messagebox.showinfo(
        "Успіх", f"Успішно розподілено фірм та адрес: {updated}"
    )
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити:\n{e}")


def paste_urls_only():
  try:
    clipboard_data = root.clipboard_get()
    if not clipboard_data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return

    urls = parse_clipboard_lines(clipboard_data)
    items = tree.get_children()

    while len(items) < len(urls):
      tree.insert("", "end", values=("", "", "", "", "", "❌ Не готово"))
      items = tree.get_children()

    updated = 0
    for idx, url in enumerate(urls):
      if idx < len(items):
        item_id = items[idx]
        vals = list(tree.item(item_id, "values"))
        vals[4] = clean_url(url)

        auto_country, _ = parse_url_meta(vals[4])
        if auto_country and not vals[3]:
          vals[3] = auto_country

        vals[5] = check_status(vals[1], vals[2], vals[3], vals[4])
        tree.item(item_id, values=vals)
        updated += 1

    update_row_info()
    messagebox.showinfo("Успіх", f"Оновлено сайтів: {updated}")
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити сайти:\n{e}")


def paste_clipboard_to_table():
  try:
    clipboard_data = root.clipboard_get()
    if not clipboard_data.strip():
      messagebox.showwarning("Буфер обміну", "Буфер обміну порожній!")
      return

    lines = [line for line in clipboard_data.splitlines() if line.strip()]
    items = tree.get_children()

    updated_count = 0
    for i, line in enumerate(lines):
      parts = [p.strip('"').strip() for p in line.split("\t")]
      if len(parts) == 1:
        parts = [p.strip('"').strip() for p in line.split(",")]

      if i >= len(items):
        tree.insert("", "end", values=("", "", "", "", "", "❌ Не готово"))
        items = tree.get_children()

      item_id = items[i]
      vals = list(tree.item(item_id, "values"))

      if len(parts) >= 4:
        vals[1], vals[2], vals[3], vals[4] = (
            parts[0],
            parts[1],
            parts[2],
            clean_url(parts[3]),
        )
      elif len(parts) == 3:
        vals[1], vals[2], vals[3] = parts[0], parts[1], parts[2]
      elif len(parts) == 2:
        vals[1], vals[2] = parts[0], parts[1]
      elif len(parts) == 1:
        if parts[0].startswith("http") or "." in parts[0]:
          vals[4] = clean_url(parts[0])
        else:
          vals[1] = parts[0]

      auto_country, _ = parse_url_meta(vals[4])
      if auto_country and not vals[3]:
        vals[3] = auto_country

      vals[5] = check_status(vals[1], vals[2], vals[3], vals[4])
      tree.item(item_id, values=vals)
      updated_count += 1

    update_row_info()
    messagebox.showinfo(
        "Успіх", f"Успішно вставлено рядків із буфера: {updated_count}"
    )
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося зчитати буфер обміну:\n{e}")


def delete_selected():
  for item in tree.selection():
    if item in memory_storage:
      del memory_storage[item]
    tree.delete(item)
  update_row_info()


def clear_table():
  memory_storage.clear()
  for item in tree.get_children():
    tree.delete(item)


btn_paste_all = tk.Button(
    ctrl_frame,
    text="📋 Вставити скопійоване (все одразу)",
    command=paste_clipboard_to_table,
    bg="#0d6efd",
    fg="white",
    font=("Segoe UI", 9, "bold"),
)
btn_paste_all.pack(side="left", padx=(0, 6))

btn_paste_ident = tk.Button(
    ctrl_frame,
    text="📋 Ідентифікатор",
    command=paste_ident_only,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 9),
)
btn_paste_ident.pack(side="left", padx=(0, 4))

btn_paste_firm = tk.Button(
    ctrl_frame,
    text="📋 Фірма + Адреса",
    command=paste_firm_address,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 9),
)
btn_paste_firm.pack(side="left", padx=(0, 4))

btn_paste_urls = tk.Button(
    ctrl_frame,
    text="🔗 Сайти",
    command=paste_urls_only,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 9),
)
btn_paste_urls.pack(side="left", padx=(0, 10))

ttk.Label(ctrl_frame, text="Кількість:").pack(side="left", padx=(0, 3))
entry_count = ttk.Entry(ctrl_frame, width=5)
entry_count.insert(0, "1")
entry_count.pack(side="left", padx=(0, 5))

ttk.Button(ctrl_frame, text="➕ Додати", command=add_rows).pack(
    side="left", padx=(0, 10)
)
ttk.Button(ctrl_frame, text="❌ Видалити", command=delete_selected).pack(
    side="left", padx=(0, 5)
)
ttk.Button(ctrl_frame, text="🗑️ Очистити", command=clear_table).pack(side="left")

columns = ("num", "ident", "firm", "address", "url", "status")
tree = ttk.Treeview(frame_table_area, columns=columns, show="headings", height=8)

tree.heading("num", text="№")
tree.heading("ident", text="Ідентифікатор")
tree.heading("firm", text="Фірма")
tree.heading("address", text="Адреса")
tree.heading("url", text="Сайт")
tree.heading("status", text="Статус")

tree.column("num", width=40, anchor="center")
tree.column("ident", width=120)
tree.column("firm", width=150)
tree.column("address", width=150)
tree.column("url", width=200)
tree.column("status", width=150, anchor="center")

tree.pack(fill="both", expand=True, side="left", pady=(4, 0))

scrollbar = ttk.Scrollbar(
    frame_table_area, orient="vertical", command=tree.yview
)
tree.configure(yscrollcommand=scrollbar.set)
scrollbar.pack(side="right", fill="y", pady=(4, 0))


def on_double_click(event):
  selection = tree.selection()
  if not selection:
    return
  item_id = selection[0]
  column = tree.identify_column(event.x)
  col_idx = int(column.replace("#", "")) - 1

  if col_idx == 0 or col_idx == 5:
    return

  x, y, width, height = tree.bbox(item_id, column)
  val = tree.item(item_id, "values")[col_idx]

  entry_edit = ttk.Entry(tree)
  entry_edit.place(x=x, y=y, width=width, height=height)
  entry_edit.insert(0, val)
  entry_edit.focus()

  def save_edit(e):
    new_val = entry_edit.get()
    current_vals = list(tree.item(item_id, "values"))
    current_vals[col_idx] = new_val

    if col_idx == 4:
      auto_country, _ = parse_url_meta(new_val)
      if auto_country:
        current_vals[3] = auto_country

    current_vals[5] = check_status(
        current_vals[1], current_vals[2], current_vals[3], current_vals[4]
    )
    tree.item(item_id, values=current_vals)
    entry_edit.destroy()

  entry_edit.bind("<Return>", save_edit)
  entry_edit.bind("<FocusOut>", lambda e: entry_edit.destroy())


tree.bind("<Double-1>", on_double_click)

frame_bottom = ttk.Frame(main_frame)
frame_bottom.pack(fill="x", pady=(5, 5))


def log_msg(msg):
  log_text.insert("end", msg + "\n")
  log_text.see("end")
  root.update()


def run_analysis_batch():
  global is_paused, is_running
  if is_running:
    messagebox.showinfo("Інформація", "Аналіз вже виконується!")
    return

  if not MY_FIXED_API_KEY or MY_FIXED_API_KEY == "ВСТАВЬ_СВОЙ_API_КЛЮЧ_СЮДА":
    messagebox.showerror(
        "Помилка",
        "Задай новий Gemini API-ключ через змінну GEMINI_API_KEY або у файлі"
        " gemini_api_key.txt поруч зі скриптом.",
    )
    return

  items = tree.get_children()
  if not items:
    messagebox.showwarning("Увага", "Таблиця порожня!")
    return

  if not os.path.exists(PROMPT_FILE):
    messagebox.showerror(
        "Помилка", f"Не знайдено файл шаблону:\n{PROMPT_FILE}"
    )
    return

  template = open(PROMPT_FILE, "r", encoding="utf-8").read()
  selected_model = combo_model.get().strip()

  log_text.delete("1.0", "end")
  log_msg(f"=== ЗАПУСК АНАЛІЗУ САЙТІВ (Модель: {selected_model}) ===")
  is_paused = False
  is_running = True
  success_count = 0

  for idx, item in enumerate(items):
    if is_paused:
      log_msg("\n⏸️ Роботу поставлено на паузу користувачем.")
      break

    vals = tree.item(item, "values")
    num, ident, firm, address, url, status = (
        vals[0],
        vals[1],
        vals[2],
        vals[3],
        vals[4],
        vals[5],
    )

    if (
        not ident.strip()
        or not firm.strip()
        or not address.strip()
        or not url.strip()
    ):
      tree.item(item, values=(num, ident, firm, address, url, "❌ Не готово"))
      continue

    tree.item(
        item, values=(num, ident, firm, address, url, "⏳ Перевірка сайту...")
    )
    root.update()

    log_msg(f"\n[{num}] Обробка фірми: {firm} ({url})")
    log_msg("  -> Перевірка та скачування вмісту сторінки...")
    site_data = fetch_landing(url)

    if not site_data["ok"]:
      tree.item(
          item, values=(num, ident, firm, address, url, "❌ Сайт не працює")
      )
      log_msg(
          f"  -> ❌ Помилка: Сайт недоступний ({site_data['error']}). Пропускаємо!"
      )
      continue

    scraped_text = site_data["text"]
    log_msg(f"  -> ✅ Сайт успішно скачано ({len(scraped_text)} символів)")

    tree.item(item, values=(num, ident, firm, address, url, "⏳ Аналіз ШІ..."))
    root.update()

    try:
      full_prompt = (
          f"Проаналізуй сайт: {url}, товари/послуги фірми '{firm}' у регіоні"
          f" '{address}'. Ось реальний текст, зібраний із цього сайту для"
          f" аналізу:\n{scraped_text[:5000]}\n\nНа основі цього згенеруй"
          " рекламну кампанію за наступним шаблоном:\n\n"
          + template
      )

      log_msg(f"  -> Відправка запиту до Gemini API ({selected_model})...")
      ai_response = call_gemini_api(
          MY_FIXED_API_KEY, full_prompt, model_name=selected_model
      )

      log_msg("  -> Перевірка відповіді на відповідність промпту...")
      ai_response = validate_and_correct_response(
          MY_FIXED_API_KEY, full_prompt, ai_response, selected_model
      )

      memory_storage[item] = ai_response

      tree.item(
          item, values=(num, ident, firm, address, url, "✅ Проаналізовано")
      )
      log_msg("  ✅ Успішно проаналізовано та збережено в пам'ять!")
      success_count += 1

      if idx < len(items) - 1 and not is_paused:
        log_msg("  ⏳ Пауза 4 секунди (захист від лімітів API)...")
        time.sleep(4)

    except Exception as e:
      tree.item(item, values=(num, ident, firm, address, url, "❌ Помилка"))
      log_msg(f"  ❌ ПОМИЛКА ШІ: {str(e)}")

  is_running = False
  log_msg(f"\n=== АНАЛІЗ ЗАВЕРШЕНО! Успішно: {success_count} з {len(items)} ===")


def pause_analysis():
  global is_paused
  if is_running:
    is_paused = True
    log_msg("\n⏸️ Запит на паузу активовано. Зупинка після поточного рядка...")
  else:
    messagebox.showinfo("Інформація", "Аналіз зараз не виконується.")


def create_csv_for_selected():
  items = tree.get_children()
  if not items:
    messagebox.showwarning("Увага", "Таблиця порожня!")
    return

  try:
    b_from = float(entry_budget_from.get().strip().replace(",", "."))
    b_to = float(entry_budget_to.get().strip().replace(",", "."))
    if b_from > b_to:
      b_from, b_to = b_to, b_from
  except ValueError:
    b_from, b_to = 2.0, 5.0

  cpc = entry_cpc.get().strip()
  use_callouts = var_callouts.get()
  use_sitelinks = var_sitelinks.get()
  use_negatives = var_negatives.get()
  selected_neg_file = combo_neg_files.get()

  created_count = 0

  for item in items:
    vals = tree.item(item, "values")
    num, ident, firm, address, url, status = (
        vals[0],
        vals[1],
        vals[2],
        vals[3],
        vals[4],
        vals[5],
    )

    if item not in memory_storage:
      continue

    rand_budget = round(random.uniform(b_from, b_to), 2)
    try:
      path = generate_and_save_csv(
          ident=ident,
          url=url,
          product_val=firm,
          geo_val=address,
          budget=str(rand_budget),
          cpc=cpc,
          raw_content=memory_storage[item],
          use_callouts=use_callouts,
          use_sitelinks=use_sitelinks,
          use_negatives=use_negatives,
          selected_neg_file=selected_neg_file,
      )
      tree.item(
          item, values=(num, ident, firm, address, url, "💾 Створено CSV")
      )
      created_count += 1
    except Exception as e:
      messagebox.showerror(
          "Помилка", f"Не вдалося створити CSV для {firm}:\n{e}"
      )

  if created_count > 0:
    message = f"Успішно створено папки та CSV файлів: {created_count}."
    if use_callouts:
      message += (
          "\nФайл callouts_<ідентифікатор>.csv потрібно окремо імпортувати в"
          " Shared library."
      )
    messagebox.showinfo("Успіх", message)
  else:
    messagebox.showwarning(
        "Увага",
        "Відсутні результати аналізу для створення CSV. Спочатку виконайте"
        " аналіз!",
    )


btn_run = tk.Button(
    frame_bottom,
    text="🚀 Запустити аналіз",
    command=run_analysis_batch,
    bg="#1a73e8",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    height=2,
)
btn_run.pack(side="left", fill="x", expand=True, padx=(0, 5))

btn_pause = tk.Button(
    frame_bottom,
    text="⏸️ Пауза",
    command=pause_analysis,
    bg="#f9ab00",
    fg="black",
    font=("Segoe UI", 10, "bold"),
    height=2,
)
btn_pause.pack(side="left", fill="x", expand=True, padx=(0, 5))

btn_create_csv = tk.Button(
    frame_bottom,
    text="📥 Створити CSV",
    command=create_csv_for_selected,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    height=2,
)
btn_create_csv.pack(side="left", fill="x", expand=True)

frame_log_area = ttk.LabelFrame(
    main_frame, text=" 📡 Журнал виконання в реальному часі ", padding=6
)
frame_log_area.pack(fill="both", expand=True)

log_text = tk.Text(
    frame_log_area,
    bg="#1e1e1e",
    fg="#dcdcdc",
    font=("Consolas", 9),
    height=10,
    padx=6,
    pady=6,
)
log_text.pack(fill="both", expand=True, side="left")

log_scrollbar = ttk.Scrollbar(
    frame_log_area, orient="vertical", command=log_text.yview
)
log_text.configure(yscrollcommand=log_scrollbar.set)
log_scrollbar.pack(side="right", fill="y")


# ==============================================================================
# ВКЛАДКА 2: YOUTUBE РК (ПОКОЛОНОЧНЫЕ КНОПКИ ВСТАВКИ)
# ==============================================================================
tab_youtube = ttk.Frame(notebook)
notebook.add(tab_youtube, text="📺 YouTube Відео РК")

yt_saved_cfg = load_yt_settings()

yt_main_frame = ttk.Frame(tab_youtube, padding=12)
yt_main_frame.pack(fill="both", expand=True)

yt_cfg_frame = ttk.LabelFrame(
    yt_main_frame,
    text=" ЕТАП 1: Налаштування параметрів YouTube кампаній ",
    padding=10,
)
yt_cfg_frame.pack(fill="x", pady=(0, 10))

ttk.Label(yt_cfg_frame, text="Загальний бюджет ($):").grid(
    row=0, column=0, sticky="w", padx=5, pady=5
)
yt_budget = ttk.Entry(yt_cfg_frame, width=12)
yt_budget.insert(0, yt_saved_cfg.get("budget", "0.01"))
yt_budget.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

ttk.Label(yt_cfg_frame, text="Target CPV ($):").grid(
    row=0, column=2, sticky="w", padx=5, pady=5
)
yt_cpc = ttk.Entry(yt_cfg_frame, width=12)
yt_cpc.insert(0, yt_saved_cfg.get("cpv", "0.05"))
yt_cpc.grid(row=0, column=3, sticky="ew", padx=5, pady=5)

ttk.Label(yt_cfg_frame, text="Локація (Країна):").grid(
    row=1, column=0, sticky="w", padx=5, pady=5
)
yt_location = ttk.Combobox(
    yt_cfg_frame, values=COUNTRIES_LIST, width=23, state="readonly"
)
yt_location.set(yt_saved_cfg.get("location", "Australia"))
yt_location.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

ttk.Label(yt_cfg_frame, text="Мова (Language):").grid(
    row=1, column=2, sticky="w", padx=5, pady=5
)
yt_language = ttk.Combobox(
    yt_cfg_frame, values=LANGS_LIST, width=15, state="readonly"
)
yt_language.set(yt_saved_cfg.get("language", "All languages"))
yt_language.grid(row=1, column=3, sticky="ew", padx=5, pady=5)

ttk.Label(yt_cfg_frame, text="Call to action:").grid(
    row=2, column=0, sticky="w", padx=5, pady=5
)
yt_cta = ttk.Entry(yt_cfg_frame, width=23)
yt_cta.insert(0, yt_saved_cfg.get("cta", "Learn more"))
yt_cta.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

yt_cfg_frame.columnconfigure(1, weight=1)
yt_cfg_frame.columnconfigure(3, weight=1)

yt_table_area = ttk.LabelFrame(
    yt_main_frame,
    text=(
        " ЕТАП 2: Таблиця даних YouTube (№ | Ідентифікатор | YouTube URL |"
        " Заголовок | Опис | Статус | Logo ID) "
    ),
    padding=10,
)
yt_table_area.pack(fill="both", expand=True, pady=(0, 10))

yt_ctrl_frame = ttk.Frame(yt_table_area)
yt_ctrl_frame.pack(fill="x", pady=(0, 6))


def yt_check_status(ident, yt_url, headline, desc, logo_id=""):
  if ident.strip() and yt_url.strip() and headline.strip():
    return "⏳ Готово"
  else:
    return "❌ Заповніть дані"


def yt_update_row_info():
  logos_db = load_logos_db()
  for idx, item in enumerate(yt_tree.get_children(), 1):
    vals = list(yt_tree.item(item, "values"))
    ident, yt_url, headline, desc = vals[1], vals[2], vals[3], vals[4]
    status = vals[5]

    logo_val = vals[6] if len(vals) > 6 else ""
    if not logo_val.strip() and ident.strip() in logos_db:
      logo_val = logos_db[ident.strip()]

    if status not in ["💾 Створено CSV"]:
      status = yt_check_status(ident, yt_url, headline, desc, logo_val)

    vals[0] = str(idx)
    vals[5] = status
    if len(vals) > 6:
      vals[6] = logo_val
    else:
      vals.append(logo_val)

    yt_tree.item(item, values=vals)


def yt_add_rows():
  try:
    count = int(yt_entry_count.get().strip())
  except ValueError:
    count = 1

  for _ in range(max(1, count)):
    yt_tree.insert("", "end", values=("", "", "", "", "", "❌ Заповніть дані", ""))
  yt_update_row_info()


# 1. Вставка ТОЛЬКО Идентификаторов (в 1-ю колонку)
def yt_paste_idents():
  try:
    data = root.clipboard_get()
    if not data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return
    lines = parse_clipboard_lines(data)
    items = yt_tree.get_children()

    while len(items) < len(lines):
      yt_tree.insert(
          "", "end", values=("", "", "", "", "", "❌ Заповніть дані", "")
      )
      items = yt_tree.get_children()

    for idx, val in enumerate(lines):
      item_id = items[idx]
      vals = list(yt_tree.item(item_id, "values"))
      if len(vals) < 7:
        vals.extend([""] * (7 - len(vals)))
      vals[1] = val.strip()
      vals[5] = yt_check_status(vals[1], vals[2], vals[3], vals[4], vals[6])
      yt_tree.item(item_id, values=vals)

    yt_update_row_info()
    messagebox.showinfo("Успіх", f"Вставлено ідентифікаторів: {len(lines)}")
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити:\n{e}")


# 2. Вставка ДАННЫХ YOUTUBE (URL + Заголовок + Описание) в колонки 2, 3, 4
def yt_paste_youtube_data():
  try:
    data = root.clipboard_get()
    if not data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return
    lines = [line for line in data.splitlines() if line.strip()]
    items = yt_tree.get_children()

    while len(items) < len(lines):
      yt_tree.insert(
          "", "end", values=("", "", "", "", "", "❌ Заповніть дані", "")
      )
      items = yt_tree.get_children()

    updated = 0
    for idx, line in enumerate(lines):
      parts = [p.strip('"').strip() for p in line.split("\t")]
      if len(parts) == 1:
        parts = [p.strip('"').strip() for p in line.split("|")]
      if len(parts) == 1:
        parts = [p.strip('"').strip() for p in line.split(",")]

      item_id = items[idx]
      vals = list(yt_tree.item(item_id, "values"))
      if len(vals) < 7:
        vals.extend([""] * (7 - len(vals)))

      if len(parts) >= 3:
        vals[2], vals[3], vals[4] = clean_url(parts[0]), parts[1], parts[2]
      elif len(parts) == 2:
        vals[2], vals[3] = clean_url(parts[0]), parts[1]
      elif len(parts) == 1:
        vals[2] = clean_url(parts[0])

      vals[5] = yt_check_status(vals[1], vals[2], vals[3], vals[4], vals[6])
      yt_tree.item(item_id, values=vals)
      updated += 1

    yt_update_row_info()
    messagebox.showinfo("Успіх", f"Вставлено даних YouTube: {updated}")
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити дані YouTube:\n{e}")


# 3. Вставка ТОЛЬКО Logo ID (в последнюю колонку)
def yt_paste_logo_ids():
  try:
    data = root.clipboard_get()
    if not data.strip():
      messagebox.showwarning("Попередження", "Буфер обміну порожній!")
      return
    lines = parse_clipboard_lines(data)
    items = yt_tree.get_children()

    while len(items) < len(lines):
      yt_tree.insert(
          "", "end", values=("", "", "", "", "", "❌ Заповніть дані", "")
      )
      items = yt_tree.get_children()

    updated = 0
    for idx, val in enumerate(lines):
      item_id = items[idx]
      vals = list(yt_tree.item(item_id, "values"))
      if len(vals) < 7:
        vals.extend([""] * (7 - len(vals)))
      vals[6] = val.strip()

      if vals[1].strip():
        save_logo_to_db(vals[1].strip(), vals[6])

      vals[5] = yt_check_status(vals[1], vals[2], vals[3], vals[4], vals[6])
      yt_tree.item(item_id, values=vals)
      updated += 1

    yt_update_row_info()
    messagebox.showinfo("Успіх", f"Вставлено Logo ID: {updated}")
  except Exception as e:
    messagebox.showerror("Помилка", f"Не вдалося вставити Logo ID:\n{e}")


def yt_delete_selected():
  for item in yt_tree.selection():
    yt_tree.delete(item)
  yt_update_row_info()


def yt_clear_table():
  for item in yt_tree.get_children():
    yt_tree.delete(item)


# --- КНОПКИ НА ПАНЕЛИ УПРАВЛЕНИЯ YOUTUBE ---
btn_yt_paste_id = tk.Button(
    yt_ctrl_frame,
    text="📋 Ідентифікатор",
    command=yt_paste_idents,
    bg="#0d6efd",
    fg="white",
    font=("Segoe UI", 9, "bold"),
)
btn_yt_paste_id.pack(side="left", padx=(0, 6))

btn_yt_paste_data = tk.Button(
    yt_ctrl_frame,
    text="🎬 YouTube (URL, Заголовок, Опис)",
    command=yt_paste_youtube_data,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 9, "bold"),
)
btn_yt_paste_data.pack(side="left", padx=(0, 6))

btn_yt_paste_logo = tk.Button(
    yt_ctrl_frame,
    text="🔑 Logo ID",
    command=yt_paste_logo_ids,
    bg="#34A853",
    fg="white",
    font=("Segoe UI", 9),
)
btn_yt_paste_logo.pack(side="left", padx=(0, 10))

ttk.Label(yt_ctrl_frame, text="Кількість:").pack(side="left", padx=(0, 3))
yt_entry_count = ttk.Entry(yt_ctrl_frame, width=5)
yt_entry_count.insert(0, "1")
yt_entry_count.pack(side="left", padx=(0, 5))

ttk.Button(yt_ctrl_frame, text="➕ Додати", command=yt_add_rows).pack(
    side="left", padx=(0, 10)
)
ttk.Button(yt_ctrl_frame, text="❌ Видалити", command=yt_delete_selected).pack(
    side="left", padx=(0, 5)
)
ttk.Button(yt_ctrl_frame, text="🗑️ Очистити", command=yt_clear_table).pack(
    side="left"
)

yt_columns = ("num", "ident", "yt_url", "headline", "desc", "status", "logo_id")
yt_tree = ttk.Treeview(
    yt_table_area, columns=yt_columns, show="headings", height=10
)

yt_tree.heading("num", text="№")
yt_tree.heading("ident", text="Ідентифікатор")
yt_tree.heading("yt_url", text="YouTube URL")
yt_tree.heading("headline", text="Заголовок")
yt_tree.heading("desc", text="Опис")
yt_tree.heading("status", text="Статус")
yt_tree.heading("logo_id", text="Logo ID")

yt_tree.column("num", width=40, anchor="center")
yt_tree.column("ident", width=120)
yt_tree.column("yt_url", width=200)
yt_tree.column("headline", width=180)
yt_tree.column("desc", width=200)
yt_tree.column("status", width=130, anchor="center")
yt_tree.column("logo_id", width=120)

yt_tree.pack(fill="both", expand=True, side="left", pady=(4, 0))

yt_scrollbar = ttk.Scrollbar(
    yt_table_area, orient="vertical", command=yt_tree.yview
)
yt_tree.configure(yscrollcommand=yt_scrollbar.set)
yt_scrollbar.pack(side="right", fill="y", pady=(4, 0))


def on_yt_double_click(event):
  selection = yt_tree.selection()
  if not selection:
    return
  item_id = selection[0]
  column = yt_tree.identify_column(event.x)
  col_idx = int(column.replace("#", "")) - 1

  if col_idx == 0 or col_idx == 5:
    return

  x, y, width, height = yt_tree.bbox(item_id, column)
  val = yt_tree.item(item_id, "values")[col_idx]

  entry_edit = ttk.Entry(yt_tree)
  entry_edit.place(x=x, y=y, width=width, height=height)
  entry_edit.insert(0, val)
  entry_edit.focus()

  def save_yt_edit(e):
    new_val = entry_edit.get()
    current_vals = list(yt_tree.item(item_id, "values"))
    current_vals[col_idx] = new_val
    current_vals[5] = yt_check_status(
        current_vals[1],
        current_vals[2],
        current_vals[3],
        current_vals[4],
        current_vals[6] if len(current_vals) > 6 else "",
    )
    yt_tree.item(item_id, values=current_vals)
    entry_edit.destroy()

  entry_edit.bind("<Return>", save_yt_edit)
  entry_edit.bind("<FocusOut>", lambda e: entry_edit.destroy())


yt_tree.bind("<Double-1>", on_yt_double_click)


def extract_youtube_video_id(raw_url):
  value = (raw_url or "").strip()
  if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
    return value
  url = clean_url(value)
  try:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.endswith("youtu.be"):
      candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
      query = urllib.parse.parse_qs(parsed.query)
      candidate = (query.get("v") or [""])[0]
      if not candidate:
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in ("embed", "shorts", "live"):
          candidate = path_parts[1]
    else:
      candidate = ""
  except Exception:
    candidate = ""
  if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate or ""):
    raise ValueError(f"Не вдалося визначити Video ID з посилання: {raw_url}")
  return candidate


YT_EU_POLITICAL_ADS = "No"


def generate_youtube_csv_from_table():
  budget = yt_budget.get().strip().replace(",", ".")
  max_cpv = yt_cpc.get().strip().replace(",", ".")
  location = yt_location.get().strip()
  language = yt_language.get().strip()
  cta_text = yt_cta.get().strip()
  logos_db = load_logos_db()

  # 💡 ВАРИАНТ 2: Оставляем Start date пустым (""), чтобы запуск происходил автоматически при импорте
  now = datetime.now()
  start_date = ""
  end_date = (now + timedelta(days=3)).strftime("%Y-%m-%d")

  save_yt_settings(budget, max_cpv, location, language, cta_text)

  lang_for_csv = "" if language == "All languages" else language

  if not cta_text or len(cta_text) > 10:
    messagebox.showwarning("Увага", "Call to action: від 1 до 10 символів.")
    return

  items = yt_tree.get_children()
  if not items:
    messagebox.showwarning("Увага", "Таблиця YouTube порожня!")
    return

  try:
    if float(budget) <= 0 or float(max_cpv) <= 0:
      raise ValueError
  except ValueError:
    messagebox.showerror(
        "Помилка", "Бюджет і Max CPV мають бути числами більше нуля."
    )
    return

  headers = [
      "Row Type",
      "Action",
      "Campaign",
      "Campaign type",
      "Campaign status",
      "EU political ads",
      "Budget",
      "Budget type",
      "Bid strategy type",
      "Start date",
      "End date",
      "Location",
      "Language",
      "Ad group",
      "Ad group type",
      "Ad group status",
      "TrueView target CPV",
      "Ad type",
      "Ad status",
      "Ad name",
      "Final URL",
      "Video",
      "Video ID",
      "Long headline",
      "Long headline 1",
      "Description 1",
      "Call to action text",
      "Logo ID",
      "Business name",
  ]
  created_count = 0
  skipped = []

  for item in items:
    vals = list(yt_tree.item(item, "values"))
    num, ident_val, v_url, headline, desc, status = vals[:6]

    ident_str = ident_val.strip()
    raw_logo = (
        vals[6].strip() if len(vals) > 6 and vals[6].strip() else ""
    )

    if not raw_logo and ident_str in logos_db:
      raw_logo = logos_db[ident_str]

    logo_id = raw_logo.split(".")[0] if raw_logo else ""

    if not ident_str or not v_url.strip() or not headline.strip():
      skipped.append(
          f"№{num}: потрібно заповнити ID, YouTube URL і заголовок"
      )
      continue

    if not logo_id:
      skipped.append(f"№{num}: вкажіть Logo ID для '{ident_str}' в таблиці")
      continue

    save_logo_to_db(ident_str, logo_id)

    try:
      video_id = extract_youtube_video_id(v_url)
    except ValueError as e:
      skipped.append(f"№{num}: {e}")
      continue

    clean_headline = headline.strip()
    clean_desc = desc.strip()

    if len(clean_headline) > 90:
      skipped.append(
          f"№{num}: заголовок (Long headline) довший за 90 символів"
      )
      continue

    # 💡 Лимит Description — до 90 символов (обрезаем, если превышает 90)
    clean_desc = clean_desc[:90].strip()

    # 💡 Лимит Business Name — ровно 25 символов (обрезаем жестко до 25)
    business_name = ident_str[:25].strip()

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Название кампании генерируется по текущей дате
    current_date_str = now.strftime("%Y-%m-%d")
    camp_name = f"Video - Video views - {current_date_str}"
    ad_group_name = f"Video views - {current_date_str}"

    personal_dir = os.path.join(YOUTUBE_OUTPUT_DIR, ident_str)
    os.makedirs(personal_dir, exist_ok=True)

    rows = [
        {
            "Row Type": "Campaign",
            "Action": "Add",
            "Campaign": camp_name,
            "Campaign type": "Video",
            "Campaign status": "Enabled",
            "EU political ads": YT_EU_POLITICAL_ADS,
            "Budget": budget,
            "Budget type": "Campaign total",
            "Bid strategy type": "Target CPV",
            "Start date": start_date,  # Поле теперь передается пустым ("")
            "End date": end_date,
            "Location": location,
            "Language": lang_for_csv,
        },
        {
            "Row Type": "Ad group",
            "Action": "Add",
            "Campaign": camp_name,
            "Ad group": ad_group_name,
            "Ad group type": "Responsive video ad",
            "Ad group status": "Enabled",
            "TrueView target CPV": max_cpv,
        },
        {
            "Row Type": "Ad",
            "Action": "Add",
            "Campaign": camp_name,
            "Ad group": ad_group_name,
            "Ad name": "Ad #1",
            "Ad type": "Responsive video ad",
            "Ad status": "Enabled",
            "Final URL": video_url,
            "Video": video_url,
            "Video ID": video_id,
            "Long headline": clean_headline,
            "Long headline 1": clean_headline,
            "Description 1": clean_desc,
            "Call to action text": cta_text,
            "Logo ID": logo_id,
            "Business name": business_name,  # <= ровно до 25 символов
        },
    ]

    file_path = os.path.join(personal_dir, f"import_youtube_{ident_str}.csv")
    try:
      _write_editor_csv(file_path, headers, rows)
      yt_tree.item(item, values=(*vals[:5], "💾 Створено CSV", logo_id))
      created_count += 1
    except Exception as e:
      skipped.append(f"№{num}: не вдалося зберегти CSV: {e}")

  if created_count:
    message = (
        f"Створено CSV для YouTube: {created_count}.\nЗагальний бюджет:"
        f" ${budget}\nДата завершення: {end_date}\nСтатус: Enabled"
    )
    if skipped:
      message += "\n\nПропущені рядки:\n" + "\n".join(skipped[:10])
    messagebox.showinfo("Готово", message)
  else:
    message = "Не створено жодного CSV."
    if skipped:
      message += "\n\n" + "\n".join(skipped[:10])
    messagebox.showwarning("Увага", message)


btn_yt_csv = tk.Button(
    yt_main_frame,
    text="🎬 Створити CSV для YouTube РК",
    command=generate_youtube_csv_from_table,
    bg="#cc0000",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    height=2,
)
btn_yt_csv.pack(fill="x", pady=5)

root.mainloop()