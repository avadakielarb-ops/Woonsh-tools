"""
PPC Gemini Generator
--------------------
URL + опис сайту -> Gemini -> чернетка (таблиця) -> CSV для веб-кабінету Google Ads.

Крок 1: "Згенерувати чернетку" — модель повертає структурований JSON, застосунок
        малює таблицю і проганяє перевірки (ліміти символів, політика, гео).
Крок 2: "Створити CSV" — збирається файл з назвою кампанії у папці "Готові РК".

Залежності: тільки стандартна бібліотека + tkinter.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
import os
import re
import csv
import json
import time
import queue
import base64
import random
import socket
import struct
import threading
import urllib.request
import urllib.error
import urllib.parse
import ctypes
import subprocess
import unicodedata

# ── Чіткість (High DPI) для Windows ───────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE  = os.path.join(BASE_DIR, "config.json")
PROMPT_FILE  = os.path.join(BASE_DIR, "prompt_gemini.txt")
# Агрегатори працюють за іншими правилами, тому промпт у них власний і
# редагується окремо: правити один файл під дві протилежні задачі неможливо.
PROMPT_FILE_AGG = os.path.join(BASE_DIR, "prompt_aggregator.txt")
OUTPUT_DIR   = os.path.join(BASE_DIR, "Готові РК")
HISTORY_DIR  = os.path.join(BASE_DIR, "Історія")
# Перероблені оголошення лежать окремо: це не нова кампанія, і мішати їх
# з готовими РК означає плутати два різні типи файлів при заливці.
REWORK_DIR   = os.path.join(BASE_DIR, "ReworkAds")
# Агрегатори тримаємо повністю окремо — і кампанії, і їхні оголошення.
# Це інші правила, інший промпт і інший рівень ризику: файли не мають
# випадково потрапити в заливку разом із білими кампаніями.
AGG_DIR        = os.path.join(BASE_DIR, "Aggregators")
AGG_REWORK_DIR = os.path.join(AGG_DIR, "ReworkAds")


BATCH_FILE = os.path.join(BASE_DIR, "batch.json")
BATCH_ARCHIVE = os.path.join(BASE_DIR, "batch_archive.json")


def ident_folder(ident):
    """Тека за ідентифікатором. Порожній ідентифікатор — кладемо в корінь."""
    cleaned = re.sub(r'[<>:"/\\|?*]', " ", (ident or "")).strip(" .")
    return re.sub(r"\s+", " ", cleaned)[:60]


def short_path(path):
    """Шлях для стрічки процесу.

    os.path.relpath падає з ValueError, якщо файл і скрипт на РІЗНИХ дисках:
    скрипт на C:, тека для готових на D: — і збереження валилося одразу
    після запису файлу. Тому на іншому диску показуємо повний шлях.
    """
    try:
        return os.path.relpath(path, BASE_DIR)
    except ValueError:
        return path


def chosen_root():
    """Тека, вибрана людиною для готових файлів.

    За замовчуванням порожньо — тоді все лягає поруч зі скриптом, як і
    було. Кнопка «Змінити» в головному вікні пише сюди свій шлях, якщо
    складати файли зручніше деінде.
    """
    try:
        root = (load_config().get("output_root") or "").strip()
    except Exception:
        return ""
    return root if root and os.path.isdir(root) else ""


def output_dir(aggregator=False, ident=""):
    root = chosen_root()
    if root:
        base = os.path.join(root, "Aggregators" if aggregator else "Готові РК")
    else:
        base = AGG_DIR if aggregator else OUTPUT_DIR
    name = ident_folder(ident)
    return os.path.join(base, name) if name else base


def rework_dir(aggregator=False, ident=""):
    root = chosen_root()
    if root:
        base = (os.path.join(root, "Aggregators", "ReworkAds") if aggregator
                else os.path.join(root, "ReworkAds"))
    else:
        base = AGG_REWORK_DIR if aggregator else REWORK_DIR
    name = ident_folder(ident)
    return os.path.join(base, name) if name else base

API_ROOT      = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"

# Окреме вікно Chrome для Gemini — основний браузер не чіпаємо.
CDP_PORT      = 9222
CHROME_PROFILE = os.path.join(BASE_DIR, "chrome-profile")
GEMINI_URL    = "https://gemini.google.com/app"
CHROME_PATHS  = [
    os.path.join(os.environ.get("ProgramFiles", ""), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), r"Microsoft\Edge\Application\msedge.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""), r"Microsoft\Edge\Application\msedge.exe"),
]

# Ліміти Google Ads
LIMIT_HEADLINE = 30
LIMIT_DESC     = 90
DESC_MIN       = 60          # нижче 60 — марнування місця, від 60 нормально
# Діапазони моделі не даємо: там, де є вилка, вона стабільно бере нижню межу.
KEYWORDS_PER_GROUP = 15
# Короткі ключі — це весь обсяг групи. Без них Google ставить Low search
# volume на кожен рядок і кампанія не показується взагалі: вузька фраза на
# кшталт «harmonogram a vysledky lig» попиту не має, скільки її не додавай.
HEAD_KEYWORDS_MIN  = 3
HEAD_KEYWORDS_MAX  = 5
HEAD_KEYWORDS_LEN  = 2       # «короткий» — це 1-2 слова
# Предметні ключі — назви конкретних речей ніші, а не сама категорія:
# Назви конкретних речей ніші, а не сама категорія. Категорія без
# предметів збирає покази й майже не збирає кліків.
ITEM_KEYWORDS_MIN  = 2       # помилка нижче цього
ITEM_KEYWORDS_AIM  = "3-5"   # скільки просимо в завданні
# Заголовок без жодного слова із семантики групи не має шансів: Google
# рахує релевантність саме по збігу з запитом. Кілька заголовків
# лишаємо вільними, решта мусить перегукуватися з ключами.
HEADLINE_KEYWORD_MIN = 12    # із 15
KEYWORD_TYPES = [
    "загальні, 1-2 слова — гола назва того, що продають, увесь обсяг тут",
    "предметні, 1-2 слова, БЕЗ слова-категорії — конкретна річ чи послуга",
    "з перевагою, 2-3 слова — предмет плюс ціна, швидкість, зручність",
    "комерційні, 2-3 слова — предмет плюс дія: ціна, купити, запис, оренда",
    "довгі хвости 4+ слів — живе питання людини, а не стос іменників",
]
HEADLINE_TYPES = [
    "з ключем через макрос — підстановка самого запиту людини",
    "ключ плюс конкретика — назва дисципліни, страви, послуги",
    "ключ плюс користь — що людина отримає",
    "ключ плюс формат або процес — як це влаштовано",
    "ключ плюс дія — що зробити на сайті",
]
CALLOUTS_TOTAL     = 8
# Мінус-слова. Широка відповідність без них — це коли Google сам добирає
# запити, а платиш за них ти. Одне правило важливіше за кількість: мінус-слово
# НЕ МОЖЕ перетинатися з власними ключами, інакше воно глушить свою ж групу.
NEGATIVES_MIN      = 8
NEGATIVES_MAX      = 15
GEO_KEYWORDS_MAX   = 3       # ліміт, а не норма: менше гео — не проблема
# Стеля автоматичних раундів у черзі. Зупиняє не лічильник, а сходимість:
# поки помилок меншає, ганяємо далі; застрягло двічі поспіль — виходимо.
# Стеля потрібна лише щоб не довбати чат, який уже не лагодиться.
AUTO_ROUNDS_MAX = 6
# Скільки кампаній на один сайт робити, коли ввімкнено «кілька кампаній».
# Кожна — окрема розмова з моделлю, окремий жереб структури й ОБОВ'ЯЗКОВО
# інша назва: однакові кампанії в одному акаунті Google вважає дублями.
WHITE_BUDGET = "155-200"
WHITE_CPC = "0.01"
MANY_DEFAULT = 10
MANY_MAX = 20
LIMIT_CALLOUT  = 25
LIMIT_SITELINK = 25
LIMIT_SL_DESC  = 35
LIMIT_SNIPPET  = 25

CSV_HEADERS = [
    "Row Type", "Action", "Asset action", "Level", "Campaign", "Campaign type",
    "Status", "Budget", "Budget type", "Bid strategy type", "Networks", "Location",
    "Location intent", "Language", "EU political ads", "Ad group", "Max CPC",
    "Keyword", "Negative keyword", "Match type", "Type", "Ad type", "Asset type",
    "Final URL",
    "Headline 1", "Headline 2", "Headline 3", "Headline 4", "Headline 5",
    "Headline 6", "Headline 7", "Headline 8", "Headline 9", "Headline 10",
    "Headline 11", "Headline 12", "Headline 13", "Headline 14", "Headline 15",
    "Description 1", "Description 2", "Description 3", "Description 4",
    "Callout text", "Structured snippet header", "Structured snippet values",
    "Sitelink text", "Sitelink description 1", "Sitelink description 2",
]

# ── Системний промпт ──────────────────────────────────────────────────────────
# Живе в окремому файлі prompt_gemini.txt поруч зі скриптом — правиш у блокноті,
# і наступна ж генерація бере новий текст, перезапускати вікно не треба.
# Текст нижче — резервна копія: із неї файл створюється, якщо його немає.
# Крок підтвердження робить сам застосунок (кнопка 2), тому в промпті його немає.

DEFAULT_SYSTEM_PROMPT = """\
ВЕРСІЯ ПРОМПТА: 99
Ти — Google Ads Search-семантик. Збираєш пошукові кампанії за описом сайту.
Результат — тільки структуровані дані за схемою, без коментарів і пояснень.

КРОК 0 — РОЗБІР ОПИСУ
Перш ніж писати, визнач із опису сайту три речі.

1. ГЕО. Визначай за всім описом, а не за одним словом: рахуй згадки міст,
   країн, адрес, регіонів і бери те, чого більше. Одна випадкова згадка
   іншої країни гео не змінює. Ніколи не бери гео з попереднього запиту
   в цьому чаті.

2. МОВА = МОВА КРАЇНИ, НА ЯКУ ЙДЕ РЕКЛАМА. Не мова, якою написано опис.
   Сайт може бути англійською, а працювати на Польщу — тоді кампанія
   ПОЛЬСЬКОЮ, бо поляки шукають польською. Англомовна кампанія на
   неангломовну країну трафіку не дає.
     сайт англійською про чеський ринок  -> language cs, усе чеською
     сайт англійською про польський ринок -> language pl, усе польською

3. ЦІЛЬОВІ ОБ'ЄКТИ — 2-4 предмети попиту, які реально є на сайті.
   Пиши їх МОВОЮ КАМПАНІЇ. Це те, що людина шукає: товар, послуга,
   заклад. Не рекламні гасла й не назви розділів сайту.

БЛОК 1. ЗАБОРОНЕНІ ТЕМИ — порушення коштує рекламного акаунта
Ці теми не рекламуються ніколи, навіть якщо вони є на сайті. Якщо тема є
на сайті — рекламуєш ЛИШЕ дозволену частину бізнесу.

- Азартні ігри й ставки: казино, рулетка, покер, слоти, букмекери,
  лотереї, ставки на спорт, гральні автомати — будь-якою мовою.
- Ліки за рецептом, аптеки без ліцензії, несхвалені речовини,
  недоведені методи лікування.
- Медичні послуги, що вимагають сертифікації: лікування залежностей,
  клініки, терапія.
- Репродуктивна медицина: аборти, фертильність, контрацепція,
  тести на ІПСШ, сурогатне материнство.
- Наркотики й супутні товари. Зброя, боєприпаси, їх частини.
- Дорослий контент і послуги 18+.
- Фінансові обіцянки: швидкий дохід, крипто-схеми, бінарні опціони,
  мікропозики, гарантований прибуток.
- Підробки брендів і торгових марок.
- Мова ворожнечі, тиск на самооцінку, експлуатація людей.

УВАГА НА ДВОЗНАЧНІ СЛОВА. У деяких мовах те саме слово означає і
дозволену річ, і заборонену. Класифікатор Google не питає, що ти мав на
увазі. Якщо слово багатозначне — став уточнення поруч.
  приклад: грецьке «παιχνίδια» — це і ігри, і іграшки. Пиши
  «επιτραπέζια παιχνίδια» або «βιντεοπαιχνίδια», а не голе слово.

БЛОК 2. КЛЮЧОВІ СЛОВА
РІВНО 15 на кожну групу. Усі в широкій відповідності, чистим текстом без
лапок і дужок. Кожен ключ до 30 символів.

Склад набору:
  3-5 КОРОТКИХ ключів по 1-2 слова. Серед них обов'язково гола родова
    назва предмета — те слово, яким цей бізнес називають усі. Без таких
    ключів група збирає Low search volume і не показується.
  3-5 ПРЕДМЕТНИХ ключів по 1-2 слова — назви конкретних речей ніші,
    БЕЗ слова-категорії всередині. Категорія з прикметником предметним
    не рахується.
  3-5 ДОВГИХ ХВОСТІВ — ключ із ЧОТИРЬОХ або більше слів. Рахуй слова
    перед тим, як записати: три слова хвостом не є.
  1-3 ключі англійською.
  максимум 3 ключі з гео на групу. Це стеля, а не норма.
  решта — комерційні запити середньої довжини основною мовою.

ЩО ТАКЕ ПРАВИЛЬНИЙ КЛЮЧ
Це те, як жива людина шукає такий бізнес у Google. Не назва розділу
сайту, не позиція меню, не характеристика товару.

Заборонено:
- Гола назва міста чи країни окремим ключем. Гео завжди йде разом
  з об'єктом.
- Службові слова самі по собі: «ремонт», «сервіс», «послуги»,
  «товари», «обладнання». Працюють лише у зв'язці з цільовим об'єктом.
- Інформаційний інтент: як, чому, що таке, інструкція, форум, відгуки,
  безкоштовно, своїми руками.
- Один корінь більше трьох разів на групу, якщо це не цільовий об'єкт.

Назви чужих брендів, ігор, страв і моделей у КЛЮЧАХ дозволені: Google не
розглядає претензії щодо торгових марок у ключових словах. У заголовках
і описах їх не пиши — там вони обмежені й знімаються за скаргою.

БЛОК 3. ANTI-FLUFF
ТІЛЬКИ ТЕ, ЩО Є В ОПИСІ САЙТУ. Опис — єдине джерело фактів. Не вигадуй
нічого: ні кількостей, ні строків, ні послуг, ні переваг.
  в описі немає числа -> не пиши «понад 200», «15 років досвіду»
  в описі немає доставки -> не пиши про доставку
  в описі немає цілодобовості -> не пиши «24/7»
Людина клікне й не знайде обіцяного — це відмова, скарга й мінус до
якості сторінки.

Заборонені непідтверджувані заяви про себе: «перевірений»,
«професійний», «сертифікований», «найкращий», «номер 1», «надійний»,
«trusted», «proven», «certified». Довести їх неможливо — Google
відхиляє оголошення як введення в оману.

Заборонені статусні надбавки: VIP, «преміум», «ексклюзивний», «люкс»,
«де-люкс», premium, exclusive, luxury, deluxe. Вони нічого не описують.

Заборонені порожні заклики без предмета: «Офіційний сайт», «Дізнатися
більше», «Зареєструватися», «Увійти». Заклик має називати, ЩО саме
людина отримає.

БЛОК 4. СИМВОЛИ — ZERO TOLERANCE
У ключах, заголовках, назвах кампанії та груп, callouts, sitelinks і
значеннях snippet дозволені ТІЛЬКИ літери, цифри та пробіли.
Жодних . , - + / % ! ? ( ) : ; жодних емодзі.
Апостроф усередині слова дозволений.
Виняток один: в описах дозволені крапка, кома, дефіс і один знак оклику.

ДІАКРИТИКА — ЦЕ ЛІТЕРИ, А НЕ СИМВОЛИ. Пиши мовою кампанії грамотно й
повністю: ę ą ś ć ż ź ó ł ń, é è à ç, ě š č ř ž ů, ä ö ü ß тощо.
«wieczor» замість «wieczór» — це помилка, яку носій мови одразу помітить.

МАКРОС пишеться рівно так: {Keyword: Фолбек} — один пробіл після
двокрапки. У ліміт довжини рахується ТІЛЬКИ слово Фолбек.
Фолбек має бути осмисленою заміною, а не обрубком слова.

БЛОК 5. ОГОЛОШЕННЯ
ЗАГОЛОВКИ — рівно 15 на кожне оголошення, кожен до 30 символів,
Кожне Слово З Великої Літери.
- Від 1 до 4 заголовків містять макрос {Keyword: Фолбек}.
- Максимум 2 заголовки з гео.
- Усі 15 різні за думкою, а не за одним словом.
- Щонайменше 12 із 15 містять слово з семантики групи: Google рахує
  релевантність за збігом заголовка із запитом.

ОПИСИ — рівно 4 на кожне оголошення, довжина 60-90 символів кожен.
Коротший за 60 марнує місце у видачі, довший за 90 обрізається.
Від 1 до 2 описів містять макрос {Keyword: Фолбек}.

ЯК РАХУВАТИ ДОВЖИНУ. Це точний підрахунок, а не оцінка на око. Літери
з діакритикою — ОДИН символ кожна. Задовге не обрізають, його
ПЕРЕПИСУЮТЬ: обрубок слова гірший за перевищення ліміту. Цілься на
3-5 символів менше ліміту, щоб був запас.

БЛОК 6. РОЗШИРЕННЯ
CALLOUTS — рівно 8, кожен до 25 символів, усі різні за змістом.

STRUCTURED SNIPPETS — 1 або 2.
ЗАГОЛОВОК (поле type) — це технічний перелік Google, а НЕ текст
оголошення. Пиши його РІВНО англійською і НІКОЛИ не перекладай:
Amenities, Brands, Courses, Degree programs, Destinations, Featured
hotels, Insurance coverage, Models, Neighborhoods, Service catalog,
Shows, Styles, Types.
Перекладений заголовок завантажувач Google не знаходить — рядок падає
з помилкою «Item not found».
Мовою кампанії пишуться ЛИШЕ значення: рівно 3 значення до 25 символів.

SITELINKS — генеруй тільки якщо це прямо задано в завданні на запуск.
Кожен: підпис до 25 символів і два описи до 35 символів.

НАЗВИ
Назва кампанії — 2-4 слова. Назва групи — 2-3 слова, інша за назву
кампанії. Без слів «кампанія», «реклама», «пошук». Без підкреслень.

ФОРМАТ ВІДПОВІДІ
Тільки дані за схемою, одним блоком ```json```.
Без пояснень, без таблиць, без CSV, без коду, без чек-листів і без
запитань користувачу.
"""


# ── Тема Aurora ───────────────────────────────────────────────────────────────

# З Aurora беремо рівно чотири кольори і градієнт — більше нічого. Фон, поля
# й текст лишаються нейтральними: інакше колір «розповзається» по всьому вікну
# і читати важко.
AURORA = ("#7a34e6", "#d6389e", "#3b74ed")     # фіолетовий -> маджента -> синій
GOLD = "#e8a531"

THEMES = {
    "dark": {
        "bg": "#100c1c", "surface": "#1a1430", "surface2": "#20193a",
        "ink": "#f2ecff", "muted": "#a99fc4", "line": "#2c2444",
        "field": "#20193a", "field_ink": "#f2ecff",
    },
}
# На темному тлі темно-червоний нечитний, тому помилки світлішого відтінку.
SEMANTIC = {"success": "#4cc98a", "danger": "#ff6b6b",
            "warning": GOLD, "info": AURORA[2], "gold": GOLD}


def lerp_hex(c1, c2, t):
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def aurora_at(t):
    """Колір градієнта Aurora у точці t від 0 до 1."""
    if t <= 0.5:
        return lerp_hex(AURORA[0], AURORA[1], t * 2)
    return lerp_hex(AURORA[1], AURORA[2], (t - 0.5) * 2)


# Тема clam малює позначку в чекбоксі ХРЕСТИКОМ, і незрозуміло, це «увімкнено»
# чи «закрито». Замінюємо індикатор власними картинками: порожній квадрат —
# вимкнено, фіолетовий із білою галочкою — увімкнено.
_CHECK_IMAGES = []          # PhotoImage треба тримати, інакше збирач їх з'їсть

# Ламана лінія галочки в квадраті 16×16.
_TICK = [(4, 8), (5, 9), (6, 10), (7, 11),
         (8, 10), (9, 9), (10, 8), (11, 7), (12, 6)]


def _install_check_images(style, t):
    size, gap = 16, 6          # gap — відступ до підпису, малюємо фоном
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
    for x, y in _TICK:                 # галочка у два пікселі завтовшки
        on.put("#ffffff", to=(x, y))
        on.put("#ffffff", to=(x, y - 1))
    _CHECK_IMAGES.extend((off, on))

    try:
        style.element_create("Aurora.indicator", "image", on,
                             ("!selected", off), sticky="", border=0)
    except tk.TclError:
        return                          # елемент уже створено в цій сесії Tk
    style.layout("TCheckbutton", [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Aurora.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                ("Checkbutton.label", {"sticky": "nswe"})]})]})])


def apply_theme(root, t):
    """Перефарбовує ttk у кольори Aurora.

    Стандартні теми Windows малюють кнопки й поля засобами системи і колір
    ігнорують — тому переходимо на clam, єдину вбудовану, яку видно наскрізь.
    """
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
                   "TNotebook", "TSeparator"):
        style.configure(widget, background=t["bg"])
    style.configure("TLabel", foreground=t["ink"])
    style.configure("TSeparator", background=t["line"])
    style.configure("TCheckbutton", foreground=t["ink"], padding=(0, 2))
    style.map("TCheckbutton", background=[("active", t["bg"])])
    style.configure("TRadiobutton", foreground=t["ink"],
                    indicatorcolor=t["field"], padding=(0, 2))
    style.map("TRadiobutton", background=[("active", t["bg"])],
              indicatorcolor=[("selected", AURORA[0]), ("!selected", t["field"])])
    _install_check_images(style, t)

    style.configure("TButton", background=t["surface2"], foreground=t["ink"],
                    bordercolor=t["line"], relief="flat", padding=(10, 4))
    style.map("TButton",
              background=[("pressed", AURORA[1]), ("active", AURORA[0])],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff")],
              bordercolor=[("active", AURORA[0])])

    style.configure("TEntry", fieldbackground=t["field"], foreground=t["field_ink"],
                    insertcolor=t["field_ink"], bordercolor=t["line"],
                    padding=4)
    style.map("TEntry", bordercolor=[("focus", AURORA[0])])
    style.configure("TCombobox", fieldbackground=t["field"], background=t["surface2"],
                    foreground=t["field_ink"], arrowcolor=t["ink"],
                    bordercolor=t["line"], padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", t["field"]), ("disabled", t["surface"])],
              foreground=[("readonly", t["field_ink"]), ("disabled", t["muted"])],
              bordercolor=[("focus", AURORA[0])])
    # Випадний список у Combobox — це класичний tk.Listbox, ttk його не бачить.
    root.option_add("*TCombobox*Listbox.background", t["surface2"])
    root.option_add("*TCombobox*Listbox.foreground", t["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", AURORA[0])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style.configure("TNotebook.Tab", background=t["bg"], foreground=t["muted"],
                    bordercolor=t["line"], padding=(16, 7))
    style.map("TNotebook.Tab",
              background=[("selected", t["surface"]), ("active", t["surface2"])],
              foreground=[("selected", AURORA[0])])

    # Таблиця заготовки (ttk.Treeview): темні рядки, фіолетове виділення,
    # заголовки колонок трохи світліші — як решта вікна.
    style.configure("Treeview", background=t["field"], fieldbackground=t["field"],
                    foreground=t["field_ink"], bordercolor=t["line"],
                    borderwidth=1, relief="solid", rowheight=28)
    style.map("Treeview", background=[("selected", AURORA[0])],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=t["surface2"],
                    foreground=t["ink"], bordercolor=t["line"], relief="flat",
                    padding=(6, 5))
    style.map("Treeview.Heading", background=[("active", t["surface2"])])

    for bar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(bar, background=t["surface2"], troughcolor=t["bg"],
                        bordercolor=t["bg"], arrowcolor=t["muted"], relief="flat")
        style.map(bar, background=[("active", AURORA[0])])
    return style


# Окремої шапки з градієнтом немає навмисно: назва застосунку вже є в заголовку
# вікна, а смуга займала місце й нічого не додавала. Aurora лишається в кнопках,
# активній вкладці й фокусі полів.


# ── Бюджет і ставка: одне число, діапазон або список ──────────────────────────
# "12"            -> завжди 12
# "10-20"         -> випадкове з проміжку, включно
# "10;12;15"      -> по черзі, позиція переживає перезапуск
# Кома як десятковий роздільник дозволена на вводі, у файл завжди йде крапка.

def _num(text, decimals):
    value = float(str(text).strip().replace(",", "."))
    return round(value, decimals)


def resolve_amount(spec, decimals, counter_key, cfg):
    """Повертає (значення, пояснення) для журналу й мінізвіту."""
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("порожнє значення")

    if ";" in spec:
        items = [s for s in (p.strip() for p in spec.split(";")) if s]
        if not items:
            raise ValueError("порожній список")
        pos = int(cfg.get(counter_key, 0)) % len(items)
        cfg[counter_key] = (pos + 1) % len(items)
        return _num(items[pos], decimals), f"список, позиція {pos + 1} з {len(items)}"

    if "-" in spec.lstrip("-"):
        left, right = spec.split("-", 1) if not spec.startswith("-") else (spec, "")
        low, high = _num(left, decimals), _num(right, decimals)
        if low > high:
            low, high = high, low
        step = 10 ** -decimals
        lo_i, hi_i = round(low / step), round(high / step)

        def draw():
            return round(random.randrange(lo_i, hi_i + 1) * step, decimals)

        # Рівномірний випадок цілком законно видає 12, 12, 12, 12 поспіль:
        # на діапазоні 10-15 це кожен 1296-й прогін. Рандом справний, але
        # виглядає зламаним, тому просто не повторюємо попереднє значення.
        last_key = counter_key + "_last"
        last = cfg.get(last_key)
        picked = draw()
        if hi_i > lo_i:
            for _ in range(12):
                if picked != last:
                    break
                picked = draw()
        cfg[last_key] = picked
        return picked, (f"випадково з {format_amount(low, decimals)}"
                        f"-{format_amount(high, decimals)}")

    return _num(spec, decimals), "фіксоване"


def format_amount(value, decimals):
    return f"{value:.{decimals}f}" if decimals else str(int(value))


# ── Історія генерацій ─────────────────────────────────────────────────────────
# Кожен запуск лягає окремою текою в "Історія": сира відповідь моделі, розібрана
# чернетка, підсумок перевірки й службові дані. Потрібне для трьох речей —
# подивитися, що генерувалося цьому клієнту раніше, відлагодити промпт і
# врятувати відповідь, якщо розбір упав.

def history_slug(text):
    slug = re.sub(r"[^\w\s-]", "", text, flags=re.U).strip()
    slug = re.sub(r"\s+", "-", slug)
    return (slug or "bez-nazvy")[:60]


def save_history(entry):
    """У цій збірці журнал не ведеться. Виклики лишились на місці,
    щоб не різати їх по всьому файлу."""
    return ""


def _save_history_off(entry):
    """Пише один запуск на диск. Ніколи не кидає виняток — це лише журнал."""
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        name = history_slug(entry.get("campaign_name") or entry.get("url") or "")
        # Два запуски в одну секунду не мають затирати один одного.
        folder = os.path.join(HISTORY_DIR, f"{stamp}_{name}")
        suffix = 2
        while os.path.exists(folder):
            folder = os.path.join(HISTORY_DIR, f"{stamp}_{name}-{suffix}")
            suffix += 1
        os.makedirs(folder)

        raw = entry.pop("raw_response", "")
        if raw:
            with open(os.path.join(folder, "raw_response.txt"), "w",
                      encoding="utf-8") as f:
                f.write(raw)

        draft = entry.pop("draft", None)
        if draft is not None:
            with open(os.path.join(folder, "draft.json"), "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)

        with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return folder
    except Exception:
        return ""


def read_history_entry(folder):
    """Читає один запуск із журналу. Повертає None, якщо чернетки там немає."""
    path = os.path.join(HISTORY_DIR, folder)
    try:
        with open(os.path.join(path, "run.json"), "r", encoding="utf-8") as f:
            run = json.load(f)
    except Exception:
        return None
    draft = None
    try:
        with open(os.path.join(path, "draft.json"), "r", encoding="utf-8") as f:
            draft = json.load(f)
    except Exception:
        pass
    if not draft or not draft.get("ad_groups"):
        return None            # збій або файл лише з оголошеннями
    raw = ""
    try:
        with open(os.path.join(path, "raw_response.txt"), "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        pass
    variant = run.get("варіант") or {}
    # Старі записи не зберігали wants — відновлюємо з варіанта запуску.
    wants = run.get("wants") or {
        "sitelinks": bool(variant.get("sitelinks")),
        "callouts": bool(variant.get("callouts", True)),
        "negatives": bool(variant.get("negatives", True)),
        "snippets": bool(variant.get("snippets_on", True)),
        "aggregator": bool(variant.get("aggregator")),
        "soft": True,
    }
    return {"folder": folder, "path": path, "run": run, "draft": draft,
            "raw": raw, "variant": variant, "wants": wants,
            "when": run.get("час", folder[:19]),
            "campaign": run.get("campaign_name") or draft.get("campaign_name", ""),
            "url": run.get("url", ""), "mode": run.get("режим", ""),
            "user_text": run.get("запит", ""),
            "errors": run.get("помилок") or [],
            "warnings": run.get("попереджень") or []}


def list_history(limit=40):
    if not os.path.isdir(HISTORY_DIR):
        return []
    items = [d for d in os.listdir(HISTORY_DIR)
             if os.path.isdir(os.path.join(HISTORY_DIR, d))]
    return sorted(items, reverse=True)[:limit]


# ── Варіант запуску: структура й акцент щоразу інші ───────────────────────────
# Однаковий вхід дає однаковий вихід, тому структуру на кожен запуск обираємо
# жеребкуванням і передаємо моделі окремим завданням. Це дає унікальність,
# не чіпаючи жодного правила якості.

STRUCTURES = [
    ("одна група, у ній ДВА різних оголошення "
     "(два незалежні набори по 15 заголовків і 4 описи)", 1, 2),
    ("дві групи, у кожній по одному оголошенню", 2, 1),
    ("дві групи, у першій ДВА оголошення, у другій одне", 2, 1),
    ("одна група з одним оголошенням", 1, 1),
]
SOLO_STRUCTURE = STRUCTURES[3]        # одна група, одне оголошення

# Назва кампанії щоразу виходила однаковою: варіативність підмішувалась у
# структуру й акцент, а до нейменгу не доходила. Однаковий вхід — однаковий
# вихід, і файл щоразу перезаписував попередній. Тому кут назви теж жеребкуємо.
NAME_ANGLES = [
    "назви за головним об'єктом попиту",
    "назви за форматом послуги",
    "назви за наміром людини, яка шукає",
    "назви за категорією товару чи послуги",
    "назви за аудиторією, якій це адресовано",
    "назви за ключовою перевагою, яку дає бізнес",
    "назви за гео, якщо воно є в описі",
    "назви за способом отримання послуги",
]

# Схожі сайти дають схожі тексти: вхід той самий — вихід той самий. Тому
# крім акценту жеребкуємо ще й граматичну форму заголовків. Це не впливає
# на зміст, але ламає звичку моделі писати ту саму фразу вкотре.
PHRASINGS = [
    "будуй заголовки переважно від іменника: «Порівняння Умов»",
    "будуй заголовки переважно від дієслова: «Порівняй Умови»",
    "чергуй іменникові та дієслівні заголовки приблизно порівну",
    "частіше став означення попереду: «Чіткі Критерії Вибору»",
    "тримай заголовки короткими, по два-три слова",
]

# Нейтральні заголовки задаємо ПАТЕРНАМИ, а не готовими фразами. Готовий банк
# дав би однакові тексти всім клієнтам — саме те, чого ми уникаємо. Патерни
# витягнуті з робочої частини клієнтського файла заголовків: там, де фраза
# щось каже про процес і не є ні заявою про себе, ні порожнім закликом.
NEUTRAL_PATTERNS = [
    "про зрозумілість процесу",
    "про повноту добірки",
    "про наступний крок",
    "про відповіді на типові питання",
    "про економію зусиль",
]

# Калаути й сніпети — найшаблонніша частина кампанії: коротко, по три-вісім
# слів, і модель щоразу тягне ті самі фрази. У чотирьох файлах із п'яти
# повторився один і той самий сніпет. Тому і їм задаємо кут.
CALLOUT_ANGLES = [
    "про склад і обсяг того, що людина отримує",
    "про умови й прозорість",
    "про формат і зручність користування",
    "про строки й швидкість",
    "про охоплення: скільки варіантів, наскільки повно",
    "про те, як влаштована перевірка й оновлення",
]

SNIPPET_ANGLES = [
    "перелічи напрями роботи",
    "перелічи критерії, за якими порівнюєш",
    "перелічи формати подачі інформації",
    "перелічи категорії того, що є на сайті",
    "перелічи етапи, які проходить людина",
]

ACCENTS = [
    "зроби акцент на швидкості та доступності",
    "зроби акцент на форматі й умовах обслуговування",
    "зроби акцент на досвіді та надійності",
    "зроби акцент на зручності звернення",
    "зроби акцент на самому об'єкті попиту, без прикрас",
]


def pick_variant(aggregator=False):
    """Жеребкує структуру кампанії й акцент для цього запуску.

    Агрегатору структуру не жеребкуємо: у нього всі ключі про одне — підбір
    і порівняння платформ. Ділити їх на дві групи означає плодити дублі й
    тягнути другий набір текстів, який нема чим наповнити.
    """
    structure, groups, ads = (SOLO_STRUCTURE if aggregator
                              else random.choice(STRUCTURES))
    return {
        "structure": structure,
        "groups": groups,
        "ads": ads,
        "accent": random.choice(ACCENTS),
        "name_angle": random.choice(NAME_ANGLES),
        # Гео в назві кампанії — це звичка агенцій, а не вимога Google.
        # «Гео + категорія» у десяти акаунтах поспіль читається як один
        # почерк, тому найчастіше жеребкуємо назву взагалі без гео.
        "geo_in_name": random.choices(
            ["БЕЗ гео в назві", "гео першим словом", "гео всередині назви",
             "гео останнім словом"], weights=[5, 2, 2, 2])[0],
        "name_words": random.randint(2, 4),
        "phrasing": random.choice(PHRASINGS),
        # Частина заголовків говорить про користь без назви вертикалі. Це не
        # маскування: решта заголовків прямо називає предмет, тому оголошення
        # в цілому лишається зрозумілим.
        "neutral_patterns": random.sample(NEUTRAL_PATTERNS, random.randint(3, 5)),
        "callout_angle": random.choice(CALLOUT_ANGLES),
        "snippet_angle": random.choice(SNIPPET_ANGLES),
        "dki_headlines": random.randint(1, 4),
        "dki_descriptions": random.randint(1, 2),
        "sitelinks": False,          # перевизначається з інтерфейсу
        "snippets": random.randint(1, 2),
        "snippet_level": random.choice(["campaign", "ad group"]),
    }


AGGREGATOR_BRIEF = """РЕЖИМ АГРЕГАТОР — ЦЕЙ БЛОК СКАСОВУЄ БЛОК 1 СИСТЕМНОЇ ІНСТРУКЦІЇ.
Акаунт пройшов сертифікацію Google Ads на рекламу азартних ігор, домен
схвалений. Тому заборона на гральну тематику ТУТ НЕ ДІЄ: ставки, букмекери,
бонуси, кешаут, коефіцієнти, порівняння платформ — це і є предмет реклами.
Пиши про нього прямо, без евфемізмів і без спроб замаскувати тему.

Натомість діють правила, за порушення яких знімають сертифікацію:
- ЖОДНИХ обіцянок виграшу, гарантованого доходу чи заробітку. Ставки — це
  дозвілля, а не джерело грошей. Заборонено: «гарантований виграш»,
  «легкі гроші», «заробіток на ставках», «без ризику», «gagner à coup sûr»,
  «revenus garantis», «sure bet», «risk-free».
- ЖОДНОГО натяку на неповнолітніх: ні слів «діти», «підлітки», «сім'я»,
  «juniors», ні дитячої стилістики, ні персонажів мультфільмів.
- Аудиторія лише повнолітня, але писати про це в оголошенні НЕ треба:
  «18+», «для дорослих», «відповідальна гра» — це маркери вертикалі, а не
  користь для людини. Вони обов'язкові НА САЙТІ й лишаються там.
- Не тисни на азарт і не змальовуй гру як спосіб вирішити фінансові проблеми.
- Не вигадуй розміри бонусів, коефіцієнти й умови: бери лише те, що є в описі.
- ЖОДНОЇ медичної та навколомедичної лексики: «консультація», «допомога»,
  «підтримка залежним», «лікування», «терапія», «здоров'я», «клініка»,
  «consultation», «traitement», «aide», «helpline». Поруч із гральною темою
  вони читаються як лікування залежності — це стан здоров'я, а Google
  забороняє будувати на ньому рекламу (Health in personalized advertising).
  Реальний випадок: сніпет «consultation options jeu» завалив завантаження.

"""


def variant_brief(v):
    """Завдання на запуск: тільки те, що перевіряє валідатор. Числа
    продубльовані явно — усе, чого тут немає, модель схильна ігнорувати."""
    sitelinks_line = ("Sitelinks: рівно 6 з двома описами кожен."
                      if v.get("sitelinks")
                      else "Sitelinks: НЕ ГЕНЕРУЙ ЖОДНОГО, поверни порожній масив [].")
    callouts_line = (f"Callouts: рівно {CALLOUTS_TOTAL}, кожен до "
                     f"{LIMIT_CALLOUT} символів, усі різні."
                     if v.get("callouts", True)
                     else "Callouts: НЕ ГЕНЕРУЙ ЖОДНОГО, поверни порожній масив [].")
    snippets_line = (
        f"Structured snippets: {v['snippets']} шт., поле level у кожного = "
        f"\"{v['snippet_level']}\". Поле type — АНГЛІЙСЬКОЮ зі списку Google, "
        f"НЕ перекладай: перекладений заголовок падає з «Item not found». "
        f"У кожному рівно 3 значення до {LIMIT_SNIPPET} символів мовою кампанії."
        if v.get("snippets_on", True)
        else "Structured snippets: НЕ ГЕНЕРУЙ ЖОДНОГО, поверни порожній масив [].")
    return (
        (AGGREGATOR_BRIEF if v.get("aggregator") else "") + SOFT_BRIEF +
        "ЗАВДАННЯ НА ЦЕЙ ЗАПУСК (обов'язкове до виконання):\n"
        "- ГЕО з опису сайту, за вагою згадок, а не за одним словом. МОВА = "
        "мова цієї країни, а не мова, якою написано опис.\n"
        "- Назва кампанії: 2-4 слова, по суті, без слів «кампанія», "
        "«реклама», «пошук».\n"
        "- Назва групи: 2-3 слова, інша за назву кампанії.\n"
        f"- Структура: {v['structure']}.\n"
        f"- Ключів: рівно {KEYWORDS_PER_GROUP} на КОЖНУ групу.\n"
        f"- КОРОТКИХ ключів по 1-2 слова: {HEAD_KEYWORDS_MIN}-{HEAD_KEYWORDS_MAX} "
        f"на групу, і серед них гола родова назва предмета. Цільові об'єкти "
        f"в JSON пиши мовою кампанії.\n"
        f"- ПРЕДМЕТНИХ ключів: {ITEM_KEYWORDS_AIM} на групу — назви конкретних "
        f"речей ніші по 1-2 слова, БЕЗ слова-категорії всередині.\n"
        "- Довгих хвостів: 3-5 на групу. Довгий хвіст = ключ із 4+ СЛІВ.\n"
        "- Жодного ключа з самої лише назви міста чи країни.\n"
        f"- Гео в ключах: МАКСИМУМ {GEO_KEYWORDS_MAX} на групу. "
        f"Гео в заголовках: максимум 2 з 15.\n"
        f"- Макрос {{Keyword: Фолбек}} рівно в {v['dki_headlines']} заголовках "
        f"із 15 і рівно в {v['dki_descriptions']} описах із 4.\n"
        f"- Заголовків 15, кожен до {LIMIT_HEADLINE} символів. Щонайменше "
        f"{HEADLINE_KEYWORD_MIN} із 15 містять слово з семантики групи.\n"
        f"- Описів 4, довжина кожного {DESC_MIN}-{LIMIT_DESC} символів.\n"
        "- ФАКТИ ТІЛЬКИ З ОПИСУ. Числа, строки, послуги й переваги бери "
        "виключно звідти. Заборонені VIP, преміум, ексклюзив, люкс.\n"
        f"- {callouts_line}\n"
        f"- {sitelinks_line}\n"
        f"- {snippets_line}\n"
    )


DEFAULT_AGG_PROMPT = """\
ВЕРСІЯ ПРОМПТА: 2
Ти — PPC-спеціаліст, який робить пошукові кампанії Google Ads для сайтів-
агрегаторів і порівнянь у сфері азартних ігор та ставок. Акаунт ПРОЙШОВ
сертифікацію Google Ads, домен схвалений. Твоє завдання — зробити кампанію,
яка ПРАЦЮЄ: пройде модерацію і не потягне за собою зняття сертифікації.

Приклади нижче — з різних ніш і країн. Це ілюстрації принципу, а не зразки
для копіювання. Бери ніші, мову й гео виключно з опису, який тобі дали.

КРОК 0. РОЗБІР ВХІДНИХ
НАЗВА КАМПАНІЇ — 3-4 слова, по суті. Назва групи — 2-3 слова, інша за назву
кампанії. Не тягни в назву все підряд.
ГЕО Й МОВУ ВИЗНАЧАЙ ПО ВСЬОМУ ОПИСУ, А НЕ ПО ОДНОМУ СЛОВУ. Рахуй, чого в
тексті більше: згадки країни й народності, міста, адреса в підвалі,
телефонний код, валюта, місцевий регулятор, мова самого опису. Одна випадкова
згадка іншої країни нічого не важить. Ніколи не бери гео з попереднього
запиту в цьому чаті — кожен сайт розглядай з нуля.
Визнач із опису: що це за сайт (порівняння операторів, огляди, рейтинг,
гайд), які саме вертикалі згадані (ставки на спорт, покер, казино, скачки),
мову сайту й країну. МОВА ОГОЛОШЕНЬ = МОВА КРАЇНИ, а не мова, якою написано
опис: сайт англійською про польський ринок означає кампанію ПОЛЬСЬКОЮ.
Location = НАЗВА КРАЇНИ АНГЛІЙСЬКОЮ і тільки вона: Czechia, Poland,
Netherlands, France. Місто й регіон у це поле не йдуть.

БЛОК 1. ЩО МОЖНА І ЧОГО НЕ МОЖНА
ЖОДНОЇ медичної та навколомедичної лексики: «консультація», «допомога»,
«лікування», «терапія», «здоров'я», «клініка», «залежність», «consultation»,
«traitement», «aide», «helpline», «support group». Поруч із гральною темою
вони читаються як лікування ігрової залежності, тобто стан здоров'я, а на
ньому Google забороняє будувати рекламу — Health in personalized advertising.
Реальний випадок: сніпет «consultation options jeu» завалив завантаження
файла з порушенням політики.

Гральна тематика ДОЗВОЛЕНА. Пиши прямо: ставки, букмекери, коефіцієнти,
бонуси, кешаут, порівняння платформ. Не маскуй тему евфемізмами — маскування
Google карає жорсткіше, ніж саму тематику.

Заборонено абсолютно, це знімає сертифікацію:
  обіцянки виграшу чи гарантованого доходу;
  подача ставок як способу заробити чи вирішити фінансові проблеми;
  «без ризику», «легкі гроші», «sure bet», «gagner à coup sûr»;
  будь-яка згадка неповнолітніх і будь-яка дитяча стилістика;
  тиск на азарт, заклики «відігратися», «останній шанс»;
  вигадані розміри бонусів, коефіцієнти й умови — тільки те, що є в описі;
  чужі торгові марки в заголовках, якщо їх немає в описі як предмет порівняння.

Обов'язково: аудиторія лише повнолітня. Якщо на сайті є розділ про
відповідальну гру — це доречна тема для одного заголовка чи опису.

БЛОК 2. МІСЦЕВЕ РЕГУЛЮВАННЯ
Сертифікація Google — не індульгенція. У багатьох країнах реклама азартних
ігор вимагає місцевої ліцензії, попереджувального повідомлення чи взагалі
заборонена. Не вигадуй ліцензій, номерів і регуляторів, яких немає в описі.
Якщо в описі є телефон допомоги гравцям чи згадка регулятора — можеш на це
спиратися, але не вставляй телефон у текст оголошення.

БЛОК 3. КЛЮЧОВІ СЛОВА
РІВНО 15 на кожну групу, широка відповідність, чистим текстом без дужок і
лапок. Склад набору:
  3-5 КОРОТКИХ КЛЮЧІВ по 1-2 слова — основа групи. Це сам предмет попиту
    простими словами, і серед них обов'язково гола родова назва вертикалі.
    Вузькі фрази без обсягу Google позначає Low search volume і не показує
    взагалі — обсяг дають саме короткі родові запити;
  3-5 ПРЕДМЕТНИХ КЛЮЧІВ — назви конкретних речей ніші по 1-2 слова, БЕЗ
    слова-категорії: дисципліни, види ставок, назви ігор. Категорія без
    предметів збирає покази й не збирає кліків. У ключах такі назви
    дозволені, у заголовках і описах чужих марок не пиши;
  3-5 ДОВГИХ ХВОСТІВ — ключ із ЧОТИРЬОХ і більше слів;
  1-3 ключі англійською;
  решта — комерційні запити середньої довжини.
Кожен ключ містить предмет попиту: порівняння, огляд, рейтинг, бонус,
конкретну вертикаль. Голе гео ключем не буває. Гео максимум у 3 ключах.
Інформаційні запити («як працює», «що таке», «форум», «безкоштовно») не беремо.

БЛОК 4. АНТИВОДА
ТІЛЬКИ ТЕ, ЩО Є В ОПИСІ САЙТУ. Опис — це єдине джерело фактів. Не вигадуй
нічого, чого там немає: ні кількостей, ні строків, ні послуг, ні переваг.
  немає в описі числа -> не пиши «понад 200 ігор», «15 років досвіду»
  немає в описі доставки -> не пиши про доставку
  немає в описі знижки -> не пиши про знижку
Людина клікне й не знайде обіцяного — це і відмова, і скарга, і мінус до
якості сторінки. Якщо описом нічого конкретного не сказано, пиши про те,
що там є, простими словами, а не додумуй.
Заборонені непідтверджувані заяви про себе: «перевірений», «професійний»,
«сертифікований», «найкращий», «номер 1», «надійний». Google відхиляє такі
оголошення як введення в оману.
Заборонені статусні надбавки: VIP, «преміум», «ексклюзивний», «люкс»,
«де-люкс». Вони нічого не описують, лише піднімають градус, і Google читає
їх як обіцянку переваги, якої ніхто не підтверджував.
Заборонені порожні заклики без предмета: «Офіційний сайт», «Дізнатися
більше», «Зареєструватися». Заклик має називати, що людина отримає:
«Порівняй коефіцієнти», «Дивись рейтинг платформ».

БЛОК 5. СИМВОЛИ
Жодних символів поза буквами, цифрами й пробілом. Діакритика — це літери, а
не символи: é, č, ł, ő пиши як є. В описах додатково дозволені крапка, кома,
дефіс і не більше одного знака оклику на весь опис.

БЛОК 6. ОГОЛОШЕННЯ
15 заголовків до 30 символів у Capitalized Case:
  1-5 — суть сайту й предмет порівняння;
  6-10 — реальна користь: вибір, умови, зручність, прозорість;
  11-15 — заклик із предметом.
4 описи по 60-90 символів. Макрос {Keyword: Фолбек} рівно в стількох
заголовках і описах, скільки замовлено в завданні на запуск. У фолбек
пиши осмислений текст, він рахується в ліміт.

БЛОК 7. РОЗШИРЕННЯ
Callouts, structured snippets і sitelinks — рівно стільки, скільки замовлено
в завданні на запуск. Якщо замовлено нуль — повертай порожній масив.
Значення сніпетів і калаутів мусять стосуватися САМЕ цього сайту. Універсальні
набори, які пасують будь-якому агрегатору, не годяться: вони однакові в усіх
кампаніях і одразу видно, що текст не про конкретний бізнес.
Жодної медичної лексики в розширеннях — див. Блок 1.

БЛОК 8. РІЗНОМАНІТНІСТЬ
Тексти не повторюють один одного і не є перестановкою тих самих слів.
Дотримуйся структури й акценту із завдання на запуск.
"""


PROMPT_VERSION_RE = re.compile(r"ВЕРСІЯ ПРОМПТА:\s*(\d+)")


def prompt_version(text):
    found = PROMPT_VERSION_RE.search(text or "")
    return int(found.group(1)) if found else 0


def ensure_prompt_file(aggregator=False):
    """Тримає файл промпта в актуальному стані.

    Промпт читається з диска, а вбудований у програму — лише резервна копія.
    Через це виправлення правил роками лежали б у коді й не доїжджали до
    роботи: файл, створений колись давно, перекриває їх. Тому в промпті є
    рядок «ВЕРСІЯ ПРОМПТА: N»; якщо у файлі версія старіша за вбудовану,
    файл оновлюємо, а попередній зберігаємо поруч — раптом там були правки
    руками.
    """
    path = PROMPT_FILE_AGG if aggregator else PROMPT_FILE
    fallback = DEFAULT_AGG_PROMPT if aggregator else DEFAULT_SYSTEM_PROMPT
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(fallback)
            return path
        with open(path, "r", encoding="utf-8") as f:
            current = f.read()
        if prompt_version(current) < prompt_version(fallback):
            base, ext = os.path.splitext(path)
            with open(f"{base}_попередній{ext}", "w", encoding="utf-8") as f:
                f.write(current)
            with open(path, "w", encoding="utf-8") as f:
                f.write(fallback)
    except Exception:
        pass
    return path


def load_system_prompt(aggregator=False):
    """Читає промпт із файлу перед кожною генерацією."""
    try:
        with open(ensure_prompt_file(aggregator), "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            return text
    except Exception:
        pass
    return DEFAULT_AGG_PROMPT if aggregator else DEFAULT_SYSTEM_PROMPT


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "campaign_name":  {"type": "STRING"},
        "website":        {"type": "STRING"},
        "location":       {"type": "STRING"},
        "language":       {"type": "STRING"},
        "target_objects": {"type": "ARRAY", "items": {"type": "STRING"}},
        "ad_groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name":     {"type": "STRING"},
                    "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "ads": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "headlines":    {"type": "ARRAY", "items": {"type": "STRING"}},
                                "descriptions": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["headlines", "descriptions"],
                        },
                    },
                },
                "required": ["name", "keywords", "ads"],
            },
        },
        "sitelinks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "text":         {"type": "STRING"},
                    "description1": {"type": "STRING"},
                    "description2": {"type": "STRING"},
                },
                "required": ["text", "description1", "description2"],
            },
        },
        "callouts":  {"type": "ARRAY", "items": {"type": "STRING"}},
        "negatives": {"type": "ARRAY", "items": {"type": "STRING"}},
        "snippets": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type":   {"type": "STRING"},
                    "values": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "level":  {"type": "STRING", "enum": ["campaign", "ad group"]},
                },
                "required": ["type", "values", "level"],
            },
        },
    },
    "required": ["campaign_name", "website", "location", "language",
                 "target_objects", "ad_groups", "sitelinks", "callouts", "snippets"],
}

# ── Конфіг ────────────────────────────────────────────────────────────────────

# ── Посадкова сторінка ────────────────────────────────────────────────────────
# Найдорожча помилка — не текст оголошення, а сторінка за посиланням. Мертвий
# домен, редирект кудись убік або вміст, що не збігається з оголошенням, —
# це відхилення, а повторно й блокування акаунта. Тому сторінку качаємо
# і дивимось, що там насправді.

TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
ANY_TAG_RE = re.compile(r"<[^>]+>")


def page_text(html, limit=20000):
    """Видимий текст сторінки без розмітки."""
    text = TAG_RE.sub(" ", html or "")
    text = ANY_TAG_RE.sub(" ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def fetch_landing(url, timeout=15):
    """Качає посадкову. Ніколи не кидає: недоступність сайту не повинна
    зривати генерацію, вона має стати зауваженням."""
    out = {"ok": False, "status": 0, "final_url": "", "text": "", "error": ""}
    if not (url or "").startswith("http"):
        out["error"] = "посилання не починається з http"
        return out
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0 Safari/537.36"),
        "Accept-Language": "en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(400000)
            out["status"] = resp.status
            out["final_url"] = resp.geturl()
        charset = "utf-8"
        head = raw[:2000].decode("latin-1", "ignore").lower()
        found = re.search(r"charset=[^A-Za-z0-9]*([A-Za-z0-9_-]+)", head)
        if found:
            charset = found.group(1)
        out["text"] = page_text(raw.decode(charset, "ignore"))
        out["ok"] = 200 <= out["status"] < 300 and len(out["text"]) > 40
        if not out["ok"] and not out["error"]:
            out["error"] = f"сторінка віддала {out['status']}, тексту {len(out['text'])} символів"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def domain_of(url):
    return re.sub(r"^www\.", "",
                  (re.sub(r"^https?://", "", url or "").split("/")[0] or "").lower())


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── Gemini ────────────────────────────────────────────────────────────────────

# Gemini API зрідка відмовляє не через нас: 429 — забагато запитів (на
# безкоштовному ключі черга впирається в це швидко), 5xx — сервер упав або
# перевантажений. Раніше одна така відмова валила рядок у «збій», і людина
# перезапускала чергу руками. Тепер чекаємо й пробуємо знову.
class RateLimited(RuntimeError):
    """429 у режимі «Авто»: замість паузи — наступна модель."""
    def __init__(self, msg, daily, wait):
        super().__init__(msg)
        self.daily, self.wait = daily, wait


class ModelMissing(RuntimeError):
    """404: такої моделі в цього ключа немає."""


RETRY_CODES = {429, 500, 502, 503, 504}
API_TRIES = 5
API_WAITS = (10, 30, 60, 90)


def _retry_delay(err_body, headers, attempt):
    """Скільки чекати перед наступною спробою.

    Google сам підказує: заголовок Retry-After або поле retryDelay у тілі
    помилки («23s»). Його й слухаємо; немає — наростаюча пауза.
    """
    try:
        ra = (headers or {}).get("Retry-After")
        if ra:
            return max(5, min(120, int(float(ra))))
    except Exception:
        pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', err_body or "")
    if m:
        return max(5, min(120, int(float(m.group(1))) + 1))
    return API_WAITS[min(attempt - 1, len(API_WAITS) - 1)]


def _request(url, payload=None, api_key="", timeout=120, on_wait=None,
             retry_429=True):
    """Запит до Gemini API з повтором при тимчасових відмовах.

    on_wait(коротко, докладно) — щоб людина бачила, що програма чекає,
    а не зависла: у черзі це текст стану рядка.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = ""
    for attempt in range(1, API_TRIES + 1):
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data else "GET")
        req.add_header("x-goog-api-key", api_key)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(body)["error"]["message"]
            except Exception:
                msg = body[:400]
            if e.code in (401, 403):
                raise RuntimeError(f"Gemini API {e.code}: ключ не підходить або "
                                   f"не має доступу. {msg}")
            if e.code == 404:
                raise ModelMissing(f"Gemini API 404: модель недоступна цьому "
                                   f"ключу — обери іншу кнопкою ↻. {msg}")
            if e.code == 429 and not retry_429:
                # Денний ліміт видно з тіла помилки: квота «PerDay». Його
                # пауза не лікує — модель відпочиває до нічного скидання.
                raise RateLimited(f"Gemini API 429: {msg}",
                                  daily="PerDay" in body,
                                  wait=_retry_delay(body, e.headers, 1))
            if e.code not in RETRY_CODES:
                raise RuntimeError(f"Gemini API {e.code}: {msg}")
            why = "ліміт Google" if e.code == 429 else f"сервер {e.code}"
            last = f"Gemini API {e.code}: {msg}"
            wait = _retry_delay(body, e.headers, attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            why = "немає зв'язку"
            last = f"Немає зв'язку з Gemini API: {reason}"
            wait = API_WAITS[min(attempt - 1, len(API_WAITS) - 1)]
        if attempt == API_TRIES:
            break
        if on_wait:
            on_wait(f"чекаю {wait}с · {attempt + 1}/{API_TRIES}",
                    f"{why}: чекаю {wait} с і пробую ще раз "
                    f"(спроба {attempt + 1} з {API_TRIES}).")
        time.sleep(wait)
    raise RuntimeError(f"{last}\n\nПовторено {API_TRIES} разів — не допомогло. "
                       f"Спробуй пізніше або перевір ключ.")


def list_models(api_key, retry_429=True):
    data = _request(f"{API_ROOT}/models?pageSize=100", api_key=api_key,
                    timeout=30, retry_429=retry_429)
    names = []
    for m in data.get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            names.append(m["name"].split("/", 1)[-1])
    return sorted(names)

# Режим «Авто»: модель обирає програма. Починаємо з найсильнішої, а коли
# в неї вичерпано ліміт — переходимо на наступну. У кожної моделі свій
# ліміт, тож перемкнутись швидше, ніж чекати.
AUTO_MODEL = "Авто (по черзі)"
MODEL_CHAIN = ("gemini-3.8-flash", "gemini-3.6-flash",
               "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
_auto = {"key": "", "chain": None, "cool": {}, "lock": threading.Lock()}


def _version_key(name):
    """Свіжіша версія вище; повна flash вище за lite; стабільна вище preview."""
    m = re.search(r"(\d+(?:\.\d+)?)", name)
    v = float(m.group(1)) if m else 0.0
    return (v, "lite" not in name, "preview" not in name and "exp" not in name)


def auto_chain(api_key):
    """Цепочка, звірена зі списком моделей, який Google дає цьому ключу.

    Назв, яких у ключа немає, не пробуємо — інакше кожен рядок починався б
    з відмови 404. Жодної з цепочки немає — беремо наявні flash, свіжі
    першими. Список не вдалося отримати — пробуємо цепочку як є, а
    відсутні моделі відпадуть самі на першому ж 404.
    """
    with _auto["lock"]:
        if _auto["chain"] is not None and _auto["key"] == api_key:
            return _auto["chain"]
    try:
        # Одна швидка спроба: на ліміті не чекаємо, а пробуємо цепочку як є.
        have = set(list_models(api_key, retry_429=False))
    except Exception:
        have = set()
    chain = [m for m in MODEL_CHAIN if m in have] if have else list(MODEL_CHAIN)
    if not chain:
        flash = [m for m in have if "flash" in m and not any(
            w in m for w in ("image", "tts", "audio", "embedding", "live"))]
        chain = sorted(flash, key=_version_key, reverse=True)[:6]
    with _auto["lock"]:
        _auto.update(key=api_key, chain=chain or list(MODEL_CHAIN), cool={})
        return _auto["chain"]


def _next_daily_reset():
    """Денні ліміти Google скидає опівночі за тихоокеанським часом —
    07:00–08:00 UTC. Беремо 08:00: зайва година дешевша за ще одну відмову."""
    now = time.time()
    reset = (now // 86400) * 86400 + 8 * 3600
    return reset if reset > now else reset + 86400


def _short(model):
    return (model or "").replace("gemini-", "")


def _call_model(api_key, model, payload, on_wait=None):
    """Один generateContent. Повертає (відповідь, якою моделлю).

    Обрана модель — як і раніше, з паузами на 429. «Авто» — по цепочці:
    ліміт вичерпано — одразу наступна модель.
    """
    def url(m):
        return f"{API_ROOT}/models/{m}:generateContent"

    if model != AUTO_MODEL:
        return _request(url(model), payload, api_key, on_wait=on_wait), model

    chain = auto_chain(api_key)
    while True:
        now = time.time()
        with _auto["lock"]:
            ready = [m for m in chain if _auto["cool"].get(m, 0) <= now]
            soonest = min((_auto["cool"].get(m, now) for m in chain), default=now)
        if not chain:
            raise RuntimeError("Жодна модель із цепочки не доступна цьому "
                               "ключу. Натисни ↻ і обери модель вручну.")
        if not ready:
            wait = int(soonest - now) + 1
            if wait > 180:
                raise RuntimeError(
                    "Денні ліміти вичерпано на всіх моделях: "
                    + ", ".join(chain) + ". Google скидає їх уночі "
                    "(близько 10:00–11:00 за Києвом). Продовж пізніше або "
                    "перемкнись на браузер.")
            if on_wait:
                on_wait(f"чекаю {wait}с · ліміти",
                        f"Хвилинні ліміти вичерпано на всіх моделях — "
                        f"чекаю {wait} с.")
            time.sleep(wait)
            continue
        m = ready[0]
        try:
            return _request(url(m), payload, api_key, on_wait=on_wait,
                            retry_429=False), m
        except RateLimited as e:
            until = _next_daily_reset() if e.daily else time.time() + max(e.wait, 60)
            with _auto["lock"]:
                _auto["cool"][m] = until
                nxt = next((x for x in chain if x != m
                            and _auto["cool"].get(x, 0) <= time.time()), "")
            kind = "денний" if e.daily else "хвилинний"
            if on_wait:
                on_wait(f"ліміт → {_short(nxt)}" if nxt else "ліміти вичерпано",
                        f"{m}: {kind} ліміт вичерпано"
                        + (f" — перемикаюсь на {nxt}." if nxt else "."))
        except ModelMissing:
            with _auto["lock"]:
                if m in chain:
                    chain.remove(m)
            if on_wait:
                on_wait("модель недоступна",
                        f"{m} недоступна цьому ключу — пропускаю.")


def generate_draft(api_key, model, user_text, repair_notes="", sink=None,
                   schema=None, aggregator=False, previous=""):
    """previous — сира попередня відповідь моделі. У API стану немає, тож
    діалог складаємо самі: завдання, відповідь моделі, зауваження. Це дешевше
    й точніше, ніж щоразу слати весь промпт наново."""
    contents = [{"role": "user", "parts": [{"text": user_text}]}]
    if repair_notes and previous:
        contents.append({"role": "model", "parts": [{"text": previous}]})
        contents.append({"role": "user", "parts": [
            {"text": "Твоя відповідь порушує правила. Виправ і поверни ВЕСЬ "
                     "JSON знову:\n" + repair_notes}]})
    elif repair_notes:
        contents[0]["parts"][0]["text"] += (
            "\n\nПопередня спроба порушила правила. Виправ САМЕ ці пункти, "
            "решту залиш якісною:\n" + repair_notes)
    payload = {
        "systemInstruction": {"parts": [{"text": load_system_prompt(aggregator)}]},
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema or RESPONSE_SCHEMA,
            "temperature": 1.0,
        },
    }
    on_wait = (sink or {}).get("on_wait")
    tries = 3
    for attempt in range(1, tries + 1):
        data, used = _call_model(api_key, model, payload, on_wait)
        if sink is not None:
            sink["model"] = used
        candidates = data.get("candidates") or []
        if not candidates:
            # Заблоковано політикою: той самий запит заблокують і вдруге.
            reason = data.get("promptFeedback", {}).get("blockReason",
                                                        "невідома причина")
            raise RuntimeError(f"Модель не повернула відповідь ({reason}).")
        cand = candidates[0]
        parts = cand.get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if sink is not None:
            sink["raw"] = text      # зберігаємо до розбору, щоб не втратити при збої
        finish = cand.get("finishReason") or ""
        if text:
            try:
                return parse_model_json(text)
            except RuntimeError:
                problem = "обірвалась" if finish == "MAX_TOKENS" else "не JSON"
        else:
            problem = f"порожня ({finish or '?'})"
        if attempt == tries:
            raise RuntimeError(
                f"Модель {tries} рази поспіль повернула відповідь, яку не "
                f"вдається розібрати: {problem}. Спробуй ще раз або іншу модель.")
        if on_wait:
            on_wait(f"{problem} · {attempt + 1}/{tries}",
                    f"Відповідь моделі: {problem}. Прошу переписати, спроба "
                    f"{attempt + 1} з {tries}.")
        # Модель бачить свою криву відповідь і прохання її виправити — так
        # вона чинить саме формат, а не пише кампанію з нуля.
        turn = [{"role": "user", "parts": [{"text": FIX_FORMAT_NOTE}]}]
        if text:
            turn.insert(0, {"role": "model", "parts": [{"text": text[:30000]}]})
        payload["contents"] = payload["contents"] + turn

# ══ РЕЖИМ «БРАУЗЕР»: Chrome DevTools Protocol без сторонніх бібліотек ═════════

class WebSocket:
    """Рівно стільки WebSocket, скільки треба для розмови з Chrome."""

    def __init__(self, url, timeout=60):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        if not m:
            raise RuntimeError(f"Незрозуміла адреса WebSocket: {url}")
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""

        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        while b"\r\n\r\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("Chrome обірвав з'єднання під час рукостискання.")
            self._buf += chunk
        head, self._buf = self._buf.split(b"\r\n\r\n", 1)
        if b" 101" not in head.split(b"\r\n")[0]:
            raise RuntimeError("Chrome не прийняв WebSocket-з'єднання.")

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("З'єднання з Chrome закрито.")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, text):
        self._frame(0x1, text.encode("utf-8"))

    def recv(self):
        chunks = []
        while True:
            b0, b1 = self._read(2)
            fin, opcode, n = b0 & 0x80, b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n) if n else b""
            if opcode == 0x8:
                raise RuntimeError("Chrome закрив вкладку.")
            if opcode == 0x9:          # ping -> pong
                self._frame(0xA, data)
                continue
            if opcode == 0xA:          # pong
                continue
            chunks.append(data)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")

    def close(self):
        try:
            self._frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Tab:
    """Одна вкладка Chrome: виконуємо в ній JavaScript."""

    def __init__(self, ws_url, timeout=60):
        self.ws = WebSocket(ws_url, timeout)
        self._id = 0
        self.keep_awake()

    def command(self, method, params=None, timeout=10):
        """Виклик CDP без очікування результату по суті — тільки підтвердження."""
        self._id += 1
        msg_id = self._id
        self.ws.sock.settimeout(timeout)
        self.ws.send(json.dumps({"id": msg_id, "method": method,
                                 "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                return data
        raise RuntimeError(f"Chrome не відповів на {method}.")

    def keep_awake(self):
        """Каже сторінці, що вона у фокусі й видима, навіть коли вікно згорнуте.
        Без цього Gemini друкує відповідь у рази довше: браузер вважає вкладку
        фоновою і притримує і таймери, і оновлення DOM."""
        for method, params in (
            ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
            ("Page.setWebLifecycleState", {"state": "active"}),
        ):
            try:
                self.command(method, params)
            except Exception:
                pass          # старий Chrome без цієї команди — не біда

    def evaluate(self, expression, timeout=60):
        self._id += 1
        msg_id = self._id
        self.ws.sock.settimeout(timeout)
        self.ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True,
                       "awaitPromise": True},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") != msg_id:
                continue                      # це подія сторінки, не наша відповідь
            if "error" in data:
                raise RuntimeError(f"CDP: {data['error'].get('message')}")
            result = data.get("result", {})
            if "exceptionDetails" in result:
                text = result["exceptionDetails"].get("text", "помилка JS")
                desc = result["exceptionDetails"].get("exception", {}).get("description", "")
                raise RuntimeError(f"JS на сторінці: {desc or text}")
            return result.get("result", {}).get("value")
        raise RuntimeError("Chrome не відповів вчасно.")

    def close(self):
        self.ws.close()


def chrome_path(saved=""):
    if saved and os.path.exists(saved):
        return saved
    for p in CHROME_PATHS:
        if p and os.path.exists(p):
            return p
    return ""


def cdp_http(path, method="GET", timeout=5):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


def cdp_alive():
    try:
        cdp_http("/json/version", timeout=2)
        return True
    except Exception:
        return False


def launch_chrome(exe):
    if not exe:
        raise RuntimeError("Не знайшов chrome.exe. Вкажи шлях у config.json → chrome_path.")
    os.makedirs(CHROME_PROFILE, exist_ok=True)
    subprocess.Popen([
        exe,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={CHROME_PROFILE}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        # Згорнуте вікно Chrome присипляє вкладку: таймери затискаються до
        # одного спрацювання на хвилину, рендер відкладається — і відповідь
        # Gemini доводиться чекати вдесятеро довше. Ці прапорці знімають
        # приспання, останній вимикає віконний розрахунок перекриття, через
        # який Windows-Chrome вважає закрите вікно невидимим.
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        # Один прапорець --disable-features на весь запуск: другий такий
        # перебиває перший, і тоді CalculateNativeWinOcclusion мовчки
        # перестав би діяти. Тому все перелічено тут через кому.
        #
        # OptimizationGuideOnDeviceModel — це локальна модель Gemini Nano,
        # яку Chrome тягне собі сам. Вона важить ЧОТИРИ ГІГАБАЙТИ і лежить
        # у нашому профілі без діла: ми працюємо з веб-версією Gemini у
        # вкладці, а не з моделлю в браузері.
        "--disable-features=CalculateNativeWinOcclusion,"
        "OptimizationGuideOnDeviceModel,OptimizationGuideModelDownloading,"
        "TextSafetyClassifier,OptimizationHints",
        GEMINI_URL,
    ])
    for _ in range(40):                      # до 20 секунд на старт
        if cdp_alive():
            return
        time.sleep(0.5)
    raise RuntimeError("Chrome запустився, але порт налагодження не відповідає.")


def open_gemini_tab(timeout=30):
    """Знаходить вкладку Gemini у нашому вікні або відкриває нову."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            targets = cdp_http("/json")
        except Exception:
            time.sleep(0.5)
            continue
        pages = [t for t in targets
                 if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        for t in pages:
            if "gemini.google.com" in (t.get("url") or ""):
                return t
        if pages:                            # вікно є, але Gemini в ньому не відкрито
            tab = Tab(pages[0]["webSocketDebuggerUrl"])
            try:
                tab.evaluate(f"location.href = {json.dumps(GEMINI_URL)}")
            finally:
                tab.close()
            time.sleep(2)
            continue
        try:
            cdp_http("/json/new?url=" + urllib.parse.quote(GEMINI_URL), method="PUT")
        except Exception:
            try:
                cdp_http("/json/new?url=" + urllib.parse.quote(GEMINI_URL))
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("Не вдалося відкрити вкладку Gemini.")


# ── JavaScript, який працює всередині сторінки Gemini ─────────────────────────

# Кнопка «Новий чат» просто на сторінці. Доти новий чат відкривався через
# location.href — тобто Gemini щоразу вантажився з нуля: секунди на кожен
# рядок, а на довгій черзі вкладка просто підвисала. Клік по кнопці нічого
# не перезавантажує: та сама сторінка, порожня розмова.
# Мова інтерфейсу може бути будь-яка, тому шукаємо і за розміткою, і за
# підписом.
JS_NEW_CHAT = r"""
(() => {
  const sels = [
    '[data-test-id="new-chat-button"]',
    'expandable-button[data-test-id="new-chat-button"]',
    'side-nav-action-button[data-test-id="new-chat-button"]',
    'button[aria-label*="New chat" i]',
    'a[aria-label*="New chat" i]',
  ];
  const press = (el) => {
    const hit = el.tagName === 'BUTTON' || el.tagName === 'A'
              ? el : (el.querySelector('button, a') || el);
    hit.click();
    return true;
  };
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) { press(el); return 'clicked:' + s; }
  }
  const words = ['new chat', 'новий чат', 'новый чат', 'nowy czat',
                 'nueva conversación', 'nouvelle discussion', 'neuer chat',
                 'nova conversa', 'nuova chat', 'nieuwe chat', 'ny chat',
                 'uusi keskustelu', 'nový chat', 'új csevegés', 'sohbet'];
  const nodes = document.querySelectorAll('button, a, [role="button"]');
  for (const el of nodes) {
    const text = ((el.getAttribute('aria-label') || '') + ' ' +
                  (el.innerText || '')).trim().toLowerCase();
    if (!text) continue;
    if (words.some(w => text.includes(w))) { press(el); return 'clicked:text'; }
  }
  return 'not-found';
})()
"""

JS_STATE = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  const signin = /accounts\.google\.com|ServiceLogin/.test(location.href)
              || !!document.querySelector('a[href*="ServiceLogin"], a[href*="accounts.google.com/ServiceLogin"]');
  return JSON.stringify({url: location.href, ready: !!box, signin: signin});
})()
"""

# Вставка тексту і надсилання — РІЗНІ кроки. Раніше це було одним: ми
# вставляли текст і тут же шукали кнопку «надіслати». Але Gemini вмикає її
# не миттєво, тож у мить пошуку вона ще disabled — кнопка не знаходилась,
# ми падали на синтетичний Enter, який Angular ігнорує, і запит лишався
# висіти в полі. Людині доводилось тиснути надсилання руками.
JS_INSERT = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  if (!box) return 'no-input';
  box.focus();
  const text = __PROMPT__;
  if (box.tagName === 'TEXTAREA') {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, text);
    box.dispatchEvent(new Event('input', {bubbles: true}));
  } else {
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, text);
    box.dispatchEvent(new Event('input', {bubbles: true}));
  }
  return 'ok';
})()
"""

JS_TRY_SEND = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  const btns = Array.from(document.querySelectorAll('button'));
  const named = btns.find(b => {
    const a = ((b.getAttribute('aria-label') || '') + ' ' +
               (b.getAttribute('mattooltip') || '') + ' ' +
               (b.getAttribute('data-test-id') || '')).toLowerCase();
    return /send|надісл|надисл|отправ|submit/.test(a);
  });
  // Кнопка-іконка без підпису: у Gemini це <mat-icon>send</mat-icon>.
  const byIcon = btns.find(b => {
    const ic = b.querySelector('mat-icon, .material-symbols-outlined, .google-symbols');
    return ic && (ic.textContent || '').trim().toLowerCase() === 'send';
  });
  const btn = [named, byIcon].find(b => b && !b.disabled &&
                                        b.getAttribute('aria-disabled') !== 'true');
  if (btn) { btn.click(); return 'button'; }
  if (box) {
    for (const type of ['keydown', 'keypress', 'keyup']) {
      box.dispatchEvent(new KeyboardEvent(type, {key: 'Enter', code: 'Enter',
        keyCode: 13, which: 13, bubbles: true, cancelable: true}));
    }
    return 'enter';
  }
  return 'nothing';
})()
"""

# Чи пішов запит: поле спорожніло або в чаті побільшало відповідей.
JS_COMPOSER = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  const text = box ? (box.value !== undefined ? box.value : box.innerText) : '';
  const nodes = document.querySelectorAll('message-content, .model-response-text, [data-response-index]');
  return JSON.stringify({len: (text || '').trim().length, answers: nodes.length});
})()
"""

JS_PROBE = r"""
(() => {
  const nodes = document.querySelectorAll('message-content, .model-response-text, [data-response-index]');
  const last = nodes[nodes.length - 1];
  const busy = Array.from(document.querySelectorAll('button')).some(b => {
    const a = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '')).toLowerCase();
    return /stop|зупин|остановить/.test(a) && b.offsetParent !== null;
  });
  return JSON.stringify({
    answers: nodes.length,
    len: last ? (last.innerText || '').length : 0,
    busy: busy
  });
})()
"""

JS_EXTRACT = r"""
(() => {
  const nodes = document.querySelectorAll('message-content, .model-response-text, [data-response-index]');
  const last = nodes[nodes.length - 1];
  if (!last) return '';
  const blocks = Array.from(last.querySelectorAll('code'));
  for (let i = blocks.length - 1; i >= 0; i--) {
    const t = (blocks[i].innerText || '').trim();
    if (t.startsWith('{') && t.endsWith('}')) return t;
  }
  return last.innerText || '';
})()
"""

JSON_SHAPE = """{
  "campaign_name": "3-4 слова, без підкреслень, по суті бізнесу",
  "website": "https://...",
  "location": "місто або країна",
  "language": "код мови, наприклад cs",
  "target_objects": ["що саме ти взяв за цільові об'єкти з Кроку 0"],
  "ad_groups": [
    {
      "name": "2-3 слова, інша за назву кампанії",
      "keywords": ["рівно 15 ключів чистим текстом"],
      "ads": [
        {
          "headlines": ["рівно 15 заголовків, кожен до 30 символів"],
          "descriptions": ["рівно 4 описи, кожен до 90 символів"]
        }
      ]
    }
  ],
  "sitelinks": [
    {"text": "до 25 символів", "description1": "до 35 символів",
     "description2": "до 35 символів"}
  ],
  "callouts": ["рівно 8, кожен до 25 символів"],
  "negatives": ["8-15 мінус-слів, кожне 1-2 слова"],
  "snippets": [
    {"type": "Amenities", "values": ["рівно 3 значення"], "level": "campaign"}
  ]
}"""


def parse_model_json(text):
    """JSON з відповіді моделі, з поправкою на типові вади.

    Порядок: як є -> вийняти з тексту чи ```-огорожі -> прибрати висячі
    коми перед } і ] (найчастіша хиба моделей). Лапки-«ялинки» й інші
    символи всередині рядків не чіпаємо: заміна зламала б справний текст.
    """
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return extract_json(text)
    except Exception:
        pass
    cleaned = re.sub(r",(\s*[}\]])", r"\1", text or "")
    try:
        return extract_json(cleaned)
    except Exception as e:
        raise RuntimeError(f"Відповідь моделі не розбирається як JSON: {e}")


FIX_FORMAT_NOTE = (
    "Твоя попередня відповідь — не валідний JSON або обірвалась на півслові. "
    "Поверни ВЕСЬ об'єкт заново, суворо за схемою, одним блоком, без тексту "
    "до чи після. Якщо не вміщається — скороти описи, але структуру не "
    "ламай і нічого не пропускай.")


def extract_json(raw):
    """Дістає об'єкт JSON із відповіді, навіть якщо навколо є текст або ```-огорожа."""
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("Gemini повернув порожню відповідь.")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    start = raw.find("{")
    if start == -1:
        raise RuntimeError("У відповіді Gemini немає JSON.")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(raw[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    raise RuntimeError("JSON у відповіді Gemini обірваний.")


def _gemini_state(tab):
    """Стан вкладки: готовність, вхід, адреса, скільки відповідей у чаті.

    Під час перезавантаження контекст JS гине, і evaluate кидає — це
    нормально, просто «ще не готово». А от обрив самого з'єднання з Chrome
    нормальним не є: раніше ми ковтали і його, і застосунок мовчки чекав
    хвилину, показуючи «Чекаю на готовність сторінки». Тому позначаємо збій
    окремо, щоб той, хто чекає, міг здатися вчасно й сказати правду.
    """
    try:
        state = json.loads(tab.evaluate(JS_STATE))
        state["answers"] = json.loads(tab.evaluate(JS_PROBE))["answers"]
        state["dead"] = False
        return state
    except Exception as e:
        dead = "закрито" in str(e) or isinstance(e, (OSError, socket.error))
        return {"ready": False, "signin": False, "url": "", "answers": 0,
                "dead": dead}


def _wait_chat(tab, progress, want_empty, deadline, label):
    """Чекає, поки сторінка справді стане тією, яку ми просили.

    Раніше тут стояв time.sleep(3) і перевірка «є поле вводу». Поле вводу є і
    на СТАРІЙ сторінці, тому за повільного завантаження ми писали запит у чат
    попереднього сайту — і отримували його країну. Так один і той самий
    ідентифікатор давав то Угорщину, то Нідерланди, то Польщу.

    Тепер ознака нового чату — порожня розмова, а не наявність поля.
    """
    dead_in_row = 0
    while time.time() < deadline:
        state = _gemini_state(tab)
        if state.get("dead"):
            # Обрив з'єднання не «розсмокчеться» від очікування: чекати тут
            # хвилину означає збрехати людині, що ми чогось чекаємо.
            dead_in_row += 1
            if dead_in_row >= 3:
                raise RuntimeError(
                    "Обірвалося з'єднання з вікном Chrome.\n\n"
                    "Найчастіше це буває, коли вікно Gemini закрили або "
                    "Chrome перезапустився. Відкрий вікно кнопкою «Відкрити "
                    "вікно Gemini» і спробуй ще раз.")
        else:
            dead_in_row = 0
        if state["signin"]:
            raise RuntimeError(
                "У вікні Gemini не виконано вхід у Google.\n\n"
                "Залогінься у тому вікні Chrome, що відкрив застосунок, "
                "і натисни «Згенерувати чернетку» ще раз.")
        if state["ready"]:
            if want_empty is None or bool(state["answers"] == 0) == want_empty:
                return state
            progress(f"{label}: сторінка ще стара, чекаю…")
        time.sleep(1)
    return None


def browser_generate(user_text, repair_notes="", progress=lambda s: None, exe="",
                     sink=None, shape=None, aggregator=False, follow_up=False,
                     new_chat=False, chat_url=""):
    """Пише запит у вкладку Gemini у нашому вікні Chrome і забирає відповідь.

    follow_up=True — це дослання в ТОЙ САМИЙ чат: системний промпт і завдання
    Gemini вже отримав першим повідомленням, свою відповідь вона бачить сама.
    Тоді шлемо лише список виправлень. Раніше на кожен раунд летіли всі 16 кБ
    промпта заново — модель перечитувала правила замість того, щоб дивитися
    на свій текст.

    chat_url — адреса конкретної розмови. Черга запам'ятовує її на кожен
    рядок, щоб регенерація йшла в чат саме цього сайту, а не в той, що
    випадково лишився відкритим.
    """
    if not cdp_alive():
        progress("Запускаю вікно Chrome для Gemini…")
        launch_chrome(chrome_path(exe))

    target = open_gemini_tab()
    tab = Tab(target["webSocketDebuggerUrl"])
    try:
        if new_chat:
            # Один чат на всю чергу — і Gemini бачить свої попередні відповіді
            # та штампує ті самі назви: одинадцять кампаній вийшли «Espace
            # Ludique France». Для кожного сайту починаємо розмову заново.
            progress("Починаю новий чат Gemini…")
            state = None
            for spin in range(3):
                # Спершу тиснемо кнопку «Новий чат» на самій сторінці:
                # розмова стає порожньою миттєво й нічого не вантажиться
                # заново. location.href піднімає весь застосунок Gemini з
                # нуля — це секунди на кожен рядок, а на довгій черзі
                # вкладка від такого підвисала. Лишаємо його запасним ходом.
                how = tab.evaluate(JS_NEW_CHAT) if spin == 0 else "not-found"
                if how == "not-found":
                    tab.evaluate(f"location.href = {json.dumps(GEMINI_URL)}")
                    time.sleep(2)
                else:
                    time.sleep(1)
                state = _wait_chat(tab, progress, True, time.time() + 45,
                                   "Новий чат")
                if state:
                    break
                progress(f"Новий чат не відкрився, спроба {spin + 2}…")
            if not state:
                raise RuntimeError(
                    "Не вдалося відкрити порожній чат Gemini: у вкладці "
                    "лишається попередня розмова.\n\nЗапит НЕ надіслано — "
                    "інакше кампанія вийшла б з чужою країною. Відкрий нову "
                    "розмову у вікні Gemini вручну й запусти ще раз.")
        elif chat_url:
            # Якщо ми вже стоїмо в потрібній розмові — не перезавантажуємо
            # сторінку заради неї ж: це просто зайві секунди на кожен раунд.
            here = _gemini_state(tab)
            if here["url"].split("?")[0].rstrip("/") != chat_url.rstrip("/"):
                progress("Повертаюся в чат цього сайту…")
                tab.evaluate(f"location.href = {json.dumps(chat_url)}")
                time.sleep(2)
                if not _wait_chat(tab, progress, False, time.time() + 45, "Чат"):
                    raise RuntimeError(
                        "Не вдалося відкрити збережену розмову Gemini для цього "
                        "рядка.\n\nЗапит НЕ надіслано. Перегенеруй рядок з нуля "
                        "кнопкою «Перегенерувати вибрані».")
        else:
            progress("Чекаю на готовність сторінки Gemini…")
            if not _wait_chat(tab, progress, None, time.time() + 60, "Сторінка"):
                raise RuntimeError("Поле вводу Gemini не з'явилося за 60 секунд.")

        before = json.loads(tab.evaluate(JS_PROBE))["answers"]

        # Дослати можна лише туди, де вже є відповідь. Якщо чат порожній
        # (Gemini почав новий), шлемо повний промпт — інакше вона не зрозуміє,
        # про яке «попереднє оголошення» йдеться.
        if follow_up and before == 0:
            progress("Чат порожній — шлю повний промпт замість дослання.")
            follow_up = False

        if follow_up:
            prompt = ("Твоя попередня відповідь порушує правила. Виправ і "
                      "поверни ВЕСЬ JSON знову, тією самою формою, одним "
                      "блоком ```json```.\n\n" + repair_notes)
        else:
            prompt = (load_system_prompt(aggregator) + "\n\n" + user_text +
                      "\n\nВідповідь дай ОДНИМ блоком ```json``` за цією формою "
                      "(без коментарів усередині JSON):\n" + (shape or JSON_SHAPE))
            if repair_notes:
                prompt += ("\n\nПопередня спроба порушила правила. Виправ САМЕ "
                           "ці пункти:\n" + repair_notes)

        # ── надсилання і очікування, з перезавантаженням при мовчанці ──
        # Gemini час від часу просто перестає відповідати: вкладка жива,
        # поле є, а відповідь не починається ніколи. Раніше ми чекали сім
        # хвилин і валили рядок. Тепер сторінка перезавантажується й запит
        # іде ще раз. Після перезавантаження спершу дивимось, чи відповідь
        # не з'явилась сама: Gemini дописує її на сервері, і часто вона вже
        # там — тоді нічого не надсилаємо повторно.
        SILENCE = 90        # стільки чекаємо ПОЧАТКУ відповіді
        FROZEN = 150        # стільки терпимо зупинку посеред відповіді
        TRIES = 3

        def send_once():
            progress("Пишу запит у вкладку Gemini…")
            if tab.evaluate(JS_INSERT.replace("__PROMPT__",
                                              json.dumps(prompt))) == "no-input":
                raise RuntimeError("Не знайшов поле вводу на сторінці Gemini.")
            # Кнопка вмикається не в ту саму мить, коли з'явився текст, тому
            # одна спроба наосліп регулярно лишала запит висіти в полі.
            progress("Надсилаю запит…")
            sent, how = False, ""
            for _ in range(15):
                state = json.loads(tab.evaluate(JS_COMPOSER))
                if state["len"] == 0 or state["answers"] > before:
                    sent = True
                    break
                how = tab.evaluate(JS_TRY_SEND)
                time.sleep(1)
            if not sent:
                state = json.loads(tab.evaluate(JS_COMPOSER))
                sent = state["len"] == 0 or state["answers"] > before
            if not sent:
                raise RuntimeError(
                    "Запит написано у вікні Gemini, але надіслати його не "
                    f"вдалося: кнопка не спрацювала за 15 спроб (остання дія: "
                    f"{how or '—'}).\n\nТекст лишився в полі — можна надіслати "
                    "вручну, відповідь застосунок підхопить сам.")

        def await_answer():
            """Чекає відповідь. Повертає True — готово, False — застрягло."""
            progress("Gemini друкує відповідь…")
            stable, last_len = 0, -1
            started = False
            start_wait = time.time()
            quiet = time.time()
            deadline = time.time() + 420
            while time.time() < deadline:
                time.sleep(1.5)
                probe = json.loads(tab.evaluate(JS_PROBE))
                if probe["answers"] <= before and probe["len"] == 0:
                    if time.time() - start_wait > SILENCE:
                        progress("Відповіді немає — перезавантажую сторінку…")
                        return False
                    continue
                if not started:
                    started = True
                # Відлік «застрягло» веде саме ДОВЖИНА тексту. Раніше його
                # збивав ще й busy: коли Gemini лишав індикатор увімкненим і
                # нічого не дописував, таймер скидався щоразу, і зупинку було
                # видно аж на сьомій хвилині.
                if probe["len"] != last_len:
                    stable, last_len = 0, probe["len"]
                    quiet = time.time()
                    continue
                if time.time() - quiet > FROZEN:
                    progress("Відповідь зупинилась — перезавантажую сторінку…")
                    return False
                if probe["busy"]:
                    stable = 0
                    continue
                stable += 1
                if stable >= 3:                # ~4.5 секунди без змін
                    return True
            progress("Сім хвилин без завершення — перезавантажую сторінку…")
            return False

        def reload_page():
            """Перезавантажує вкладку й повертає True, якщо відповідь уже є."""
            try:
                tab.evaluate("location.reload()")
            except Exception:
                pass
            time.sleep(3)
            if not _wait_chat(tab, progress, None, time.time() + 60, "Сторінка"):
                return False
            try:
                probe = json.loads(tab.evaluate(JS_PROBE))
            except Exception:
                return False
            # Відповідь дописалась на сервері, поки ми чекали — забираємо її
            # й не надсилаємо запит повторно.
            return probe["answers"] > before and not probe["busy"]

        done = False
        for spin in range(TRIES):
            send_once()
            if await_answer():
                done = True
                break
            if spin == TRIES - 1:
                break
            progress(f"Перезапуск сторінки, спроба {spin + 2} з {TRIES}…")
            if reload_page():
                done = True
                break
        if not done:
            raise RuntimeError(
                f"Gemini не відповів за {TRIES} спроби з перезавантаженням "
                f"сторінки.\n\nЧастіше за все це не наш збій: вкладка жива, "
                f"але модель мовчить. Спробуй цей рядок ще раз пізніше або "
                f"перевір вікно Gemini вручну.")

        progress("Забираю відповідь…")
        raw = tab.evaluate(JS_EXTRACT)
        if sink is not None:
            sink["raw"] = raw       # зберігаємо до розбору, щоб не втратити при збої
            # Адресу розмови запам'ятовуємо: за нею черга повернеться сюди ж,
            # коли рядок доведеться доопрацювати.
            try:
                url = json.loads(tab.evaluate(JS_STATE))["url"]
                if "/app/" in url:
                    sink["chat"] = url
            except Exception:
                pass
        # Відповідь не розбирається — не валимо рядок одразу, а просимо
        # Gemini в тому самому чаті переписати її. Вона бачить свій текст,
        # тож чинить саме формат, а не пише кампанію наново.
        for fix in range(1, 3):
            try:
                return parse_model_json(raw)
            except RuntimeError:
                progress(f"Відповідь не JSON — прошу переписати "
                         f"(спроба {fix + 1} з 3)…")
                if sink is not None and sink.get("on_wait"):
                    sink["on_wait"](f"не JSON · {fix + 1}/3",
                                     f"Відповідь не JSON — прошу Gemini "
                                     f"переписати, спроба {fix + 1} з 3.")
            before = json.loads(tab.evaluate(JS_PROBE))["answers"]
            prompt = FIX_FORMAT_NOTE
            send_once()
            if not await_answer():
                raise RuntimeError("Gemini не відповів на прохання "
                                   "переписати відповідь у JSON.")
            raw = tab.evaluate(JS_EXTRACT)
            if sink is not None:
                sink["raw"] = raw
        return parse_model_json(raw)
    finally:
        tab.close()


# ── Перевірки ─────────────────────────────────────────────────────────────────

DKI_RE = re.compile(r"\{\s*keyword\s*:\s*([^}]*)\}", re.I)

def effective_len(text):
    """Довжина так, як її рахує Google: макрос {Keyword: X} зводиться до X."""
    return len(DKI_RE.sub(lambda m: m.group(1).strip(), text).strip())

# Гемблінг — блокує генерацію. Решта — попередження.
#
# Сайти клієнтів бувають із гральною зоною (лаунж, рулетка, дилери), і згадка
# про неї в оголошенні коштує акаунта. Тому список навмисно широкий і покриває
# мови, у яких ми реально працюємо. Складені слова (Glücksspiel, Speellounge)
# шукаємо без межі слова — інакше корінь усередині компаунда не знайдеться.
# ПРАВИЛО ВІДБОРУ, а не список випадків. Сюди йде слово, у якого НЕМАЄ
# побутового значення: назви гральних ігор, казино, букмекер. Щойно слово
# щось означає й поза гемблінгом — «gry» (ігри), «zakład» (майстерня),
# «fogadás» (весільний прийом), «inzet» (відданість справі), «slot» (вікно
# для запису) — воно йде в BANNED_HARD_AMBIGUOUS і спрацьовує лише поруч
# з однозначною ознакою звідси. Інакше ми блокуємо не гемблінг, а мову.
BANNED_HARD = [
    # довгі однозначні корені — шукаємо будь-де, зокрема всередині компаундів
    r"casin[oó]", r"kasino", r"kasyno", r"kaszin", r"roulett", r"rulet",
    # Кирилиця, румунська, грецька, іврит, японська, корейська — те саме
    # казино. Мовний протяг показав, що «казино онлайн» проходило наскрізь:
    # у списку були самі латинські форми.
    r"казино", r"казіно", r"cazino", r"cazinou", r"καζίνο", r"קזינו",
    r"カジノ", r"카지노", r"kumarhane",
    r"blackjack", r"black\s*jack", r"блекджек", r"блэкджек", r"jackpot",
    r"джекпот", r"poker", r"покер", r"póker", r"croupier", r"крупьє", r"крупье",
    r"gokk", r"gokh", r"kansspel", r"glücksspiel", r"gluecksspiel",
    r"szerencsej", r"spielautomat", r"spielbank", r"spielhalle", r"speellounge",
    r"speelhal", r"speelautomat", r"nyerőgép", r"nyerogep", r"spilleautomat",
    r"kladionic", r"bookmaker", r"букмекер", r"гемблінг", r"гэмблинг",
    # «hazard» — азартна гра польською й чеською, але англійською це
    # небезпека: «hazardous» до гемблінгу стосунку не має.
    r"\bhazard\b", r"\bhazardn\w*", r"\bhazardow\w*", r"\bhazárd\w*",
    r"baccarat", r"bakarat", r"баккара", r"bingo", r"бінго", r"бинго", r"\bkeno\b",
    r"tombola", r"gokspel",
    # Скандинавські й фінські гральні автомати та ставки: були покриті лише
    # німецька й голландська форми, а шведське «spelautomater» проходило.
    r"\bspelautomat\w*", r"\bpengespill\w*", r"\bvadslagning\w*",
    r"\bvadhållning\w*", r"\bvadhallning\w*", r"\boddsspel\w*",
    r"\buhkapel\w*", r"\brahapel\w*", r"\bvedonly\w*",
    # Турецька, грецька, болгарська: основні слова вертикалі, яких не було.
    r"\bbahis\w*", r"\biddaa\b", r"\bkumar\b", r"\bkumarb\w*",
    r"στοίχημα", r"στοιχήματ", r"τζόγο", r"τζόγος",
    r"хазарт", r"залагани", r"тотализатор", r"тоталізатор",
    # Романські: «jogos de azar» / «juegos de azar» — це і є азартні ігри.
    r"\bjogos?\s+de\s+azar\b", r"\bjuegos?\s+de\s+azar\b",
    r"\bjocuri\s+de\s+noroc\b", r"\bcase\s+de\s+pariuri\b", r"\bpariu\w*",
    # «roleta» саме по собі — ще й турнікет, тому беремо гральні зв'язки.
    r"\broleta\s+(online|ao\s+vivo|europeia|americana|russa)\b",
    r"\bruleta\s+(online|en\s+vivo|europea|americana)\b",
    # Словенська «igralnica» — і казино, і дитяча ігрова кімната
    # («igralnica za otroke»). Однозначна лише зв'язка з «spletna»/«online».
    r"\bspletn\w*\s+igralnic\w*", r"\bonline\s+igralnic\w*",
    r"\bigralnic\w*\s+online\b",
    # коротші корені — тільки з початку слова
    r"\bграль\w*", r"\bазарт\w*",
    r"\bставк\w*", r"\bставок\b", r"\bлотере\w*",
    r"\bрулетк\w*", r"\bgambl\w*",
    # «bet» тільки цілим словом: \bbet\w* ловило between, better, beta, betray
    # і вирізало з опису кіберспорту три речення поспіль.
    r"\bbets?\b", r"\bbettors?\b", r"\bbet\s+on\b",
    r"\blotter\w*", r"\bloterij\w*", r"\bloterie\w*", r"\bwager\w*",
    r"\bsázk\w*", r"\bsazk\w*", r"\bwedden\w*",
    # «wett» ловило німецьке Wetter — погоду. Беремо самі ставки.
    r"\bwette\b", r"\bwetten\b", r"\bsportwetten\b", r"\bwettb[üu]ro\w*",
    # Романські мови. «paris» окремо НЕ беремо — це місто, а «côte» і «mise»
    # у ресторані означають реберце й mise en place.
    r"\bparis?\s+sportif\w*", r"\bparier\w*", r"\bpariez\b", r"\bfree\s*bet\w*",
    r"\bcash\s*out\b", r"\bapuesta\w*", r"\baposta\w*", r"\bscommess\w*",
    r"\bbetting\b", r"\bbookmak\w*", r"\bbukmach\w*", r"\bbukmacher\w*",
    r"\bobstaw\w*",
    # Багатозначні слова беремо тільки у гральній зв'язці. Саме слово живе
    # в ambiguous, а ось ця пара однозначна.
    r"\bautomat\w*\s+do\s+gier\b", r"\bgry\s+hazardow\w*",
    r"\bzakład\w*\s+bukmachersk\w*", r"\bzaklad\w*\s+bukmachersk\w*",
    r"\bzakład\w*\s+sportow\w*", r"\bzaklad\w*\s+sportow\w*",
    r"\bsportfogad\w*", r"\bfogadóirod\w*", r"\bfogadoirod\w*",
    # «fogadás» саме по собі — ще й прийом гостей, тому беремо тільки
    # зв'язки, у яких це однозначно ставка.
    r"\btétfogad\w*", r"\btetfogad\w*",
    r"\bfogad[áa]s\w*\s+(ma|most|élőben|eloben|online|szorzó|szorzo)\b",
    r"\b(élő|elo|online|sport)\s+fogad[áa]s\w*",
    r"\bfogad[áa]si\s+(szorzó|szorzo|esély|esely|irod)\w*",
    r"\bhrac[ií]\s+automat\w*", r"\bslot\s+machin\w*", r"\bслот[- ]?машин\w*",
    r"\bгральн\w*\s+автомат\w*", r"\bавтомат\w*\s+для\s+гри\b",
    r"\bігров\w*\s+автомат\w*", r"\bигров\w*\s+автомат\w*",
    r"\bжетон\w*\s+казино\b", r"\bżeton\w*\s+kasyn\w*",
    r"\bfiches\s+(kopen|inwisselen)\b", r"\bspeeltafel\w*\s+casino\b",
    # «výherní» — саме виграшний автомат; «výherce» (переможець конкурсу)
    # під цей корінь не підпадає.
    r"\bvýhern\w*", r"\bvyhern\w*",
]

# Слова, які в гральному контексті — евфемізми, а поза ним — звичайна лексика
# ніші. «Gaming» для кіберспорту, «play» для настолок, «гра» для дитячого
# центру. Блокувати їх завжди означало ламати кожну кампанію в цих нішах:
# «Dutch Board Cafes» і «Esports Leagues» валилися десятком помилок на рівному
# місці. Тому вмикаємо їх лише тоді, коли поруч є однозначно гральні ознаки.
BANNED_HARD_AMBIGUOUS = [
    r"\bgaming\b", r"\bplay\w*", r"\bgames?\b", r"\bgamer\w*",
    r"\bігр\w*", r"\bгра\b", r"\bгри\b", r"\bгру\b", r"\bгрі\b", r"\bгрою\b",
    r"\bграти\b", r"\bграє\w*", r"\bграють\b", r"\bигра\b", r"\bигры\b",
    r"\bиграт\w*", r"\bigr\w*",
    r"\bspel\w*", r"\bspeel\w*", r"\bspill\w*", r"\bspiel\w*",
    r"\bjeux?\b", r"\bjáték\w*", r"\bjatek\w*", r"\bjuego\w*", r"\bgioc\w*",
    r"\bhra\b", r"\bhry\b", r"\bhru\b", r"\bhře\b", r"\bhre\b", r"\bhrou\b",
    r"\bher\b", r"\bhraní\b", r"\bhrani\b", r"\bhrát\b", r"\bhrat\b",
    # Польська «gra» — це і настолка, і відеогра, і матч. Вона лежала в
    # жорсткому списку, і сайт про планшувки не міг пройти взагалі: 21
    # помилка на рівному місці, включно з цільовим об'єктом «gry planszowe».
    # Сам гемблінг тут ловлять kasyno, zakłady, hazard, ruletka, bukmacher
    # і «automat do gier» — вони лишилися жорсткими.
    r"\bgra\b", r"\bgry\b", r"\bgrze\b", r"\bgrą\b", r"\bgra\w*ć\b",
    r"\bgier\b", r"\bgrach\b", r"\bgranie\b", r"\bgraj\w*", r"\bgracz\w*",
    # «herna» — і гральний зал, і дитяча ігрова кімната. Без інших ознак
    # це друге: «dětská herna» є в половини чеських кафе.
    r"\bhern\w*",
    # «hrací karty», «hrací kostky» — карти й кубики для настолок.
    r"\bhrac[ií]\w*",
    # Голландське «tafelspel» — це і настільна гра, і гральний стіл;
    # «speeltafel» у дитячому кафе — столик для ігор.
    r"\btafelspel\w*", r"\bspeeltafel\w*",
    # «ігор» — родовий відмінок від «гра»: «клуб настільних ігор».
    r"\bігор\b", r"\bфішк\w*",
    # «slot» — це ще й вікно для запису: «вільні слоти», «booking slots».
    r"\bslots?\b", r"\bслот\w*",
    # Угорське «fogadás» — це ще й прийом: «esküvői fogadás», весільний банкет.
    r"\bfogadás\w*", r"\bfogadas\w*",
    # Голландське «inzet» — відданість справі: «onze inzet voor kwaliteit».
    r"\binzet\w*",
    # Французьке «fiches» — картки й бланки: «fiches produits».
    r"\bfiches\b", r"\bžeton\w*", r"\bzeton\w*", r"\bjeton\w*",
    # Польське «zakład» — це майстерня, салон, підприємство: «zakład
    # fryzjerski», «zakład produkcyjny». Ставку тут робить лише зв'язка
    # «zakłady bukmacherskie», і вона лишилась у жорсткому списку.
    r"\bzakład\w*", r"\bzaklad\w*",
    # «Vegas» саме по собі — топонім і частина назв: «Vegas Grill».
    r"\bvegas\b",
    # «roleta» португальською — ще й турнікет, «ruleta» іспанською теж
    # трапляється поза грою. Гральні зв'язки з ними — у жорсткому списку.
    r"\broleta\w*", r"\bruleta\w*",
    # «igralnica» словенською — казино, хорватською — дитяча ігрова.
    r"\bigralnic\w*", r"\bigraonic\w*",
]
BANNED_HARD_AMBIGUOUS_RE = [re.compile(p, re.I | re.U) for p in BANNED_HARD_AMBIGUOUS]

# Слово, яке лежить в обох списках, назавжди лишається жорстким: до
# контекстної перевірки черга не доходить. Саме так «гра» і «игра» роками
# були помилкою в будь-якому тексті, хоч і значилися серед контекстних.
BANNED_OVERLAP = sorted(set(BANNED_HARD) & set(BANNED_HARD_AMBIGUOUS))
# Непідтверджувані заяви. Google уже відхиляв за них оголошення («Ověřený Servis»,
# «profesionální servis»), тому це помилка, а не зауваження.
BANNED_CLAIMS = [
    r"\bověřen\w*", r"\bprofesionáln\w*", r"\bprofesjonaln\w*", r"\bпрофесійн\w*",
    r"\bprofessional\w*", r"\bprofessionele\w*", r"\bcertified\b", r"\bcertifi\w*",
    r"\bверифік\w*", r"\bверифиц\w*", r"\bверевер\w*",
    r"\btrusted\b", r"\btrust\w*\s+by\b", r"\bproven\b", r"\bkompletn\w*",
    r"\btop[- ]rated\b", r"\bпровірен\w*", r"\bперевірен\w*", r"\bпроверенн\w*",
    r"\bsprawdzon\w*", r"\bniezawodn\w*", r"\bспеціаліст[иі]\s+високо\w*",
    r"\bбездоганн\w*", r"\bбезупречн\w*", r"\bnajlep\w*", r"\bnejlep\w*",
    r"\bnumber\s*one\b", r"\bексперт[нi]\w*\s+рівн\w*",
    # Романські переваги. Сайт-агрегатор сам зветься «Best… Guide», тож
    # спокуса написати «meilleur» у заголовку висока, а Google це відхиляє.
    r"\bmeilleur\w*", r"\bmejor(?:es)?\b", r"\bmigliori?\b", r"\bmelhor\w*",
    r"\bnuméro\s+un\b", r"\bn[°º]\s*1\b", r"\bgaranti\w*", r"\bplus\s+fiable\w*",
    # Англійський шар заяв про себе. Пройшовши по банку фраз клієнта, ці
    # формулювання просочувалися всі до одного — зокрема «Quality service
    # assured», про яке я сам попереджав.
    r"\breliab\w*", r"\btrusted\b", r"\btrustworthy\b",
    r"\byou\s+(?:can\s+)?trust\b", r"\btrust\s+in\s+\w+",
    r"\bquality\s+(?:service|platform|support|work|care)\w*",
    r"\b(?:service|support|results?)\s+assured\b", r"\bassured\b",
    r"\bexcellence\b", r"\bdependab\w*", r"\bworld[- ]class\b", r"\bleading\b",
    r"\bpremier\b", r"\bunmatched\b", r"\brenowned\b", r"\bsuperior\b",
    # Обіцянки та лестощі: перевірити неможливо, а тон рекламний.
    r"\byou\s+deserve\b", r"\bresults?\s+you\s+deserve\b",
    r"\brealize\s+your\s+dreams?\b", r"\bno\s+experience\s+needed\b",
    # Статусні надбавки. Нічого не описують, лише піднімають градус, і Google
    # читає їх як обіцянку переваги, яку ніхто не підтверджував.
    r"\bvip\b", r"\bві[- ]?ай[- ]?пі\b",
    r"\bpremium\b", r"\bpr[ée]miov\w*", r"\bpremiov\w*", r"\bpremium[- ]?class\w*",
    r"\bпреміум\w*", r"\bпремиум\w*", r"\bпреміальн\w*", r"\bпремиальн\w*",
    r"\bpremiow\w*", r"\bprémiov\w*",
    r"\bexclusiv\w*", r"\bexclusif\w*", r"\bexkluziv\w*", r"\bekskluzyw\w*",
    r"\bексклюзив\w*", r"\bэксклюзив\w*", r"\bexklusiv\w*",
    r"\bluxury\b", r"\bluxusn\w*", r"\bluksusow\w*", r"\bлюксов\w*",
    r"\bde\s*luxe\b", r"\bdeluxe\b", r"\blusso\b", r"\bl[uú]xo\b",
]
BANNED_CLAIMS_RE = [re.compile(p, re.I | re.U) for p in BANNED_CLAIMS]

BANNED_SOFT = [
    # "dealer" буває легальним (автодилер), тому не блокуємо, а попереджаємо
    r"\bdealer\w*", r"\bдилер\w*", r"\bvertier\b", r"\blounge\b",
    r"100\s*%", r"\bbest\b", r"\bbeste\b", r"\bно?мер\s*1\b", r"\bnumber\s*1\b",
    r"\btips?\b", r"\btricks?\b", r"\brisk[- ]free\b",
    r"\bгарант\w*", r"\bguarante\w*", r"\bzáruk\w*",
    r"\bалкогол\w*", r"\balcohol\w*", r"\bпиво\b", r"\bbeer\b",
    r"\bвино\b", r"\bwine\b", r"\bкоктейл\w*", r"\bcocktail\w*",
]
BANNED_HARD_RE = [re.compile(p, re.I | re.U) for p in BANNED_HARD]
BANNED_SOFT_RE = [re.compile(p, re.I | re.U) for p in BANNED_SOFT]

# ── М'яка лексика ─────────────────────────────────────────────────────────────
# Тематика оголошення мусить збігатися з посадковою — інакше це обхід систем.
# Але подача може бути спокійною: «порівняння платформ за критеріями» замість
# «коефіцієнти, кешаут, бонус 100 євро». Тема та сама, тиску немає.

# Назви операторів у тексті оголошення — чужі торгові марки й найяскравіший
# сигнал промо. Список неповний навмисно: доповнюй під свої ринки.
SOFT_BRANDS = [
    "betclic", "bwin", "netbet", "unibet", "winamax", "parions", "pmu",
    "bet365", "1xbet", "betway", "pokerstars", "888", "ladbrokes",
    "william hill", "betfair", "pinnacle", "vbet", "zebet", "genybet",
    "barriere", "barrière", "partouche", "betsson", "leovegas", "casumo",
    "tipico", "fortuna", "sazka", "tipsport", "betano", "superbet",
    "stoiximan", "betfred", "paddy power", "sky bet", "betvictor", "bet at home",
    # Латинська Америка, Азія, Африка, Північна Америка
    "blaze", "estrela bet", "kto", "rivalo", "codere", "rushbet", "wplay",
    "caliente", "bplay", "parimatch", "melbet", "mostbet", "dafabet",
    "sportybet", "betking", "bangbet", "hollywoodbets", "sunbet", "supabets",
    "draftkings", "fanduel", "bet mgm", "betmgm", "caesars", "pointsbet",
    "sportsbet", "tab", "ladbrokes au", "bodog", "stake",
]
SOFT_BRANDS_RE = [re.compile(r"\b" + re.escape(b) + r"\b", re.I | re.U)
                  for b in SOFT_BRANDS]

# Конкретні суми й відсотки: умови акцій змінюються, а оголошення лишається.
# Це і ризик невідповідності, і зайвий промо-тиск.
AMOUNT_RE = [
    re.compile(r"\d[\d\s.,]*\s*[€$£₴]", re.U),
    re.compile(r"[€$£₴]\s*\d", re.U),
    re.compile(r"\d[\d\s.,]*\s*%", re.U),
    re.compile(r"\d[\d\s.,]*\s*(?:eur|usd|gbp|pln|czk|huf|ron)\b", re.I | re.U),
]

# Промо-лексика. Не заборонена Google, але саме вона робить оголошення
# «гарячим». У м'якому режимі просимо модель переписати спокійніше.
SOFT_PROMO = [
    r"\bcotes?\b", r"\bcash\s*out\b", r"\bfree\s*bets?\b", r"\bfreebets?\b",
    r"\bbonus\w*\b", r"\bdépôts?\b", r"\bdepots?\b", r"\bgagn\w*", r"\bgains?\b",
    r"\bmises?\b", r"\bpromo\w*", r"\bodds\b", r"\bpayout\w*", r"\bdeposit\w*",
    r"\bwins?\b", r"\bwinnings?\b", r"\bjackpot\w*", r"\bwelcome\s+offer\b",
    r"\bкоефіцієнт\w*", r"\bвиплат\w*", r"\bдепозит\w*", r"\bбонус\w*",
    # «kurs» і «kurzy» — це ще й курси навчання; «quote» — англійська
    # пропозиція ціни. Для попередження надто широко, прибрано.
    r"\bwypłat\w*", r"\bdepozyt\w*", r"\bvklad\w*",
    # Іспанська, португальська, італійська, румунська, турецька, грецька
    r"\bcuotas?\b", r"\bapuesta\s+gratis\b", r"\bdep[óo]sito\w*", r"\bretiros?\b",
    r"\bganancias?\b", r"\bpremios?\b", r"\bodds\b", r"\bcotas?\b",
    r"\bsaques?\b", r"\bganhos?\b", r"\bvincit\w*",
    r"\bprelievi?\b", r"\bc[âa][șs]tig\w*", r"\bretrageri?\b",
    r"\boranlar\w*", r"\bkazan[çc]\w*", r"\b[çc]ekim\w*", r"\bαποδόσε\w*",
    r"\bκέρδ\w*", r"\bανάληψ\w*",
]
SOFT_PROMO_RE = [re.compile(p, re.I | re.U) for p in SOFT_PROMO]

# Інтонація казино. Слова самі по собі дозволені, але разом вони роблять
# з білої кампанії гральну на слух: «без реєстрації», «грай зараз»,
# «спробуй удачу» — це впізнаваний почерк вертикалі. Модерація дивиться
# на нього прискіпливіше, а приходить по ньому не та аудиторія.
SOFT_CASINO_TONE = [
    # без реєстрації
    r"без\s+ре[єе]страц\w*", r"без\s+регистрац\w*", r"bez\s+rejestrac\w*",
    r"bez\s+registrac\w*", r"zonder\s+registrat\w*", r"ohne\s+anmeldung\b",
    r"sans\s+inscription\b", r"no\s+registration\b", r"without\s+signup\b",
    r"senza\s+registrazion\w*", r"sin\s+registro\b", r"sem\s+registo\b",
    r"regisztr[áa]ci[óo]\s+n[ée]lk[üu]l\b",
    # грай просто зараз
    r"грай\s+зараз\b", r"играй\s+сейчас\b", r"graj\s+teraz\b",
    r"hraj\s+(hned|te[ďd])\b", r"play\s+now\b", r"jetzt\s+spielen\b",
    r"jouer?\s+maintenant\b", r"juega\s+ahora\b", r"jogue\s+agora\b",
    r"gioca\s+ora\b", r"speel\s+nu\b", r"j[áa]tssz\s+most\b",
    # спробуй удачу
    r"спробуй\s+удач\w*", r"испытай\s+удач\w*", r"spr[óo]buj\s+szcz[ęe][śs]c\w*",
    r"zkus\s+[šs]t[ěe]st[íi]\b", r"try\s+your\s+luck\b", r"tenter?\s+sa\s+chance\b",
    r"prueba\s+tu\s+suerte\b", r"gl[üu]ck\s+versuchen\b",
]
SOFT_CASINO_TONE_RE = [re.compile(p, re.I | re.U) for p in SOFT_CASINO_TONE]

# Вікові маркери й формули відповідальної гри — самі по собі сигнал тематики.
# На сайті вони обов'язкові й там лишаються; у тексті оголошення лише
# підсвічують вертикаль, нічого не додаючи. Це зауваження, а не заборона:
# у деяких країнах попередження в рекламі вимагає закон.
SOFT_AGE = [
    r"18\s*\+", r"21\s*\+", r"\b18\s*(?:ans|plus|lat|let|év|години)\b",
    r"\badultes?\b", r"\badults?\b", r"\bmajeur\w*", r"\bmineur\w*",
    r"\bповнолітн\w*", r"\bсовершеннолетн\w*", r"\bdorosł\w*", r"\bdospěl\w*",
    r"\bjeu\s+responsable\b", r"\bjouer\s+avec\s+modération\b",
    r"\bresponsible\s+gam\w*", r"\bgamble\s+responsibly\b",
    r"\bвідповідальн\w*\s+гр\w*", r"\bodpowiedzialn\w*", r"\bzodpovědn\w*",
    r"\bzodpovedn\w*", r"\bfelelősség\w*", r"\bverantwoord\w*",
    r"\bloisir\b", r"\bbudget\b", r"\baddiction\b", r"\bdépendance\b",
    # Іспанська, португальська, італійська, румунська, турецька, грецька
    r"\bmayores?\s+de\s+18\b", r"\bs[óo]lo\s+adultos\b", r"\bjuego\s+responsable\b",
    r"\bmaiores?\s+de\s+18\b", r"\bjogo\s+respons[áa]vel\b",
    r"\bmaggiorenn\w*", r"\bgioco\s+responsabile\b",
    r"\bjoc\s+responsabil\b", r"\bpeste\s+18\s+ani\b",
    r"\b18\s+ya[şs]\b", r"\bsorumlu\s+oyun\b",
    r"\bυπεύθυν\w*\s+παιχνίδ\w*", r"\bενήλικ\w*",
    r"\bansvarsfullt\s+spelande\b", r"\bspelmissbruk\b",
]
SOFT_AGE_RE = [re.compile(p, re.I | re.U) for p in SOFT_AGE]

# ── Заборонені категорії Google Ads ──────────────────────────────────────────
# Діють у ВСІХ режимах, а не лише в гральному. Раніше вони жили тільки текстом
# у промпті — тобто трималися на добрій волі моделі. Тепер це помилки, які
# блокують файл, як і гемблінг. Хибне спрацювання знімається галочкою на
# вкладці «Перевірка»: у сертифікованій аптеки свої правила, але тоді це
# свідоме рішення, а не непомічений недогляд.
BANNED_TOPICS = {
    # Рівень 1 із довідки Google: «акаунт блокується негайно, без попередження».
    "аптеки без ліцензії та рецептурні препарати": [
        # Аптека кожною мовою, з якою ми працюємо.
        r"\bаптек\w*", r"\baptek\w*", r"\bpharmac\w*", r"\bfarmac\w*",
        r"\bapothe\w*", r"\bapotek\w*", r"\bl[ée]k[áa]rn\w*",
        r"\bgy[óo]gyszert[áa]r\w*", r"\bдрогері\w*", r"\bdrogeri\w*",
        # «Без рецепта» — головна ознака нелегальної аптеки.
        r"\bбез\s+рецепт\w*", r"\bbez\s+recept\w*", r"\bsans\s+ordonnance\b",
        r"\bsin\s+receta\b", r"\bsenza\s+ricetta\b", r"\bohne\s+rezept\b",
        r"\bzonder\s+recept\b", r"\bwithout\s+prescription\b", r"\bno\s+rx\b",
        r"\bprescription\w*", r"\bрецептурн\w*", r"\bрецепт\s+онлайн\b",
        r"\bтелемедицин\w*", r"\btelemedicine\b", r"\btelemedycyn\w*",
    ],
    "опіоїди": [
        r"\bопіоїд\w*", r"\bопиоид\w*", r"\bopioid\w*", r"\boxycodon\w*",
        r"\bоксикодон\w*", r"\bfentanyl\w*", r"\bфентаніл\w*", r"\bфентанил\w*",
        r"\btramadol\w*", r"\bтрамадол\w*", r"\bcodeine\b", r"\bкодеїн\w*",
        r"\bmorphine\b", r"\bморфін\w*", r"\bморфин\w*",
    ],
    "несхвалені речовини": [
        r"\bephedr\w*", r"\bефедр\w*", r"\bhcg\b", r"\bхгч\b",
        r"\banabolic\w*", r"\bанаболік\w*", r"\bанаболик\w*",
        r"\bстероїд\w*", r"\bстероид\w*", r"\bsteroid\w*",
        r"\bviagra\b", r"\bвіагр\w*", r"\bвиагр\w*", r"\bsildenafil\b",
        r"\bбад\b", r"\bдієтичн\w*\s+добавк\w*", r"\bдобавк\w*\s+для\s+схудн\w*",
        r"\bfat\s+burner\w*", r"\bжироспалюв\w*",
    ],
    "недоведені методи лікування": [
        r"\bстволов\w*\s+кліт\w*", r"\bstem\s+cell\w*", r"\bcell\s+therap\w*",
        r"\bgene\s+therap\w*", r"\bклітинн\w*\s+терап\w*",
        r"\bгенн\w*\s+терап\w*", r"\bекспериментальн\w*\s+лікуванн\w*",
        r"\bміракл\w*", r"\bmiracle\s+cure\w*", r"\bчудодійн\w*",
    ],
    # Рівень 2: дозволено лише з сертифікацією Google і лише в частині країн.
    "медицина, потребує сертифікації": [
        r"\bлікуванн\w*", r"\bлечени\w*", r"\bвилікув\w*", r"\btherap\w*",
        r"\bтерап\w*", r"\bterapi\w*", r"\bdiagnosti\w*", r"\bдіагноз\w*",
        r"\bдиагноз\w*", r"\bsymptom\w*", r"\bсимптом\w*", r"\bклінік\w*",
        # Французька clinique й німецька Klinik — теж клініка.
        r"\bклиник\w*", r"\bclini[cqk]\w*", r"\bklinik\w*", r"\bhospital\w*",
        r"\bлікар\w*",
        r"\bврач\w*", r"\bdoctor\w*", r"\bmédecin\w*", r"\bпрепарат\w*",
        r"\bтаблетк\w*", r"\bpills?\b", r"\bвакцин\w*", r"\bvaccin\w*",
        r"\bsupplements?\b", r"\bхвороб\w*", r"\bболезн\w*", r"\bdisease\w*",
        r"\bmaladie\w*", r"\bmedic(?:al|ine|ines)\b", r"\bмедичн\w*",
        r"\bмедицин\w*", r"\bпсихіатр\w*", r"\bpsychiatr\w*",
        r"\bпохуд\w*", r"\bсхудн\w*", r"\bweight\s+loss\b",
        r"\bperte\s+de\s+poids\b", r"\bмедстрахув\w*",
        r"\bhealth\s+insurance\b", r"\bстрахування\s+здоров\w*",
    ],
    "допомога залежним": [
        r"\bреабілітац\w*", r"\bреабилитац\w*", r"\brehabilit\w*",
        r"\bдетокс\w*", r"\bdetoks\w*", r"\bdetox\w*", r"\bнаркологі\w*",
        r"\bнарколог\w*", r"\balcohol\s+(?:rehab|addiction)\b",
        r"\bлікування\s+залежн\w*", r"\bодвикан\w*",
    ],
    # Рівень 3: заборонено або обмежено в більшості країн.
    "репродуктивна медицина": [
        r"\bаборт\w*", r"\babortion\b", r"\bfertilit\w*", r"\bфертильн\w*",
        r"\bсурогатн\w*", r"\bsurrogac\w*", r"\bпротизаплідн\w*",
        r"\bcontracepti\w*", r"\bпрезерватив\w*", r"\bcondom\w*",
        r"\bтест\s+на\s+вагітн\w*", r"\bpregnancy\s+test\w*",
    ],
    "тести та дослідження": [
        r"\bвіл[- ]тест\w*", r"\bhiv\s+test\w*", r"\bтест\s+на\s+віл\b",
        r"\bклінічн\w*\s+дослідж\w*", r"\bclinical\s+trial\w*",
        r"\bstd\s+test\w*", r"\bіппп\b",
    ],
    "наркотики": [
        r"\bнаркотик\w*", r"\bнаркоти[кч]\w*", r"\bdrugs?\b", r"\bdrogue\w*",
        r"\bканабіс\w*", r"\bканнабис\w*", r"\bcannabis\w*", r"\bmarijuana\b",
        r"\bмарихуан\w*", r"\bcbd\b", r"\bthc\b", r"\bкокаїн\w*", r"\bкокаин\w*",
        r"\bcoca[ïi]ne\b", r"\bамфетамін\w*", r"\bamphetamin\w*", r"\bmdma\b",
        r"\blsd\b", r"\bгероїн\w*", r"\bheroin\w*", r"\bспайс\w*",
        r"\bметамфетамін\w*", r"\bmethamphetamin\w*", r"\bmephedron\w*",
        r"\bмефедрон\w*", r"\bкальян\w*", r"\bhookah\b", r"\bshisha\b",
        r"\bvape\w*", r"\bвейп\w*", r"\be-?cig\w*", r"\bтютюн\w*",
        r"\bсигарет\w*", r"\bcigarette\w*", r"\btobacco\b",
    ],
    "зброя": [
        r"\bзброя\b", r"\bзброї\b", r"\bоружи\w*", r"\bweapons?\b",
        r"\bfirearms?\b", r"\bпістолет\w*", r"\bпистолет\w*", r"\bhandgun\w*",
        r"\bguns?\b", r"\brifles?\b", r"\bгвинтівк\w*", r"\bammunition\b",
        r"\bammo\b", r"\bнабо[їя]\b", r"\bпатрон\w*", r"\bглушник\w*",
        r"\bsilencer\w*", r"\bвибухів\w*", r"\bexplosiv\w*", r"\bгранат[ыа]\b",
        r"\bножі\s+бойов\w*", r"\bкастет\w*",
    ],
    "дорослий контент": [
        r"\bпорно\w*", r"\bporn\w*", r"\bescort\w*", r"\bескорт\w*",
        r"\bінтим\w*", r"\bинтим\w*", r"\bsex\w*", r"\bсекс\w*",
        r"\berotic\w*", r"\bеротик\w*", r"\bwebcam\s+girl\w*", r"\bвебкам\w*",
        r"\bsugar\s+dadd\w*", r"\bstriptease\b", r"\bстриптиз\w*",
        r"\bmassage\s+érotique\b", r"\bадульт\w*", r"\badult\s+(?:content|site|video)\b",
    ],
    "торгівля людьми": [
        r"\bрабств\w*", r"\bслейв\w*", r"\bslavery\b", r"\btrafficking\b",
        r"\bторгівля\s+людьми\b", r"\bторговля\s+людьми\b",
        r"\bсурогатн\w*\s+матер\w*", r"\bsurrogac\w*", r"\bпродам\s+нирк\w*",
        r"\borgan\s+donor\s+paid\b",
    ],
    "фінансові обіцянки й крипто": [
        r"\bкрипто\w*", r"\bcrypto\w*", r"\bbitcoin\b", r"\bбіткоїн\w*",
        r"\bбиткоин\w*", r"\bforex\b", r"\bфорекс\w*", r"\bhyip\b",
        r"\bпірамід\w*", r"\bпирамид\w*", r"\bponzi\b", r"\bбінарн\w*\s+опціон\w*",
        r"\bbinary\s+options?\b", r"\bмикрозайм\w*", r"\bмікропозик\w*",
        r"\bpayday\s+loan\w*", r"\bкредит\s+без\s+відмов\w*",
    ],
    "підробки": [
        r"\bрепліка\w*", r"\breplica\w*", r"\bпідробк\w*", r"\bподделк\w*",
        r"\bcounterfeit\w*", r"\bfake\s+brand\w*", r"\bкопія\s+бренд\w*",
        r"\baaa\s+quality\b",
    ],
    # «Другие типы бизнеса»: попередження за сім днів, потім блокування.
    "заборонений тип бізнесу": [
        r"\bпоручительств\w*\s+під\s+заставу", r"\bbail\s+bond\w*",
        r"\bстороння\s+техпідтримк\w*", r"\bthird[- ]party\s+tech\s+support\b",
        r"\bдовідков\w*\s+служб\w*", r"\bпереадресац\w*\s+дзвінк\w*",
        r"\bcall\s+forwarding\b", r"\bзапис\s+розмов\b",
        r"\bcall\s+recording\b", r"\bпоручительств\w*",
    ],
    # «Неприемлемый контент»: блокування негайно, без попередження.
    "мова ворожнечі та дискримінація": [
        r"\bдискримінац\w*", r"\bдискриминац\w*", r"\bhate\s+speech\b",
        r"\bрасов\w*\s+переваг\w*", r"\bнижча\s+раса\b", r"\bracial\s+slur\w*",
        r"\bцькуванн\w*", r"\bharassment\b", r"\bbullying\b",
    ],
    "тиск на самооцінку": [
        # Ограничения таргетинга персонализированной рекламы: заборонено
        # просувати товар через негативний підтекст і бодішеймінг.
        r"\bбодішейм\w*", r"\bbody\s+sham\w*", r"\bсоромно\s+бути\b",
        r"\bнадмірн\w*\s+вага\b", r"\bзайв\w*\s+вага\b", r"\bлишний\s+вес\b",
        r"\bug[l]y\b", r"\bпотворн\w*", r"\bсоромитись\s+свого\b",
        r"\bfat\s+shaming\b", r"\bненавидиш\s+себе\b",
    ],
}
BANNED_TOPICS_RE = {name: [re.compile(p, re.I | re.U) for p in pats]
                    for name, pats in BANNED_TOPICS.items()}

# Категорії, за які Google блокує акаунт негайно й без попередження.
# Решта — обмеження, які знімаються сертифікацією і лише в частині країн.
TOPICS_SUSPEND = {"аптеки без ліцензії та рецептурні препарати", "опіоїди",
                  "несхвалені речовини", "недоведені методи лікування",
                  "наркотики", "зброя", "торгівля людьми", "дорослий контент",
                  "мова ворожнечі та дискримінація"}

# Гео, куди Google взагалі не пускає рекламу. Не плутати з гральним банлістом:
# тут справа не в тематиці, а в самій країні.
GEO_SUSPENDED = {
    "Russia": ("Google призупинив показ реклами користувачам у Росії та показ "
               "оголошень російських рекламодавців по всьому світу. Кампанія "
               "не запуститься незалежно від тематики."),
}


def _scan_topics(label, text, errors):
    """Заборонені категорії Google Ads. Діють у будь-якому режимі."""
    for name, patterns in BANNED_TOPICS_RE.items():
        hit = _hit(patterns, text)
        if not hit:
            continue
        if name in TOPICS_SUSPEND:
            errors.append(f"{label}: «{hit}» — категорія «{name}». Google "
                          f"блокує акаунт негайно й без попередження → {text}")
        else:
            errors.append(f"{label}: «{hit}» — категорія «{name}». Потрібна "
                          f"сертифікація Google і дозволене гео → {text}")
        return

# Health in personalized advertising. Ці слова самі по собі нейтральні —
# «консультація» потрібна юристу, «допомога» будь-кому. Але поруч із гральною
# темою вони читаються як лікування ігрової залежності, тобто стан здоров'я,
# а на ньому Google забороняє будувати рекламу. Реальний випадок: сніпет
# «consultation options jeu» завалив завантаження. Тому — лише в агрегаторі.
HEALTH_TERMS = [
    r"\bconsultation\w*", r"\bconsulta\w*", r"\bkonsultac\w*", r"\bконсультац\w*",
    r"\btraitement\w*", r"\btratamiento\w*", r"\btrattament\w*", r"\btreatment\w*",
    r"\bsant[ée]\b", r"\bsalud\b", r"\bsa[úu]de\b", r"\bsalute\b",
    r"\bhealth\w*", r"\bздоров\w*", r"\bpsycholog\w*", r"\bпсихолог\w*",
    r"\bréhabilit\w*", r"\brehab\w*", r"\bguérison\b", r"\bcure\b",
    r"\bhelpline\b", r"\bligne\s+d.aide\b", r"\bsupport\s+group\w*",
    r"\bgroupe\s+de\s+parole\b", r"\bдопомог\w*\s+залежн\w*",
]
HEALTH_TERMS_RE = [re.compile(p, re.I | re.U) for p in HEALTH_TERMS]


SOFT_BRIEF = """М'ЯКА ПОДАЧА — ДІЄ ЗАВЖДИ, У БУДЬ-ЯКІЙ НІШІ.
Тема оголошення мусить збігатися з тим, що людина побачить на сторінці:
приховувати рід діяльності НЕ можна, це порушення. Змінюється не тема,
а тон: замість промо-тиску — спокійний опис того, що дає сайт.

Пиши по суті: що це, для кого, які умови, чим зручно, як влаштовано.

НЕ пиши в заголовках, описах і розширеннях:
- чужі торгові марки й назви конкретних компаній;
- суми, відсотки й розміри пропозицій: «100 %», «120 €», «знижка 50»;
- акційну лексику й тиск: бонус, депозит, виграш, кешаут, bonus, odds,
  payout, win, «встигни», «останній шанс», «тільки сьогодні».

Приклад підміни ТОНУ, а не теми. Це ілюстрація принципу, не текст для
копіювання:
  було: «Bonus 100 % Et Cash Out»  ->  стало: «Умови Викладені Зрозуміло»
  було: «Знижка 50 На Все»         ->  стало: «Ціни Вказані Одразу»

"""


def _scan_soft(label, text, errors, warnings, aggregator=False):
    """Перевірки м'якої подачі. Бренди й суми блокують, промо-лексика —
    зауваження, яке запускає повторний запит до моделі.

    Вікові маркери перевіряємо лише в режимі агрегатора: поза гральною
    вертикаллю «budget» чи «loisir» — звичайні робочі слова, і чіплятися
    до них означає засипати журнал шумом.
    """
    hit = _hit(SOFT_BRANDS_RE, text)
    if hit:
        errors.append(f"{label}: назва оператора «{hit}» у тексті оголошення — "
                      f"чужа торгова марка й зайвий промо-сигнал → {text}")
    hit = _hit(AMOUNT_RE, text)
    if hit:
        errors.append(f"{label}: сума чи відсоток «{hit.strip()}» — умови "
                      f"змінюються, оголошення лишається → {text}")
    hit = _hit(SOFT_CASINO_TONE_RE, text)
    if hit:
        warnings.append(f"{label}: інтонація казино «{hit}» — біла кампанія "
                        f"звучить як гральна, і приходить по ній не та "
                        f"аудиторія → {text}")
    hit = _hit(SOFT_PROMO_RE, text)
    if hit:
        warnings.append(f"{label}: м'яка лексика — замінити «{hit}» спокійнішим "
                        f"формулюванням → {text}")
    if aggregator:
        hit = _hit(SOFT_AGE_RE, text)
        if hit:
            warnings.append(f"{label}: м'яка лексика — «{hit}» підсвічує "
                            f"вертикаль. Вік і відповідальна гра лишаються на "
                            f"сайті, не в оголошенні → {text}")


def _hit(patterns, text):
    """Шукає і в оригіналі, і в тексті без діакритики: «Kasíno», «hrací»
    та «Výherní» мають ловитися так само, як їхні голі форми."""
    folded = defold(text)
    for rx in patterns:
        m = rx.search(text) or rx.search(folded)
        if m:
            return m.group(0)
    return ""


# ── Режим «Агрегатор»: сайт із сертифікацією Google на азартні ігри ───────────
# Коли акаунт пройшов сертифікацію і домен схвалений, гральна лексика дозволена.
# Але саме тут з'являються ВЛАСНІ заборони, за які знімають сертифікацію:
# обіцянки виграшу, подача ставок як заробітку і будь-який натяк на дітей.
BANNED_WIN_PROMISES = [
    r"\bгарантован\w*\s+виграш", r"\bвиграш\s+гарантован\w*", r"\bбез\s+ризик\w*",
    r"\bлегк[іиі]\w*\s+гро\w*", r"\bшвидк[іиі]\w*\s+гро\w*", r"\bзаробіт\w*",
    r"\bзаработ\w*", r"\bдохід\s+від\s+ставок", r"\bstable\s+income\b",
    r"\bguaranteed\s+win\w*", r"\bwin\s+guaranteed\b", r"\bsure\s+bet\b",
    r"\bsurebet\b", r"\brisk[- ]free\s+bet\b", r"\beasy\s+money\b",
    r"\bfast\s+money\b", r"\bmake\s+money\b", r"\bearn\w*\s+income\b",
    r"\bgain\w*\s+garanti\w*", r"\bargent\s+facile\b", r"\brevenus?\s+garanti\w*",
    r"\bgagner\s+à\s+coup\s+sûr\b", r"\bsans\s+risque\b", r"\bprofit\s+garanti\w*",
    r"\bpewn\w*\s+wygran\w*", r"\bzarobek\b", r"\bjistá\s+výhra\b",
    r"\bgarantierter\s+gewinn\b",
    # Іспанська, португальська, італійська, румунська, турецька, грецька
    r"\bganancias?\s+garantizad\w*", r"\bdinero\s+f[áa]cil\b",
    r"\bsin\s+riesgo\b", r"\bgana\s+seguro\b", r"\bingresos?\s+garantizad\w*",
    r"\bganhos?\s+garantid\w*", r"\bdinheiro\s+f[áa]cil\b", r"\bsem\s+risco\b",
    r"\brenda\s+extra\b", r"\bvincite?\s+garantit\w*", r"\bsoldi\s+facili\b",
    r"\bsenza\s+rischio\b", r"\bc[âa][șs]tig\w*\s+garantat\w*",
    r"\bbani\s+u[șs]or\w*", r"\bf[ăa]r[ăa]\s+risc\b",
    r"\bgarantili\s+kazan\w*", r"\bkolay\s+para\b", r"\brisksiz\b",
    r"\bεγγυημέν\w*\s+κέρδ\w*", r"\bεύκολα\s+χρήματα\b",
    r"\bgegarandeerde?\s+winst\b", r"\bsnel\s+geld\b", r"\bzonder\s+risico\b",
    r"\bgaranterad\s+vinst\b", r"\bnem\s+kereset\b",
    # «Реальні гроші» — головна червона лінія і для агрегатора, і для
    # соціального казино. У списку її не було взагалі: «Win Real Money»
    # проходило наскрізь.
    r"\breal\s+money\b", r"\bwin\s+money\b", r"\bmoney\s+prizes?\b",
    r"\bprawdziw\w*\s+pieni[ąa]dz\w*", r"\bwygra\w*\s+pieni[ąa]dz\w*",
    r"\bреальн\w*\s+деньг\w*", r"\bреальн\w*\s+грош\w*",
    r"\bвыигр\w*\s+деньг\w*", r"\bвигра\w*\s+грош\w*",
    r"\bskute[čc]n[ée]\s+pen[íi]ze\b", r"\bechtgeld\b", r"\becht\s+geld\b",
    r"\bargent\s+r[ée]el\b", r"\bdinero\s+real\b", r"\bdinheiro\s+real\b",
    r"\bsoldi\s+veri\b", r"\bger[çc]ek\s+para\b", r"\bαληθιν\w*\s+χρήματ\w*",
    # Заробіток у слов'янських мовах: був лише «zarobek» і «заработ».
    r"\bzarabia\w*", r"\bзарабатыва\w*", r"\bзаробля\w*",
    r"\bлегк\w*\s+деньг\w*", r"\bбыстр\w*\s+деньг\w*",
]
BANNED_WIN_PROMISES_RE = [re.compile(p, re.I | re.U) for p in BANNED_WIN_PROMISES]

# Будь-яка згадка неповнолітніх у рекламі азартних ігор — миттєва відмова.
BANNED_MINORS = [
    r"\bдіт\w*", r"\bдитяч\w*", r"\bпідліт\w*", r"\bдетск\w*", r"\bподрост\w*",
    r"\bkids?\b", r"\bchild\w*", r"\bteen\w*", r"\bjunior\b", r"\bfamil\w*",
    r"\benfant\w*", r"\bado(?:lescent)?s?\b", r"\bjeunesse\b", r"\bmineur\w*",
    r"\bdziec\w*", r"\bdět\w*", r"\bkinder\w*", r"\bgyerek\w*",
    # «сім» окремо не беремо — це число сім і «сімнадцять».
    r"\bсімей\w*", r"\bсім'\w*", r"\bсемей\w*", r"\bсемь[ия]\b", r"\bродинн\w*",
    # Іспанська, португальська, італійська, румунська, турецька, грецька,
    # скандинавські. «niño/criança/bambino/copil/çocuk/παιδί/barn».
    r"\bniñ[oa]s?\b", r"\bnin[oa]s?\b", r"\bmenor(?:es)?\s+de\s+edad\b",
    r"\badolescent\w*", r"\bfamiliar(?:es)?\b", r"\bcrian[çc]as?\b",
    r"\bbambin[oi]\b", r"\bragazz[oi]\b", r"\bminorenn\w*", r"\bfamigli\w*",
    r"\bcopi[il]\w*", r"\bfamilie\b", r"\b[çc]ocuk\w*", r"\bgen[çc]ler\b",
    r"\baile\s+dostu\b", r"\bπαιδι\w*", r"\bανηλίκ\w*", r"\boικογενει\w*",
    r"\bbarn\b", r"\bbørn\b",
    # Сім'я польською, чеською, голландською, угорською.
    r"\brodzin\w*", r"\brodin\w*", r"\bgezin\w*", r"\bcsal[áa]d\w*",
]
BANNED_MINORS_RE = [re.compile(p, re.I | re.U) for p in BANNED_MINORS]

# Країни, де реклама азартних ігор заборонена (див. «Правила Google.md»).
# Це офіційний перелік Google — тут сертифікація не допомагає взагалі.
GAMBLING_BANNED_COUNTRIES = {
    "Afghanistan", "Algeria", "Bahrain", "Bangladesh", "Bhutan", "Bulgaria",
    "China", "Djibouti", "Egypt", "Estonia", "Hong Kong", "India", "Indonesia",
    "Iraq", "Italy", "Jordan", "Kuwait", "Lebanon", "Libya", "Lithuania",
    "Malaysia", "Maldives", "Morocco", "Oman", "Pakistan", "Palestine",
    "Philippines", "Qatar", "Saudi Arabia", "Singapore", "South Korea", "Sudan",
    "Syria", "Taiwan", "Thailand", "Tunisia", "Turkey", "Ukraine",
    "United Arab Emirates", "Vietnam", "Yemen",
}

# Місцеві вимоги понад сертифікацію Google. Сертифікація дозволяє показ —
# вона не звільняє від національного регулювання, і саме на ньому кампанії
# зупиняються після запуску. Тут не юридична консультація, а чеклист:
# що саме піти перевірити перед заливкою.
# Станом на початок 2026 року; правила змінюються, тому звіряй перед запуском.
GAMBLING_RULES = {
    "France": ("Регулятор ANJ. Вимога попереджувального повідомлення в рекламі "
               "стосується того, ХТО РЕКЛАМУЄ, тобто твого акаунта. Ліцензія "
               "оператора, на якого веде посилання, тебе не покриває."),
    "Netherlands": ("Регулятор KSA. Ненацільована реклама онлайн-гемблінгу "
                    "заборонена з 2023 року, показ дозволений лише на "
                    "перевірену аудиторію. Заборонено таргетувати 18-24."),
    "Belgium": ("Регулятор Gaming Commission. Реклама азартних ігор майже "
                "повністю заборонена з 2023 року — перевір, чи взагалі є "
                "легальний формат для твого випадку."),
    "Germany": ("Регулятор GGL. Потрібна німецька ліцензія, є обмеження за "
                "часом показу і за форматами. Пошук — з умовами."),
    "Spain": ("Регулятор DGOJ. Бонуси для нових користувачів заборонені, "
              "реклама обмежена за часом. Ліцензія обов'язкова."),
    "Poland": ("Онлайн-казино — монополія Totalizator Sportowy. Букмекери "
               "потребують ліцензії Міністерства фінансів. Реклама решти "
               "операторів незаконна."),
    "Czechia": "Ліцензія Міністерства фінансів. Потрібне попередження про ризики.",
    "Portugal": "Регулятор SRIJ. Ліцензія обов'язкова, є вимоги до подачі.",
    "Sweden": "Регулятор Spelinspektionen. Вимога «поміркованості» реклами.",
    "Denmark": "Регулятор Spillemyndigheden. Ліцензія обов'язкова.",
    "Greece": "Регулятор HGC. Ліцензія обов'язкова.",
    "Romania": "Регулятор ONJN. Ліцензія обов'язкова.",
    "United Kingdom": ("Регулятор UKGC. Ліцензія обов'язкова, потрібні "
                       "посилання на BeGambleAware, суворо 18+."),
    "Ireland": "Регулятор GRAI. Правила оновлюються — звір актуальний стан.",
    "Austria": "Монополія на частину вертикалей. Перевір, що саме дозволено.",
    "Switzerland": "Дозволені лише оператори з місцевою ліцензією.",
    "Finland": "Монополія Veikkaus, реформа ринку триває.",
    "Slovakia": "Регулятор ÚRHH. Ліцензія обов'язкова.",
    "Hungary": "Ліцензія обов'язкова, ринок обмежений.",
    "Croatia": "Ліцензія Міністерства фінансів.",
    "Canada": "Правила відрізняються по провінціях, Онтаріо регулює AGCO окремо.",
    "United States": ("Регулювання по штатах. Потрібна сертифікація Google "
                      "під конкретний штат і вертикаль."),
    "Australia": ("ACMA. Онлайн-казино заборонені, ставки на спорт — "
                  "з ліцензією та обмеженнями."),
    "Brazil": "Ринок ліцензується з 2025 року. Потрібна місцева ліцензія.",
    "Mexico": "Ліцензія SEGOB.",
    "Argentina": "Регулювання по провінціях, Буенос-Айрес окремо.",
    "Colombia": "Регулятор Coljuegos, ліцензія обов'язкова.",
    "Chile": "Ринок у процесі врегулювання — звір актуальний стан.",
    "Peru": "Ліцензування з 2024 року, регулятор MINCETUR.",
    "South Africa": "Провінційні ліцензії, онлайн-казино заборонені.",
    "Nigeria": "Регулювання штатами, ліцензія обов'язкова.",
    "Kenya": "Регулятор BCLB, є податок на ставки.",
    "New Zealand": "Пропонувати послуги можуть лише місцеві оператори.",
    "Japan": "Майже все заборонено, крім кількох державних вертикалей.",
    "Israel": "Азартні ігри заборонені, крім державних лотерей.",
    "Serbia": "Ліцензія Міністерства фінансів.",
    "Cyprus": "Регулятор NBA, онлайн-казино заборонені.",
    "Malta": "Регулятор MGA. Ліцензія MGA не дає права реклами в інших країнах.",
    "Norway": "Монополія Norsk Tipping, реклама решти операторів заборонена.",
    "Belarus": "Ліцензування, доступ до нелегальних сайтів блокується.",
    "Kazakhstan": "Ліцензування, є обмеження для резидентів.",
}


def gambling_geo_notes(country):
    """Повертає (помилки, попередження) щодо гео для режиму агрегатора."""
    if not country:
        return ([], [])
    if country in GAMBLING_BANNED_COUNTRIES:
        return ([f"{country}: реклама азартних ігор тут заборонена. "
                 f"Сертифікація Google цього не змінює — кампанія не "
                 f"запуститься."], [])
    note = GAMBLING_RULES.get(country)
    if note:
        # Рекламодавець — акаунт, а не оператор із посадкової. Ліцензії й
        # дозволи партнерів відповідальності з акаунта не знімають.
        return ([], [f"{country}: {note} Відповідальність на рекламному "
                     f"акаунті, ліцензія партнера її не переносить."])
    return ([], [f"{country}: країни немає в моєму чеклисті. Перевір сам, чи "
                 f"дозволена реклама азартних ігор і чи покриває сертифікація "
                 f"це гео — вона видається під конкретні країни."])


def draft_texts(draft):
    """Усе, що модель написала: назви, ключі, тексти, розширення."""
    out = [draft.get("campaign_name") or ""]
    out += [str(o) for o in (draft.get("target_objects") or [])]
    for g in draft.get("ad_groups") or []:
        out.append(g.get("name") or "")
        out += [k for k in (g.get("keywords") or [])]
        for ad in g.get("ads") or []:
            out += list(ad.get("headlines") or [])
            out += list(ad.get("descriptions") or [])
    out += [c for c in (draft.get("callouts") or [])]
    for sn in draft.get("snippets") or []:
        out += [str(v) for v in (sn.get("values") or [])]
    for sl in draft.get("sitelinks") or []:
        out += [sl.get("text") or "", sl.get("description1") or "",
                sl.get("description2") or ""]
    return [t for t in out if t]


def gambling_context(draft):
    """Чи є в кампанії однозначні гральні ознаки.

    Якщо так — «gaming», «play», «гра» стають евфемізмами й забороняються.
    Якщо ні — це кіберспорт, настолки чи дитячий центр, і чіпати їх не можна.
    """
    return any(_hit(BANNED_HARD_RE, t) for t in draft_texts(draft))


def _scan_policy(label, text, errors, warnings, aggregator=False, claims=True,
                 soft=False, ambiguous=False):
    """claims=False для ключових слів: «meilleur site de paris» — це те, що
    людина ВВОДИТЬ у пошук, а не заява про себе в оголошенні. Google модерує
    тексти оголошень, а не ключі, тож блокувати такий ключ було помилкою."""
    # Заборонені категорії перевіряємо ЗАВЖДИ: медицина, наркотики, зброя,
    # дорослий контент і решта не залежать від того, який зараз режим.
    _scan_topics(label, text, errors)
    # Двозначні категорії — теж завжди: класифікатор Google не дивиться на
    # наш режим і не питає, що ми мали на увазі.
    for rx, quals, msg in AMBIGUOUS_CATEGORY_RE:
        if rx.search(text or "") and not any(q.search(text or "") for q in quals):
            errors.append(f"{label}: {msg} → {text}")
    if soft:
        _scan_soft(label, text, errors, warnings, aggregator)
    if aggregator:
        hit = _hit(HEALTH_TERMS_RE, text)
        if hit:
            errors.append(f"{label}: «{hit}» поруч із гральною темою читається "
                          f"як лікування залежності. Google блокує це за "
                          f"Health in personalized advertising → {text}")
        # Гральна лексика дозволена — сертифікація саме на неї і видається.
        hit = _hit(BANNED_WIN_PROMISES_RE, text)
        if hit:
            errors.append(f"{label}: обіцянка виграшу чи заробітку «{hit}» — "
                          f"за це знімають сертифікацію → {text}")
        hit = _hit(BANNED_MINORS_RE, text)
        if hit:
            errors.append(f"{label}: згадка неповнолітніх «{hit}» у рекламі "
                          f"азартних ігор → {text}")
    else:
        hit = _hit(BANNED_HARD_RE, text)
        if hit:
            errors.append(f"{label}: заборонена лексика «{hit}» → {text}")
        elif ambiguous:
            hit = _hit(BANNED_HARD_AMBIGUOUS_RE, text)
            if hit:
                errors.append(f"{label}: «{hit}» у гральному контексті читається "
                              f"як евфемізм → {text}")
    if claims:
        hit = _hit(BANNED_CLAIMS_RE, text)
        if hit:
            errors.append(f"{label}: непідтверджувана заява «{hit}» — "
                          f"Google відхиляє такі формулювання → {text}")
    hit = _hit(BANNED_SOFT_RE, text)
    if hit:
        warnings.append(f"{label}: ризикове слово «{hit}» → {text}")


SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|[\n\r]+|(?<=•)\s*")


def scrub_description(text):
    """Вирізає з опису сайту все, що стосується гральної тематики.

    Модель не напише про те, чого не бачила. Це надійніше за заборону: заборону
    вона іноді обходить синонімом, а видаленого тексту просто немає в запиті.
    Рекламуємо ресторан — гральна зона лишається проблемою сайту, не нашою.
    """
    if not (text or "").strip():
        return "", []
    kept, removed = [], []
    for chunk in SENTENCE_SPLIT.split(text):
        chunk = (chunk or "").strip()
        if not chunk:
            continue
        if _hit(BANNED_HARD_RE, chunk):
            removed.append(chunk)
        else:
            kept.append(chunk)
    return " ".join(kept), removed

# Google приймає тільки ці типи structured snippet (мовою кампанії).
# Слова, які самі по собі означають дві різні речі, і одна з них — тематика
# під забороною. Класифікатор Google не питає, що ми мали на увазі.
#
# Реальний випадок: грецька кампанія про настільні ігри, рядок «σύγχρονα
# παιχνίδια». Грецьке «παιχνίδια» — це і ігри, і ІГРАШКИ, тож фраза поїхала
# в політику «Birth Control, Fertility and Testing» як товари для дорослих.
# Лікується не забороною слова, а вимогою уточнення поруч.
AMBIGUOUS_CATEGORY = [
    (r"\bπαιχνίδ\w*",
     (r"επιτραπέζ", r"βιντεο", r"βίντεο", r"ηλεκτρονικ", r"στρατηγικ",
      r"παιδικ", r"σκάκ", r"κάρτ"),
     "грецьке «παιχνίδια» означає і ігри, і іграшки. Без уточнення Google "
     "читає це як товари для дорослих — реальна кампанія впала в політику "
     "Birth Control. Пиши «επιτραπέζια παιχνίδια», «βιντεοπαιχνίδια»"),
]
AMBIGUOUS_CATEGORY_RE = [
    (re.compile(p, re.I | re.U),
     [re.compile(q, re.I | re.U) for q in quals], msg)
    for p, quals, msg in AMBIGUOUS_CATEGORY
]

# ── Соціальні казино ──────────────────────────────────────────────────────────
# Окрема категорія Google з окремою сертифікацією. Ключове з довідки:
#   • дозволено ЛИШЕ у двох групах країн, і групи не можна змішувати
#     в одному акаунті — під кожну потрібен свій;
#   • акаунт сертифікується АБО під соціальне казино, АБО під гемблінг;
#   • агрегатори й афіліати соціальних казино заборонені взагалі;
#   • марки справжніх казино в оголошеннях заборонені;
#   • порушення цієї політики Google вважає грубим: блокування без
#     попередження і без права рекламуватись надалі.
SOCIAL_CASINO = False          # у збірці для соцказино стає True

SOCIAL_GROUP_1 = {
    # Точний перелік, дозволений конвеєром: Європа, Британія, США
    # та Австралія. Решту країн прибрано свідомо.
    "Australia", "Austria", "Czechia", "Czech Republic", "Denmark",
    "Finland", "France", "Germany", "Greece", "Hungary", "Latvia",
    "Netherlands", "Norway", "Spain", "Sweden", "Switzerland",
    "United Kingdom", "United States",
}
SOCIAL_GROUP_2 = {
    "Hong Kong", "India", "South Korea", "Korea", "Malaysia", "Taiwan",
    "Thailand", "Vietnam",
}

# Оголошення мусить прямо казати, що гра безкоштовна й без реальних грошей:
# це вимога сертифікації, а не побажання.
FREE_PLAY_MARKERS = [
    r"\bбезкоштовн\w*", r"\bбесплатн\w*", r"\bза\s+darmo\b", r"\bdarmow\w*",
    r"\bzdarma\b", r"\bfree\b", r"\bgratis\b", r"\bkostenlos\b",
    r"\bgratuit\w*", r"\bgratuito\b", r"\bgratuit[ao]\b", r"\bingyenes\w*",
    r"\bδωρεάν\b", r"\bbedava\b", r"\bfor\s+fun\b", r"\bplay\s+money\b",
    r"\bвіртуальн\w*", r"\bвиртуальн\w*", r"\bwirtualn\w*", r"\bvirtu[áa]ln\w*",
    r"\bvirtual\w*", r"\bsocial\s+casino\b", r"\bbez\s+depozytu\b",
    r"\bbez\s+vkladu\b", r"\bno\s+deposit\b",
]

FREE_PLAY_RE = [re.compile(p, re.I | re.U) for p in FREE_PLAY_MARKERS]

SNIPPET_TYPES = {
    "amenities", "brands", "courses", "degree programs", "destinations",
    "featured hotels", "insurance coverage", "models", "neighborhoods",
    "service catalog", "shows", "styles", "types",
}

# Інформаційний інтент — трафік без комерційної цінності.
INFO_INTENT = [
    r"\bяк\b", r"\bчому\b", r"\bщо робити\b", r"\bінструкц\w*", r"\bформум\w*",
    r"\bфорум\w*", r"\bвідгук\w*", r"\bсвоїми руками\b", r"\bсамостійно\b",
    r"\bкак\b", r"\bпочему\b", r"\bинструкц\w*", r"\bотзыв\w*",
    r"\bhow\b", r"\bwhy\b", r"\bwhat is\b", r"\bfree\b", r"\bdownload\b",
    r"\bdiy\b", r"\bhoe\b", r"\bwaarom\b", r"\bgratis\b",
]
INFO_INTENT_RE = [re.compile(p, re.I | re.U) for p in INFO_INTENT]

APOSTROPHES = "'’ʼ"

# Зауваження, які варті ще одного запиту до моделі: усе, що ламає структуру
# кампанії, а не просто виглядає негарно.
STRUCTURAL_RE = re.compile(
    r"треба рівно|треба 3-5|треба 1-2|треба 1-4|дозволено до|дозволено 3|"
    r"недобір|марнується|повторюється|перетинається|м'яка лексика|"
    r"треба 2-4|треба 2-3|немає самого предмета|коротких ключів|"
    r"стосу іменників|"
    r"інтонація казино|заголовків без ключа", re.U)


def _covers_object(keyword, objects):
    """Чи є в ключі сам предмет попиту.

    Порівнюємо по кореню з 5 літер, а не по цілому слову: у чеській і
    польській те саме слово в ключі й у списку об'єктів стоїть у різних
    відмінках («deskove hry» проти «deskovych her»), і точне порівняння
    завалило б перевірку на рівному місці.
    """
    low = defold(keyword)
    for obj in objects:
        parts = [w for w in re.findall(r"[^\W\d_]+", obj, re.U) if len(w) >= 4]
        if not parts:
            # Об'єкт з коротких слів («bar», «spa») — шукаємо як є.
            if obj and obj in low:
                return True
            continue
        if any(w[:5] in low for w in parts):
            return True
    return False


WORD_ROOT_LEN = 4


def _word_roots(texts):
    """Корені по 4 літери: у слов'янських мовах закінчення з'їдає п'яту.

    «матчи», «матча», «матчей» дають три різні п'ятилітерні корені й не
    склеюються між собою — саме через це заголовок «Не Пропусти Начало
    Матча» не зараховувався до ключа «матчи». Основа тут чотирилітерна.
    """
    out = set()
    for text in texts:
        for word in re.findall(r"[^\W\d_]+", defold(text or ""), re.U):
            out.add(word[:WORD_ROOT_LEN] if len(word) >= WORD_ROOT_LEN else word)
    return out


def noun_stack_tails(keywords):
    """Довгі хвости, які ніхто не набирає.

    Живий хвіст — це питання людини, і майже в кожній мові в ньому є
    коротке службове слово: kam, na, v, pro, s, dla, do, voor, met, for.
    Чотири змістовні слова поспіль — це не запит, а опис розділу сайту:
    «actuele esports schema resultaten», «uitgebreide team profielen
    statistieken». Саме так модель переказує опис замість семантики.
    """
    out = []
    for k in keywords:
        words = re.findall(r"[^\W\d_]+", defold(k), re.U)
        if len(words) >= 4 and not any(len(w) <= 3 for w in words):
            out.append(k)
    return out


def item_keywords(keywords, objects, geo_roots):
    """Короткі ключі, які називають КОНКРЕТНУ річ ніші, а не саму категорію.

    Ознака проста й не залежить від мови: ключ на 1-2 слова, у якому немає
    ані кореня цільового об'єкта, ані гео. «restaurace levne» — це та сама
    категорія з прикметником, а «burger» і «sushi» приносять свою лексику.
    Саме за такими запитами приходить людина, яка вже знає, чого хоче.
    """
    obj_roots = _word_roots(objects)
    found = []
    for k in keywords:
        if len(k.split()) > HEAD_KEYWORDS_LEN:
            continue
        words = re.findall(r"[^\W\d_]+", defold(k), re.U)
        if not words:
            continue
        # Слово-категорія в ключі — і це вже не предмет, а та сама категорія
        # з прикметником: «dobra restaurace», «gry strategiczne».
        if any(w in obj_roots or w[:WORD_ROOT_LEN] in obj_roots for w in words):
            continue
        # Саме лише гео предметом теж не є: «praha» — це не страва.
        if not any(not any(g in w or w[:5] in g for g in geo_roots)
                   for w in words):
            continue
        found.append(k)
    return found


def headlines_with_keyword(headlines, keywords):
    """Заголовки, у яких є хоч одне слово з семантики групи.

    Порівнюємо по кореню з 5 літер — інакше «турнірів» у заголовку не
    збіглося б із «турніри» в ключі. Макрос {Keyword} рахується завжди:
    він і є підстановкою запиту.
    """
    roots = _word_roots(keywords)
    found = []
    for h in headlines:
        if DKI_RE.search(h or ""):
            found.append(h)
            continue
        words = re.findall(r"[^\W\d_]+", defold(h or ""), re.U)
        if any(w in roots or w[:WORD_ROOT_LEN] in roots for w in words):
            found.append(h)
    return found


def bad_symbols(text, extra_allowed=""):
    """Символи поза дозволеним набором. DKI-конструкція зводиться до фолбека."""
    stripped = DKI_RE.sub(lambda m: m.group(1).strip(), text)
    bad = {ch for ch in stripped
           if not (ch.isalnum() or ch.isspace() or ch in APOSTROPHES or ch in extra_allowed)}
    return "".join(sorted(bad))


def shouty_words(text):
    return [w for w in re.findall(r"[^\W\d_]{4,}", text, re.U) if w.isupper()]


# Мови з нелатинською писемністю — тільки в них латиниця означає «англійський ключ».
NON_LATIN_LANGS = {"uk", "ru", "be", "bg", "sr", "mk", "el", "ka", "hy",
                   "he", "ar", "fa", "zh", "ja", "ko", "th", "hi"}


# ── Локація у форматі, який приймає Google ────────────────────────────────────
# Завантажувач не розуміє місцевих назв: «Praha, Česko» він відхиляє й пропонує
# «Prague,Prague,Czechia». Потрібна англійська канонічна назва БЕЗ пробілів
# після ком. Один такий промах валить рядок кампанії, а за ним і весь файл.

# Міста не беремо принципово: у Google для них свої канонічні назви, які не
# вгадуються («Karlovy Vary» насправді «Karlovy Vary Region»), і таблицю під
# кожне місто світу не втримати. Країна завжди валідна й список її назв сталий.
# Точну локацію звужуєш у кабінеті після імпорту — там автодоповнення.

COUNTRY_ALIASES = {
    "cesko": "Czechia", "ceska republika": "Czechia", "czech republic": "Czechia",
    "czechia": "Czechia", "cechia": "Czechia",
    "polska": "Poland", "poland": "Poland",
    "nederland": "Netherlands", "holland": "Netherlands",
    "netherlands": "Netherlands", "the netherlands": "Netherlands",
    "deutschland": "Germany", "germany": "Germany",
    "osterreich": "Austria", "austria": "Austria",
    "schweiz": "Switzerland", "suisse": "Switzerland", "switzerland": "Switzerland",
    "france": "France", "espana": "Spain", "spain": "Spain",
    "italia": "Italy", "italy": "Italy", "portugal": "Portugal",
    "ukraina": "Ukraine", "ukrajina": "Ukraine", "ukraine": "Ukraine",
    "magyarorszag": "Hungary", "hungary": "Hungary",
    "norge": "Norway", "norway": "Norway",
    "hrvatska": "Croatia", "croatia": "Croatia",
    "sverige": "Sweden", "sweden": "Sweden",
    "suomi": "Finland", "finland": "Finland",
    "danmark": "Denmark", "denmark": "Denmark",
    "belgie": "Belgium", "belgique": "Belgium", "belgium": "Belgium",
    "slovensko": "Slovakia", "slovakia": "Slovakia",
    "slovenija": "Slovenia", "slovenia": "Slovenia",
    "romania": "Romania", "bulgaria": "Bulgaria",
    "ellada": "Greece", "greece": "Greece",
    "turkiye": "Turkey", "turkey": "Turkey",
    "ireland": "Ireland", "eesti": "Estonia", "estonia": "Estonia",
    "latvija": "Latvia", "latvia": "Latvia",
    "lietuva": "Lithuania", "lithuania": "Lithuania",
    "united kingdom": "United Kingdom", "great britain": "United Kingdom",
    "england": "United Kingdom", "uk": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "velika britanija": "United Kingdom",
    # Решта Європи
    "srbija": "Serbia", "serbia": "Serbia", "србија": "Serbia",
    "bosna i hercegovina": "Bosnia and Herzegovina",
    "bosnia and herzegovina": "Bosnia and Herzegovina",
    "crna gora": "Montenegro", "montenegro": "Montenegro",
    "makedonija": "North Macedonia", "north macedonia": "North Macedonia",
    "shqiperi": "Albania", "albania": "Albania",
    "moldova": "Moldova", "молдова": "Moldova",
    "belarus": "Belarus", "беларусь": "Belarus", "білорусь": "Belarus",
    "rossiya": "Russia", "russia": "Russia", "россия": "Russia",
    "kypros": "Cyprus", "cyprus": "Cyprus", "malta": "Malta",
    "luxembourg": "Luxembourg", "letzebuerg": "Luxembourg",
    "island": "Iceland", "iceland": "Iceland",
    "gruzia": "Georgia", "georgia": "Georgia", "sakartvelo": "Georgia",
    "armenia": "Armenia", "hayastan": "Armenia",
    "azerbaijan": "Azerbaijan", "azerbaycan": "Azerbaijan",
    "kazakhstan": "Kazakhstan", "qazaqstan": "Kazakhstan", "казахстан": "Kazakhstan",
    "ellada": "Greece", "ελλαδα": "Greece",
    # Америки
    "mexico": "Mexico", "brasil": "Brazil", "brazil": "Brazil",
    "argentina": "Argentina", "chile": "Chile", "colombia": "Colombia",
    "peru": "Peru", "ecuador": "Ecuador", "uruguay": "Uruguay",
    "paraguay": "Paraguay", "bolivia": "Bolivia", "venezuela": "Venezuela",
    "costa rica": "Costa Rica", "panama": "Panama",
    "republica dominicana": "Dominican Republic",
    "dominican republic": "Dominican Republic",
    "guatemala": "Guatemala", "honduras": "Honduras",
    # Азія
    "nihon": "Japan", "japan": "Japan", "nippon": "Japan",
    "india": "India", "bharat": "India", "indonesia": "Indonesia",
    "vietnam": "Vietnam", "viet nam": "Vietnam",
    "thailand": "Thailand", "philippines": "Philippines", "pilipinas": "Philippines",
    "singapore": "Singapore", "malaysia": "Malaysia",
    "south korea": "South Korea", "korea": "South Korea",
    "republic of korea": "South Korea",
    "taiwan": "Taiwan", "hong kong": "Hong Kong", "china": "China",
    "pakistan": "Pakistan", "bangladesh": "Bangladesh", "sri lanka": "Sri Lanka",
    "nepal": "Nepal", "uzbekistan": "Uzbekistan",
    # Близький Схід і Африка
    "israel": "Israel", "yisrael": "Israel",
    "united arab emirates": "United Arab Emirates", "uae": "United Arab Emirates",
    "saudi arabia": "Saudi Arabia", "qatar": "Qatar", "kuwait": "Kuwait",
    "bahrain": "Bahrain", "oman": "Oman", "jordan": "Jordan", "lebanon": "Lebanon",
    "egypt": "Egypt", "misr": "Egypt", "maroc": "Morocco", "morocco": "Morocco",
    "tunisie": "Tunisia", "tunisia": "Tunisia", "algerie": "Algeria",
    "algeria": "Algeria", "nigeria": "Nigeria", "kenya": "Kenya",
    "ghana": "Ghana", "south africa": "South Africa", "suid-afrika": "South Africa",
    "tanzania": "Tanzania", "uganda": "Uganda", "ethiopia": "Ethiopia",
    # Океанія та Північна Америка
    "united states": "United States", "usa": "United States",
    "united states of america": "United States",
    "canada": "Canada", "australia": "Australia",
    "new zealand": "New Zealand", "aotearoa": "New Zealand",
}

# Запасний варіант, коли країну з опису не впізнали: беремо з мови кампанії.
LANG_TO_COUNTRY = {
    "cs": "Czechia", "pl": "Poland", "nl": "Netherlands", "fr": "France",
    "de": "Germany", "uk": "Ukraine", "sk": "Slovakia", "hu": "Hungary",
    "ro": "Romania", "hr": "Croatia", "sl": "Slovenia", "bg": "Bulgaria",
    "el": "Greece", "pt": "Portugal", "es": "Spain", "it": "Italy",
    "sv": "Sweden", "no": "Norway", "da": "Denmark", "fi": "Finland",
    "et": "Estonia", "lv": "Latvia", "lt": "Lithuania", "tr": "Turkey",
    "en": "United Kingdom",
    # Мова однозначно вказує країну далеко не завжди: іспанська — це і Іспанія,
    # і пів Латинської Америки. Тому це саме ЗАПАСНИЙ варіант, і якщо гео
    # важливе, воно має бути в описі сайту.
    "sr": "Serbia", "bs": "Bosnia and Herzegovina", "mk": "North Macedonia",
    "sq": "Albania", "be": "Belarus", "ru": "Russia", "ka": "Georgia",
    "hy": "Armenia", "az": "Azerbaijan", "kk": "Kazakhstan", "is": "Iceland",
    "ja": "Japan", "ko": "South Korea", "zh": "China", "th": "Thailand",
    "vi": "Vietnam", "id": "Indonesia", "ms": "Malaysia", "tl": "Philippines",
    "hi": "India", "bn": "Bangladesh", "ur": "Pakistan", "ta": "India",
    "he": "Israel", "ar": "United Arab Emirates", "fa": "Iran",
    "sw": "Kenya", "af": "South Africa", "am": "Ethiopia",
}


# Опис сайту майже завжди видає країну сам: демонімом («Czech tabletop»),
# містом чи адресою в підвалі. Якщо модель написала іншу країну — вона взяла
# її не з опису, і кампанія піде не туди. Реальний випадок: чеський сайт із
# адресою в Празі отримав Location=France, бо в тому ж чаті перед ним були
# французькі сайти.
COUNTRY_HINTS = {
    "czech": "Czechia", "czechia": "Czechia", "cesky": "Czechia",
    "ceska": "Czechia", "praha": "Czechia", "prague": "Czechia",
    "brno": "Czechia", "ostrava": "Czechia", "koruna": "Czechia",
    "french": "France", "francais": "France", "france": "France",
    "paris": "France", "lyon": "France", "marseille": "France",
    "bordeaux": "France", "toulouse": "France", "nantes": "France",
    "polish": "Poland", "polska": "Poland", "polski": "Poland",
    "warszawa": "Poland", "warsaw": "Poland", "krakow": "Poland",
    "wroclaw": "Poland", "poznan": "Poland", "gdansk": "Poland",
    "dutch": "Netherlands", "nederland": "Netherlands",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "utrecht": "Netherlands", "eindhoven": "Netherlands",
    "german": "Germany", "deutsch": "Germany", "deutschland": "Germany",
    "berlin": "Germany", "munchen": "Germany", "hamburg": "Germany",
    "hungarian": "Hungary", "magyar": "Hungary", "budapest": "Hungary",
    "spanish": "Spain", "espanol": "Spain", "espana": "Spain",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
    "italian": "Italy", "italiano": "Italy", "italia": "Italy",
    "roma": "Italy", "milano": "Italy", "napoli": "Italy",
    "portuguese": "Portugal", "portugues": "Portugal", "lisboa": "Portugal",
    "lisbon": "Portugal", "porto": "Portugal",
    "slovak": "Slovakia", "slovensko": "Slovakia", "bratislava": "Slovakia",
    "romanian": "Romania", "romania": "Romania", "bucuresti": "Romania",
    "croatian": "Croatia", "hrvatska": "Croatia", "zagreb": "Croatia",
    "greek": "Greece", "ellada": "Greece", "athens": "Greece",
    "swedish": "Sweden", "sverige": "Sweden", "stockholm": "Sweden",
    "danish": "Denmark", "danmark": "Denmark", "kobenhavn": "Denmark",
    "norwegian": "Norway", "norge": "Norway", "oslo": "Norway",
    "finnish": "Finland", "suomi": "Finland", "helsinki": "Finland",
    "belgian": "Belgium", "belgie": "Belgium", "bruxelles": "Belgium",
    "austrian": "Austria", "osterreich": "Austria", "wien": "Austria",
    "swiss": "Switzerland", "schweiz": "Switzerland", "zurich": "Switzerland",
    "ukrainian": "Ukraine", "ukraina": "Ukraine", "kyiv": "Ukraine",
    "lviv": "Ukraine", "odesa": "Ukraine",
    "turkish": "Turkey", "turkiye": "Turkey", "istanbul": "Turkey",
    "british": "United Kingdom", "london": "United Kingdom",
    "manchester": "United Kingdom",
}


# Мова кампанії визначається країною показу, а не мовою сайту. Сайт може бути
# англійським, але поляки шукають польською — англомовна кампанія на Польщу
# трафіку не дає. Для країн із кількома робочими мовами перелічені всі.
# Мови, які Google Ads приймає в таргетингу. Це ЗАКРИТИЙ перелік: азербайджанської,
# казахської, грузинської, вірменської в ньому немає, хоч ISO-коди в них є.
# Модель про це не знає й спокійно віддає «az» — а такий рядок кампанії
# завантажувач не приймає. Тому звіряємо явно.
GOOGLE_ADS_LANGS = {
    "ar", "bn", "bg", "ca", "zh", "hr", "cs", "da", "nl", "en", "et", "tl",
    "fi", "fr", "de", "el", "gu", "he", "iw", "hi", "hu", "is", "id", "it",
    "ja", "kn", "ko", "lv", "lt", "ms", "ml", "mr", "no", "fa", "pl", "pt",
    "pa", "ro", "ru", "sr", "sk", "sl", "es", "sv", "ta", "te", "th", "tr",
    "uk", "ur", "vi",
}

COUNTRY_LANGS = {
    "Poland": {"pl"}, "Czechia": {"cs"}, "Slovakia": {"sk"},
    "France": {"fr"}, "Netherlands": {"nl"}, "Germany": {"de"},
    "Austria": {"de"}, "Switzerland": {"de", "fr", "it"},
    "Belgium": {"nl", "fr"}, "Hungary": {"hu"}, "Spain": {"es"},
    "Italy": {"it"}, "Portugal": {"pt"}, "Ukraine": {"uk"},
    "Slovenia": {"sl"}, "Croatia": {"hr"}, "Serbia": {"sr"},
    "Romania": {"ro"}, "Bulgaria": {"bg"}, "Greece": {"el"},
    "Turkey": {"tr"}, "Sweden": {"sv"}, "Norway": {"no"},
    "Denmark": {"da"}, "Finland": {"fi"}, "Iceland": {"is"},
    "Estonia": {"et"}, "Latvia": {"lv"}, "Lithuania": {"lt"},
    "United Kingdom": {"en"}, "Ireland": {"en"}, "Malta": {"en"},
    "United States": {"en", "es"}, "Canada": {"en", "fr"},
    "Australia": {"en"}, "New Zealand": {"en"}, "South Africa": {"en"},
    "Brazil": {"pt"}, "Portugal ": {"pt"}, "Mexico": {"es"},
    "Argentina": {"es"}, "Chile": {"es"}, "Colombia": {"es"},
    "Peru": {"es"}, "Japan": {"ja"}, "South Korea": {"ko"},
    "Israel": {"he"},
    # Грузинської та азербайджанської в Google Ads немає — там працює
    # російська, як і в Казахстані.
    "Georgia": {"ru", "en"}, "Azerbaijan": {"ru"},
    # Казахстан шукає російською: казахська дає обсяг, якого немає.
    # Це не політика, а те, як там реально працює пошук.
    "Kazakhstan": {"ru"},
}

# Службові слова, які майже не трапляються поза англійською. За ними видно,
# що кампанію написали англійською, хоча мова заявлена інша.
ENGLISH_MARKERS = {
    "the", "and", "with", "your", "our", "from", "this", "that", "these",
    "you", "are", "was", "were", "have", "has", "will", "would", "their",
    "more", "most", "now", "what", "how", "why", "when", "where", "which",
    "every", "each", "about", "into", "over", "through", "between",
    "discover", "explore", "experience", "choose", "find", "learn",
}


def english_ratio(texts):
    """Частка англійських службових слів. У польській чи чеській кампанії
    вона майже нульова, в англійській — від десятої частини."""
    words = [w for t in texts for w in re.findall(r"[a-z']{2,}", (t or "").lower())]
    if len(words) < 12:
        return 0.0
    return sum(1 for w in words if w in ENGLISH_MARKERS) / len(words)


def country_scores(text):
    """Скільки разів опис натякає на кожну країну.

    Рахуємо ВСІ згадки, а не факт наявності: одне слово «France» посеред
    чеського опису нічого не доводить, а вісім «Czech» і адреса в Празі —
    доводять. Слова беремо цілими, тому «Parisian» не дасть France.
    """
    words = re.findall(r"[^\W\d_]+", defold(text or ""), re.U)
    scores = {}
    for w in words:
        country = COUNTRY_HINTS.get(w)
        if country:
            scores[country] = scores.get(country, 0) + 1
    return scores


def detect_countries(text):
    """Усі згадані країни — без ваги, для довідки."""
    return set(country_scores(text))


def dominant_country(text):
    """Країна, якої в описі відчутно більше за решту. Якщо нічия — порожньо:
    краще промовчати, ніж наполягати на здогадці."""
    scores = country_scores(text)
    if not scores:
        return ""
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, n = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    return top if n > second else ""


# Національний домен — другий орієнтир на гео, і сильніший за згадки
# в описі. Привід: сайт ресторану у Франції на домені .fr, а в описі
# italiano, pasta, Toscana — це КУХНЯ, а не країна показу. Модель бачила
# купу італійських слів і ставила Location: Italy, перевірка з нею
# погоджувалась, і кампанія йшла не в ту країну.
# Домени на кшталт .com, .net, .org нічого про країну не кажуть — там
# лишається опис.
TLD_COUNTRY = {
    "fr": "France", "de": "Germany", "at": "Austria", "ch": "Switzerland",
    "it": "Italy", "es": "Spain", "pt": "Portugal", "nl": "Netherlands",
    "be": "Belgium", "cz": "Czechia", "sk": "Slovakia", "pl": "Poland",
    "hu": "Hungary", "ro": "Romania", "bg": "Bulgaria", "gr": "Greece",
    "se": "Sweden", "no": "Norway", "dk": "Denmark", "fi": "Finland",
    "lv": "Latvia", "lt": "Lithuania", "ee": "Estonia", "ie": "Ireland",
    "uk": "United Kingdom", "us": "United States", "ca": "Canada",
    "au": "Australia", "nz": "New Zealand", "jp": "Japan", "br": "Brazil",
    "mx": "Mexico", "za": "South Africa", "ua": "Ukraine", "si": "Slovenia",
    "hr": "Croatia", "rs": "Serbia", "tr": "Turkey", "il": "Israel",
}


def tld_country(url):
    """Країна з національного домену: a.fr -> France, a.co.uk -> United
    Kingdom. Нічого не каже про країну — порожньо."""
    host = re.sub(r"^https?://", "", (url or "").strip().lower())
    host = host.split("/")[0].split("?")[0].split(":")[0].strip(".")
    if not host or host.replace(".", "").isdigit():
        return ""
    parts = host.split(".")
    if len(parts) < 2:
        return ""
    return TLD_COUNTRY.get(parts[-1], "")


# Як країни пишуть в уточненнях: російською, українською, англійською.
# COUNTRY_ALIASES знає лише англійські й місцеві назви, а люди пишуть
# «гео польша» — і раніше таке уточнення програма просто не бачила.
# Основи слів, щоб ловити відмінки: Польша / Польшу / Польщі.
_NOTE_STEMS = {
    "Poland": ("польш", "польщ"), "Ukraine": ("украин", "україн"),
    "Germany": ("герман", "німеч"), "France": ("франц",),
    "Austria": ("австри", "австрі"), "Australia": ("австрал",),
    "Switzerland": ("швейцар",), "Italy": ("итали", "італі"),
    "Spain": ("испан", "іспан"), "Portugal": ("португал",),
    "Netherlands": ("нидерланд", "нідерланд", "голланд"),
    "Belgium": ("бельги", "бельгі"), "Czechia": ("чехи", "чехі", "чеськ"),
    "Slovakia": ("словаки", "словакі", "словаччин"),
    "Hungary": ("венгри", "угорщин"), "Romania": ("румын", "румун"),
    "Bulgaria": ("болгар",), "Greece": ("греци", "греці"),
    "Sweden": ("швеци", "швеці"), "Norway": ("норвеги", "норвегі"),
    "Finland": ("финлянд", "фінлянд"), "Latvia": ("латви", "латві"),
    "Lithuania": ("литв",), "Estonia": ("эстони", "естоні"),
    "Ireland": ("ирланд", "ірланд"),
    "United Kingdom": ("великобритан", "британи", "британі"),
    "United States": ("сша",), "Canada": ("канад",),
    "New Zealand": ("зеланди", "зеланді"), "Japan": ("япони", "японі"),
    "Brazil": ("бразили", "бразилі"), "Mexico": ("мексик",),
    "Slovenia": ("словени", "словені"), "Croatia": ("хорвати", "хорваті"),
    "Serbia": ("серби", "сербі"), "Turkey": ("турци", "туреч"),
    "Israel": ("израил", "ізраїл", "израїл"),
}
# Слова, що збігаються з основою, але про інше: «данные» — не Данія.
_NOTE_WORDS = {"дания": "Denmark", "данию": "Denmark", "данией": "Denmark",
               "данія": "Denmark", "данії": "Denmark", "данію": "Denmark"}
_NOTE_MARKS = ("гео", "geo", "страна", "країна", "country", "location",
               "локація", "локация", "таргет")


def _note_country(word, codes=False):
    w = defold(word)
    if w in _NOTE_WORDS:
        return _NOTE_WORDS[w]
    for country, stems in _NOTE_STEMS.items():
        if any(w.startswith(defold(s)) for s in stems):
            return country
    found = COUNTRY_ALIASES.get(w)
    if found:
        return found
    # Двобуквений код — лише одразу після «гео»: інакше «de» чи «it»
    # у звичайному тексті ставали б Німеччиною й Італією.
    if codes and len(w) == 2:
        return TLD_COUNTRY.get(w, "")
    return ""


def geo_from_notes(text):
    """Країна, яку людина задала в уточненні. Порожньо — якщо не задала.

    Спершу слово одразу після «гео» / «країна» / «geo»: «гео польша, сайт
    україни» — це Польща, хоч Україну теж названо. Немає такого слова —
    беремо країну, лише якщо вона в тексті одна; дві без підказки — не
    вгадуємо.
    """
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    for i, w in enumerate(words):
        if defold(w) in _NOTE_MARKS and i + 1 < len(words):
            c = _note_country(words[i + 1], codes=True)
            if c:
                return c
    found = {c for c in (_note_country(w) for w in words) if c}
    return found.pop() if len(found) == 1 else ""


def apply_notes_geo(wants, notes):
    """Країна з уточнення стає ЗАДАНИМ гео: її вимагає і завдання моделі,
    і перевірка. Раніше уточнення йшло моделі простим текстом, а перевірка
    про нього не знала: модель ставила Польщу, перевірка бачила домен
    .com.ua, рахувала Польщу помилкою, і доопрацювання повертало Україну.
    У соціалі країну поза ПЕРЕЛІКОМ 1 не беремо — її однаково не можна.
    """
    country = geo_from_notes(notes)
    if not country or (SOCIAL_CASINO and country not in SOCIAL_GROUP_1):
        return ""
    wants["geo"] = country
    return country


# Чи схожа тема на ремонт/техпідтримку пристроїв. Потрібно не для заборони,
# а щоб підказати моделі безпечні формулювання: цю нішу Google відхиляє як
# «сторонню техпідтримку», коли оголошення звучить як підтримка чужих брендів.
_TECH_REPAIR = [
    r"\bремонт\w*\s+(телефон|смартфон|ноутбук|комп|планшет|ґаджет|гаджет|apple|iphone|samsung|xiaomi|макбук|macbook)",
    r"\b(телефон|смартфон|ноутбук|комп|планшет|екран|скл|акумулятор|батаре|диспле)\w*\s+ремонт",
    r"\brepair\w*\s+(of\s+)?(phone|smartphone|laptop|comput|pc|tablet|device|screen|iphone|macbook)",
    r"\b(phone|laptop|computer|pc|tablet|device|screen|iphone|macbook|samsung)\s+repair",
    r"\breparatur\w*", r"\br[ée]paration\s+(de\s+)?(t[ée]l[ée]phone|ordinateur|portable|smartphone)",
    r"\breparaci[óo]n\s+(de\s+)?(tel[ée]fono|ordenador|port[áa]til|m[óo]vil)",
    r"\briparazion\w*", r"\bnaprawa\s+(telefon|komputer|laptop)",
    r"\bзаміна\s+(екран|скл|акумулятор|батаре|диспле)", r"\bзамена\s+(экран|стекл|аккумулятор|батаре|диспле)",
    r"\bscreen\s+replacement", r"\bbattery\s+replacement",
    r"\bтехпідтримк\w*", r"\bтехподдержк\w*", r"\btech\s+support",
    r"\bпрошивк\w*", r"\bрозблокуванн\w*\s+(телефон|iphone)", r"\bунлок\w*", r"\bunlock\s+(phone|iphone)",
    r"\bсервісн\w*\s+центр", r"\bсервисн\w*\s+центр", r"\bservice\s+center",
]
_TECH_REPAIR_RE = [re.compile(p, re.I | re.U) for p in _TECH_REPAIR]


def user_extra_hint(x):
    return x or ""


def is_tech_repair(text):
    low = (text or "").lower()
    return any(r.search(low) for r in _TECH_REPAIR_RE)


TECH_SUPPORT_BRIEF = (
    "\n\nОБЕРЕЖНО — ТЕМА РЕМОНТУ/ТЕХПІДТРИМКИ. Google відхиляє таку рекламу "
    "як «сторонню техпідтримку», коли вона звучить як служба підтримки чужих "
    "брендів. Щоб пройшло, подавай це як МАЙСТЕРНЮ (локальний сервіс):\n"
    "- пиши про послугу й майстерню, а не про «підтримку» чи «допомогу»: "
    "уникай слів support, техпідтримка, служба підтримки, гаряча лінія, "
    "допомога з пристроєм, вирішення проблем;\n"
    "- бренди не став поруч із «ремонт»: не «ремонт Apple/Samsung», а "
    "«ремонт смартфонів», «заміна екрана», «ремонт ноутбуків». Бренд можна "
    "лише як перелік того, що беруть у роботу, а не як обіцянку підтримки;\n"
    "- наголошуй на ФІЗИЧНОМУ ремонті в майстерні: приніс пристрій — забрав "
    "полагоджений. Жодного віддаленого доступу, дзвінків на гарячу лінію чи "
    "входу в акаунт;\n"
    "- гаразд: конкретні роботи (заміна екрана, акумулятора, чистка, "
    "діагностика), гарантія на ремонт, терміни, ціна від."
)


def geo_signals(url, source, wants=None):
    """Два орієнтири на гео: опис сайту й національний домен.

    Повертає (задане, за описом, за доменом). Задане буває лише там, де
    гео тягне сама програма (соціал), і тоді воно головне. В інших
    збірках дивимось на обидва орієнтири РАЗОМ, і жоден не перебиває
    інший наосліп: на .fr може бути ресторан з італійською кухнею, а на
    .com — магазин, що торгує лише в Польщі.
    """
    return ((wants or {}).get("geo") or "",
            dominant_country(source),
            tld_country(url))


def normalize_location(location, language=""):
    """Повертає лише назву країни англійською — єдине, що Google приймає
    без сюрпризів. Місто й регіон відкидаємо."""
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    for p in reversed(parts):          # країна зазвичай остання
        found = COUNTRY_ALIASES.get(defold(p))
        if found:
            return found
    return LANG_TO_COUNTRY.get((language or "").strip().lower()[:2], "")


def defold(text):
    """Знімає діакритику: «Česko» і «cesku» мають зіставлятися однаково.
    NFKD не розкладає ł, ø, ß — їх додаємо вручну."""
    text = text.lower()
    for a, b in (("ł", "l"), ("ø", "o"), ("ß", "ss"), ("đ", "d"), ("æ", "ae")):
        text = text.replace(a, b)
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def _geo_tokens(location):
    """Корені міста й країни окремо: потрібно рівно 2 ключі з містом і 1 з країною.
    Беремо перші 4 літери, щоб ловити відмінки (Praha / Prahy / Praze)."""
    def roots_of(chunk):
        # Відрізаємо два останні символи під відмінювання, але не коротше трьох:
        # чеське «Praha» у місцевому стає «v Praze», тобто змінюється і приголосна.
        out = []
        for t in chunk.split():
            t = defold(t)
            if len(t) >= 4:
                out.append(t[:max(3, len(t) - 2)])
        return out

    parts = [p.strip() for p in location.split(",") if p.strip()]
    city_roots, country_roots = [], []
    if parts:
        city_roots = roots_of(parts[0])
    if len(parts) > 1:
        country_roots = roots_of(parts[-1])
    elif parts:
        # Location без коми — вважаємо це країною, міста немає
        city_roots, country_roots = [], city_roots
    return city_roots, country_roots

def validate(draft, wants=None):
    """Повертає (errors, warnings). errors блокують створення CSV.

    wants — які розширення замовлені: {"sitelinks","callouts","snippets"}.
    Вимкнене розширення не має давати зауваження про недобір.
    """
    errors, warnings = [], []
    agg = bool((wants or {}).get("aggregator"))
    # М'якість стосується текстів оголошень і розширень. Ключові слова — це те,
    # що вводить людина, там промо-лексика природна й нічого не порушує.
    # Вимкнути її не можна: спокійна подача потрібна в будь-якій ніші.
    soft = bool((wants or {}).get("soft", True))
    # «gaming», «play», «гра» — евфемізми лише поруч із гральними ознаками.
    # Ознака може бути в самій кампанії або в описі сайту, з якого ми її
    # вирізали: scrub_description повідомляє про це через wants["scrubbed"].
    ambiguous = (not agg) and (gambling_context(draft)
                               or bool((wants or {}).get("scrubbed")))

    name = (draft.get("campaign_name") or "").strip()
    if not name:
        errors.append("Порожня назва кампанії.")
    if "_" in name:
        errors.append(f"Назва кампанії містить підкреслення: {name}")
    words = len(name.split())
    if words > 4:
        warnings.append(f"Назва кампанії {words} слів, треба 2-4 — довгі назви "
                        f"нечитні в кабінеті: {name}")
    elif words < 2:
        warnings.append(f"Назва кампанії з одного слова, треба 2-4: {name}")
    # Назва кампанії й назви груп видно в кабінеті і в звітах, а раніше вони
    # взагалі не проходили фільтр — гральне слово пролізало саме сюди.
    _scan_policy("Назва кампанії", name, errors, warnings, agg,
                 ambiguous=ambiguous)

    website = (draft.get("website") or "").strip()
    if not website.startswith("http"):
        errors.append(f"Final URL має починатися з http(s): {website}")

    # Локація — найдорожча помилка: через неї відпадає рядок кампанії, а разом
    # із ним і всі інші рядки файлу.
    loc_raw = (draft.get("location") or "").strip()
    loc = normalize_location(loc_raw, draft.get("language", ""))
    if not loc:
        errors.append(
            f"Не впізнав країну в Location «{loc_raw}». Впиши країну англійською "
            f"(Czechia, Poland, Netherlands) — місто в це поле не йде.")
    elif loc != loc_raw:
        warnings.append(f"Location зведено до країни: «{loc_raw}» → «{loc}». "
                        f"Місто в цьому полі Google не приймає — звужуй "
                        f"локацію вручну в кабінеті після імпорту.")
    # Гео мусить збігатися з описом сайту, а не з тим, що модель бачила
    # в попередньому запиті. Судимо за вагою згадок, не за одним словом.
    source = (wants or {}).get("source_desc", "")
    forced, by_desc, by_tld = geo_signals(website, source, wants)
    if loc and forced and loc != forced:
        errors.append(
            f"Location «{loc}» не та, що задана на цей запуск ({forced}). "
            f"Гео задає програма — бери його як є.")
    elif loc and not forced:
        # Привід: ресторан на .fr з італійським меню. Модель ставила
        # France, а перевірка дивилась лише в опис, бачила Італію й
        # зараховувала правильне гео як помилку.
        allowed = [g for g in (by_desc, by_tld) if g]
        if allowed and loc not in allowed:
            seen = []
            if by_desc:
                seen.append(f"опис сайту — {by_desc}")
            if by_tld:
                seen.append(f"домен — {by_tld}")
            errors.append(
                f"Location «{loc}» не збігається з жодним орієнтиром: "
                f"{'; '.join(seen)}. Країна показу — та, де сайт продає чи "
                f"працює. Кухня, стиль чи походження товару — це не країна.")
    # Мова мусить бути мовою країни показу. Сайт англійською, що працює на
    # Польщу, — це польська кампанія, а не англійська.
    lang = (draft.get("language") or "").strip().lower()[:2]
    # Мова мусить бути з переліку Google Ads. Азербайджанська, казахська,
    # грузинська існують як ISO-коди, але в таргетингу їх немає — рядок
    # кампанії з такою мовою завантажувач не прийме.
    if lang and lang not in GOOGLE_ADS_LANGS:
        works = COUNTRY_LANGS.get(loc)
        hint = (f" У {loc} реклама йде {'/'.join(sorted(works))}."
                if works else "")
        errors.append(
            f"Мову «{lang}» Google Ads не підтримує — такої мови немає в "
            f"таргетингу, і кампанія не завантажиться.{hint} Перепиши всю "
            f"кампанію мовою, якою там справді шукають.")

    expected = COUNTRY_LANGS.get(loc)
    if expected and lang and lang not in expected:
        errors.append(
            f"Мова «{lang}» не для країни {loc} — там шукають "
            f"{'/'.join(sorted(expected))}. Опис сайту може бути англійським, "
            f"але кампанія мусить бути мовою країни, інакше трафіку не буде.")
    # Мова заявлена одна, а тексти написані англійською.
    if expected and "en" not in expected:
        texts = []
        for g in draft.get("ad_groups") or []:
            texts += [k for k in (g.get("keywords") or [])]
            for ad in g.get("ads") or []:
                texts += list(ad.get("headlines") or [])
                texts += list(ad.get("descriptions") or [])
        ratio = english_ratio(texts)
        if ratio > 0.08:
            errors.append(
                f"Кампанія написана англійською, хоча гео {loc}: англійських "
                f"службових слів {ratio:.0%}. Перепиши ключі, заголовки й "
                f"описи мовою {'/'.join(sorted(expected))}.")
    # Країни, куди Google не пускає рекламу взагалі — перевіряємо завжди.
    if loc in GEO_SUSPENDED:
        errors.append(f"{loc}: {GEO_SUSPENDED[loc]}")
    # Сертифікація дозволяє показ, але не скасовує місцевого регулювання.
    if agg:
        geo_err, geo_warn = gambling_geo_notes(loc)
        errors.extend(geo_err)
        warnings.extend(geo_warn)

    # ── СОЦІАЛЬНЕ КАЗИНО ─────────────────────────────────────────────────
    # Google називає порушення цієї політики грубими: акаунт вимикають без
    # попередження й без права рекламуватись далі. Тому тут помилки, а не
    # зауваження.
    if SOCIAL_CASINO:
        if loc and loc not in SOCIAL_GROUP_1 and loc not in SOCIAL_GROUP_2:
            errors.append(
                f"Соціальні казино не можна рекламувати в «{loc}». Google "
                f"дозволяє лише два переліки країн, і ця до них не входить — "
                f"оголошення відхилять, а за повтори знімуть акаунт.")
        # Дві групи країн не можна змішувати в одному акаунті: сертифікація
        # видається під одну з них.
        # Саме тексти оголошень, а не весь чернетка: вимога про
        # безкоштовність стосується того, що людина ПОБАЧИТЬ.
        # Назва кампанії й ключі їй не годяться — їх у видачі немає.
        head_text = " ".join(all_ad_texts(draft.get("ad_groups")))
        if not _hit(FREE_PLAY_RE, head_text):
            errors.append(
                "Ніде не сказано, що гра безкоштовна й без реальних грошей. "
                "Це пряма вимога сертифікації соціальних казино: у текстах "
                "мусить бути «безкоштовно», «віртуальні фішки», «for fun» "
                "або подібне.")
        else:
            groups_ = draft.get("ad_groups") or []
            for g_ in groups_:
                for ad_ in (g_.get("ads") or []):
                    heads_ = [h for h in (ad_.get("headlines") or []) if h.strip()]
                    descs_ = [d for d in (ad_.get("descriptions") or []) if d.strip()]
                    if heads_ and not any(_hit(FREE_PLAY_RE, h) for h in heads_):
                        warnings.append(
                            f"[{(g_.get('name') or '').strip()}] жоден заголовок "
                            f"не каже, що гра безкоштовна. Сертифікація вимагає "
                            f"це показувати, а не ховати в описі.")
                    if descs_ and not any(_hit(FREE_PLAY_RE, d) for d in descs_):
                        warnings.append(
                            f"[{(g_.get('name') or '').strip()}] жоден опис не "
                            f"каже, що гра без реальних грошей.")

    # ── ПОСАДКОВА СТОРІНКА ───────────────────────────────────────────────
    # Найдорожче в цій роботі — не текст оголошення, а те, що людина побачить
    # за посиланням. Мертвий домен і сторінка не про те, що в оголошенні, —
    # це відхилення, а повторно й блокування акаунта.
    page = (wants or {}).get("page") or {}
    if page:
        if not page.get("ok"):
            errors.append(
                f"Посадкова сторінка не відкрилася: {page.get('error') or 'немає відповіді'}. "
                f"Оголошення на неробочу сторінку Google відхиляє, а за повтори "
                f"знімає акаунт. Перевір посилання, перш ніж заливати.")
        else:
            here = domain_of(website)
            there = domain_of(page.get("final_url") or "")
            if here and there and here != there:
                warnings.append(
                    f"Посилання веде на інший домен: {here} -> {there}. "
                    f"Google звіряє кінцевий URL із показаним, і розбіжність "
                    f"читає як обхід систем.")
            # Тема оголошення мусить бути на сторінці. Це і вимога Google,
            # і те, від чого залежить, чи клікне людина вдруге.
            low = defold(page.get("text") or "")
            objs = [o for o in (draft.get("target_objects") or []) if (o or "").strip()]
            missing = [o for o in objs if not _covers_object(low, [o])]
            if objs and len(missing) == len(objs):
                warnings.append(
                    f"Жодного цільового об'єкта немає на самій сторінці "
                    f"({', '.join(objs)}). Або сторінка не про це, або об'єкти "
                    f"вигадані — і те, і те веде до відхилення за невідповідність.")

    # Число, якого немає на сайті, — це вигадка: «Přes 200 her» ніхто не
    # перевіряв, а людина побачить його в оголошенні й не знайде на сторінці.
    # Вік 18/21 пропускаємо: у частині гео попередження вимагає закон.
    source = defold((wants or {}).get("source_desc") or "")
    if source:
        known = set(re.findall(r"\d+", source))
        seen_nums = set()
        for text in draft_texts(draft):
            for num in re.findall(r"\d{2,}", text or ""):
                if num in known or num in ("18", "21") or num in seen_nums:
                    continue
                seen_nums.add(num)
                errors.append(
                    f"Число «{num}» є в оголошенні, але його немає в описі "
                    f"сайту. Пиши лише те, що на сайті справді є — інакше "
                    f"це обіцянка, яку сторінка не підтверджує: {text[:70]}")

    groups = draft.get("ad_groups") or []
    if not groups:
        errors.append("Жодної групи оголошень.")
    if len(groups) > 2:
        warnings.append(f"Груп більше двох ({len(groups)}), спека дозволяє 1-2.")

    city_roots, country_roots = _geo_tokens(draft.get("location") or "")
    geo_roots = city_roots + country_roots

    def has_city(text):
        low = defold(text)
        return any(r in low for r in city_roots)

    def has_country(text):
        low = defold(text)
        return any(r in low for r in country_roots)

    def has_geo(text):
        low = defold(text)
        return any(r in low for r in geo_roots)

    # Корені цільових об'єктів: по них перевіряємо, що гола родова назва
    # предмета таки є серед коротких ключів. Беремо перші 5 літер слова —
    # так «deskove» знайдеться і в «deskovych», і в «deskove hry».
    objects = [defold(o) for o in (draft.get("target_objects") or [])
               if (o or "").strip()]

    seen_headlines = set()
    seen_keywords, all_headlines = {}, {}
    for g in groups:
        gname = (g.get("name") or "").strip()
        if "_" in gname:
            errors.append(f"Назва групи містить підкреслення: {gname}")
        if len(gname.split()) > 3:
            warnings.append(f"Назва групи {len(gname.split())} слів, треба 2-3: {gname}")
        if gname and defold(gname) == defold(name):
            warnings.append(f"Назва групи дублює назву кампанії: {gname}")
        _scan_policy("Назва групи", gname, errors, warnings, agg,
                     ambiguous=ambiguous)

        kws = [k.strip() for k in (g.get("keywords") or []) if k.strip()]
        if len(kws) != KEYWORDS_PER_GROUP:
            warnings.append(f"[{gname}] ключів {len(kws)}, треба рівно "
                            f"{KEYWORDS_PER_GROUP} — недобір звужує охоплення.")
        dupes = {k.lower() for k in kws if [x.lower() for x in kws].count(k.lower()) > 1}
        for dup in sorted(dupes):
            warnings.append(f"[{gname}] ключ повторюється: {dup}")
        # Гео — це ЛІМІТ, а не норма: забагато гео звужує охоплення, а мало —
        # не біда. Тому лаємось лише на перебір.
        geo_kws = sum(1 for k in kws if has_geo(k))
        if geo_kws > GEO_KEYWORDS_MAX:
            warnings.append(f"[{gname}] ключів з гео {geo_kws}, "
                            f"дозволено до {GEO_KEYWORDS_MAX}.")

        # Поріг саме 4 слова: у слов'янських і романських мовах три слова — це
        # звичайний частотний запит через прийменник («restaurace v centru»),
        # а не довгий хвіст. За порогом 3 еталонний файл теж «не проходив».
        long_tail = sum(1 for k in kws if len(k.split()) >= 4)
        if long_tail < 3:
            warnings.append(f"[{gname}] довгих хвостів (4+ слова) {long_tail}, треба 3-5.")

        # Короткі ключі — це весь обсяг групи, тому тут помилка, а не
        # зауваження. Кампанія з самих вузьких фраз збирає Low search volume
        # на кожному рядку й не показується взагалі: реальний випадок —
        # чеська група, де всі 15 ключів були «Not eligible».
        head = [k for k in kws if len(k.split()) <= HEAD_KEYWORDS_LEN]
        if len(head) < HEAD_KEYWORDS_MIN:
            errors.append(
                f"[{gname}] коротких ключів (1-2 слова) {len(head)}, треба "
                f"{HEAD_KEYWORDS_MIN}-{HEAD_KEYWORDS_MAX}. Саме вони дають "
                f"обсяг: з самих лише вузьких фраз Google ставить Low search "
                f"volume і кампанія не показується.")
        elif objects and not any(_covers_object(k, objects) for k in head):
            errors.append(
                f"[{gname}] серед коротких ключів немає самого предмета "
                f"({', '.join(draft.get('target_objects') or [])}). Додай "
                f"голу родову назву окремим ключем — на ній тримається обсяг.")

        # Сама категорія збирає покази, але не кліки: людина шукає конкретну
        # річ. Ресторан без «бургер» і «суші», настолки без «Monopoly»,
        # кіберспорт без «Dota» — це набір, який місяць чекає першого кліку.
        stacks = noun_stack_tails(kws)
        if stacks:
            warnings.append(
                f"[{gname}] хвости зі стосу іменників, без жодного короткого "
                f"службового слова — так не шукають, це опис розділу сайту: "
                + "; ".join(stacks[:4]))

        items = item_keywords(kws, draft.get("target_objects") or [], geo_roots)
        if len(items) < ITEM_KEYWORDS_MIN:
            errors.append(
                f"[{gname}] предметних ключів {len(items)}, треба "
                f"{ITEM_KEYWORDS_AIM}. Усі короткі ключі побудовані на самій "
                f"категорії — за такими запитами приходять рідко. Додай назви "
                f"конкретних речей цієї ніші окремими ключами: страви для "
                f"ресторану, назви ігор для настолок і кіберспорту, послуги "
                f"для сервісу.")

        # Англійські ключі впізнаємо за латиницею — але це працює лише тоді, коли
        # основна мова кампанії не латинська. Для нідерландської чи чеської
        # латиниця нічого не доводить, тому там не перевіряємо взагалі.
        if (draft.get("language") or "").strip().lower()[:2] in NON_LATIN_LANGS:
            latin = sum(1 for k in kws if re.fullmatch(r"[A-Za-z0-9\s'’-]+", k))
            if not 1 <= latin <= 3:
                warnings.append(f"[{gname}] англійських ключів {latin}, треба 1-3.")

        # Семантичні петлі: один корінь не більше 3 разів на групу.
        # Цільові об'єкти й гео сюди НЕ входять: правило якоря вимагає об'єкт
        # у кожному ключі, а гео має власний ліміт. Інакше два правила
        # суперечили б одне одному на бізнесі з одним об'єктом (ресторан).
        exempt = set(city_roots) | set(country_roots)
        for obj in (draft.get("target_objects") or []):
            for word in re.findall(r"[^\W\d_]{4,}", defold(obj), re.U):
                exempt.add(word[:5])
                exempt.add(word[:4])

        roots = {}
        for k in kws:
            for word in re.findall(r"[^\W\d_]{4,}", defold(k), re.U):
                if word[:5] in exempt or word[:4] in exempt:
                    continue
                roots[word[:5]] = roots.get(word[:5], 0) + 1
        for root, n in sorted(roots.items()):
            if n > 3:
                warnings.append(f"[{gname}] корінь «{root}» повторюється {n} разів, "
                                f"дозволено 3 — шукай інші об'єкти.")

        # Гола назва міста чи країни ключем — той самий семантичний вакуум,
        # що й «сервісний центр»: запит будь-кого про будь-що.
        for k in kws:
            words = [w for w in re.findall(r"[^\W\d_]+", defold(k), re.U)]
            if words and all(any(r in w for r in geo_roots) for w in words):
                errors.append(f"[{gname}] ключ — сама лише назва гео, без об'єкта: {k}")

        for k in kws:
            if "[" in k or "]" in k or '"' in k:
                errors.append(f"[{gname}] ключ із дужками/лапками: {k}")
            bad = bad_symbols(k)
            if bad:
                errors.append(f"[{gname}] ключ із забороненими символами «{bad}»: {k}")
            if len(k) > 30:
                warnings.append(f"[{gname}] ключ {len(k)} символів, ліміт 30: {k}")
            for rx in INFO_INTENT_RE:
                if rx.search(k):
                    warnings.append(f"[{gname}] інформаційний інтент у ключі: {k}")
                    break
            _scan_policy(f"[{gname}] ключ", k, errors, warnings, agg,
                         claims=False, ambiguous=ambiguous)
            cross = seen_keywords.get(k.lower())
            if cross and cross != gname:
                warnings.append(f"[{gname}] ключ перетинається з групою «{cross}»: {k}")
            seen_keywords[k.lower()] = gname

        ads = g.get("ads") or []
        if not ads:
            errors.append(f"[{gname}] жодного оголошення.")
        if len(ads) > 2:
            warnings.append(f"[{gname}] оголошень {len(ads)}, передбачено 1-2.")

        for ad_i, ad in enumerate(ads, 1):
            tag = f"{gname}" if len(ads) == 1 else f"{gname} / оголошення {ad_i}"
            _validate_ad(ad, tag, geo_roots, has_geo, errors, warnings, agg, soft,
                         ambiguous, kws)

    return _validate_assets(draft, errors, warnings, wants)


def _validate_ad(ad, gname, geo_roots, has_geo, errors, warnings, agg=False,
                 soft=False, ambiguous=False, kws=()):
        seen_headlines = set()
        heads = [h.strip() for h in (ad.get("headlines") or []) if h.strip()]
        if len(heads) != 15:
            warnings.append(f"[{gname}] заголовків {len(heads)}, треба рівно 15.")
        geo_heads = sum(1 for h in heads if has_geo(h))
        if geo_roots and geo_heads > 2:
            warnings.append(f"[{gname}] гео згадано в {geo_heads} заголовках, дозволено до 2.")
        dki_heads = sum(1 for h in heads if DKI_RE.search(h))
        if not 1 <= dki_heads <= 4:
            warnings.append(f"[{gname}] заголовків з макросом {dki_heads}, треба 1-4.")
        # Релевантність Google рахує по збігу заголовка з запитом. Заголовок,
        # у якому немає жодного слова з семантики групи, працює вхолосту.
        # Три вільні лишаємо під нейтральний шар.
        covered = headlines_with_keyword(heads, kws)
        if kws and heads and len(covered) < HEADLINE_KEYWORD_MIN:
            warnings.append(
                f"[{gname}] заголовків без ключа {len(heads) - len(covered)}, "
                f"з ключем має бути щонайменше {HEADLINE_KEYWORD_MIN} із 15 — "
                f"саме за збігом із запитом Google рахує релевантність.")
        for h in heads:
            n = effective_len(h)
            if n > LIMIT_HEADLINE:
                # Не «скороти на 1»: за такою підказкою модель відрізає хвіст
                # слова — «Budově» перетворюється на «Budo». Просимо переписати
                # і даємо ціль із запасом, щоб думка вмістилася цілком.
                errors.append(
                    f"[{gname}] заголовок {n}/{LIMIT_HEADLINE} — ПЕРЕПИШИ "
                    f"коротше, ціль до {LIMIT_HEADLINE - 3} символів. Не "
                    f"обрізай слово й не скорочуй крапкою: {h}")
            bad = bad_symbols(h)
            if bad:
                errors.append(f"[{gname}] заголовок із забороненими символами «{bad}»: {h}")
            plain = DKI_RE.sub(lambda m: m.group(1).strip(), h)
            words = [w for w in re.findall(r"[^\W\d_]{2,}", plain, re.U)]
            if words and not all(w[0].isupper() for w in words):
                warnings.append(f"[{gname}] заголовок не в Capitalized Case: {h}")
            for shout in shouty_words(plain):
                warnings.append(f"[{gname}] слово капсом «{shout}» у заголовку: {h}")
                break
            key = h.lower()
            if key in seen_headlines:
                errors.append(f"[{gname}] дубль заголовка: {h}")
            seen_headlines.add(key)
            _scan_policy(f"[{gname}] заголовок", h, errors, warnings, agg,
                         soft=soft, ambiguous=ambiguous)

        descs = [d.strip() for d in (ad.get("descriptions") or []) if d.strip()]
        if len(descs) != 4:
            warnings.append(f"[{gname}] описів {len(descs)}, треба рівно 4.")
        dki_descs = sum(1 for d in descs if DKI_RE.search(d))
        if not 1 <= dki_descs <= 2:
            warnings.append(f"[{gname}] описів з макросом {dki_descs}, треба 1-2.")
        for d in descs:
            n = effective_len(d)
            if n > LIMIT_DESC:
                errors.append(
                    f"[{gname}] опис {n}/{LIMIT_DESC} — ПЕРЕПИШИ коротше, "
                    f"ціль до {LIMIT_DESC - 5} символів. Не обрізай слово "
                    f"й не викидай кінець речення: {d}")
            elif n < DESC_MIN:
                warnings.append(f"[{gname}] опис лише {n} символів із {LIMIT_DESC} — "
                                f"додай ще {DESC_MIN - n}, місце марнується: {d}")
            bad = bad_symbols(d, extra_allowed=".,-!")
            if bad:
                errors.append(f"[{gname}] опис із забороненими символами «{bad}»: {d}")
            if d.count("!") > 1:
                errors.append(f"[{gname}] більше одного знака оклику в описі: {d}")
            for shout in shouty_words(d):
                warnings.append(f"[{gname}] слово капсом «{shout}» в описі: {d}")
                break
            _scan_policy(f"[{gname}] опис", d, errors, warnings, agg,
                         soft=soft, ambiguous=ambiguous)


def _validate_assets(draft, errors, warnings, wants=None):
    wants = wants or {}
    want_callouts = wants.get("callouts", True)
    # ── МІНУС-СЛОВА ──────────────────────────────────────────────────────
    want_neg = wants.get("negatives", True)
    negs = [n.strip() for n in (draft.get("negatives") or []) if n and n.strip()]
    if want_neg and not NEGATIVES_MIN <= len(negs) <= NEGATIVES_MAX:
        warnings.append(f"Мінус-слів {len(negs)}, треба "
                        f"{NEGATIVES_MIN}-{NEGATIVES_MAX} — без них широка "
                        f"відповідність тягне запити, за які платиш дарма.")
    if not want_neg and negs:
        warnings.append(f"Мінус-слова вимкнені, але модель повернула {len(negs)}.")
    if negs:
        dupes = {n.lower() for n in negs if [x.lower() for x in negs].count(n.lower()) > 1}
        for d in sorted(dupes):
            warnings.append(f"Мінус-слово повторюється: {d}")
        # Найдорожча помилка: мінус-слово, яке глушить власний ключ. У широкій
        # відповідності досить збігу кореня — і група замовкає повністю.
        own = [k for g in (draft.get("ad_groups") or [])
               for k in (g.get("keywords") or []) if k.strip()]
        own_roots = _word_roots(own)
        for n in negs:
            words = re.findall(r"[^\W\d_]+", defold(n), re.U)
            hit = [w for w in words
                   if w in own_roots or w[:WORD_ROOT_LEN] in own_roots]
            if hit:
                errors.append(
                    f"Мінус-слово «{n}» збігається з власним ключем по «{hit[0]}» "
                    f"— у широкій відповідності воно заглушить свою ж групу. "
                    f"Прибери його або звузь.")
        for n in negs:
            if len(n) > 30:
                warnings.append(f"Мінус-слово {len(n)} символів, ліміт 30: {n}")
            bad = bad_symbols(n)
            if bad:
                errors.append(f"Мінус-слово із забороненими символами «{bad}»: {n}")

    want_snippets = wants.get("snippets", True)
    agg = bool(wants.get("aggregator"))
    soft = bool(wants.get("soft", True))
    ambiguous = (not agg) and (gambling_context(draft)
                               or bool(wants.get("scrubbed")))
    def check_asset(label, items, limit):
        for item in items:
            if len(item) > limit:
                errors.append(f"{label} {len(item)}/{limit}, "
                              f"скороти на {len(item) - limit}: {item}")
            bad = bad_symbols(item)
            if bad:
                errors.append(f"{label} із забороненими символами «{bad}»: {item}")
            for shout in shouty_words(item):
                warnings.append(f"{label}: слово капсом «{shout}» → {item}")
                break
            _scan_policy(label, item, errors, warnings, agg, soft=soft,
                         ambiguous=ambiguous)

    sitelinks = [sl for sl in (draft.get("sitelinks") or [])
                 if (sl.get("text") or "").strip()]
    if sitelinks and len(sitelinks) != 6:
        warnings.append(f"Сайтлінків {len(sitelinks)}, треба рівно 6.")
    check_asset("Сайтлінк", [sl["text"].strip() for sl in sitelinks], LIMIT_SITELINK)

    seen_sl = set()
    for sl in sitelinks:
        text = sl["text"].strip()
        if text.lower() in seen_sl:
            warnings.append(f"Сайтлінк повторюється: {text}")
        seen_sl.add(text.lower())
        for n in (1, 2):
            desc = (sl.get(f"description{n}") or "").strip()
            if not desc:
                warnings.append(f"Сайтлінк «{text}»: немає опису {n} — "
                                f"це втрачений CTR.")
                continue
            if len(desc) > LIMIT_SL_DESC:
                errors.append(f"Опис {n} сайтлінка «{text}» {len(desc)}/"
                              f"{LIMIT_SL_DESC}, скороти на {len(desc) - LIMIT_SL_DESC}: {desc}")
            bad = bad_symbols(desc, extra_allowed=".,-")
            if bad:
                errors.append(f"Опис {n} сайтлінка «{text}» "
                              f"із забороненими символами «{bad}»: {desc}")
            _scan_policy(f"Опис сайтлінка «{text}»", desc, errors, warnings, agg,
                         soft=soft)

    callouts = [c.strip() for c in (draft.get("callouts") or []) if c.strip()]
    if want_callouts and len(callouts) != CALLOUTS_TOTAL:
        warnings.append(f"Callouts {len(callouts)}, треба рівно {CALLOUTS_TOTAL} — "
                        f"Google ротує їх, менше означає гірший добір.")
    if not want_callouts and callouts:
        warnings.append(f"Калаути вимкнені, але модель повернула {len(callouts)} — "
                        f"у файл вони не підуть.")
    if len(callouts) != len({c.lower() for c in callouts}):
        warnings.append("Серед callouts є повтори.")
    check_asset("Callout", callouts, LIMIT_CALLOUT)

    snippets = draft.get("snippets") or []
    if want_snippets and not 1 <= len(snippets) <= 2:
        warnings.append(f"Сніпетів {len(snippets)}, треба 1-2.")
    if not want_snippets and snippets:
        warnings.append(f"Сніпети вимкнені, але модель повернула {len(snippets)} — "
                        f"у файл вони не підуть.")
    for sn in snippets:
        values = [v.strip() for v in (sn.get("values") or []) if v.strip()]
        if len(values) != 3:
            warnings.append(f"У сніпеті значень {len(values)}, треба рівно 3.")
        check_asset("Snippet value", values, LIMIT_SNIPPET)

        sn_type = (sn.get("type") or "").strip()
        # Заголовок сніпета — це фіксований перелік Google, а не текст. Він
        # мусить лишатись АНГЛІЙСЬКИМ навіть у грецькій чи чеській кампанії:
        # перекладений заголовок завантажувач не знаходить і повертає
        # «Item not found». Реальний випадок: грецька кампанія, 43 рядки
        # завантажились, сніпет упав саме на цьому.
        if sn_type and sn_type.lower() not in SNIPPET_TYPES:
            errors.append(
                f"Тип snippet «{sn_type}» не зі списку Google — завантаження "
                f"впаде з «Item not found». Заголовок НЕ ПЕРЕКЛАДАЄТЬСЯ, пиши "
                f"рівно англійською: {', '.join(sorted(SNIPPET_TYPES))}. "
                f"Мовою кампанії пишуться лише значення сніпета.")

        level = (sn.get("level") or "").lower()
        if level not in ("campaign", "ad group"):
            warnings.append(f"У сніпеті level «{sn.get('level')}», "
                            f"очікується campaign або ad group.")

    for obj in (draft.get("target_objects") or []):
        _scan_policy("Цільовий об'єкт", obj, errors, warnings, agg)

    return errors, warnings

# ── Малювання таблиці ─────────────────────────────────────────────────────────

def all_ad_texts(ad_groups):
    """Усі заголовки й описи одним списком — для звірки між раундами."""
    out = []
    for g in ad_groups or []:
        for ad in g.get("ads") or []:
            out += [t.strip() for t in (ad.get("headlines") or []) if t.strip()]
            out += [t.strip() for t in (ad.get("descriptions") or []) if t.strip()]
    return out


def find_truncations(old_texts, new_texts):
    """Ловить рядки, які модель не переписала, а обрізала.

    «Sezonni Menu Na Terase» -> «Sezonni Menu Na Ter».
    Ознака точна: новий рядок є початком старого. Випадково так не буває,
    а виглядає це в кабінеті як недописане слово.
    """
    found = []
    for new in new_texts:
        if len(new) < 6:
            continue
        for old in old_texts:
            if old != new and old.startswith(new) and len(old) - len(new) <= 8:
                # Обрізали посеред слова: наступний символ не пробіл.
                if old[len(new)] != " ":
                    found.append((old, new))
                    break
    return found


def repair_snapshot(ad_groups, errors, warnings=()):
    """Показує моделі її ж попередній варіант із порахованими довжинами.

    Без цього в запиті були самі претензії — «скороти на 2», — а тексту, до
    якого вони стосуються, не було. Модель щоразу писала все з нуля і ламала
    те, що вже виправила: «Kompletní» полагодили в раунді 2 і отримали знову
    в раунді 5. Тепер вона бачить рядок, його довжину й позначку.
    """
    problems = list(errors) + list(warnings)

    def flag(text):
        return "ВИПРАВ" if any(text.strip() and text.strip() in p
                               for p in problems) else "лишити"

    out = ["ОСЬ ТВІЙ ПОПЕРЕДНІЙ ВАРІАНТ І ПОРАХОВАНІ ДОВЖИНИ.",
           "Рядки з позначкою «лишити» поверни ДОСЛІВНО, символ у символ.",
           "Переписуй ТІЛЬКИ ті, де стоїть «ВИПРАВ».", ""]
    for g in ad_groups:
        name = (g.get("name") or "").strip()
        for i, ad in enumerate(g.get("ads") or [], 1):
            out.append(f"[{name}] оголошення {i}")
            out.append("  Заголовки:")
            for j, h in enumerate(ad.get("headlines") or [], 1):
                out.append(f"   {j:>2}. {h}".ljust(46) +
                           f"[{effective_len(h)}/{LIMIT_HEADLINE}] {flag(h)}")
            out.append("  Описи:")
            for j, d in enumerate(ad.get("descriptions") or [], 1):
                out.append(f"   {j:>2}. {d}")
                out.append(" " * 7 + f"[{effective_len(d)}/{LIMIT_DESC}] {flag(d)}")
            out.append("")
    return "\n".join(out)


COUNTING_RULE = """\
ЯК РАХУВАТИ ДОВЖИНУ. Це не оцінка на око, а точний підрахунок.
Перш ніж записати заголовок, порахуй у ньому символи по одному, разом із
пробілами. Літери з діакритикою — Č, ě, ů, é, ł, ő — це ОДИН символ кожна,
не два. Макрос {Keyword: Фолбек} рахується як довжина самого фолбека.

ЗАДОВГЕ НЕ ОБРІЗАЮТЬ, ЙОГО ПЕРЕПИСУЮТЬ. Обрубок слова — це брак, гірший за
перевищення ліміту: людина бачить в оголошенні недописане слово.
  було: Sezonni Menu Na Letni Terase     31 символ
  ТАК НЕ МОЖНА: Sezonni Menu Na Letni Ter        обрубок
  ТАК НЕ МОЖНА: Sezonni Menu Na Let. Terase      скорочення крапкою
  правильно:    Sezonni Menu Na Terase           22, думка ціла

Прибирай ціле слово або добирай коротший синонім, але фраза мусить лишатися
осмисленою й граматично правильною. Цілься на 3-5 символів МЕНШЕ ліміту,
щоб був запас.

Довгі назви міст у заголовок не тягни: якщо місто саме по собі займає понад
третину ліміту, у заголовках його не згадуй узагалі, місце йому в описі.
"""


def build_repair_notes(draft, wants, seen_errors=(), truncated=(), extra=""):
    """Список виправлень для дослання в той самий чат.

    Одна точка для одиночного запуску й для черги. Поки черга робила свій
    «повний перезапуск» замість дослання, вона щоразу кидала нові кубики:
    інша назва, інший кут подачі, інколи інша країна. Модель ніколи не бачила
    власну зламану чернетку, тож і не сходилась.

    Повертає (notes, errors, warnings).
    """
    wants = dict(wants or {})
    asked = apply_notes_geo(wants, extra)
    errors, warnings = validate(draft, wants)
    structural = [w for w in warnings if STRUCTURAL_RE.search(w)]
    other = [w for w in warnings if w not in structural]

    notes = "\n".join(f"- {e}" for e in errors[:25])
    if structural:
        notes += ("\n" if notes else "") + "\n".join(f"- {w}" for w in structural[:25])
    if other:
        notes += ("\n\nЗаодно прибери, якщо не ламає решту:\n"
                  + "\n".join(f"- {w}" for w in other[:10]))

    # Рецидиви називаємо вголос: без цього модель лагодить одне й повертає
    # інше по колу. «Kompletní» полагодили в раунді 2 і отримали в п'ятому.
    repeats = sorted(set(errors) & set(seen_errors or ()))
    if repeats:
        notes = ("ТИ ВЖЕ ВИПРАВЛЯВ ЦЕ РАНІШЕ І ЗЛАМАВ ЗНОВУ. Не повертай "
                 "формулювання, які вже відхилили:\n"
                 + "\n".join(f"- {e}" for e in repeats[:10]) + "\n\n" + notes)

    # Обрубки з минулого раунду називаємо першими: це найгрубіша помилка,
    # її людина побачить у кабінеті одразу.
    if truncated:
        notes = ("ТИ ОБРІЗАВ РЯДКИ ЗАМІСТЬ ТОГО, ЩОБ ПЕРЕПИСАТИ. Так не "
                 "можна: у тексті лишається недописане слово. Перепиши "
                 "їх осмислено, коротшими словами:\n"
                 + "\n".join(f"- «{n}» — обрубок від «{o}»" for o, n in list(truncated)[:8])
                 + "\n\n" + notes)

    if not notes.strip():
        notes = ("Зауважень немає — тексти проходять перевірку. Перепиши "
                 "їх інакше: інші синоніми, інший порядок слів, інший кут "
                 "подачі. Довжини й правила лишаються ті самі.")

    snapshot = repair_snapshot(draft.get("ad_groups") or [], errors, warnings)
    notes = f"{snapshot}\n\n{COUNTING_RULE}\n{notes}"
    if extra:
        notes += f"\n\nОкремо від клієнта:\n{extra}"
    if asked and (draft.get("location") or "") != asked:
        notes = (f"ГЕО ЗМІНЕНО УТОЧНЕННЯМ: {asked}. Перепиши location і "
                 f"language під цю країну й переклади ВСІ тексти — ключі, "
                 f"заголовки, описи, розширення — її мовою. Структуру "
                 f"кампанії залиш.\n\n" + notes)
    return notes, errors, warnings


def render_table(draft):
    rows = [("Campaign Name",  draft.get("campaign_name", "")),
            ("Website",        draft.get("website", "")),
            ("Location",       draft.get("location", "")),
            ("Language",       draft.get("language", "")),
            ("Цільові об'єкти", ", ".join(draft.get("target_objects") or []))]

    groups = draft.get("ad_groups") or []
    for gi, g in enumerate(groups, 1):
        suffix = f" (група {gi})" if len(groups) > 1 else ""
        rows.append((f"Ad Group Name{suffix}", g.get("name", "")))
        for i, k in enumerate(g.get("keywords") or [], 1):
            rows.append((f"Keyword {i}{suffix}", k))
        ads = g.get("ads") or []
        for ai, ad in enumerate(ads, 1):
            mark = suffix if len(ads) == 1 else f"{suffix} огол.{ai}"
            for i, h in enumerate(ad.get("headlines") or [], 1):
                rows.append((f"H{i}{mark}", f"{h}   ({effective_len(h)}/{LIMIT_HEADLINE})"))
            for i, d in enumerate(ad.get("descriptions") or [], 1):
                rows.append((f"D{i}{mark}", f"{d}   ({effective_len(d)}/{LIMIT_DESC})"))

    for i, sl in enumerate(draft.get("sitelinks") or [], 1):
        text = (sl.get("text") or "")
        rows.append((f"Sitelink {i}", f"{text}   ({len(text)}/{LIMIT_SITELINK})"))
        for n in (1, 2):
            desc = (sl.get(f"description{n}") or "")
            rows.append((f"  опис {n}", f"{desc}   ({len(desc)}/{LIMIT_SL_DESC})"))
    for i, c in enumerate(draft.get("callouts") or [], 1):
        rows.append((f"Callout {i}", f"{c}   ({len(c)}/{LIMIT_CALLOUT})"))
    for si, sn in enumerate(draft.get("snippets") or [], 1):
        tag = "" if len(draft.get("snippets") or []) == 1 else f" {si}"
        rows.append((f"Snippet Type{tag}",
                     f"{sn.get('type', '')}   (рівень: {sn.get('level', '')})"))
        for i, v in enumerate(sn.get("values") or [], 1):
            rows.append((f"Snippet Value {i}{tag}", v))

    width = max((len(k) for k, _ in rows), default=10)
    out = [f"{'Element'.ljust(width)} | Значення",
           f"{'-' * width}-+-{'-' * 40}"]
    out += [f"{k.ljust(width)} | {v}" for k, v in rows]
    return "\n".join(out)

# ── Збірка CSV ────────────────────────────────────────────────────────────────

def tidy_name(name):
    """Прибирає те, чого в назві кампанії бути не повинно: нерозривні пробіли,
    табуляції, подвійні та хвостові пробіли. Саме через них завантажувач
    Google не впізнає наявну кампанію і створює нову."""
    text = (name or "").replace(" ", " ").replace(" ", " ")
    text = text.replace(" ", " ").replace("\t", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def safe_filename(name):
    cleaned = re.sub(r'[<>:"/\\|?*]', " ", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "campaign")[:120]

def build_rows(draft, budget, cpc, wants=None):
    wants    = wants or {}
    camp     = draft["campaign_name"].strip()
    website  = draft["website"].strip()
    groups   = draft["ad_groups"]
    rows = []

    rows.append({
        "Action": "Add", "Campaign": camp, "Campaign type": "Search",
        "Status": "Enabled", "Budget": budget, "Budget type": "Daily",
        "Bid strategy type": "Manual CPC", "Networks": "Google search",
        "Location": normalize_location(draft["location"], draft.get("language", "")),
        "Location intent": "Presence only",
        "Language": draft["language"].strip(), "EU political ads": "No",
    })

    for g in groups:
        gname = g["name"].strip()
        # Status у рядку групи є в еталонному файлі: без нього Google покладається
        # на власне значення за замовчуванням, а це зайва невизначеність.
        rows.append({"Action": "Add", "Campaign": camp, "Ad group": gname,
                     "Max CPC": cpc, "Status": "Enabled"})

        for kw in g["keywords"]:
            kw = kw.strip()
            if kw:
                rows.append({"Action": "Add", "Campaign": camp, "Ad group": gname,
                             "Keyword": kw, "Match type": "Broad"})

        # У групі може бути одне або два оголошення — кожне окремим рядком.
        for ad_data in g["ads"]:
            ad = {"Action": "Add", "Campaign": camp, "Status": "Enabled",
                  "Ad group": gname, "Ad type": "Responsive search ad",
                  "Final URL": website}
            for i, h in enumerate(ad_data["headlines"][:15], 1):
                ad[f"Headline {i}"] = h.strip()
            for i, d in enumerate(ad_data["descriptions"][:4], 1):
                ad[f"Description {i}"] = d.strip()
            rows.append(ad)

    first = groups[0]["name"].strip()
    # Знята галочка сильніша за відповідь моделі: якщо розширення не потрібне,
    # у файл воно не потрапляє, навіть коли модель його все одно вигадала.
    for c in (draft["callouts"] if wants.get("callouts", True) else []):
        c = c.strip()
        if c:
            rows.append({"Action": "Add", "Campaign": camp, "Ad group": first,
                         "Asset type": "Callout", "Callout text": c})

    # Мінус-слова — на рівні кампанії: те, що не потрібно жодній групі.
    for neg in (draft.get("negatives") or []) if wants.get("negatives", True) else []:
        neg = (neg or "").strip()
        if neg:
            rows.append({"Action": "Add", "Campaign": camp,
                         "Negative keyword": neg, "Match type": "Broad"})

    for sn in (draft["snippets"] if wants.get("snippets", True) else []):
        values = [v.strip() for v in (sn.get("values") or []) if v.strip()][:3]
        if not values:
            continue
        row = {"Action": "Add", "Campaign": camp,
               "Asset type": "Structured snippet",
               "Structured snippet header": (sn.get("type") or "").strip(),
               "Structured snippet values": ";".join(values)}
        if (sn.get("level") or "").lower() == "campaign":
            row["Level"] = "Campaign"
        else:
            row["Ad group"] = first
        rows.append(row)

    # Сайтлінки вимкнені за замовчуванням: їхні URL з якорями #1-#6 вели на
    # головну, а підпис обіцяв окрему сторінку — Google рахує це обходом систем.
    sitelinks = draft.get("sitelinks") if wants.get("sitelinks", True) else []
    for i, sl in enumerate(sitelinks or [], 1):
        text = (sl.get("text") or "").strip()
        if not text:
            continue
        rows.append({"Row Type": "Sitelink", "Action": "Add",
                     "Asset action": "Create new", "Level": "Campaign",
                     "Campaign": camp, "Final URL": f"{website}#{i}",
                     "Sitelink text": text,
                     "Sitelink description 1": (sl.get("description1") or "").strip(),
                     "Sitelink description 2": (sl.get("description2") or "").strip()})
    return rows

def write_many_csv(rows, label, aggregator=False, ident=""):
    """Кілька кампаній одним файлом.

    Фармер заливає це в чистий акаунт одним завантаженням, тому дробити на
    десять файлів немає сенсу. Ім'я файла — не назва кампанії (їх тут
    багато), а сайт або ідентифікатор.
    """
    folder = output_dir(aggregator, ident)
    os.makedirs(folder, exist_ok=True)
    path = free_path(folder, safe_filename(label))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def free_path(folder, base, ext=".csv"):
    """Вільне ім'я файла в теці.

    Раніше однакова назва кампанії просто затирала попередній файл: два
    прогони на той самий акаунт — і перший CSV зникав, ніхто про це не
    дізнавався. На конвеєрі це втрата роботи, тому імена не повторюються.
    """
    path = os.path.join(folder, base + ext)
    if not os.path.exists(path):
        return path
    n = 2
    while True:
        path = os.path.join(folder, f"{base} ({n}){ext}")
        if not os.path.exists(path):
            return path
        n += 1


def write_csv(rows, campaign_name, aggregator=False, ident=""):
    folder = output_dir(aggregator, ident)
    os.makedirs(folder, exist_ok=True)
    path = free_path(folder, safe_filename(campaign_name))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


# ══ РЕЖИМ «ТІЛЬКИ ОГОЛОШЕННЯ» ════════════════════════════════════════════════
# Кампанія вже в акаунті, оголошення відхилили. Треба нове оголошення в ту саму
# групу — і більше нічого. Старі тексти за основу НЕ беремо: якщо відхилили,
# у них щось не так, і повторювати їх формулювання немає сенсу. Орієнтир —
# ключові слова групи. Рядків Remove не пишемо: старе користувач знімає сам.

AD_SHAPE = """{
  "groups": [
    {
      "name": "назва групи РІВНО як у завданні",
      "ads": [
        {
          "headlines": ["рівно 15 заголовків, кожен до 30 символів"],
          "descriptions": ["рівно 4 описи, кожен від 60 до 90 символів"]
        }
      ]
    }
  ]
}"""

AD_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "ads": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "headlines":    {"type": "ARRAY", "items": {"type": "STRING"}},
                                "descriptions": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["headlines", "descriptions"],
                        },
                    },
                },
                "required": ["name", "ads"],
            },
        },
    },
    "required": ["groups"],
}


def _source_from_draft(path):
    """Кампанія з журналу: там лежить рівно та структура, яку ми ж і склали."""
    with open(path, "r", encoding="utf-8") as f:
        draft = json.load(f)
    groups = []
    for g in draft.get("ad_groups") or []:
        name = tidy_name(g.get("name"))
        if not name:
            continue
        groups.append({
            "name": name,
            "keywords": [k.strip() for k in (g.get("keywords") or []) if k.strip()],
            "ads": len(g.get("ads") or []),
        })
    if not groups:
        return None
    return {
        "campaign_name":  tidy_name(draft.get("campaign_name")),
        "website":        (draft.get("website") or "").strip(),
        "location":       (draft.get("location") or "").strip(),
        "language":       (draft.get("language") or "").strip(),
        "target_objects": draft.get("target_objects") or [],
        "groups":         groups,
        "type":           "Search",
        "assets": {
            "калаути":   len(draft.get("callouts") or []),
            "сніпети":   len(draft.get("snippets") or []),
            "сайтлінки": len(draft.get("sitelinks") or []),
        },
    }


def _source_from_csv(path):
    """Кампанія з готового файла: збираємо назад із рядків того ж формату."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    # Назви з файла чистимо одразу: якщо в кампанії затесався подвійний пробіл,
    # він поїде і в файл оголошень, і Google створить дубль кампанії.
    campaign = website = location = language = ""
    ctype = "Search"
    assets = {"калаути": 0, "сніпети": 0, "сайтлінки": 0}
    order, groups = [], {}
    for r in rows:
        camp = tidy_name(r.get("Campaign"))
        if camp and not campaign:
            campaign = camp
        if (r.get("Campaign type") or "").strip():
            ctype = (r.get("Campaign type") or "").strip()
            location = (r.get("Location") or "").strip()
            language = (r.get("Language") or "").strip()
        atype = (r.get("Asset type") or "").strip()
        if atype == "Callout":
            assets["калаути"] += 1
        elif atype == "Structured snippet":
            assets["сніпети"] += 1
        if (r.get("Row Type") or "").strip() == "Sitelink":
            assets["сайтлінки"] += 1
        url = (r.get("Final URL") or "").strip()
        # Якір #1-#6 — це сайтлінк, а не посадкова оголошення.
        if url and not website and "#" not in url:
            website = url

        gname = tidy_name(r.get("Ad group"))
        if not gname:
            continue
        if gname not in groups:
            groups[gname] = {"name": gname, "keywords": [], "ads": 0}
            order.append(gname)
        kw = (r.get("Keyword") or "").strip()
        if kw:
            groups[gname]["keywords"].append(kw)
        if (r.get("Ad type") or "").strip() == "Responsive search ad":
            groups[gname]["ads"] += 1

    if not campaign or not order:
        return None
    return {
        "campaign_name": campaign, "website": website,
        "location": location, "language": language,
        "target_objects": [],
        "groups": [groups[n] for n in order],
        "type": ctype, "assets": assets,
    }


def list_sources(kind="folder"):
    """Кампанії, до яких можна дописати оголошення.

    kind="folder" — готові CSV із «Готові РК», тобто те, що фізично лежить
    файлом. kind="history" — журнал запусків. Два різні списки, бо шукають
    у них по-різному: у папці за назвою кампанії, в історії за датою.
    """
    found = []
    if kind == "folder":
        # Обидві папки: звичайні кампанії й агрегатори. Підпапки ReworkAds
        # не чіпаємо — там лежать файли лише з оголошеннями. Теки дня
        # («11.08») обходимо: саме там тепер лежать свіжі файли.
        for base, tag in ((OUTPUT_DIR, ""), (AGG_DIR, "агрегатор")):
            if not os.path.isdir(base):
                continue
            folders = [base] + [os.path.join(base, d)
                                for d in sorted(os.listdir(base), reverse=True)
                                if os.path.isdir(os.path.join(base, d))
                                and d.lower() != "reworkads"]
            names = [(f, n) for f in folders if os.path.isdir(f)
                     for n in sorted(os.listdir(f), reverse=True)]
            for folder, name in names:
                if not name.lower().endswith(".csv"):
                    continue
                path = os.path.join(folder, name)
                try:
                    src = _source_from_csv(path)
                except Exception:
                    src = None
                # Файл без жодного ключа — це вивантаження оголошень, а не
                # кампанія: переробляти в ньому нічого.
                if not src or not any(g["keywords"] for g in src["groups"]):
                    continue
                src["kind"] = "файл"
                src["aggregator"] = bool(tag)
                src["path"] = path
                # Тека, у якій лежить файл, — це і є ідентифікатор клієнта.
                # Без нього переробка складала все в корінь ReworkAds, і
                # серед сотні файлів годі було щось знайти.
                sub = os.path.basename(folder)
                src["ident"] = "" if os.path.normpath(folder) == os.path.normpath(base) else sub
                src["created"] = time.strftime(
                    "%d/%m %H:%M", time.localtime(os.path.getmtime(path)))
                prefix = f"[{tag}] " if tag else ""
                who = f"{src['ident']}   ·   " if src["ident"] else ""
                src["label"] = f"{prefix}{who}{src['campaign_name']}   ·   {name}"
                found.append(src)
        return found

    for folder in list_history(limit=80):
        path = os.path.join(HISTORY_DIR, folder, "draft.json")
        if not os.path.exists(path):
            continue
        try:
            src = _source_from_draft(path)
        except Exception:
            src = None
        if not src:
            continue
        src["kind"] = "історія"
        src["path"] = path
        # Ідентифікатор пишеться в журнал із того запуску. У старих записах
        # його немає — тоді просто не показуємо.
        src["ident"] = ""
        try:
            with open(os.path.join(HISTORY_DIR, folder, "run.json"),
                      encoding="utf-8") as f:
                src["ident"] = (json.load(f).get("ідентифікатор") or "").strip()
        except Exception:
            pass
        # Ім'я теки історії — це 2026-08-07_14-15-03_назва.
        stamp = folder[:16]
        src["created"] = (f"{stamp[8:10]}/{stamp[5:7]} {stamp[11:13]}:{stamp[14:16]}"
                          if len(stamp) >= 16 else stamp)
        who = f"{src['ident']}   ·   " if src["ident"] else ""
        src["label"] = f"{who}{src['campaign_name']}   ·   {src['created']}"
        found.append(src)
    return found


def source_summary(src):
    """Короткий опис кампанії для превью у вікні оголошень."""
    if not src:
        return ""
    groups = src.get("groups") or []
    ads = sum(g.get("ads", 0) for g in groups)
    keys = sum(len(g.get("keywords") or []) for g in groups)
    assets = src.get("assets") or {}
    have = ", ".join(f"{k} {v}" for k, v in assets.items() if v) or "немає"
    return (f"{src.get('type', 'Search')}  ·  груп {len(groups)}  ·  "
            f"оголошень {ads}  ·  ключів {keys}\n"
            f"Розширення: {have}\n"
            f"Гео {src.get('location') or '—'}  ·  мова "
            f"{src.get('language') or '—'}  ·  створено {src.get('created', '—')}")


def ad_brief(ctx, targets, extra=""):
    """Завдання на переписування оголошень. Старих текстів свідомо не даємо.

    targets — список груп, які переробляємо: [{"name", "keywords", "want"}].
    Можна віддати одну групу, а можна всі одразу одним запитом.
    """
    dki_h = random.randint(1, 4)
    dki_d = random.randint(1, 2)
    total = sum(t["want"] for t in targets)
    lines = [
        AGGREGATOR_BRIEF if ctx.get("aggregator") else "",
        SOFT_BRIEF,
        "УВАГА: цей запуск ПЕРЕВИЗНАЧАЄ формат відповіді з системної інструкції. "
        "Повна кампанія НЕ потрібна. Правила якості текстів із системної "
        "інструкції лишаються чинними — змінюється лише те, що ти повертаєш.",
        "",
        "ЗАВДАННЯ: написати ТІЛЬКИ тексти оголошень для груп, які вже існують "
        "в акаунті Google Ads.",
        "Кампанію, ключові слова, калаути, сніпети й сайтлінки НЕ чіпай — вони "
        "вже завантажені. Поверни лише заголовки й описи.",
        "",
        f"Кампанія: {ctx['campaign_name']}",
        f"Посадкова сторінка: {ctx['website']}",
        f"Мова текстів: {ctx['language'] or 'та сама, що й у ключових словах'}",
        f"Гео: {ctx['location'] or 'не вказано'}",
    ]
    if ctx.get("description"):
        lines += ["", "Опис бізнесу:", ctx["description"]]

    lines += ["", f"Груп до переробки: {len(targets)}. "
                  f"Усього оголошень: {total}.",
              "Для КОЖНОЇ групи поверни об'єкт із її назвою рівно як тут "
              "написано і потрібною кількістю оголошень."]
    for t in targets:
        keywords = "\n".join(f"    - {k}" for k in t["keywords"]) or "    - (немає)"
        lines += [
            "",
            f"ГРУПА «{t['name']}» — потрібно оголошень: {t['want']}.",
            "  Ключові слова цієї групи. Пиши тексти САМЕ під них — це єдиний "
            "орієнтир, звідки береться зміст оголошення:",
            keywords,
        ]

    lines += [
        "",
        "Кожне оголошення — рівно 15 заголовків і рівно 4 описи. "
        "Тексти різних груп не повторюються.",
        "",
        "ОБОВ'ЯЗКОВО:",
        f"- Макрос {{Keyword: Фолбек}} рівно в {dki_h} заголовках із 15 і рівно "
        f"в {dki_d} описах із 4.",
        f"- Кожен опис завдовжки {DESC_MIN}-{LIMIT_DESC} символів.",
        "- Заголовки 1-5 — суть послуги, 6-10 — реальна вигода, 11-15 — заклик, "
        "у якому названо, що саме людина отримає.",
        "- Гео максимум у 2 заголовках із 15.",
        "- Жодних заяв про себе, які неможливо перевірити: «перевірений», "
        "«професійний», «сертифікований», «надійний», «найкращий», «№1». "
        "Google відхиляє такі оголошення як обхід систем.",
        "- Жодних порожніх закликів без предмета: «Офіційний сайт», "
        "«Зареєструватися», «Детальніше». Заклик має називати об'єкт.",
        "- Пиши лише про те, що реально є на сайті. Нічого не вигадуй і нічого "
        "не приховуй.",
        "- Заклик має називати, ЩО людина отримає. Заборонені порожні "
        "(«Офіційний сайт», «Увійти») і заяви про себе («надійний», "
        "«експерти», «якісний сервіс»).",
        f"- Стилістика: {random.choice(ACCENTS)}.",
        f"- Форма заголовків: {random.choice(PHRASINGS)}.",
        "- Схожість бізнесу на інші в ніші не привід писати ті самі фрази: "
        "міняй синоніми, порядок слів і кут подачі.",
    ]
    if extra:
        lines += ["", "Додаткові вимоги:", extra]
    return "\n".join(lines)


def match_groups(data, targets):
    """Розкладає відповідь моделі по замовлених групах.

    Модель інколи міняє регістр чи додає лапки в назві, тому звіряємо
    нормалізовано, а якщо груп рівно стільки ж — просто беремо по порядку.
    """
    got = [g for g in (data.get("groups") or []) if g]
    by_name = {defold((g.get("name") or "").strip()): g for g in got}
    out = []
    for i, t in enumerate(targets):
        g = by_name.get(defold(t["name"]))
        if g is None and len(got) == len(targets):
            g = got[i]
        ads = [a for a in ((g or {}).get("ads") or []) if a]
        out.append({"name": t["name"], "ads": ads})
    return out


def name_mismatch_risk(name):
    """Завантажувач Google дописує оголошення в кампанію, якщо ім'я збіглося
    ТОЧНО. Не збіглося — він мовчки створює нову кампанію. Хвостовий пробіл
    чи подвійний усередині око не бачить, а Google бачить."""
    problems = []
    if name != name.strip():
        problems.append("пробіл на початку або в кінці")
    if "  " in name:
        problems.append("подвійний пробіл усередині")
    if "\t" in name or "\n" in name:
        problems.append("табуляція або перенос рядка")
    if any(ch in name for ch in "   "):
        problems.append("нерозривний пробіл")
    return problems


def validate_ads(groups, ctx, targets=None):
    """Ті самі перевірки, що й для повної кампанії, але лише для текстів."""
    errors, warnings = [], []
    agg = bool(ctx.get("aggregator"))
    soft = bool(ctx.get("soft", True))
    website = (ctx.get("website") or "").strip()
    if not website.startswith("http"):
        errors.append(f"Final URL має починатися з http(s): {website}")
    camp = ctx.get("campaign_name") or ""
    if not camp.strip():
        errors.append("Не вказано кампанію.")
    for problem in name_mismatch_risk(camp):
        errors.append(f"У назві кампанії {problem}: «{camp}». Google не знайде "
                      f"таку кампанію і створить НОВУ замість того, щоб "
                      f"дописати оголошення в наявну.")
    if not groups:
        errors.append("Модель не повернула жодної групи.")
    if agg:
        geo_err, geo_warn = gambling_geo_notes(
            normalize_location(ctx.get("location") or "", ctx.get("language") or ""))
        errors.extend(geo_err)
        warnings.extend(geo_warn)

    city_roots, country_roots = _geo_tokens(ctx.get("location") or "")
    geo_roots = city_roots + country_roots

    def has_geo(text):
        low = defold(text)
        return any(r in low for r in geo_roots)

    want = {t["name"]: t["want"] for t in (targets or [])}
    seen = set()
    for g in groups:
        gname = (g.get("name") or "").strip()
        if not gname:
            errors.append("Група без назви — не знаю, куди її класти.")
        raw_name = g.get("name") or ""
        for problem in name_mismatch_risk(raw_name):
            errors.append(f"У назві групи {problem}: «{raw_name}». Google "
                          f"створить НОВУ групу замість наявної.")
        # Назву групи ми тут не генеруємо — вона вже в акаунті, і виправити її
        # цим файлом не можна. Тому не блокуємо, а показуємо.
        ge, gw = [], []
        _scan_policy("Назва групи", gname, ge, gw, agg)
        warnings.extend(ge + gw)
        ads = [a for a in (g.get("ads") or []) if a]
        if not ads:
            errors.append(f"[{gname}] модель не повернула жодного оголошення.")
        need = want.get(gname)
        if need and len(ads) != need:
            warnings.append(f"[{gname}] оголошень {len(ads)}, замовляли {need}.")
        for i, ad in enumerate(ads, 1):
            tag = gname if len(ads) == 1 else f"{gname} / оголошення {i}"
            _validate_ad(ad, tag, geo_roots, has_geo, errors, warnings, agg, soft)
            # Два оголошення в одній групі не мають бути одним і тим самим.
            for h in (ad.get("headlines") or []):
                key = (gname, h.strip().lower())
                if key in seen:
                    warnings.append(f"[{gname}] заголовок повторюється між "
                                    f"оголошеннями: {h}")
                seen.add(key)
    return errors, warnings


def build_ad_rows(ctx, groups):
    """Лише рядки RSA з Action=Add. Старе оголошення користувач знімає сам,
    тому рядків Remove тут немає навмисно."""
    camp    = (ctx["campaign_name"] or "").strip()
    website = (ctx["website"] or "").strip()
    rows = []
    for g in groups:
        gname = (g.get("name") or "").strip()
        for ad_data in (g.get("ads") or []):
            row = {"Action": "Add", "Campaign": camp, "Status": "Enabled",
                   "Ad group": gname, "Ad type": "Responsive search ad",
                   "Final URL": website}
            for i, h in enumerate(ad_data.get("headlines") or [], 1):
                if i > 15:
                    break
                row[f"Headline {i}"] = h.strip()
            for i, d in enumerate(ad_data.get("descriptions") or [], 1):
                if i > 4:
                    break
                row[f"Description {i}"] = d.strip()
            rows.append(row)
    return rows


def write_ads_csv(rows, campaign_name, groups, aggregator=False, ident=""):
    folder = rework_dir(aggregator, ident)
    os.makedirs(folder, exist_ok=True)
    # Ім'я файла — сама назва кампанії плюс «ads», без дати. На одну кампанію
    # один актуальний файл; попередній перезаписується, але його чернетка
    # лишається в «Історія», тому нічого не втрачається.
    name = safe_filename(f"{campaign_name} - ads")
    path = free_path(folder, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path

# ── Буфер обміну на кирилічній розкладці ──────────────────────────────────────
# Tk прив'язує Ctrl+C/V/X/A до ЛІТЕРИ, а не до клавіші. На російській чи
# українській розкладці замість "v" приходить "м" — і вставка мовчки не працює.
# Ловимо за keycode: він однаковий за будь-якої розкладки.
# Прив'язка саме до віджета (не bind_all), щоб на англійській розкладці штатне
# сполучення не спрацювало другий раз і не вставило текст двічі.

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
    """Праву кнопку миші — щоб вставити можна було і без клавіатури."""
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вирізати",
                     command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копіювати",
                     command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставити",
                     command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Виділити все", command=lambda: _select_all(widget))

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


# ══ ІНТЕРФЕЙС ═════════════════════════════════════════════════════════════════

def prompt_is_base():
    """Чи лежить у теці ще базовий промпт. Порівнюємо з вбудованою копією:
    щойно людина допише своє, тексти розійдуться й підказка зникне сама."""
    try:
        have = io.open(PROMPT_FILE, encoding="utf-8").read()
    except Exception:
        return True
    return have.strip() == DEFAULT_SYSTEM_PROMPT.strip()


def show_start_notice(app):
    """Каже при ПЕРШОМУ запуску, що промпт базовий і його треба замінити.

    Без цього фармер вважає, що програма вже налаштована, і жене кампанії
    на голих лімітах: модерацію вони проходять, а кліків не приносять.
    Показується один раз: щоразу при запуску вона лише заважала. Позначка
    лежить у config.json.
    """
    root = app.root
    if app.cfg.get("start_notice_shown") or not prompt_is_base():
        return
    app.cfg["start_notice_shown"] = True
    try:
        save_config(app.cfg)
    except Exception:
        pass
    text = ("У цій збірці лежить БАЗОВИЙ промпт.\n\n"
            "Він знає ліміти Google Ads і заборонені теми — кампанія пройде "
            "модерацію. Але підхід, заголовки й інтонація в ньому не "
            "прописані: такі оголошення не приносять кліків.\n\n"
            "Встав свій промпт кнопкою «Промпт» угорі вікна. Файл читається "
            "перед кожною генерацією — перезапускати програму не треба.\n\n"
            "Відкрити інструкцію зі знімками просто зараз?")
    try:
        if messagebox.askyesno("Промпт ще базовий", text, parent=root):
            # Інструкція зі знімками головна, txt лишається запасним.
            guide = ""
            for name in ("instrukciya.html", "ЯК ПОЧАТИ.txt"):
                p = os.path.join(BASE_DIR, name)
                if os.path.exists(p):
                    guide = p
                    break
            if guide:
                # Саме браузером, а не через os.startfile: .html у системі
                # часто прив'язаний до редактора коду, і людина бачила
                # розмітку замість інструкції. Шлях кодуємо через
                # pathname2url: інакше кирилиця й пробіл у «ЦСВ Вайт» лишались
                # сирими, і браузер такий file:// не відкривав.
                import webbrowser, urllib.request
                url = "file:" + urllib.request.pathname2url(guide)
                opened = False
                try:
                    opened = webbrowser.open(url)
                except Exception:
                    opened = False
                if not opened:
                    # Запасний хід — .bat поруч уже вміє відкрити браузером.
                    bat = os.path.join(BASE_DIR, "ІНСТРУКЦІЯ.bat")
                    if os.path.exists(bat):
                        os.startfile(bat)
                    else:
                        os.startfile(guide)
            else:
                messagebox.showinfo(
                    "Немає файлу",
                    "Інструкції не знайдено поруч із програмою.",
                    parent=root)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.draft = None
        self.q = queue.Queue()
        self.busy = False
        self._tick = 0
        self.log_lines = []          # уся стрічка кроків, іде і в журнал
        self.theme = THEMES["dark"]

        root.title("ЦСВ Вайт — Search для звичайних сайтів")
        root.geometry("1020x920")
        root.minsize(900, 780)
        root.option_add("*Font", ("Segoe UI", 10))
        apply_theme(root, self.theme)

        self._build_ui()
        self.root.after(120, self._poll)
        # Підказку показуємо після того, як вікно вже на екрані.
        self.root.after(700, lambda: show_start_notice(self))

    @staticmethod
    def _shown_hint(text, limit=70):
        one = " ".join((text or "").split())
        return one if len(one) <= limit else one[:limit - 1] + "…"

    # ── UI ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _paint(button, enabled, colour):
        """tk.Button не міняє фон за станом сам, а білий текст на кольорі
        в вимкненому вигляді нечитний — гасимо фон разом із кнопкою."""
        button.configure(bg=colour if enabled else "#d2d2da",
                         fg="#ffffff" if enabled else "#7a7a86")

    def _skin_text(self, widget, surface="surface2"):
        """tk.Text і tk.Canvas ttk не фарбує — робимо це вручну."""
        t = self.theme
        widget.configure(bg=t[surface], fg=t["ink"], insertbackground=t["ink"],
                         selectbackground=AURORA[0], selectforeground="#ffffff",
                         relief="flat", highlightthickness=1,
                         highlightbackground=t["line"], highlightcolor=AURORA[0])
        return widget

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)

        # Джерело: браузер (за замовчуванням) або API
        src = ttk.Frame(top)
        src.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 6))
        self.mode = tk.StringVar(value=self.cfg.get("mode", "browser"))
        ttk.Label(src, text="Джерело:").pack(side="left")
        ttk.Radiobutton(src, text="Браузер (вкладка Gemini)", value="browser",
                        variable=self.mode, command=self._on_mode)\
            .pack(side="left", padx=(8, 12))
        ttk.Radiobutton(src, text="API-ключ", value="api",
                        variable=self.mode, command=self._on_mode).pack(side="left")
        ttk.Separator(src, orient="vertical").pack(side="left", fill="y", padx=14)
        self.lbl_chrome = ttk.Label(src, text="")
        self.lbl_chrome.pack(side="left")
        self.btn_chrome = ttk.Button(src, text="Відкрити вікно Gemini",
                                     command=self.on_open_chrome)
        self.btn_chrome.pack(side="left", padx=(10, 0))
        ttk.Button(src, text="Промпт", width=9, command=self.on_edit_prompt)\
            .pack(side="left", padx=(6, 0))
        ttk.Button(src, text="Папка", width=8, command=self.on_open_output)\
            .pack(side="left", padx=(6, 0))
        ttk.Button(src, text="Масовий запуск", width=15,
                   command=self.on_batch_window).pack(side="left", padx=(6, 0))

        # Ключ і модель потрібні лише в режимі API. У режимі браузера цей рядок
        # прибирається з вікна повністю, а не просто гасне.
        self.api_row = ttk.Frame(top)
        self.api_row.grid(row=1, column=0, columnspan=5, sticky="ew", pady=3)
        ttk.Label(self.api_row, text="API-ключ:").pack(side="left")
        self.e_key = ttk.Entry(self.api_row, show="•")
        self.e_key.insert(0, self.cfg.get("api_key", ""))
        self.e_key.pack(side="left", fill="x", expand=True, padx=(8, 12))
        ttk.Label(self.api_row, text="Модель:").pack(side="left")
        # «Авто» першим і за замовчуванням: вставив ключ — і працюєш, модель
        # обирає програма. Стара gemini-2.5-flash у конфізі — це колишнє
        # значення за замовчуванням, а не свідомий вибір, якщо список
        # моделей ніхто ні разу не оновлював.
        self.cb_model = ttk.Combobox(
            self.api_row, width=26,
            values=[AUTO_MODEL] + list(self.cfg.get("models") or []))
        saved = self.cfg.get("model", "")
        if not saved or (saved == DEFAULT_MODEL and not self.cfg.get("models")):
            saved = AUTO_MODEL
        self.cb_model.set(saved)
        self.cb_model.pack(side="left", padx=(8, 4))
        self.btn_models = ttk.Button(self.api_row, text="↻", width=3,
                                     command=self.on_refresh_models)
        self.btn_models.pack(side="left")

        # Ідентифікатор — назва теки, куди ляже CSV. Порожній означає корінь.
        ttk.Label(top, text="Ідентифікатор:").grid(row=2, column=0, sticky="w", pady=3)
        self.e_ident = ttk.Entry(top)
        self.e_ident.insert(0, self.cfg.get("ident", ""))
        self.e_ident.grid(row=2, column=1, columnspan=4, sticky="ew",
                          padx=(8, 0), pady=3)

        # Куди складати готові файли. Порожньо — поруч зі скриптом, як було.
        ttk.Label(top, text="Готові файли:").grid(row=6, column=0, sticky="w",
                                                  pady=3)
        frame_out = ttk.Frame(top)
        frame_out.grid(row=6, column=1, columnspan=4, sticky="ew",
                       padx=(8, 0), pady=3)
        self.lbl_out = ttk.Label(frame_out, anchor="w",
                                 foreground=self.theme["muted"])
        self.lbl_out.pack(side="left", fill="x", expand=True)
        ttk.Button(frame_out, text="Змінити", width=10,
                   command=self.on_pick_output).pack(side="left", padx=(8, 0))
        ttk.Button(frame_out, text="Поруч зі скриптом", width=20,
                   command=self.on_reset_output).pack(side="left", padx=(6, 0))
        self._refresh_output_label()

        ttk.Label(top, text="Сайт (URL):").grid(row=3, column=0, sticky="w", pady=3)
        frame_url = ttk.Frame(top)
        frame_url.grid(row=3, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=3)
        self.e_url = ttk.Entry(frame_url)
        self.e_url.pack(side="left", fill="x", expand=True)
        ttk.Button(frame_url, text="Вставити", width=10,
                   command=self.on_paste_url).pack(side="left", padx=(8, 0))

        ttk.Label(top, text="Опис сайту:").grid(row=4, column=0, sticky="nw", pady=(8, 3))
        self.t_desc = tk.Text(top, height=6, wrap="word", font=("Segoe UI", 10),
                              padx=8, pady=6)
        self._skin_text(self.t_desc, "field")
        self.t_desc.grid(row=4, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=(8, 3))

        self._on_mode()

        params = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        params.pack(fill="x")
        ttk.Label(params, text="Budget:").pack(side="left")
        self.e_budget = ttk.Entry(params, width=8)
        # Бюджет і ставка задані конвеєром, користувач їх не міняє.
        self.e_budget.insert(0, WHITE_BUDGET)
        self.e_budget.configure(state="readonly")
        self.e_budget.pack(side="left", padx=(6, 20))
        ttk.Label(params, text="Max CPC:").pack(side="left")
        self.e_cpc = ttk.Entry(params, width=8)
        self.e_cpc.insert(0, WHITE_CPC)
        self.e_cpc.configure(state="readonly")
        self.e_cpc.pack(side="left", padx=(6, 20))
        self.want_random = tk.BooleanVar(
            value=bool(self.cfg.get("random_assets", False)))
        head = ttk.Checkbutton(params, text="Випадково",
                               variable=self.want_random,
                               command=self._on_random)
        assets = ttk.LabelFrame(params, labelwidget=head,
                                padding=(8, 2, 8, 4))
        assets.pack(side="left", padx=(0, 18))
        self.want_sitelinks = tk.BooleanVar(
            value=bool(self.cfg.get("sitelinks", True)))
        self.want_negatives = tk.BooleanVar(
            value=bool(self.cfg.get("negatives", True)))
        self.want_callouts = tk.BooleanVar(
            value=bool(self.cfg.get("callouts", True)))
        self.want_snippets = tk.BooleanVar(
            value=bool(self.cfg.get("snippets", True)))
        self.asset_boxes = []
        for label, var in (("Сайтлінки", self.want_sitelinks),
                           ("Мінус-слова", self.want_negatives),
                           ("Калаути", self.want_callouts),
                           ("Сніпети", self.want_snippets)):
            box = ttk.Checkbutton(assets, text=label, variable=var)
            box.pack(side="left", padx=(0, 10))
            self.asset_boxes.append(box)
        # Поля лишаються, бо на них спирається решта коду, але у вікні
        # їх немає: кілька кампаній і агрегатор цій збірці не потрібні.
        self.want_many = tk.BooleanVar(value=False)
        self.e_many = ttk.Entry(params, width=4)
        self.e_many.insert(0, str(MANY_DEFAULT))
        self.want_aggregator = tk.BooleanVar(value=False)
        self._on_random()
        ttk.Label(params, text="Уточнення:").pack(side="left")
        self.e_notes = ttk.Entry(params)
        self.e_notes.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # Стрічка процесу одразу під рядком бюджету: видно, що відбувається,
        # не відводячи очей від параметрів запуску.
        log_wrap = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        log_wrap.pack(fill="x")
        # wrap="word", а не "none": горизонтальної прокрутки тут немає, тож
        # довгий рядок просто обрізався по краю — і текст помилки читався
        # до половини. Тепер переноситься.
        self.t_log = tk.Text(log_wrap, height=6, wrap="word",
                             font=("Comic Sans MS", 14),
                             state="disabled", padx=10, pady=6)
        self._skin_text(self.t_log, "surface")
        sb_log = ttk.Scrollbar(log_wrap, orient="vertical", command=self.t_log.yview)
        self.t_log.configure(yscrollcommand=sb_log.set)
        sb_log.pack(side="right", fill="y")
        self.t_log.pack(side="left", fill="x", expand=True)
        attach_context_menu(self.t_log)
        self.t_log.tag_configure("time", foreground=self.theme["muted"])
        for name, colour in SEMANTIC.items():
            self.t_log.tag_configure(name, foreground=colour)

        enable_clipboard(self.e_key, self.e_url, self.e_ident, self.t_desc,
                         self.e_budget, self.e_cpc, self.e_notes, self.cb_model)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        f_table = ttk.Frame(nb)
        nb.add(f_table, text="Чернетка")
        self.t_table = tk.Text(f_table, wrap="none", font=("Consolas", 9),
                               state="disabled", padx=10, pady=8)
        self._skin_text(self.t_table)
        sb_y = ttk.Scrollbar(f_table, orient="vertical", command=self.t_table.yview)
        sb_x = ttk.Scrollbar(f_table, orient="horizontal", command=self.t_table.xview)
        self.t_table.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self.t_table.pack(side="left", fill="both", expand=True)

        # Вкладка перевірки — прокручуваний список, бо на кожну помилку потрібна
        # галочка «беру на себе»: фільтр навмисне широкий і колись помилиться.
        f_check = ttk.Frame(nb)
        nb.add(f_check, text="Перевірка")
        # Усередині канви лежить ttk.Frame — фон беремо той самий, інакше
        # навколо списку перевірок буде світла рамка.
        canvas = tk.Canvas(f_check, highlightthickness=0, bg=self.theme["bg"])
        sb_c = ttk.Scrollbar(f_check, orient="vertical", command=canvas.yview)
        self.check_body = ttk.Frame(canvas)
        self.check_body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.check_body, anchor="nw")
        canvas.configure(yscrollcommand=sb_c.set)
        sb_c.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.overrides = []
        self.nb = nb

        bottom = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        bottom.pack(fill="x")
        t = self.theme
        self.btn_draft = tk.Button(bottom, text="1. Згенерувати чернетку",
                                   command=self.on_draft, height=2,
                                   bg=AURORA[0], fg="#ffffff",
                                   activebackground=AURORA[1],
                                   activeforeground="#ffffff",
                                   disabledforeground=t["muted"],
                                   font=("Segoe UI", 10, "bold"),
                                   relief="flat", bd=0, cursor="hand2")
        self.btn_draft.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_regen = tk.Button(bottom, text="Регенерувати",
                                   command=self.on_regenerate, height=2,
                                   state="disabled", bg=AURORA[1], fg="#ffffff",
                                   activebackground=AURORA[0],
                                   activeforeground="#ffffff",
                                   disabledforeground=t["muted"],
                                   font=("Segoe UI", 10, "bold"),
                                   relief="flat", bd=0, cursor="hand2")
        self.btn_regen.pack(side="left", padx=(6, 6))
        self._paint(self.btn_regen, False, AURORA[1])
        self.btn_paste = tk.Button(bottom, text="Вставити відповідь",
                                   command=self.on_paste_answer, height=2,
                                   bg=t["surface2"], fg=t["ink"],
                                   activebackground=t["surface"],
                                   activeforeground=t["ink"],
                                   disabledforeground=t["muted"],
                                   relief="flat", bd=0, cursor="hand2")
        self.btn_paste.pack(side="left", padx=(6, 6))
        self.btn_csv = tk.Button(bottom, text="2. Створити CSV",
                                 command=self.on_csv, height=2, state="disabled",
                                 bg=AURORA[2], fg="#ffffff",
                                 activebackground=AURORA[1],
                                 activeforeground="#ffffff",
                                 disabledforeground=t["muted"],
                                 font=("Segoe UI", 10, "bold"),
                                 relief="flat", bd=0, cursor="hand2")
        self.btn_csv.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._paint(self.btn_csv, False, AURORA[2])   # стартує вимкненою

        self.status = ttk.Label(self.root, text="Готовий до роботи.", anchor="w",
                                padding=(14, 0, 14, 8))
        self.status.pack(fill="x")

    # ── допоміжне ─────────────────────────────────────────────────────────────
    def _log(self, text, tag=""):
        """Стрічка процесу: видно, на якому кроці застрягло і скільки це тривало."""
        stamp = time.strftime("%H:%M:%S")
        self.t_log.configure(state="normal")
        self.t_log.insert(tk.END, stamp + "  ", "time")
        self.t_log.insert(tk.END, text + "\n", tag or ())
        self.t_log.see(tk.END)
        self.t_log.configure(state="disabled")
        self.log_lines.append(f"{stamp}  {text}")

    def _set_text(self, widget, content, tags=None):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        if tags:
            for chunk, tag in tags:
                widget.insert(tk.END, chunk, tag)
        else:
            widget.insert(tk.END, content)
        widget.configure(state="disabled")

    def _set_busy(self, busy, message=""):
        self.busy = busy
        self.btn_draft.configure(state="disabled" if busy else "normal")
        self._paint(self.btn_draft, not busy, AURORA[0])
        self.btn_paste.configure(state="disabled" if busy else "normal")
        # Регенерувати можна лише тоді, коли є що виправляти.
        can_regen = not busy and bool(self.draft)
        self.btn_regen.configure(state="normal" if can_regen else "disabled")
        self._paint(self.btn_regen, can_regen, AURORA[1])
        if busy:
            self.btn_csv.configure(state="disabled")
            self._paint(self.btn_csv, False, AURORA[2])
        else:
            self._refresh_csv_button()
        if message:
            self.status.configure(text=message)

    def build_request(self, url, desc, wants, extra="", used_names=()):
        """Складає варіант запуску й текст запиту. Одна точка для одиночного
        запуску й для черги — інакше вони почнуть розходитись."""
        cut = []
        if not wants["aggregator"]:
            desc, cut = scrub_description(desc)
        # З опису вирізали гральне — отже сайт гральний, і «gaming» чи «play»
        # в оголошенні вже не про кіберспорт.
        wants["scrubbed"] = bool(cut)
        wants["source_desc"] = desc      # щоб звірити гео з тим, що на сайті
        # Сторінку качаємо ОДИН раз на запуск, а не в кожній перевірці:
        # validate() мусить лишатися швидким і без мережі.
        wants["page"] = fetch_landing(url) if url else {}
        variant = pick_variant(wants["aggregator"])
        variant["sitelinks"]   = wants["sitelinks"]
        variant["callouts"]    = wants["callouts"]
        variant["snippets_on"] = wants["snippets"]
        variant["aggregator"]  = wants["aggregator"]
        text = (f"Сайт: {url}\n\n"
                f"Опис сайту:\n{desc or '(опису немає, орієнтуйся на URL)'}\n\n"
                + variant_brief(variant))
        # Домен каже про країну прямо, тож кажемо це й моделі. Інакше вона
        # рахує згадки в описі й бере кухню за країну показу: ресторан на
        # .fr з італійським меню їхав кампанією на Італію.
        by_tld = tld_country(url)
        asked = apply_notes_geo(wants, extra)
        if asked:
            text += (f"\n\nГЕО ЗАДАНО В УТОЧНЕННІ КЛІЄНТА: {asked}. Це "
                     f"головніше за домен і опис сайту. location: {asked}, "
                     f"мова — мова цієї країни: ключі, заголовки, описи й "
                     f"розширення — усе нею.")
        elif by_tld:
            text += (f"\n\nГЕО — ДВА ОРІЄНТИРИ, дивись на обидва: опис "
                     f"сайту і його домен. Домен тут національний — "
                     f"{by_tld}. Країна показу — та, де сайт продає чи "
                     f"працює. Кухня, стиль чи походження товару в описі — "
                     f"це не країна: італійське меню на сайті .fr — це "
                     f"Франція.")
        if used_names:
            # Схожі описи дають однакові назви. Перелічуємо вже зайняті —
            # без цього вся черга виходить під однією назвою, і CSV
            # затирають один одного.
            text += ("\n\nЦІ НАЗВИ ВЖЕ ЗАЙНЯТІ В ЦЬОМУ ЗАПУСКУ. Не повторюй "
                     "їх і не роби з них варіації — потрібна інша назва:\n"
                     + "\n".join(f"- {n}" for n in list(used_names)[-20:]))
        if is_tech_repair(desc) or is_tech_repair(user_extra_hint(extra)):
            text += TECH_SUPPORT_BRIEF
        if extra:
            text += f"\n\nДодаткові побажання клієнта:\n{extra}"
        return variant, text, desc, cut

    def _on_random(self):
        """«Випадково» гасить ручний вибір: набір вирішує жереб."""
        state = "disabled" if self.want_random.get() else "normal"
        for box in self.asset_boxes:
            box.configure(state=state)

    def _roll_assets(self):
        """Жереб на одну кампанію: кожен асет окремо, монетою."""
        return {k: random.random() < 0.5
                for k in ("sitelinks", "negatives", "callouts", "snippets")}

    def _wants(self):
        # soft вимикати нікуди: спокійна подача — базове правило, а не опція.
        picked = (self._roll_assets() if self.want_random.get() else
                  {"sitelinks": self.want_sitelinks.get(),
                   "negatives": self.want_negatives.get(),
                   "callouts":  self.want_callouts.get(),
                   "snippets":  self.want_snippets.get()})
        return {"sitelinks":  picked["sitelinks"],
                "callouts":   picked["callouts"],
                "negatives":  picked["negatives"],
                "snippets":   picked["snippets"],
                "aggregator": self.want_aggregator.get(),
                "soft":       True}

    def _on_aggregator(self):
        """Режим свідомо не запам'ятовується в конфізі: він має вмикатися
        рішенням під конкретний сертифікований домен, а не залишатися
        увімкненим з минулого разу."""
        if self.want_aggregator.get():
            self._log("Агрегатор увімкнено: гральна лексика дозволена, фільтр "
                      "перемкнувся на обіцянки виграшу, згадки дітей і вікові "
                      "маркери. Структура — одна група, одне оголошення.",
                      "warning")
            self.status.configure(
                text="Агрегатор: вмикай лише для домену з сертифікацією Google.")
        else:
            self._log("Агрегатор вимкнено: гральна лексика знову заборонена.")

    def _persist(self):
        self.cfg["api_key"] = self.e_key.get().strip()
        self.cfg["model"]   = self.cb_model.get().strip()
        self.cfg["budget"]  = WHITE_BUDGET
        self.cfg["cpc"]     = WHITE_CPC
        self.cfg["mode"]      = self.mode.get()
        self.cfg["random_assets"] = self.want_random.get()
        self.cfg["sitelinks"] = self.want_sitelinks.get()
        self.cfg["callouts"]  = self.want_callouts.get()
        self.cfg["negatives"] = self.want_negatives.get()
        self.cfg["many"] = self.want_many.get()
        self.cfg["many_count"] = self.e_many.get().strip()
        self.cfg["snippets"]  = self.want_snippets.get()
        self.cfg["ident"]     = self.e_ident.get().strip()
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _on_mode(self):
        api = self.mode.get() == "api"
        if api:
            self.api_row.grid()
        else:
            self.api_row.grid_remove()
        self.btn_chrome.configure(state="disabled" if api else "normal")
        self._refresh_chrome_label()

    def _refresh_chrome_label(self):
        if self.mode.get() == "api":
            self.lbl_chrome.configure(text="")
            return
        if cdp_alive():
            self.lbl_chrome.configure(text="вікно Gemini: підключено",
                                      foreground=SEMANTIC["success"])
            self.btn_chrome.configure(text="Показати вікно")
        else:
            self.lbl_chrome.configure(text="вікно Gemini: не запущено",
                                      foreground=SEMANTIC["warning"])
            self.btn_chrome.configure(text="Відкрити вікно Gemini")

    def _refresh_output_label(self):
        root = chosen_root()
        self.lbl_out.configure(
            text=root if root else f"поруч зі скриптом: {BASE_DIR}")

    def on_pick_output(self):
        """Вибір теки для готових CSV. Журнал і профіль Chrome лишаються
        поруч зі скриптом — переносити треба саме результат роботи."""
        folder = filedialog.askdirectory(
            title="Куди складати готові CSV",
            initialdir=chosen_root() or BASE_DIR)
        if not folder:
            return
        self.cfg["output_root"] = os.path.normpath(folder)
        try:
            save_config(self.cfg)
        except Exception as e:
            messagebox.showerror("Не вдалося зберегти", str(e))
            return
        self._refresh_output_label()
        self._log(f"Готові файли тепер лягають у {self.cfg['output_root']}",
                  "success")

    def on_reset_output(self):
        self.cfg["output_root"] = ""
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._refresh_output_label()
        self._log(f"Готові файли знову лягають поруч зі скриптом: {BASE_DIR}")

    def on_paste_url(self):
        """Вставка URL кнопкою — працює за будь-якої розкладки."""
        try:
            raw = self.root.clipboard_get()
        except Exception:
            self.status.configure(text="У буфері обміну немає тексту.")
            return
        found = re.search(r"(https?://[^\s)\]]+)", raw)
        url = (found.group(1) if found else raw).strip()
        if url and not url.startswith("http"):
            url = "https://" + url
        self.e_url.delete(0, tk.END)
        self.e_url.insert(0, url)

    def on_paste_answer(self):
        """Ручний обхід, якщо автоматика не змогла забрати відповідь: беремо JSON
        із буфера обміну — його можна скопіювати просто з вкладки Gemini."""
        try:
            raw = self.root.clipboard_get()
        except Exception:
            messagebox.showwarning("Увага", "У буфері обміну немає тексту.")
            return
        try:
            draft = extract_json(raw)
        except Exception as e:
            messagebox.showerror(
                "Не розібрав", f"{e}\n\nСкопіюй саме блок JSON із відповіді Gemini "
                               f"(разом із фігурними дужками).")
            return

        url = self.e_url.get().strip()
        if url:
            draft["website"] = url
        self.draft = draft
        errors, warnings = validate(draft, self._wants())
        self._set_text(self.t_table, render_table(draft))
        self._render_check(errors, warnings)
        save_history({
            "час": time.strftime("%Y-%m-%d %H:%M:%S"),
            "статус": "вставлено вручну",
            "режим": "ручний",
            "url": url,
            "campaign_name": draft.get("campaign_name", ""),
            "помилок": errors,
            "попереджень": warnings,
            "raw_response": raw,
            "draft": draft,
        })
        self.nb.select(1 if errors else 0)
        self.status.configure(
            text=f"Відповідь прийнято вручну. Помилок: {len(errors)}, "
                 f"попереджень: {len(warnings)}.")

    def _open(self, folder):
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
            self.status.configure(text=f"Відкрито {os.path.basename(folder)}")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося відкрити папку:\n{e}")

    def on_open_output(self):
        """Відкриває ту папку, куди ляже наступний файл — з урахуванням
        режиму й ідентифікатора."""
        self._open(output_dir(self.want_aggregator.get(),
                              self.e_ident.get().strip()))

    def on_open_rework(self):
        self._open(rework_dir(self.want_aggregator.get(),
                              self.e_ident.get().strip()))

    def adopt_batch_row(self, row, index, window):
        """Ставить чернетку з черги в головне вікно як поточну. Далі працюють
        усі звичні кнопки: галочки на помилки, «Регенерувати», «Створити CSV».
        Регенерація б'є саме по цьому рядку — у ньому лежить і запит, і сира
        відповідь моделі."""
        self.draft = row["draft"]
        self.batch_ref = (window, index)
        self.round = row.get("round", 1)
        # Підхоплюємо стан рядка, а не починаємо з чистого аркуша: інакше
        # регенерація тут забуває, що вже виправляли й що обрізали, і йде
        # по другому колу.
        self.seen_errors = set(row.get("seen") or [])
        self.truncated = [tuple(t) for t in (row.get("truncated") or [])]
        self.prev_texts = (row.get("texts")
                           or all_ad_texts(row["draft"].get("ad_groups")))
        # Адреса чату саме цього сайту. Без неї дослання полетіло б у той
        # чат, що випадково лишився відкритим після черги, — і кампанія
        # повернулася б з чужою країною.
        self.chat_url = row.get("chat", "")
        self.last_raw = row.get("raw", "")
        self.last_run = {"key": self.e_key.get().strip(),
                         "model": self.cb_model.get().strip(),
                         "user_text": row.get("user_text", ""),
                         "url": row.get("url", ""),
                         "variant": row.get("variant") or pick_variant(),
                         "wants": row.get("wants") or self._wants()}
        self.e_url.delete(0, tk.END)
        self.e_url.insert(0, row.get("url", ""))
        self.e_ident.delete(0, tk.END)
        self.e_ident.insert(0, row.get("ident", ""))
        self._set_text(self.t_desc, row.get("desc", ""))
        self._set_text(self.t_table, render_table(row["draft"]))
        self._render_check(row["errors"], row["warnings"])
        self.busy = False
        self._set_busy(False, f"Черга, рядок {index + 1}: "
                              f"помилок {len(row['errors'])}, "
                              f"попереджень {len(row['warnings'])}.")
        self.nb.select(1 if row["errors"] else 0)
        self.root.lift()

    def adopt_history(self, entry):
        """Відкриває чернетку з журналу так само, як свіжу: перевірка,
        регенерація, CSV. Файлу могло не бути — тепер його можна створити."""
        self.draft = entry["draft"]
        self.batch_ref = None
        self.round = entry["run"].get("раунд", 1)
        # Чат тієї генерації давно закритий, тому дослання тут неможливе:
        # регенерація піде повним промптом із переліком правок.
        self.chat_url = ""
        self.seen_errors = set()
        self.truncated = []
        self.prev_texts = all_ad_texts(entry["draft"].get("ad_groups"))
        self.last_raw = entry.get("raw", "")
        self.last_run = {"key": self.e_key.get().strip(),
                         "model": self.cb_model.get().strip(),
                         "user_text": entry.get("user_text", ""),
                         "url": entry.get("url", ""),
                         "variant": entry.get("variant") or pick_variant(),
                         "wants": entry["wants"]}
        # Ставимо галочки так, як були на тому запуску — інакше перевірка
        # й склад файла розійдуться з тим, що бачив тоді.
        w = entry["wants"]
        self.want_sitelinks.set(bool(w.get("sitelinks")))
        self.want_callouts.set(bool(w.get("callouts", True)))
        self.want_negatives.set(bool(w.get("negatives", True)))
        self.want_snippets.set(bool(w.get("snippets", True)))
        self.want_aggregator.set(bool(w.get("aggregator")))
        self.e_url.delete(0, tk.END)
        self.e_url.insert(0, entry.get("url", ""))
        errors, warnings = validate(self.draft, w)
        self._set_text(self.t_table, render_table(self.draft))
        self._render_check(errors, warnings)
        self.busy = False
        self._set_busy(False, f"З журналу: {entry['when'][:16]} — "
                              f"помилок {len(errors)}, попереджень {len(warnings)}.")
        self._log(f"Відкрито з журналу: {os.path.basename(entry['folder'])}")
        self.nb.select(1 if errors else 0)
        self.root.lift()

    def on_batch_window(self):
        existing = getattr(self, "_batch_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        self._batch_window = BatchWindow(self)

    def on_edit_prompt(self):
        """Відкриває той промпт, за яким піде наступна генерація. Зміни
        підхопляться одразу — перезапускати вікно не треба."""
        agg = self.want_aggregator.get()
        try:
            path = ensure_prompt_file(agg)
            os.startfile(path)
            self.status.configure(
                text=f"Відкрито {os.path.basename(path)} — "
                     f"{'промпт агрегатора' if agg else 'звичайний промпт'}. "
                     f"Збережи файл, наступна генерація візьме новий текст.")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося відкрити промпт:\n{e}")

    def on_open_chrome(self):
        """Піднімає окреме вікно Chrome із профілем застосунку і вкладкою Gemini."""
        self._set_busy(True, "Відкриваю вікно Chrome…")
        threading.Thread(target=self._chrome_worker, daemon=True).start()

    def _chrome_worker(self):
        try:
            if not cdp_alive():
                launch_chrome(chrome_path(self.cfg.get("chrome_path", "")))
            open_gemini_tab()
            self.q.put(("chrome", "Вікно Gemini готове. Якщо просить вхід — залогінься в ньому."))
        except Exception as e:
            self.q.put(("error", str(e)))

    # ── моделі ────────────────────────────────────────────────────────────────
    def on_refresh_models(self):
        key = self.e_key.get().strip()
        if not key:
            messagebox.showwarning("Увага", "Спочатку введи API-ключ.")
            return
        self._set_busy(True, "Отримую список моделей…")
        threading.Thread(target=self._models_worker, args=(key,), daemon=True).start()

    def _models_worker(self, key):
        try:
            self.q.put(("models", list_models(key)))
        except Exception as e:
            self.q.put(("error", str(e)))

    # ── чернетка ──────────────────────────────────────────────────────────────
    def on_draft(self):
        key = self.e_key.get().strip()
        url = self.e_url.get().strip()
        desc = self.t_desc.get("1.0", tk.END).strip()
        if self.mode.get() == "api" and not key:
            messagebox.showwarning("Увага", "Введи API-ключ Gemini або перемкнись на браузер.")
            return
        if not url and not desc:
            messagebox.showwarning("Увага", "Вкажи URL сайту або його опис.")
            return
        if url and not url.startswith("http"):
            url = "https://" + url
            self.e_url.delete(0, tk.END)
            self.e_url.insert(0, url)

        self._persist()

        # Гральну частину прибираємо з опису ДО запиту — рекламуємо дозволену
        # частину бізнесу. У режимі агрегатора чистка вимкнена: там гральна
        # тематика і є предметом реклами, домен сертифікований.
        wants = self._wants()
        variant, user_text, desc, cut = self.build_request(
            url, desc, wants, self.e_notes.get().strip())
        if cut and not desc:
            messagebox.showwarning(
                "Опис порожній після чистки",
                "Увесь опис сайту стосується гральної тематики — після чистки "
                "не лишилось нічого.\n\nОпиши дозволену частину бізнесу: що "
                "саме пропонує сайт, для кого, на яких умовах.")
            return
        self.status.configure(text=f"Варіант запуску: {variant['structure']}")
        self._log("── Новий запуск " + "─" * 40)
        on = lambda flag: "так" if flag else "ні"
        self._log(f"Варіант: {variant['structure']}; груп {variant['groups']}, "
                  f"оголошень у групі {variant['ads']}")
        self._log(f"Розширення: сайтлінки {on(wants['sitelinks'])}, "
                  f"калаути {on(wants['callouts'])}, "
                  f"сніпети {on(wants['snippets'])}")
        if wants["aggregator"]:
            self._log("Режим агрегатора: промпт prompt_aggregator.txt, гральна "
                      "тематика дозволена, опис не чистимо.", "warning")
        self._log("М'яка подача: тема та сама, промо-лексика, суми й чужі "
                  "торгові марки в текстах оголошень заборонені.")
        for chunk in cut:
            self._log(f"Вирізано з опису: {chunk[:90]}", "warning")

        self.draft = None
        self.round = 1
        self.batch_ref = None      # звичайний запуск — не з черги
        self.chat_url = ""         # новий запуск — нова розмова
        self.seen_errors = set()
        # Запам'ятовуємо запуск: кнопка «Регенерувати» шле той самий запит
        # ще раз, додаючи до нього помилки поточної чернетки.
        self.last_run = {"key": key, "model": self.cb_model.get().strip(),
                         "user_text": user_text, "url": url,
                         "variant": variant, "wants": wants}
        # Кілька кампаній на один сайт: окремий прохід, свій чат на кожну.
        if self.want_many.get():
            try:
                count = max(2, min(MANY_MAX, int(self.e_many.get().strip() or MANY_DEFAULT)))
            except ValueError:
                count = MANY_DEFAULT
            self.many, self.many_stop = [], False
            self._log(f"Кілька кампаній на сайт: {count}. Кожна — окрема "
                      f"розмова, окремий жереб і обов'язково інша назва.",
                      "warning")
            self._set_busy(True, f"Генерую {count} кампаній…")
            threading.Thread(
                target=self._many_worker,
                args=(key, self.cb_model.get().strip(), url, desc, wants,
                      self.e_notes.get().strip(), count),
                daemon=True).start()
            return

        self.many = []
        self._set_busy(True, "Генерую чернетку…")
        threading.Thread(target=self._draft_worker,
                         args=(key, self.cb_model.get().strip(), user_text, url,
                               variant, wants, ""),
                         daemon=True).start()

    def _many_worker(self, key, model, url, desc, wants, extra, count):
        """Кілька самостійних кампаній на один сайт.

        Кожна йде в СВІЙ чат із власним жеребом варіанта, а список уже
        зайнятих назв передається в запит — інакше десять кампаній виходять
        під одним іменем, і CSV затирають один одного. Помилки доводимо тут
        же, як у черзі: поки їх меншає.
        """
        browser = self.mode.get() == "browser"
        exe = self.cfg.get("chrome_path", "")
        done, used = [], []
        for i in range(count):
            if getattr(self, "many_stop", False):
                break
            self.q.put(("status", f"Кампанія {i + 1} з {count}: запит…"))
            sink = {"on_wait": lambda short, full, n=i: self.q.put(
                ("status", f"Кампанія {n + 1} з {count}: {full}"))}
            try:
                # Гео з уточнення — у спільні параметри, щоб перевірка
                # кожної кампанії вимагала саме його.
                apply_notes_geo(wants, extra)
                variant, user_text, _, _ = self.build_request(
                    url, desc, dict(wants), extra, used)
                agg = bool(wants.get("aggregator"))
                if browser:
                    draft = browser_generate(user_text, "", lambda s: None,
                                             exe, sink, None, agg, new_chat=True)
                else:
                    draft = generate_draft(key, model, user_text, "", sink,
                                           None, agg)
                if url:
                    draft["website"] = url
                errors, warnings = validate(draft, wants)
                seen = set(errors)
                texts = all_ad_texts(draft.get("ad_groups"))
                rounds, stall = 1, 0
                while errors and rounds < AUTO_ROUNDS_MAX and not getattr(self, "many_stop", False):
                    self.q.put(("status", f"Кампанія {i + 1} з {count}: "
                                          f"раунд {rounds + 1}, помилок {len(errors)}"))
                    notes, _, _ = build_repair_notes(draft, wants, seen, [], extra)
                    prev_n, prev_texts = len(errors), texts
                    if browser:
                        draft = browser_generate(user_text, notes, lambda s: None,
                                                 exe, sink, None, agg,
                                                 follow_up=True)
                    else:
                        draft = generate_draft(key, model, user_text, notes, sink,
                                               None, agg, previous=sink.get("raw", ""))
                    if url:
                        draft["website"] = url
                    errors, warnings = validate(draft, wants)
                    texts = all_ad_texts(draft.get("ad_groups"))
                    seen |= set(errors)
                    rounds += 1
                    stall = stall + 1 if len(errors) >= prev_n else 0
                    if stall >= 2:
                        break
                name = (draft.get("campaign_name") or "").strip()
                if name and defold(name) in {defold(n) for n in used}:
                    errors = list(errors) + [
                        f"Назва «{name}» уже зайнята іншою кампанією цього "
                        f"запуску — у одному акаунті це дубль."]
                if name:
                    used.append(name)
                save_history({
                    "час": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "статус": "готово",
                    "режим": ("браузер" if browser else "API") + f", кампанія {i + 1}",
                    "модель": "gemini web" if browser else model,
                    "url": url, "campaign_name": name,
                    "варіант": variant, "wants": wants, "раунд": rounds,
                    "ідентифікатор": self.e_ident.get().strip(),
                    "помилок": errors, "попереджень": warnings,
                    "запит": user_text, "промпт": load_system_prompt(agg),
                    "raw_response": sink.get("raw", ""), "draft": draft,
                })
                done.append({"draft": draft, "errors": list(errors),
                             "warnings": list(warnings), "rounds": rounds})
                self.q.put(("many_one", (i + 1, count, name, list(errors), rounds)))
            except Exception as e:
                self.q.put(("many_one", (i + 1, count, "", [str(e)], 0)))
        self.q.put(("many_done", done))

    def on_regenerate(self):
        """Ще один прохід із поточними помилками. Скільки завгодно разів:
        рішення, чи помилка критична, лишається за людиною, а не за лічильником
        спроб. Автоматичні дві спроби витрачали запити наосліп."""
        run = getattr(self, "last_run", None)
        if not run or not self.draft:
            messagebox.showinfo("Немає чого регенерувати",
                                "Спочатку згенеруй чернетку.")
            return
        seen = getattr(self, "seen_errors", set())
        # Гео з уточнення лягає в параметри запуску, а не лише в текст: по
        # них перевіряється й наступна чернетка.
        apply_notes_geo(run["wants"], self.e_notes.get().strip())
        notes, errors, warnings = build_repair_notes(
            self.draft, run["wants"], seen, getattr(self, "truncated", []),
            self.e_notes.get().strip())
        structural = [w for w in warnings if STRUCTURAL_RE.search(w)]
        repeats = sorted(set(errors) & seen)
        if repeats:
            self._log(f"Повернулося з минулих раундів: {len(repeats)}", "warning")
        self.seen_errors = seen | set(errors)

        self.round = getattr(self, "round", 1) + 1
        self._log(f"── Регенерація, раунд {self.round}: помилок {len(errors)}, "
                  f"суттєвих зауважень {len(structural)}",
                  "danger" if errors else "warning")
        self._set_busy(True, f"Регенерую (раунд {self.round})…")
        threading.Thread(
            target=self._draft_worker,
            args=(run["key"], run["model"], run["user_text"], run["url"],
                  run["variant"], run["wants"], notes),
            daemon=True).start()

    def _draft_worker(self, key, model, user_text, url, variant, wants,
                      repair_notes=""):
        browser = self.mode.get() == "browser"
        exe = self.cfg.get("chrome_path", "")
        progress = lambda s: self.q.put(("status", s))
        # Поки API чекає на повтор, людина бачить це в рядку стану.
        sink = {"on_wait": lambda short, full: progress(full)}
        agg = bool(wants.get("aggregator"))

        previous = getattr(self, "last_raw", "")

        def ask(notes=""):
            # Є зауваження — значить це дослання в той самий діалог, а не
            # новий запит: промпт і завдання модель уже отримала.
            #
            # Досилаємо ЛИШЕ туди, де точно лежить попередня відповідь. Без
            # відомої адреси чату «виправ свою відповідь» полетіло б у першу-
            # ліпшу відкриту розмову — саме так чернетка з журналу приносила
            # чужу країну. Не знаємо чату — шлемо повний промпт із правками.
            chat = getattr(self, "chat_url", "")
            if browser:
                draft = browser_generate(user_text, notes, progress, exe,
                                         sink, None, agg,
                                         follow_up=bool(notes) and bool(chat),
                                         chat_url=chat if notes else "",
                                         # Новий запуск — новий чат, інакше
                                         # модель тягне гео й лексику з
                                         # попереднього сайту.
                                         new_chat=not notes)
                if sink.get("chat"):
                    self.chat_url = sink["chat"]
                return draft
            return generate_draft(key, model, user_text, notes, sink, None, agg,
                                  previous=previous)

        def journal(status, draft=None, errors=(), warnings=(), error_text=""):
            return save_history({
                "час": time.strftime("%Y-%m-%d %H:%M:%S"),
                "статус": status,
                "режим": "браузер" if browser else "API",
                "модель": model if not browser else "gemini web",
                "url": url,
                "campaign_name": (draft or {}).get("campaign_name", ""),
                "варіант": variant,
                "wants": wants,
                "раунд": getattr(self, "round", 1),
                # Пишемо в журнал ідентифікатор: за ним потім видно, чия це
                # кампанія, і туди ж лягає переробка оголошень.
                "ідентифікатор": self.e_ident.get().strip(),
                "виправлення": repair_notes,
                "помилок": list(errors),
                "попереджень": list(warnings),
                "текст_помилки": error_text,
                "запит": user_text,
                "промпт": load_system_prompt(agg),
                "raw_response": sink.get("raw", ""),
                "draft": draft,
            })

        try:
            # Рівно один запит. Далі рішення за людиною: критичні помилки —
            # кнопка «Регенерувати», некритичні — галочки на вкладці
            # «Перевірка» і одразу CSV.
            draft = ask(repair_notes)
            if url:
                draft["website"] = url
            errors, warnings = validate(draft, wants)
            self.last_raw = sink.get("raw", "")   # для наступного раунду в API
            folder = journal("готово", draft, errors, warnings)
            self.q.put(("draft", (draft, errors, warnings, folder)))
        except Exception as e:
            folder = journal("збій", error_text=str(e))
            hint = ""
            if sink.get("raw"):
                hint = ("\n\nСиру відповідь моделі збережено — її можна вставити "
                        "вручну кнопкою «Вставити відповідь»:\n" + folder)
            self.q.put(("error", str(e) + hint))

    # ── CSV ───────────────────────────────────────────────────────────────────
    def on_csv(self):
        if not self.draft:
            return
        wants = self._wants()
        errors, _ = validate(self.draft, wants)
        unresolved = [e for e, var in zip(errors, self.overrides) if not var.get()]
        if unresolved:
            messagebox.showerror(
                "Не можу зібрати файл",
                "Лишилися помилки без галочки на вкладці «Перевірка»:\n\n"
                + "\n".join(unresolved[:8]))
            return
        if errors and not messagebox.askyesno(
                "Помилки взято на себе",
                f"Ти позначив {len(errors)} помилок як перевірені вручну.\n"
                f"Google може відхилити такі рядки при завантаженні.\n\nСтворюємо файл?"):
            return
        # Бюджет і ставка можуть бути числом, діапазоном «10-20» або списком
        # «10; 12; 15», який іде по колу від запуску до запуску.
        try:
            budget_val, why_b = resolve_amount(self.e_budget.get(), 0, "budget_i", self.cfg)
            cpc_val, why_c    = resolve_amount(self.e_cpc.get(), 2, "cpc_i", self.cfg)
        except ValueError as e:
            messagebox.showerror(
                "Бюджет або ставка",
                f"Не розумію значення: {e}\n\n"
                f"Можна: число «10», діапазон «10-20» (візьму випадкове) "
                f"або список «10; 12; 15» (піде по колу).")
            return
        budget, cpc = format_amount(budget_val, 0), format_amount(cpc_val, 2)

        # Кілька кампаній — один файл. Чисті беремо всі, брудні не беремо
        # взагалі: CSV з помилками на диску не відрізнити від справного.
        many = getattr(self, "many", None)
        if many:
            clean = [d for d in many if not d["errors"]]
            if not clean:
                messagebox.showerror(
                    "Немає чого зберігати",
                    f"Жодна з {len(many)} кампаній не пройшла перевірку. "
                    f"Тисни «Регенерувати» або запусти ще раз.")
                return
            ident = self.e_ident.get().strip()
            all_rows = []
            for d in clean:
                b, _ = resolve_amount(self.e_budget.get(), 0, "budget_i", self.cfg)
                cp, _ = resolve_amount(self.e_cpc.get(), 2, "cpc_i", self.cfg)
                all_rows += build_rows(d["draft"], format_amount(b, 0),
                                       format_amount(cp, 2), wants)
            label = ident or domain_short(self.e_url.get().strip()) or "campaigns"
            try:
                path = write_many_csv(all_rows, label, wants["aggregator"], ident)
            except Exception as e:
                self._log(f"CSV не зібрався: {e}", "danger")
                messagebox.showerror("Помилка", "Не вдалося зібрати CSV: " + str(e))
                return
            self._persist()
            names = [d["draft"].get("campaign_name", "") for d in clean]
            self.status.configure(text=f"{os.path.basename(path)} — "
                                       f"кампаній {len(clean)}, рядків {len(all_rows)}")
            self._log(f"Файл: {short_path(path)} — кампаній {len(clean)}, "
                      f"рядків {len(all_rows)}", "success")
            for n in names:
                self._log(f"   {n}")
            skipped = len(many) - len(clean)
            if skipped:
                self._log(f"Не збережено через помилки: {skipped}", "warning")
            return

        name = self.draft["campaign_name"].strip()
        ident = self.e_ident.get().strip()
        folder = output_dir(wants["aggregator"], ident)
        path = os.path.join(folder, f"{safe_filename(name)}.csv")
        if os.path.exists(path) and not messagebox.askyesno(
                "Файл існує", f"«{os.path.basename(path)}» вже є. Перезаписати?"):
            return
        try:
            rows = build_rows(self.draft, budget, cpc, wants)
            path = write_csv(rows, name, wants["aggregator"], ident)
        except Exception as e:
            self._log(f"CSV не зібрався: {e}", "danger")
            messagebox.showerror("Помилка", f"Не вдалося зібрати CSV:\n{e}")
            return

        self._persist()
        # Рядок черги позначаємо збереженим — далі по списку.
        ref = getattr(self, "batch_ref", None)
        if ref:
            win, idx = ref
            if win.winfo_exists() and idx < len(win.rows):
                win.rows[idx]["status"] = "збережено"
                win.rows[idx]["draft"] = self.draft
                win.rows[idx]["csv"] = path
                win._refresh()
                # Далі по списку — той, що справді чекає людину. Чисті
                # рядки розбору не потребують, їх забирає кнопка гуртом.
                nxt = next((n for n, r in enumerate(win.rows)
                            if r["status"] == "потрібна увага"), None)
                if nxt is None:
                    nxt = next((n for n, r in enumerate(win.rows)
                                if r["status"] == "чисто"), None)
                if nxt is not None:
                    win._open_row(nxt)
                else:
                    win.deiconify()
                    win.lift()
        self.status.configure(text=f"{os.path.basename(path)} — рядків {len(rows)}")
        self._log(f"Файл: {short_path(path)} — рядків {len(rows)}", "success")
        for line in self._mini_report(self.draft, rows, budget, cpc, why_b, why_c):
            self._log("   " + line)

    def _mini_report(self, draft, rows, budget, cpc, why_b, why_c):
        """Короткий підсумок у стрічку процесу — замість модального вікна."""
        groups = draft.get("ad_groups") or []
        counts = {}
        for r in rows:
            if r.get("Row Type") == "Sitelink":
                key = "сайтлінки"
            elif r.get("Asset type") == "Callout":
                key = "калаути"
            elif r.get("Asset type") == "Structured snippet":
                key = "сніпети"
            elif r.get("Ad type"):
                key = "оголошення"
            elif r.get("Keyword"):
                key = "ключі"
            elif r.get("Ad group"):
                key = "групи"
            else:
                key = "кампанія"
            counts[key] = counts.get(key, 0) + 1
        order = ["кампанія", "групи", "ключі", "оголошення",
                 "калаути", "сніпети", "сайтлінки"]
        parts = [f"{k} {counts[k]}" for k in order if counts.get(k)]
        loc = normalize_location(draft.get("location", ""), draft.get("language", ""))
        return [
            ", ".join(parts),
            f"бюджет {budget} ({why_b}), ставка {cpc} ({why_c})",
            f"гео {loc or '—'}, мова {draft.get('language') or '—'}, "
            f"груп у чернетці {len(groups)}",
        ]

    # ── черга результатів з потоків ───────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()

                if kind == "status":
                    self.status.configure(text=payload)
                    self._log(payload)

                elif kind == "chrome":
                    self._set_busy(False, payload)
                    self._refresh_chrome_label()

                elif kind == "models":
                    if payload:
                        self.cb_model.configure(values=[AUTO_MODEL] + payload)
                        self.cfg["models"] = payload
                        if self.cb_model.get() not in [AUTO_MODEL] + payload:
                            self.cb_model.set(AUTO_MODEL)
                        self._persist()
                    self._set_busy(False, f"Доступно моделей: {len(payload)}")

                elif kind == "draft":
                    draft, errors, warnings, folder = payload
                    # Звіряємо з попереднім раундом: якщо модель просто
                    # обрізала рядок, це видно одразу і йде в наступний запит.
                    new_texts = all_ad_texts(draft.get("ad_groups"))
                    cut = find_truncations(getattr(self, "prev_texts", []), new_texts)
                    self.truncated = cut
                    for old, new in cut:
                        self._log(f"Обрізано, а не переписано: «{new}» "
                                  f"замість «{old}»", "danger")
                    self.prev_texts = new_texts
                    self.draft = draft
                    self._set_text(self.t_table, render_table(draft))
                    self.busy = False
                    self._render_check(errors, warnings)
                    rnd = getattr(self, "round", 1)
                    # Якщо чернетка з черги — оновлюємо її в буфері, щоб
                    # результат регенерації не загубився при перемиканні рядків.
                    ref = getattr(self, "batch_ref", None)
                    if ref and ref[0].winfo_exists() and ref[1] < len(ref[0].rows):
                        row = ref[0].rows[ref[1]]
                        # Стан рядка мусить лишитись таким самим, як після
                        # проходу черги: інакше «Зберегти всі чисті» цей
                        # рядок не побачить, а наступне доопрацювання
                        # піде без сирої відповіді й без обрубків.
                        row.update(
                            {"draft": draft, "errors": errors,
                             "warnings": warnings, "round": rnd,
                             "raw": getattr(self, "last_raw", row.get("raw", "")),
                             "chat": getattr(self, "chat_url", "")
                                     or row.get("chat", ""),
                             "texts": new_texts, "truncated": cut,
                             "seen": sorted(set(row.get("seen") or [])
                                            | set(errors)),
                             "repair": False,
                             "status": "потрібна увага" if errors else "чисто"})
                        ref[0]._refresh()
                    self._log(f"Раунд {rnd}: помилок {len(errors)}, "
                              f"попереджень {len(warnings)}.",
                              "danger" if errors else "success")
                    if folder:
                        self._log(f"Журнал: {os.path.basename(folder)}")
                    if errors:
                        self.nb.select(1)
                        self._set_busy(
                            False,
                            f"Помилок: {len(errors)}. Критичні — «Регенерувати», "
                            f"некритичні — галочки на «Перевірці» і CSV.")
                    else:
                        self.nb.select(0)
                        self._set_busy(
                            False,
                            f"Чернетка готова, помилок немає. "
                            f"Попереджень: {len(warnings)}.")

                elif kind == "many_one":
                    i, total, name, errs, rounds = payload
                    tail = (f"раундів {rounds}" if rounds > 1 else "з першого разу")
                    if errs:
                        self._log(f"Кампанія {i} з {total}: «{name}» — "
                                  f"помилок {len(errs)}, {tail}", "danger")
                        for x in errs[:3]:
                            self._log(f"   {x[:110]}", "danger")
                    else:
                        self._log(f"Кампанія {i} з {total}: «{name}» — чисто, "
                                  f"{tail}", "success")

                elif kind == "many_done":
                    self.many = payload
                    clean = [d for d in payload if not d["errors"]]
                    self.busy = False
                    # Поточною робимо першу кампанію, щоб було що дивитись.
                    if payload:
                        first = clean[0] if clean else payload[0]
                        self.draft = first["draft"]
                        self._set_text(self.t_table, render_table(self.draft))
                        self._render_check(first["errors"], first["warnings"])
                    self._set_busy(False, f"Готово: {len(clean)} чистих із "
                                          f"{len(payload)}. Тисни «Створити CSV» "
                                          f"— усі чисті ляжуть в один файл.")
                    self._log(f"Усього кампаній {len(payload)}, чистих {len(clean)}.",
                              "success" if len(clean) == len(payload) else "warning")

                elif kind == "batch_status":
                    i, state = payload
                    win = getattr(self, "_batch_window", None)
                    if win and win.winfo_exists() and i < len(win.rows):
                        win.rows[i]["status"] = state
                        win._refresh()
                        self._log(f"Черга {i + 1}: {state} "
                                  f"{domain_short(win.rows[i]['url'])}")

                elif kind == "batch_done":
                    (i, draft, errors, warnings, raw, variant, user_text,
                     folder, wants, cut, chat, rounds, seen, texts,
                     trunc) = payload
                    win = getattr(self, "_batch_window", None)
                    if win and win.winfo_exists() and i < len(win.rows):
                        win.rows[i].update({
                            "draft": draft, "errors": errors,
                            "warnings": warnings, "raw": raw,
                            "variant": variant, "user_text": user_text,
                            "folder": folder, "wants": wants,
                            "chat": chat, "texts": texts, "truncated": trunc,
                            "seen": seen, "repair": False, "round": rounds,
                            "status": "потрібна увага" if errors else "чисто"})
                        win._refresh()
                        for old, new in trunc:
                            self._log(f"   черга {i + 1}: обрізано, а не "
                                      f"переписано: «{new}» замість «{old}»",
                                      "danger")
                    tail = (f"раундів {rounds}" if rounds > 1 else "з першого разу")
                    if errors:
                        self._log(f"Черга {i + 1}: потрібна увага, {tail}, "
                                  f"помилок {len(errors)}, "
                                  f"попереджень {len(warnings)}", "danger")
                    else:
                        self._log(f"Черга {i + 1}: чисто, {tail}, "
                                  f"попереджень {len(warnings)} — чекає "
                                  f"схвалення", "success")
                    for chunk in cut:
                        self._log(f"   вирізано з опису: {chunk[:80]}", "warning")

                elif kind == "batch_fail":
                    i, text, raw = payload
                    win = getattr(self, "_batch_window", None)
                    if win and win.winfo_exists() and i < len(win.rows):
                        win.rows[i].update({"status": "збій", "raw": raw})
                        win._refresh()
                    self._log(f"Черга {i + 1}: збій — {text.splitlines()[0]}",
                              "danger")

                elif kind == "batch_end":
                    win = getattr(self, "_batch_window", None)
                    done, need = 0, []
                    if win and win.winfo_exists():
                        win.running = False
                        win.btn_run.configure(state="normal")
                        self._paint(win.btn_run, True, AURORA[0])
                        win.btn_stop.configure(state="disabled")
                        left = sum(1 for r in win.rows if r["status"] == "очікує")
                        done = sum(1 for r in win.rows if r["status"] == "чисто")
                        need = [n for n, r in enumerate(win.rows)
                                if r["status"] == "потрібна увага"]
                        # Підсвічуємо перший рядок, який справді чекає розбору;
                        # чисті достатньо переглянути й забрати однією кнопкою.
                        first = need[0] if need else next(
                            (n for n, r in enumerate(win.rows)
                             if r["status"] == "чисто"), None)
                        if first is not None:
                            win.select(first)
                        tail = (f" Потрібна увага: {len(need)} — обери рядок і "
                                f"тисни «Перейти до перегляду»."
                                if need else "")
                        win.status.configure(
                            text=f"Готово. Чистих: {done} — перевір і тисни "
                                 f"«Зберегти всі чисті»." + tail
                                 + (f" Не оброблено: {left}." if left else ""))
                        win._on_pick()
                    self._log(f"Черга завершена: чистих {done}, "
                              f"потребують уваги {len(need)}.",
                              "warning" if need else "success")

                elif kind == "error":
                    self._set_busy(False, "Помилка.")
                    self._log(payload.split("\n")[0], "danger")
                    self._refresh_chrome_label()
                    messagebox.showerror("Помилка", payload)
        except queue.Empty:
            pass

        # Раз на ~4 секунди звіряємо, чи живе вікно Gemini.
        self._tick += 1
        if self._tick % 33 == 0 and not self.busy:
            self._refresh_chrome_label()

        self.root.after(120, self._poll)

    def _render_check(self, errors, warnings):
        for child in self.check_body.winfo_children():
            child.destroy()
        self.overrides = []

        if errors:
            ttk.Label(self.check_body, foreground=SEMANTIC["danger"],
                      font=("Segoe UI", 10, "bold"),
                      text=f"ПОМИЛКИ ({len(errors)}) — блокують CSV, поки не "
                           f"виправиш або не візьмеш на себе").pack(anchor="w", pady=(8, 2))
            for e in errors:
                row = ttk.Frame(self.check_body)
                row.pack(fill="x", anchor="w", padx=10)
                var = tk.BooleanVar(value=False)
                var.trace_add("write", lambda *_: self._refresh_csv_button())
                ttk.Checkbutton(row, variable=var).pack(side="left", anchor="n")
                ttk.Label(row, text=e, foreground=SEMANTIC["danger"], wraplength=820,
                          justify="left").pack(side="left", anchor="w")
                self.overrides.append(var)
            ttk.Label(self.check_body, foreground=self.theme["muted"], wraplength=860,
                      justify="left",
                      text="Галочка означає: перевірив сам, це хибне спрацювання. "
                           "Google все одно може відхилити такий рядок.")\
                .pack(anchor="w", padx=10, pady=(4, 10))

        if warnings:
            ttk.Label(self.check_body, foreground=SEMANTIC["warning"],
                      font=("Segoe UI", 10, "bold"),
                      text=f"ПОПЕРЕДЖЕННЯ ({len(warnings)}) — файл створиться")\
                .pack(anchor="w", pady=(8, 2))
            for w in warnings:
                ttk.Label(self.check_body, text="• " + w, foreground=SEMANTIC["warning"],
                          wraplength=860, justify="left").pack(anchor="w", padx=10)

        if not errors and not warnings:
            ttk.Label(self.check_body, foreground=SEMANTIC["success"],
                      text="Перевірки пройдено, зауважень немає.")\
                .pack(anchor="w", pady=10, padx=10)
        self._refresh_csv_button()

    def _refresh_csv_button(self):
        """CSV дозволено, коли всі помилки або зникли, або взяті на себе."""
        if not self.draft or self.busy:
            return
        blocked = any(not v.get() for v in self.overrides)
        self.btn_csv.configure(state="disabled" if blocked else "normal")
        self._paint(self.btn_csv, not blocked, AURORA[2])


def render_ads(groups):
    out = []
    for g in groups:
        ads = g.get("ads") or []
        out.append("═" * 66)
        out.append(f"ГРУПА: {g.get('name', '')}   (оголошень {len(ads)})")
        out.append("═" * 66)
        for i, ad in enumerate(ads, 1):
            out.append(f"── Оголошення {i} " + "─" * 46)
            out.append("Заголовки:")
            for j, h in enumerate(ad.get("headlines") or [], 1):
                out.append(f"  {j:>2}. {h}".ljust(46) +
                           f"[{effective_len(h)}/{LIMIT_HEADLINE}]")
            out.append("")
            out.append("Описи:")
            for j, d in enumerate(ad.get("descriptions") or [], 1):
                out.append(f"  {j:>2}. {d}")
                out.append(" " * 6 + f"[{effective_len(d)}/{LIMIT_DESC}]")
            out.append("")
    return "\n".join(out)


class BatchWindow(tk.Toplevel):
    """Черга сайтів: заводимо список, генеруємо все підряд, потім розбираємо.

    Чернетки живуть у буфері до збереження CSV. Той, що не сподобався,
    перегенеровується поштучно — буфер тримає і запит, і сиру відповідь,
    тож є що надіслати моделі назад.
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.rows = []            # {url, desc, draft, errors, warnings, raw,
                                  #  variant, user_text, status, folder}
        self.running = False
        self.stop_flag = False

        self.title("Масовий запуск")
        # Висота з запасом на заготовку: інакше нижні кнопки («Згенерувати
        # всі», «Зберегти всі чисті») з'їжджають за край екрана.
        self.geometry("1000x880")
        self.minsize(900, 720)
        # НЕ transient: таке вікно Windows тримає поверх головного, і чернетка,
        # яку ми туди відкриваємо, лишається за спиною. Хай будуть незалежні.
        self.option_add("*Font", ("Segoe UI", 10))
        self.theme = app.theme
        self.configure(bg=self.theme["bg"])

        self._build()
        self._load_buffer()
        self.after(150, self._poll)

    # ── інтерфейс ─────────────────────────────────────────────────────────────
    def _build(self):
        # Дві вкладки, бо це два різні заняття: спершу складаєш перелік
        # профілів і сайтів, потім дописуєш описи й аж тоді запускаєш.
        # В одному стовпчику це не вміщалось і плуталось.
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(12, 0))
        stage = ttk.Frame(self.tabs, padding=(10, 10, 10, 6))
        queue = ttk.Frame(self.tabs, padding=(10, 10, 10, 6))
        self.tabs.add(stage, text="  Заготовка  ")
        self.tabs.add(queue, text="  Черга  ")
        self._build_stage(stage)
        self._build_queue(queue)
        self._build_bottom()

    # ── вкладка «Заготовка»: таблиця на три колонки ──────────────────────────
    # Раніше тут були два поля для вставки, список рядків із кнопкою «Опис»
    # і окремий редактор опису. Набивати сотню акаунтів так було довго:
    # профілі в одне поле, сайти в інше, описи по одному. Тепер це одна
    # таблиця, як в Excel: клітинки правляться на місці, блок з Excel чи
    # Google Таблиць вставляється одним Ctrl+V.
    TABLE_COLS = ("ident", "url", "desc")
    TABLE_HEAD = {"ident": "Профіль", "url": "Сайт", "desc": "Опис"}
    TABLE_MIN = 100

    def _build_stage(self, root):
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        t = self.theme

        bar = ttk.Frame(root)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="З файлу", command=self._on_stage_file)\
            .pack(side="left")
        ttk.Button(bar, text="Видалити рядки",
                   command=self._on_table_delete_rows).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Очистити таблицю",
                   command=self._on_table_clear).pack(side="left", padx=(8, 0))
        self.lbl_table = ttk.Label(bar, foreground=t["muted"])
        self.lbl_table.pack(side="right")

        # Таблиця намальована на Canvas, бо ttk.Treeview не вміє вертикальних
        # ліній між колонками — а без них це не таблиця, а список. Тут —
        # справжня сітка: лінії в усі боки, ширину колонки видно тягнути.
        self.tbl_rows = []          # [[профіль, сайт, опис], ...] — джерело правди
        self.tbl_sel = set()        # індекси виділених рядків
        self.tbl_cur = (0, 0)       # (рядок, колонка) — поточна клітинка
        self.tbl_anchor = 0         # від кого рахувати Shift-діапазон
        self.tbl_editor = None
        self.col_keys = ("n",) + self.TABLE_COLS
        self.col_w = {"n": 48, "ident": 220, "url": 210, "desc": 440}
        self.ROW_H = 28
        self.HDR_H = 30

        box = ttk.Frame(root)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.hdr = tk.Canvas(box, height=self.HDR_H, highlightthickness=0,
                             bg=t["surface2"])
        self.hdr.grid(row=0, column=0, sticky="ew")
        self.cv = tk.Canvas(box, highlightthickness=1, bg=t["field"],
                            highlightbackground=t["line"], takefocus=1)
        self.cv.grid(row=1, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(box, orient="vertical", command=self.cv.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self.cv.configure(yscrollcommand=vsb.set)
        self.hdr.configure(xscrollcommand=lambda *a: None)

        self.cv.bind("<Button-1>", self._grid_click)
        self.cv.bind("<Shift-Button-1>", lambda e: self._grid_click(e, "shift"))
        self.cv.bind("<Control-Button-1>", lambda e: self._grid_click(e, "ctrl"))
        self.cv.bind("<Double-1>", self._grid_double)
        self.cv.bind("<Return>", lambda e: self._grid_edit_cur())
        self.cv.bind("<F2>", lambda e: self._grid_edit_cur())
        self.cv.bind("<Delete>", self._tbl_clear_rows)
        self.cv.bind("<Up>", lambda e: self._grid_move(-1, 0))
        self.cv.bind("<Down>", lambda e: self._grid_move(1, 0))
        self.cv.bind("<Left>", lambda e: self._grid_move(0, -1))
        self.cv.bind("<Right>", lambda e: self._grid_move(0, 1))
        self.cv.bind("<Control-KeyPress>", self._tbl_ctrl)
        self.cv.bind("<Key>", self._tbl_type)
        self.cv.bind("<MouseWheel>", self._grid_wheel)
        self.cv.bind("<Configure>", lambda e: self._grid_fit())
        # Шапка: перетягування меж колонок міняє ширину.
        self.hdr.bind("<Motion>", self._hdr_motion)
        self.hdr.bind("<Button-1>", self._hdr_press)
        self.hdr.bind("<B1-Motion>", self._hdr_drag)
        self.hdr.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_col", None))
        self._drag_col = None

        fill = ttk.Frame(root)
        fill.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        fill.columnconfigure(2, weight=1)
        ttk.Label(fill, text="Виділеним рядкам:").grid(row=0, column=0, sticky="w")
        self.cb_fill = ttk.Combobox(
            fill, state="readonly", width=10,
            values=[self.TABLE_HEAD[c] for c in self.TABLE_COLS])
        self.cb_fill.set(self.TABLE_HEAD["desc"])
        self.cb_fill.grid(row=0, column=1, padx=(8, 8))
        self.e_fill = ttk.Entry(fill)
        self.e_fill.grid(row=0, column=2, sticky="ew")
        self.e_fill.bind("<Return>", lambda e: self._on_table_fill())
        ttk.Button(fill, text="Заповнити", command=self._on_table_fill)\
            .grid(row=0, column=3, padx=(8, 0))
        enable_clipboard(self.e_fill)

        ttk.Label(root, foreground=t["muted"], justify="left", wraplength=940,
                  text=("Подвійний клік, Enter або просто почни друкувати — "
                        "правиш клітинку. Enter — нижче, Tab — праворуч. "
                        "Ctrl+V — вставити блок з Excel чи Google Таблиць, "
                        "Ctrl+C — скопіювати виділені рядки. Shift/Ctrl+клік — "
                        "кілька рядків, Delete — очистити їх. Ширину колонки "
                        "тягни за межу в шапці. У чергу підуть рядки, де "
                        "заповнено всі три колонки."))\
            .grid(row=3, column=0, sticky="w", pady=(8, 0))

        foot = ttk.Frame(root)
        foot.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.st_status = ttk.Label(foot, text="", anchor="w",
                                   foreground=t["muted"])
        self.st_status.pack(side="left", fill="x", expand=True)
        self.btn_to_queue = ttk.Button(foot, text="Додати в чергу",
                                       command=self._on_to_queue)
        self.btn_to_queue.pack(side="right")
        self._table_set([])

    def _build_queue(self, root):
        head = ttk.Frame(root)
        head.pack(fill="x")
        ttk.Label(head, text="Черга", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(head, text="Позначити всі", width=15,
                   command=lambda: self._mark_all(True)).pack(side="left", padx=(10, 4))
        ttk.Button(head, text="Зняти позначки", width=16,
                   command=lambda: self._mark_all(False)).pack(side="left")

        acts = ttk.Frame(root)
        acts.pack(fill="x", pady=(8, 0))
        ttk.Button(acts, text="Перегенерувати вибрані",
                   command=lambda: self._on_regen_marked(False))\
            .pack(side="left")
        ttk.Button(acts, text="Перегенерувати з коментарем",
                   command=lambda: self._on_regen_marked(True))\
            .pack(side="left", padx=(8, 0))
        ttk.Button(acts, text="Видалити вибрані", command=self._on_delete)\
            .pack(side="left", padx=(8, 0))
        ttk.Button(acts, text="У архів", command=self._on_archive)\
            .pack(side="left", padx=(8, 0))
        ttk.Button(acts, text="Очистити чергу", command=self._on_clear)\
            .pack(side="left", padx=(8, 0))

        box = ttk.Frame(root, padding=(0, 6, 0, 0))
        box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(box, highlightthickness=1, bg=self.theme["surface"],
                                highlightbackground=self.theme["line"])
        sb = ttk.Scrollbar(box, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.body.bind("<Configure>",
                       lambda e: self.canvas.configure(
                           scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(
                                 int(-e.delta / 120), "units"))
        self.checks = []          # BooleanVar на кожен рядок
        self.current = -1         # рядок, відкритий у головному вікні

    # ── нижня смуга: лишається на видноті за будь-якої вкладки ────────────────
    def _build_bottom(self):
        bottom = ttk.Frame(self, padding=(14, 6, 14, 6))
        bottom.pack(fill="x")
        t = self.theme
        self.btn_run = tk.Button(bottom, text="Згенерувати всі",
                                 command=self._on_run, height=2,
                                 bg=AURORA[0], fg="#ffffff",
                                 activebackground=AURORA[1],
                                 activeforeground="#ffffff",
                                 disabledforeground=t["muted"],
                                 font=("Segoe UI", 10, "bold"),
                                 relief="flat", bd=0, cursor="hand2")
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_open = tk.Button(bottom, text="Перейти до перегляду",
                                  command=self._on_open, height=2,
                                  state="disabled", bg=AURORA[2], fg="#ffffff",
                                  activebackground=AURORA[1],
                                  activeforeground="#ffffff",
                                  disabledforeground=t["muted"],
                                  font=("Segoe UI", 10, "bold"),
                                  relief="flat", bd=0, cursor="hand2")
        self.btn_open.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.app._paint(self.btn_open, False, AURORA[2])
        # Файли забирає людина, а не черга: рішення про завантаження в кабінет
        # лишається за нею. Кнопка забирає все чисте одним рухом.
        self.btn_save = tk.Button(bottom, text="Зберегти всі чисті",
                                  command=self._on_save_clean, height=2,
                                  state="disabled", bg=SEMANTIC["success"],
                                  fg="#ffffff", activeforeground="#ffffff",
                                  disabledforeground=t["muted"],
                                  font=("Segoe UI", 10, "bold"),
                                  relief="flat", bd=0, cursor="hand2")
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.app._paint(self.btn_save, False, SEMANTIC["success"])
        self.btn_stop = tk.Button(bottom, text="Зупинити", command=self._on_stop,
                                  height=2, state="disabled",
                                  bg=t["surface2"], fg=t["ink"],
                                  activebackground=t["surface"],
                                  disabledforeground=t["muted"],
                                  relief="flat", bd=0, cursor="hand2")
        self.btn_stop.pack(side="left", padx=(6, 0))

        self.status = ttk.Label(self, text="Черга порожня.", anchor="w",
                                padding=(14, 0, 14, 10))
        self.status.pack(fill="x")

    # ── черга ─────────────────────────────────────────────────────────────────
    def _new_row(self, ident, url, desc):
        if url and not url.startswith("http"):
            url = "https://" + url
        return {"ident": ident, "url": url, "desc": desc, "status": "очікує",
                "draft": None, "errors": [], "warnings": [], "raw": "",
                "variant": None, "user_text": "", "folder": "", "round": 1,
                # chat — адреса розмови Gemini саме цього рядка: за нею
                # доопрацювання повертається туди, де лежить його чернетка.
                "chat": "", "seen": [], "texts": [], "truncated": [],
                "repair": False}

    # ── заготовка: дані таблиці ───────────────────────────────────────────────
    # Таблиця живе ОКРЕМО від черги, у своєму файлі. Причина: черга пише
    # стани в рядки за їхнім номером у self.rows. Якби таблиця перебудовувала
    # той самий список, поки черга працює, номери зсувались би, і стан
    # «чисто» одного акаунта лягав би на інший.
    STAGE = "заготовка"

    # ── Canvas-таблиця: геометрія ─────────────────────────────────────────────
    def _col_x(self):
        """X-межі колонок: [0, 48, 268, 478, 918]."""
        x, out = 0, [0]
        for c in self.col_keys:
            x += self.col_w[c]
            out.append(x)
        return out

    def _total_w(self):
        return sum(self.col_w[c] for c in self.col_keys)

    def _grid_fit(self):
        """Остання колонка — резинова: тягнеться до правого краю, щоб не
        лишалося порожнечі й не було зайвого горизонтального скролу."""
        vis = self.cv.winfo_width()
        fixed = sum(self.col_w[c] for c in self.col_keys[:-1])
        self.col_w["desc"] = max(260, vis - fixed - 4)
        self._grid_redraw()

    @staticmethod
    def _shown(text):
        return " ".join(str(text or "").split())

    def _fit_text(self, text, width):
        """Обрізає текст із «…», щоб не вилазив за лінію колонки."""
        text = self._shown(text)
        if not text:
            return ""
        f = tkfont.Font(font=("Segoe UI", 10))
        if f.measure(text) <= width:
            return text
        while text and f.measure(text + "…") > width:
            text = text[:-1]
        return text + "…" if text else ""

    # ── Canvas-таблиця: малювання ─────────────────────────────────────────────
    def _grid_redraw(self):
        if not hasattr(self, "cv"):
            return
        t = self.theme
        self.cv.delete("all")
        self.hdr.delete("all")
        xs = self._col_x()
        W = xs[-1]
        n = len(self.tbl_rows)
        H = self.HDR_H  # для scrollregion шапки неважливо
        body_h = n * self.ROW_H
        self.cv.configure(scrollregion=(0, 0, W, body_h))

        # ── шапка ──
        self.hdr.configure(scrollregion=(0, 0, W, self.HDR_H))
        self.hdr.create_rectangle(0, 0, W, self.HDR_H, fill=t["surface2"],
                                  outline=t["line"])
        for i, c in enumerate(self.col_keys):
            left, right = xs[i], xs[i + 1]
            self.hdr.create_line(right, 0, right, self.HDR_H, fill=t["line"])
            if c == "n":
                label = "№"
            else:
                mark = "▸ " if c == self.tbl_cur[1] + 1 == i or \
                    self.col_keys[self.tbl_cur[1] + 1] == c else ""
                label = mark + self.TABLE_HEAD[c]
            anchor = "e" if c == "n" else "w"
            tx = right - 8 if c == "n" else left + 8
            self.hdr.create_text(tx, self.HDR_H // 2, text=label, anchor=anchor,
                                 fill=t["ink"], font=("Segoe UI", 10, "bold"))

        # ── видима частина тіла ──
        top = self.cv.canvasy(0)
        bottom = top + self.cv.winfo_height()
        first = max(0, int(top // self.ROW_H) - 1)
        last = min(n, int(bottom // self.ROW_H) + 2)
        for r in range(first, last):
            y = r * self.ROW_H
            row = self.tbl_rows[r]
            selected = r in self.tbl_sel
            if selected:
                bg = AURORA[0]
            else:
                bg = t["surface"] if r % 2 else t["field"]
            self.cv.create_rectangle(0, y, W, y + self.ROW_H, fill=bg,
                                     outline="")
            fg = "#ffffff" if selected else (
                t["field_ink"] if all(row) else
                SEMANTIC["warning"] if any(row) else t["muted"])
            # № колонка
            self.cv.create_text(xs[1] - 8, y + self.ROW_H // 2, text=str(r + 1),
                                anchor="e", fill="#ffffff" if selected
                                else t["muted"], font=("Segoe UI", 9))
            for ci, c in enumerate(self.TABLE_COLS):
                left = xs[ci + 1]
                cw = self.col_w[c] - 12
                val = self._fit_text(row[ci], cw)
                if val:
                    self.cv.create_text(left + 6, y + self.ROW_H // 2, text=val,
                                        anchor="w", fill=fg,
                                        font=("Segoe UI", 10))
            # горизонтальна лінія під рядком
            self.cv.create_line(0, y + self.ROW_H, W, y + self.ROW_H,
                                fill=t["line"])
        # вертикальні лінії сітки
        for x in xs:
            self.cv.create_line(x, top, x, min(bottom, body_h), fill=t["line"])
        # рамка поточної клітинки
        cr, cc = self.tbl_cur
        if 0 <= cr < n:
            left, right = xs[cc + 1], xs[cc + 2]
            y = cr * self.ROW_H
            self.cv.create_rectangle(left + 1, y + 1, right - 1,
                                     y + self.ROW_H - 1, outline=AURORA[1],
                                     width=2)

    def _grid_seerow(self, r):
        """Прокручує так, щоб рядок r був видимий."""
        n = max(1, len(self.tbl_rows))
        top = self.cv.canvasy(0)
        h = self.cv.winfo_height()
        y = r * self.ROW_H
        if y < top:
            self.cv.yview_moveto(y / (n * self.ROW_H))
        elif y + self.ROW_H > top + h:
            self.cv.yview_moveto((y + self.ROW_H - h) / (n * self.ROW_H))

    def _grid_wheel(self, event):
        self._tbl_commit()
        self.cv.yview_scroll(int(-event.delta / 120), "units")
        self._grid_redraw()

    # ── Canvas-таблиця: сумісність зі старим кодом і тестами ──────────────────
    def _tbl_order(self):
        return list(range(len(self.tbl_rows)))

    def _tbl_get(self, r):
        if 0 <= r < len(self.tbl_rows):
            return list(self.tbl_rows[r])
        return ["", "", ""]

    def _tbl_put(self, r, col, value):
        if 0 <= r < len(self.tbl_rows):
            self.tbl_rows[r][self.TABLE_COLS.index(col)] = str(value or "").strip()

    def _grid_selected(self):
        return sorted(i for i in self.tbl_sel if 0 <= i < len(self.tbl_rows))

    def _grid_select(self, rows, anchor=None):
        self.tbl_sel = set(r for r in rows if 0 <= r < len(self.tbl_rows))
        if anchor is not None:
            self.tbl_anchor = anchor
        self._grid_redraw()
        self._table_counts()

    def _tbl_ensure(self, count):
        while len(self.tbl_rows) < count:
            self.tbl_rows.append(["", "", ""])

    def _table_set(self, data):
        self._tbl_commit()
        self.tbl_rows = [[str(x or "").strip() for x in (list(r) + ["", "", ""])[:3]]
                         for r in (data or [])]
        self._tbl_ensure(max(self.TABLE_MIN, len(self.tbl_rows) + 20))
        self.tbl_sel = set()
        self.tbl_cur = (0, 0)
        self._grid_redraw()
        self._table_counts()

    def _table_data(self):
        rows = [list(r) for r in self.tbl_rows]
        while rows and not any(rows[-1]):
            rows.pop()
        return rows

    def _table_path(self):
        return os.path.splitext(BATCH_FILE)[0] + "_table.json"

    def _table_save(self):
        try:
            with open(self._table_path(), "w", encoding="utf-8") as f:
                json.dump(self._table_data(), f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _table_load(self):
        data = []
        try:
            if os.path.exists(self._table_path()):
                with open(self._table_path(), "r", encoding="utf-8") as f:
                    data = json.load(f) or []
        except Exception:
            data = []
        old = [r for r in self.rows if r.get("status") == self.STAGE]
        if old:
            data = list(data) + [[r.get("ident", ""), r.get("url", ""),
                                  r.get("desc", "")] for r in old]
            self.rows = [r for r in self.rows if r.get("status") != self.STAGE]
            self._save_buffer()
        self._table_set(data)
        if old:
            self._table_save()
        self._refresh()

    def _table_changed(self):
        self._tbl_ensure(max(self.TABLE_MIN, len(self._table_data()) + 20))
        self._table_save()
        self._grid_redraw()
        self._table_counts()

    def _stage_rows(self):
        return [i for i, r in enumerate(self.rows) if r["status"] == self.STAGE]

    # ── Canvas-таблиця: миша й клавіші ────────────────────────────────────────
    def _grid_hit(self, event):
        """(рядок, колонка-даних) під курсором, або (-1, 0)."""
        x = self.cv.canvasx(event.x)
        y = self.cv.canvasy(event.y)
        r = int(y // self.ROW_H)
        if not (0 <= r < len(self.tbl_rows)):
            return -1, 0
        xs = self._col_x()
        for ci in range(len(self.TABLE_COLS)):
            if xs[ci + 1] <= x < xs[ci + 2]:
                return r, ci
        return r, 0

    def _grid_click(self, event, mode=None):
        self._tbl_commit()
        self.cv.focus_set()
        r, c = self._grid_hit(event)
        if r < 0:
            return "break"
        self.tbl_cur = (r, c)
        if mode == "shift":
            lo, hi = sorted((self.tbl_anchor, r))
            self.tbl_sel = set(range(lo, hi + 1))
        elif mode == "ctrl":
            self.tbl_sel ^= {r}
            self.tbl_anchor = r
        else:
            self.tbl_sel = {r}
            self.tbl_anchor = r
        self._grid_redraw()
        self._table_counts()
        return "break"

    def _grid_double(self, event):
        r, c = self._grid_hit(event)
        if r >= 0:
            self.tbl_cur = (r, c)
            self._grid_edit(r, c)
        return "break"

    def _grid_edit_cur(self):
        r, c = self.tbl_cur
        self._grid_edit(r, c)
        return "break"

    def _grid_move(self, dr, dc):
        if self.tbl_editor:
            return None
        r = max(0, min(len(self.tbl_rows) - 1, self.tbl_cur[0] + dr))
        c = max(0, min(len(self.TABLE_COLS) - 1, self.tbl_cur[1] + dc))
        self.tbl_cur = (r, c)
        self.tbl_sel = {r}
        self.tbl_anchor = r
        self._grid_seerow(r)
        self._grid_redraw()
        return "break"

    def _tbl_type(self, event):
        if self.tbl_editor or (event.state & 0x4):
            return None
        ch = event.char
        if ch and ch.isprintable():
            r, c = self.tbl_cur
            self._grid_edit(r, c, initial=ch)
            return "break"
        return None

    def _grid_edit(self, r, c, initial=None):
        self._tbl_commit()
        if not (0 <= r < len(self.tbl_rows)):
            return
        self._grid_seerow(r)
        self.cv.update_idletasks()
        xs = self._col_x()
        x = xs[c + 1] - self.cv.canvasx(0)
        y = r * self.ROW_H - self.cv.canvasy(0)
        w = self.col_w[self.TABLE_COLS[c]]
        ed = ttk.Entry(self.cv)
        if initial is None:
            ed.insert(0, self.tbl_rows[r][c])
            ed.select_range(0, "end")
        else:
            ed.insert(0, initial)
            ed.icursor("end")
        ed.place(x=x, y=y, width=w, height=self.ROW_H)
        ed.focus_set()
        enable_clipboard(ed)
        self.tbl_editor = (ed, r, c)
        self.tbl_cur = (r, c)
        ed.bind("<Return>", lambda e: self._tbl_commit(move="down"))
        ed.bind("<Tab>", lambda e: self._tbl_commit(move="right"))
        ed.bind("<Escape>", lambda e: self._tbl_cancel())
        ed.bind("<FocusOut>", lambda e: self._tbl_commit())

    def _tbl_cancel(self):
        if self.tbl_editor:
            ed = self.tbl_editor[0]
            self.tbl_editor = None
            ed.destroy()
            self.cv.focus_set()
        return "break"

    def _tbl_commit(self, move=None):
        if not getattr(self, "tbl_editor", None):
            return "break"
        ed, r, c = self.tbl_editor
        self.tbl_editor = None
        value = ed.get()
        ed.destroy()
        if 0 <= r < len(self.tbl_rows):
            self.tbl_rows[r][c] = value.strip()
            self._table_changed()
        if move == "down":
            nr = min(r + 1, len(self.tbl_rows) - 1)
            self.tbl_cur = (nr, c)
            self.tbl_sel = {nr}
            self._grid_seerow(nr)
            self._grid_redraw()
        elif move == "right":
            if c + 1 < len(self.TABLE_COLS):
                nr, nc = r, c + 1
            else:
                nr, nc = min(r + 1, len(self.tbl_rows) - 1), 0
            self.tbl_cur = (nr, nc)
            self._grid_seerow(nr)
            self.after_idle(lambda: self._grid_edit(nr, nc))
        else:
            self.cv.focus_set()
        return "break"

    # ── Canvas-таблиця: зміна ширини колонок ──────────────────────────────────
    def _hdr_edge(self, x):
        """Номер колонки, чию ПРАВУ межу схопили (у межах 4 пікселів)."""
        for i, bx in enumerate(self._col_x()[1:]):
            if abs(x - bx) <= 4:
                return i
        return None

    def _hdr_motion(self, event):
        self.hdr.configure(cursor="sb_h_double_arrow"
                           if self._hdr_edge(event.x) is not None else "")

    def _hdr_press(self, event):
        self._drag_col = self._hdr_edge(event.x)

    def _hdr_drag(self, event):
        if self._drag_col is None:
            return
        key = self.col_keys[self._drag_col]
        left = self._col_x()[self._drag_col]
        self.col_w[key] = max(40, int(event.x) - left)
        self._grid_redraw()

    # ── Canvas-таблиця: буфер обміну й групові дії ────────────────────────────
    def _tbl_ctrl(self, event):
        code = event.keycode
        if code == 86:
            self._tbl_paste()
        elif code == 67:
            self._tbl_copy()
        elif code == 65:
            self._grid_select(range(len(self.tbl_rows)))
        else:
            return None
        return "break"

    def _tbl_paste(self):
        self._tbl_commit()
        try:
            raw = self.clipboard_get()
        except Exception:
            return
        grid = [r for r in csv.reader(raw.splitlines(True), delimiter="\t")]
        while grid and not any(c.strip() for c in grid[-1]):
            grid.pop()
        if not grid:
            return
        r0, c0 = self.tbl_cur
        self._tbl_ensure(r0 + len(grid) + 20)
        cells = 0
        for dr, line in enumerate(grid):
            for dc, value in enumerate(line):
                if c0 + dc < len(self.TABLE_COLS):
                    self.tbl_rows[r0 + dr][c0 + dc] = str(value or "").strip()
                    cells += 1
        self._grid_select(range(r0, r0 + len(grid)), anchor=r0)
        self._table_changed()
        self._stage_say(f"Вставлено рядків: {len(grid)}, клітинок: {cells}.")

    def _tbl_copy(self):
        sel = self._grid_selected()
        if not sel:
            return
        text = "\n".join("\t".join(self.tbl_rows[i]) for i in sel)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._stage_say(f"Скопійовано рядків: {len(sel)}.")

    def _tbl_clear_rows(self, event=None):
        sel = self._grid_selected()
        if not sel:
            return "break"
        for i in sel:
            self.tbl_rows[i] = ["", "", ""]
        self._table_changed()
        self._stage_say(f"Очищено рядків: {len(sel)}.")
        return "break"

    def _on_table_delete_rows(self):
        sel = set(self._grid_selected())
        if not sel:
            messagebox.showinfo("Нічого не виділено",
                                "Виділи рядки, які треба прибрати.", parent=self)
            return
        keep = [self.tbl_rows[i] for i in range(len(self.tbl_rows)) if i not in sel]
        self._table_set(keep)
        self._table_save()
        self._stage_say(f"Прибрано рядків: {len(sel)}. Решта підтягнулась угору.")

    def _on_table_clear(self):
        if not self._table_data():
            return
        if not messagebox.askyesno("Очистити таблицю",
                                   "Прибрати все з таблиці? Черги це не торкнеться.",
                                   parent=self):
            return
        self._table_set([])
        self._table_save()
        self._stage_say("Таблиця порожня.")

    def _on_table_fill(self):
        self._tbl_commit()
        names = {self.TABLE_HEAD[c]: c for c in self.TABLE_COLS}
        col = names.get(self.cb_fill.get(), "desc")
        ci = self.TABLE_COLS.index(col)
        value = self.e_fill.get().strip()
        sel = self._grid_selected()
        if not sel:
            messagebox.showinfo(
                "Нічого не виділено",
                "Виділи рядки: клац по першому, Shift+клац по останньому. "
                "Ctrl+A — усі.", parent=self)
            return
        if not value:
            messagebox.showwarning("Порожньо", "Впиши, чим заповнити.", parent=self)
            return
        target = [i for i in sel if col == "ident" or self.tbl_rows[i][0]]
        if not target:
            messagebox.showinfo(
                "Немає профілів",
                "У виділених рядках немає профілів. Сайт і опис вписуються "
                "туди, де профіль уже є.", parent=self)
            return
        for i in target:
            self.tbl_rows[i][ci] = value
        self._table_changed()
        skipped = len(sel) - len(target)
        tail = f" Пропущено порожніх рядків: {skipped}." if skipped else ""
        self._stage_say(f"Колонка «{self.TABLE_HEAD[col]}» заповнена в "
                        f"{len(target)} рядках.{tail}")

    def _on_stage_file(self):
        path = filedialog.askopenfilename(
            title="Файл зі списком: профіль, сайт, опис",
            filetypes=[("Таблиці", "*.csv *.tsv *.txt"), ("Усі файли", "*.*")],
            parent=self)
        if not path:
            return
        rows, err = read_table(path)
        if err:
            messagebox.showerror("Не вдалося прочитати", err, parent=self)
            return
        rows = [(list(r) + ["", "", ""])[:3] for r in rows if any(r[:3])]
        if not rows:
            messagebox.showwarning("Порожньо", "У файлі немає рядків.", parent=self)
            return
        self._table_set(self._table_data() + rows)
        self._table_save()
        self._stage_say(f"З файлу взято рядків: {len(rows)}.")

    def _on_to_queue(self):
        self._tbl_commit()
        data = self._table_data()
        ready = [r for r in data if all(r)]
        rest = [r for r in data if any(r) and not all(r)]
        if not ready:
            messagebox.showwarning(
                "Нічого не готово",
                "Немає жодного повного рядка: потрібні профіль, сайт і опис.",
                parent=self)
            return
        for ident, url, desc in ready:
            self.rows.append(self._new_row(ident, url, desc))
        self._table_set(rest)
        self._table_save()
        self._refresh()
        tail = (f" У таблиці лишилось недороблених: {len(rest)} — допиши їм "
                f"те, чого бракує." if rest else "")
        self._stage_say(f"У чергу додано: {len(ready)}.{tail}")
        self.status.configure(text=f"У чергу додано рядків: {len(ready)}.{tail}")
        if not rest:
            self.tabs.select(1)

    def _stage_say(self, text):
        self.st_status.configure(text=text)

    def _refresh_stage(self):
        self._table_counts()

    def _table_counts(self):
        if not hasattr(self, "cv"):
            return
        data = self._table_data()
        full = sum(1 for r in data if all(r))
        part = sum(1 for r in data if any(r) and not all(r))
        sel = len(self._grid_selected())
        bits = [f"повних: {full}"]
        if part:
            bits.append(f"недороблених: {part}")
        if sel > 1:
            bits.append(f"виділено: {sel}")
        self.lbl_table.configure(text=" · ".join(bits))
        self.btn_to_queue.configure(
            text=f"Додати в чергу ({full})" if full else "Додати в чергу")
        filled = full + part
        self.tabs.tab(0, text=f"  Заготовка{f' ({filled})' if filled else ''}  ")
        n = len(self.rows) - len(self._stage_rows())
        self.tabs.tab(1, text=f"  Черга{f' ({n})' if n else ''}  ")

    def _marked(self):
        """Номери рядків черги з поставленою галочкою."""
        idx = getattr(self, "check_idx", [])
        return [idx[i] for i, v in enumerate(self.checks)
                if v.get() and i < len(idx)]

    def _mark_all(self, value):
        for v in self.checks:
            v.set(value)

    def select(self, index):
        """Робить рядок поточним — його відкриє «Перейти до перегляду»."""
        if 0 <= index < len(self.rows):
            self.current = index
            self._refresh()

    def _selected(self):
        return self.current

    def _on_delete(self):
        picked = sorted(self._marked(), reverse=True)
        if not picked:
            messagebox.showinfo("Нічого не позначено",
                                "Постав галочки навпроти рядків, які треба "
                                "прибрати.", parent=self)
            return
        for i in picked:
            if 0 <= i < len(self.rows):
                del self.rows[i]
        self.current = -1
        self._refresh()
        self.status.configure(text=f"Видалено рядків: {len(picked)}.")

    def _ask_hint(self, picked, repair, prev=""):
        """Вікно «що саме виправити» перед перегенерацією.

        Без нього єдиний спосіб щось пояснити моделі — поле нагорі
        головного вікна, одне на всю чергу. А пояснення зазвичай потрібне
        саме цьому рядку: «гео Франція, італійська тут це кухня».

        Повертає текст вказівок або None, якщо людина передумала.
        """
        win = tk.Toplevel(self)
        win.title("Що виправити")
        win.geometry("760x520")
        win.configure(bg=self.theme["bg"])
        win.transient(self)
        win.grab_set()
        t = self.theme
        box = ttk.Frame(win, padding=(14, 12, 14, 12))
        box.pack(fill="both", expand=True)

        ttk.Label(box, text=f"Рядків: {len(picked)}  ·  "
                            f"{'доопрацювання' if repair else 'з нуля'}",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")

        # Показуємо помилки рядка: людина має бачити, на що відповідає,
        # а не згадувати їх по пам'яті.
        errs = []
        for i in picked[:3]:
            r = self.rows[i]
            for e in (r.get("errors") or [])[:4]:
                errs.append(f"· {e}")
        if errs:
            ttk.Label(box, text="Що знайшла перевірка:",
                      foreground=t["muted"]).pack(anchor="w", pady=(10, 2))
            seen = tk.Text(box, height=7, wrap="word", padx=8, pady=6)
            self.app._skin_text(seen, "surface2")
            seen.insert("1.0", "\n".join(errs[:12]))
            seen.configure(state="disabled")
            seen.pack(fill="x")

        ttk.Label(box, text="Твої вказівки моделі:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 2))
        ttk.Label(box, foreground=t["muted"], justify="left",
                  text=("Пиши прямо, як людині: що саме не так і як треба. "
                        "Це піде в той самий чат разом зі списком помилок.\n"
                        "Напр.: «Гео — Франція, домен .fr. Італійська в описі "
                        "— це кухня, а не країна показу»."))\
            .pack(anchor="w", pady=(0, 4))
        hint = tk.Text(box, height=6, wrap="word", padx=8, pady=6)
        self.app._skin_text(hint, "field")
        hint.pack(fill="both", expand=True)
        if prev:
            # Минуле уточнення лишаємо на виду: так ясно, що саме вже
            # надсилали і на що відповіла модель. Порожнє — знімає його.
            hint.insert("1.0", prev)
        hint.focus_set()
        enable_clipboard(hint)

        out = {"text": None}

        def go():
            out["text"] = hint.get("1.0", tk.END).strip()
            win.destroy()

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(12, 0))
        run = tk.Button(row, text="Перегенерувати", command=go, height=2,
                        bg=AURORA[0], fg="#ffffff", activebackground=AURORA[1],
                        activeforeground="#ffffff",
                        font=("Segoe UI", 10, "bold"),
                        relief="flat", bd=0, cursor="hand2")
        run.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(row, text="Скасувати", command=win.destroy)\
            .pack(side="left")
        # Порожні вказівки — теж відповідь: перегенеруємо як раніше.
        win.bind("<Escape>", lambda e: win.destroy())
        self.wait_window(win)
        return out["text"]

    def _on_regen_marked(self, with_hint=False):
        """Скидає позначені рядки в чергу заново. Потрібно, коли чернетки вже
        збережені: «Згенерувати всі» їх пропускає, бо вони не «очікує».
        Старі CSV на диску не чіпаємо — вони лишаються, поки не збережеш нові.
        """
        picked = self._marked()
        if not picked:
            messagebox.showinfo("Нічого не позначено",
                                "Постав галочки навпроти рядків, які треба "
                                "перегенерувати.", parent=self)
            return
        if self.running:
            messagebox.showinfo("Черга працює",
                                "Зачекай, поки закінчиться поточний прохід.",
                                parent=self)
            return
        # Доопрацювання й «з нуля» — різні речі, і плутати їх дорого.
        # Доопрацювання лагодить те, що не так, і лишає назву та кут подачі.
        # «З нуля» кидає кубики заново — інша назва, інший файл.
        ready = [i for i in picked if self.rows[i].get("draft")]
        answer = True
        if ready:
            answer = messagebox.askyesnocancel(
                "Перегенерувати",
                f"Рядків: {len(picked)}, з готовою чернеткою: {len(ready)}.\n\n"
                f"ТАК — доопрацювати: помилки летять у той самий чат Gemini, "
                f"вона бачить свою чернетку й лагодить саме її. Назва кампанії "
                f"й назва файлу лишаються.\n\n"
                f"НІ — почати з нуля: новий чат, новий кут подачі, інша назва "
                f"кампанії й інший файл.\n\n"
                f"Старі CSV на диску лишаться, поки не збережеш нові поверх.",
                parent=self)
            if answer is None:
                return
        elif not messagebox.askyesno(
                "Перегенерувати",
                f"Рядків: {len(picked)}. Кожен піде в Gemini заново.\n\n"
                f"Починаємо?", parent=self):
            return
        # Без коментаря — просто перегенерувати, і старе уточнення знімаємо.
        # З коментарем — вікно; порожнє поле там теж означає «просто».
        hint = ""
        if with_hint:
            prev = next((self.rows[i].get("hint") for i in picked
                         if self.rows[i].get("hint")), "")
            hint = self._ask_hint(picked, bool(answer), prev)
            if hint is None:
                return
        for i in picked:
            # Вказівки живуть у рядку: черга бере їх, коли дійде саме до нього.
            self.rows[i]["hint"] = hint
            if answer and self.rows[i].get("draft"):
                self.rows[i].update({"status": "очікує", "repair": True,
                                     "csv": ""})
            else:
                self.rows[i].update({"status": "очікує", "draft": None,
                                     "errors": [], "warnings": [], "raw": "",
                                     "variant": None, "user_text": "",
                                     "folder": "", "round": 1, "csv": "",
                                     "chat": "", "seen": [], "texts": [],
                                     "truncated": [], "repair": False})
        self.current = -1
        self._refresh()
        self._on_run()

    def _on_archive(self):
        """Складає в архів позначені рядки, а якщо галочок немає — усе, що
        вже збережено в CSV. Список звільняється під нову партію."""
        picked = self._marked()
        done = ([self.rows[i] for i in picked] if picked
                else [r for r in self.rows if r["status"] == "збережено"])
        if not done:
            messagebox.showinfo("Архівувати нічого",
                                "Постав галочки або збережи хоч один CSV — "
                                "у архів іде саме це.", parent=self)
            return
        try:
            old = []
            if os.path.exists(BATCH_ARCHIVE):
                with open(BATCH_ARCHIVE, "r", encoding="utf-8") as f:
                    old = json.load(f)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(BATCH_ARCHIVE, "w", encoding="utf-8") as f:
                json.dump(old + [dict(r, archived=stamp) for r in done],
                          f, ensure_ascii=False, indent=1)
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося записати архів:\n{e}",
                                 parent=self)
            return
        gone = set(id(r) for r in done)
        self.rows = [r for r in self.rows if id(r) not in gone]
        self.current = -1
        self._refresh()
        self.status.configure(
            text=f"У архів пішло {len(done)}. У черзі лишилось {len(self.rows)}.")

    def _on_clear(self):
        """Чистить саме чергу. Заготовка лишається: у неї своя кнопка,
        інакше одним рухом злітала б робота, яку тільки-но набили."""
        queue = [r for r in self.rows if r["status"] != self.STAGE]
        if queue and not messagebox.askyesno(
                "Очистити чергу", f"Видалити всі {len(queue)} рядків черги?"
                + (f"\nЗаготовка ({len(self.rows) - len(queue)}) лишиться."
                   if len(queue) != len(self.rows) else ""),
                parent=self):
            return
        self.rows = [r for r in self.rows if r["status"] == self.STAGE]
        self.current = -1
        self._refresh()

    def _refresh(self):
        """Перемальовує чергу. Галочка — для гуртових дій, кнопка праворуч —
        відкрити саме цей рядок. Так нічого не плутається."""
        marked = set(self._marked())
        for child in self.body.winfo_children():
            child.destroy()
        self.checks = []
        # Галочки живуть за показаними рядками, а рядок заготовки в черзі
        # не показується — тому тримаємо мапу «галочка -> номер рядка».
        self.check_idx = []
        t = self.theme
        for n, i in enumerate(i for i, r in enumerate(self.rows)
                              if r["status"] != self.STAGE):
            r = self.rows[i]
            line = ttk.Frame(self.body)
            line.pack(fill="x", anchor="w", pady=1)
            var = tk.BooleanVar(value=(i in marked))
            self.checks.append(var)
            self.check_idx.append(i)
            ttk.Checkbutton(line, variable=var).pack(side="left")

            status = r["status"]
            # «раунд N» — це рядок, який зараз у роботі: підсвічуємо так само,
            # як «генерується», інакше він губиться сірим.
            # «чекаю 30с · 2/5» і «не JSON · 2/3» — теж робота, не простій.
            busy = (status.startswith("раунд ") or " · " in status
                    or status in ("генерується", "доопрацювання"))
            colour = (SEMANTIC["warning"] if busy else
                      {"збій": SEMANTIC["danger"],
                       "потрібна увага": SEMANTIC["danger"],
                       "чисто": SEMANTIC["success"],
                       "збережено": SEMANTIC["success"]}.get(status, t["muted"]))
            # Раунд видно одразу: скільки разів цей рядок уже доопрацьовували.
            if r.get("round", 1) > 1 and not busy:
                status = f"{status} · р{r['round']}"
            ttk.Label(line, text=f"{n + 1:>2}.", width=4,
                      foreground=t["muted"]).pack(side="left")
            ttk.Label(line, text=status, width=15,
                      foreground=colour).pack(side="left")
            # Ідентифікатор не ріжемо: коли один домен розкладено по списку
            # профілів, назва профілю — єдине, чим рядки різняться.
            ttk.Label(line, text=(r.get("ident") or "—")[:28], width=29,
                      foreground=t["muted"]).pack(side="left")
            ttk.Label(line, text=domain_short(r["url"])[:24],
                      width=25).pack(side="left")

            name = (r["draft"] or {}).get("campaign_name", "")
            tail = ""
            if r["status"] == "чисто":
                tail = f"{name[:26]}   помилок нема, чекає схвалення"
            elif r["status"] == "потрібна увага":
                tail = f"{name[:26]}   помилок {len(r['errors'])}"
            elif r["status"] == "збережено":
                # Показуємо не «нібито збережено», а чи файл справді на диску.
                path = r.get("csv") or ""
                mark = "файл є" if path and os.path.exists(path) else "ФАЙЛУ НЕМА"
                tail = f"{name[:26]}   {mark}"
            if r.get("hint"):
                # Видно одразу, що рядок генерувався з уточненням: інакше
                # не зрозуміти, чи помилки після нього — це відповідь на
                # твій коментар, чи на щось інше.
                tail = (tail + "   · з уточненням").strip(" ·")
            ttk.Label(line, text=tail, width=42,
                      foreground=t["ink"] if i == self.current else t["muted"])\
                .pack(side="left")

            if r.get("draft"):
                ttk.Button(line, text="Переглянути", width=13,
                           command=lambda n=i: self._open_row(n))\
                    .pack(side="left", padx=(6, 0))
        self._refresh_stage()
        self._on_pick()
        done = sum(1 for r in self.rows
                   if r["status"] in ("чисто", "потрібна увага", "збережено"))
        on_disk = sum(1 for r in self.rows
                      if r.get("csv") and os.path.exists(r["csv"]))
        in_queue = len(self.rows) - len(self._stage_rows())
        stage = len(self._stage_rows())
        tail = f" У заготовці {stage}." if stage else ""
        self.status.configure(
            text=f"У черзі {in_queue}, згенеровано {done}, "
                 f"файлів на диску {on_disk}.{tail}"
            if in_queue else f"Черга порожня.{tail}")
        self._save_buffer()

    def _on_pick(self):
        """Кнопка внизу веде на перший готовий рядок, якщо поточного немає."""
        i = self.current
        if not (0 <= i < len(self.rows) and self.rows[i].get("draft")):
            i = next((n for n, r in enumerate(self.rows) if r.get("draft")), -1)
        ready = i >= 0
        self.btn_open.configure(state="normal" if ready else "disabled")
        self.app._paint(self.btn_open, ready, AURORA[2])
        clean = any(r["status"] == "чисто" for r in self.rows)
        self.btn_save.configure(state="normal" if clean else "disabled")
        self.app._paint(self.btn_save, clean, SEMANTIC["success"])

    def _on_save_clean(self):
        """Забирає CSV для рядків без помилок. Є галочки — беремо тільки
        позначені, немає — усі чисті. Рядок з помилками не збережеться
        ніколи: такий файл на диску не відрізнити від справного."""
        clean = [i for i, r in enumerate(self.rows) if r["status"] == "чисто"]
        marked = [i for i in self._marked() if self.rows[i]["status"] == "чисто"]
        target = marked or clean
        if not target:
            skipped = sum(1 for r in self.rows if r["status"] == "потрібна увага")
            messagebox.showinfo(
                "Зберігати нічого",
                "Чистих рядків немає."
                + (f"\n\nРядків з помилками: {skipped}. Їх треба спочатку "
                   f"доопрацювати — відкрий рядок і подивись, що не так."
                   if skipped else ""), parent=self)
            return
        if not messagebox.askyesno(
                "Зберегти",
                f"Рядків: {len(target)}. Кожен ляже CSV у папку свого "
                f"ідентифікатора.\n\nЯкщо файл з такою назвою вже є — "
                f"перезапишеться.\n\nЗберігаємо?", parent=self):
            return
        saved, failed = 0, []
        for i in target:
            r = self.rows[i]
            try:
                path = self._save_row(r, r["draft"], r.get("wants")
                                      or self.app._wants())
                r.update({"status": "збережено", "csv": path})
                saved += 1
                self.app._log(f"Черга {i + 1}: збережено "
                              f"{os.path.basename(path)}", "success")
            except Exception as e:
                failed.append(f"рядок {i + 1}: {e}")
                self.app._log(f"Черга {i + 1}: CSV не зібрався — {e}", "danger")
        self._save_buffer()
        self._refresh()
        self.status.configure(text=f"Збережено файлів: {saved}."
                                   + (f" Не вийшло: {len(failed)}."
                                      if failed else ""))
        if failed:
            messagebox.showwarning("Не всі збереглися",
                                   "\n".join(failed[:8]), parent=self)

    def _open_row(self, index):
        """Чернетка їде в головне вікно з усією його механікою: галочки на
        помилки, «Регенерувати», «Створити CSV». Вікно черги прибираємо з
        дороги, інакше воно перекриває те, що ми щойно відкрили."""
        if not (0 <= index < len(self.rows)):
            return
        r = self.rows[index]
        if not r.get("draft"):
            messagebox.showinfo("Ще не згенеровано",
                                f"Рядок у стані «{r['status']}». Спочатку "
                                f"згенеруй.", parent=self)
            return
        self.current = index
        self._refresh()
        self.app.adopt_batch_row(r, index, self)
        self.lower()

    def _on_open(self):
        i = self.current
        if not (0 <= i < len(self.rows) and self.rows[i].get("draft")):
            i = next((n for n, r in enumerate(self.rows) if r.get("draft")), -1)
        if i < 0:
            messagebox.showinfo("Нема чого дивитись",
                                "Спочатку згенеруй чергу.", parent=self)
            return
        self._open_row(i)

    # ── запуск ────────────────────────────────────────────────────────────────
    def _on_run(self):
        pending = [r for r in self.rows if r["status"] in ("очікує", "збій")]
        if not pending:
            messagebox.showinfo("Нема чого генерувати",
                                "Усі рядки вже оброблені.", parent=self)
            return
        if self.app.mode.get() == "api" and not self.app.e_key.get().strip():
            messagebox.showwarning("Увага", "Введи API-ключ або перемкнись "
                                            "на браузер.", parent=self)
            return
        self.running, self.stop_flag = True, False
        self.btn_run.configure(state="disabled")
        self.app._paint(self.btn_run, False, AURORA[0])
        self.btn_stop.configure(state="normal")
        threading.Thread(target=self._runner, daemon=True).start()

    def _on_stop(self):
        self.stop_flag = True
        self.status.configure(text="Зупиняю після поточного сайту…")

    def _runner(self):
        wants = self.app._wants()
        browser = self.app.mode.get() == "browser"
        key = self.app.e_key.get().strip()
        model = self.app.cb_model.get().strip()
        exe = self.app.cfg.get("chrome_path", "")
        extra = self.app.e_notes.get().strip()

        for i, r in enumerate(self.rows):
            if self.stop_flag:
                break
            if r["status"] not in ("очікує", "збій"):
                continue

            # Доопрацювання — це дослання в чат САМЕ цього сайту, як в
            # одиночному режимі. Раніше черга на кожну регенерацію кидала
            # кубики заново: новий варіант, нова назва, новий чат. Модель не
            # бачила власну зламану чернетку й не сходилась, а людина щоразу
            # діставала іншу назву файлу.
            repair = bool(r.get("repair") and r.get("draft") and r.get("user_text")
                          and (r.get("chat") or not browser))
            self.app.q.put(("batch_status",
                            (i, "доопрацювання" if repair else "генерується")))
            if r.get("hint"):
                self.app.q.put(("status", f"Черга {i + 1}: з уточненням "
                                          f"«{self.app._shown_hint(r['hint'])}»"))
            # Черга оновлюється наживо: поки API чекає повтор, у рядку видно
            # «чекаю 30с · 2/5», а не застиглий стан, що здається зависанням.
            sink = {"on_wait": lambda short, full, n=i: (
                self.app.q.put(("batch_status", (n, short))),
                self.app.q.put(("status", f"Черга {n + 1}: {full}")))}
            # Вказівки, написані для цього рядка у вікні перегенерації,
            # їдуть разом із загальними побажаннями згори.
            row_extra = chr(10).join(x for x in (extra, r.get("hint") or "") if x)
            try:
                if repair:
                    variant  = r.get("variant") or pick_variant(wants["aggregator"])
                    user_text = r["user_text"]
                    row_wants = dict(r.get("wants") or wants)
                    apply_notes_geo(row_wants, row_extra)
                    agg, cut = bool(row_wants.get("aggregator")), []
                    notes, _, _ = build_repair_notes(
                        r["draft"], row_wants, r.get("seen") or [],
                        r.get("truncated") or [], row_extra)
                    if browser:
                        draft = browser_generate(user_text, notes, lambda s: None,
                                                 exe, sink, None, agg,
                                                 follow_up=True,
                                                 chat_url=r.get("chat", ""))
                    else:
                        draft = generate_draft(key, model, user_text, notes, sink,
                                               None, agg, previous=r.get("raw", ""))
                else:
                    w0 = dict(wants)
                    variant, user_text, _, cut = self.app.build_request(
                        r["url"], r["desc"], w0, row_extra,
                        self._taken_names(i))
                    agg = wants["aggregator"]
                    # w0, а не wants: у w0 build_request записав гео з
                    # уточнення, і перевірка має його бачити.
                    row_wants = dict(w0, scrubbed=bool(cut),
                                     source_desc=r["desc"])
                    if browser:
                        draft = browser_generate(user_text, "", lambda s: None,
                                                 exe, sink, None, agg,
                                                 new_chat=True)
                    else:
                        draft = generate_draft(key, model, user_text, "", sink,
                                               None, agg)
                if r["url"]:
                    draft["website"] = r["url"]
                errors, warnings = validate(draft, row_wants)
                clash = self._name_clash(i, draft.get("campaign_name") or "")
                if clash:
                    errors.append(clash)

                # Доводимо рядок до пуття тут же, не смикаючи людину на кожну
                # дрібницю: черга для того й є. Ганяємо, поки помилок меншає;
                # перестало меншати двічі поспіль — далі це холостий хід.
                seen = set(r.get("seen") or []) | set(errors)
                texts = all_ad_texts(draft.get("ad_groups"))
                trunc = (find_truncations(r.get("texts") or [], texts)
                         if repair else [])
                rounds = r.get("round", 1) + (1 if repair else 0)
                stall = 0
                while (errors and rounds < AUTO_ROUNDS_MAX and not self.stop_flag):
                    self.app.q.put(("batch_status",
                                    (i, f"раунд {rounds + 1}")))
                    notes, _, _ = build_repair_notes(
                        draft, row_wants, seen, trunc, row_extra)
                    prev_n, prev_texts = len(errors), texts
                    if browser:
                        # Ми вже стоїмо в чаті цього рядка — переходити нікуди
                        # не треба, дослання йде туди ж.
                        draft = browser_generate(user_text, notes, lambda s: None,
                                                 exe, sink, None, agg,
                                                 follow_up=True)
                    else:
                        draft = generate_draft(key, model, user_text, notes, sink,
                                               None, agg,
                                               previous=sink.get("raw", ""))
                    if r["url"]:
                        draft["website"] = r["url"]
                    errors, warnings = validate(draft, row_wants)
                    clash = self._name_clash(i, draft.get("campaign_name") or "")
                    if clash:
                        errors.append(clash)
                    texts = all_ad_texts(draft.get("ad_groups"))
                    trunc = find_truncations(prev_texts, texts)
                    seen |= set(errors)
                    rounds += 1
                    stall = stall + 1 if len(errors) >= prev_n else 0
                    if stall >= 2:
                        break

                # Файл сама черга не пише: рішення про завантаження в кабінет
                # лишається за людиною. Чистий рядок просто чекає схвалення
                # в буфері, а забирає його кнопка «Зберегти всі чисті».
                folder = save_history({
                    "час": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "статус": "готово",
                    "режим": ("браузер" if browser else "API") + ", черга"
                             + (", доопрацювання" if repair else ""),
                    "модель": "gemini web" if browser else model,
                    "url": r["url"],
                    "campaign_name": draft.get("campaign_name", ""),
                    "варіант": variant,
                    "wants": row_wants,
                    "раунд": rounds,
                    "ідентифікатор": (r.get("ident") or "").strip(),
                    "помилок": errors,
                    "попереджень": warnings,
                    "запит": user_text,
                    "промпт": load_system_prompt(agg),
                    "raw_response": sink.get("raw", ""),
                    "draft": draft,
                })
                self.app.q.put(("batch_done", (i, draft, errors, warnings,
                                               sink.get("raw", ""), variant,
                                               user_text, folder, row_wants, cut,
                                               sink.get("chat", r.get("chat", "")),
                                               rounds, sorted(seen), texts, trunc)))
            except Exception as e:
                self.app.q.put(("batch_fail", (i, str(e), sink.get("raw", ""))))
        self.app.q.put(("batch_end", None))

    def _save_row(self, row, draft, wants):
        """Збирає CSV одного рядка — те саме, що кнопка «Створити CSV» в
        головному вікні. Бюджет і ставку беремо з головного вікна на кожен
        рядок окремо: діапазон «10-20» і список «10; 12; 15» мають гуляти
        від кампанії до кампанії, а не застигнути на одному числі для всієї
        черги."""
        budget_val, _ = resolve_amount(self.app.e_budget.get(), 0, "budget_i",
                                       self.app.cfg)
        cpc_val, _ = resolve_amount(self.app.e_cpc.get(), 2, "cpc_i",
                                    self.app.cfg)
        rows = build_rows(draft, format_amount(budget_val, 0),
                          format_amount(cpc_val, 2), wants)
        return write_csv(rows, draft["campaign_name"].strip(),
                         bool(wants.get("aggregator")), row.get("ident", ""))

    def _taken_names(self, index):
        """Назви кампаній інших рядків — щоб Gemini не видала ту саму."""
        return [n for j, r in enumerate(self.rows) if j != index
                for n in [((r.get("draft") or {}).get("campaign_name") or "").strip()]
                if n]

    def _name_clash(self, index, name):
        """Помилку даємо лише тоді, коли файли справді затруть один одного.

        CSV лягає в папку ідентифікатора, тож однакова назва у двох різних
        клієнтів нікому не заважає. Сварити за неї — це гнати людину на зайву
        регенерацію там, де все гаразд.
        """
        name = (name or "").strip()
        if not name:
            return ""
        mine = self.rows[index]
        here = ident_folder(mine.get("ident", ""))
        for j, r in enumerate(self.rows):
            if j == index:
                continue
            other = ((r.get("draft") or {}).get("campaign_name") or "").strip()
            if other and defold(other) == defold(name) \
                    and ident_folder(r.get("ident", "")) == here:
                return (f"Назва «{name}» уже зайнята рядком {j + 1} "
                        f"({domain_short(r.get('url', ''))}) з тим самим "
                        f"ідентифікатором — CSV зветься за кампанією, і цей "
                        f"файл затре сусідній. Тисни «Перегенерувати вибрані».")
        return ""

    # ── буфер ─────────────────────────────────────────────────────────────────
    def _save_buffer(self):
        """Чернетки живуть на диску до збереження CSV: закрив вікно, вимкнув
        світло — черга й тексти на місці."""
        try:
            with open(BATCH_FILE, "w", encoding="utf-8") as f:
                json.dump(self.rows, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _load_buffer(self):
        try:
            if os.path.exists(BATCH_FILE):
                with open(BATCH_FILE, "r", encoding="utf-8") as f:
                    self.rows = json.load(f)
        except Exception:
            self.rows = []
        # Черга з попередньої версії не знає про нові поля — добиваємо їх,
        # інакше доопрацювання не матиме куди записати адресу чату.
        blank = self._new_row("", "", "")
        for r in self.rows:
            for k, v in blank.items():
                r.setdefault(k, v if not isinstance(v, list) else list(v))
        # Таблиця заготовки підтягується після черги: їй треба знати, чи не
        # лишилось у batch.json рядків «заготовка» зі старої версії.
        self._table_load()

    def _poll(self):
        self.after(400, self._poll)


def read_table(path):
    """Читає CSV/TSV як список рядків-колонок. Повертає (рядки, помилка).

    Роздільник і кодування вгадуємо: файли приходять із Excel, Google Sheets
    і просто з блокнота, і три різні джерела дають три різні формати. Крапка
    з комою — звичайний випадок для Excel з українською локаллю.
    """
    raw = None
    for code in ("utf-8-sig", "cp1251", "cp1252", "utf-16"):
        try:
            with open(path, "r", encoding=code, newline="") as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
    if raw is None:
        return [], "Не вдалося підібрати кодування файлу."
    head = raw[:4000]
    delim = max(("\t", ";", ","), key=head.count)
    if head.count(delim) == 0:
        delim = "\t"
    out = []
    try:
        for cells in csv.reader(raw.splitlines(), delimiter=delim):
            cells = [c.strip() for c in cells]
            if any(cells):
                out.append(cells)
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"
    # Заголовок таблиці в чергу не потрібен. Пізнаємо його за ТОЧНОЮ назвою
    # колонки, а не за входженням слова: опис «Турніри щодня, опис короткий»
    # теж містить «опис», і такий рядок колись зїдався як заголовок.
    heads = {"профіль", "профиль", "profile", "ident", "ідентифікатор",
             "идентификатор", "акаунт", "аккаунт", "account", "сайт",
             "site", "url", "домен", "domain", "опис", "описание",
             "description", "desc", "a", "b", "c"}
    if out and any((cell or "").strip().lower().rstrip(":") in heads
                   for cell in out[0][:3]):
        out = out[1:]
    return out, ""


def domain_short(url):
    text = re.sub(r"^https?://(www\.)?", "", (url or "").strip())
    return (text.split("/")[0] or "(без сайту)")[:34]


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
