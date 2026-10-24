# Woonsh Tools — Архитектура

## Обзор

Десктопное приложение (tkinter, Windows) объединяющее 5 инструментов.
Два режима запуска: **Farmer** (мультифармер) и **Woonsh Tools** (основное приложение).
Переключатель в `launcher.pyw`.

## Меню (Sidebar)

```
[Farmer ◄► Woonsh Tools]     — переключатель режимов вверху

ПОИСК ФИРМ
  🔍 Поиск                   — процесс поиска фирм (DnB/реестр)
  🌍 Гео и выдача            — таблица по странам + взять в работу

GOOGLE ADS
  📋 Генератор CSV           — Search / YouTube переключатель (ЦСВ Вайт)
  👤 Профили                 — платёжные профили (Excel/CSV/ссылка)
  🏢 Компании                — привязка фирм к аккаунтам (ЦСВ Вайт)

GOOGLE DRIVE
  ☁️ Загрузка                — загрузка PDF на Google Drive (rclone)

ДОКУМЕНТАЦИЯ
  📄 Документы               — шаблоны документов
  📦 Склад                   — архив документов

⚙️ Настройки                 — внизу сайдбара, отдельный заголовок
```

## Тема оформления

**Aurora** — тёмная тема, основная для всей CRM.
Переключатель в Настройках: Aurora / Стандарт (без заливки).

Основной градиент (90°, слева направо):
- `#7a34e6` — фиолетовый
- `#d6389e` — малиново-розовый
- `#3b74ed` — синий

Где используется:
- Шапки таблиц: градиент на всю строку, текст белый жирный, снизу оранжевая линия 3px `#E8A531`
- Заголовки: текст залит градиентом
- Основные кнопки, активный пункт меню: фон градиентом, текст белый
- Активная вкладка: градиент + оранжевая рамка

Отдельный градиент по колонкам (auroraColor):
- Каждая ячейка шапки — свой цвет на пути фиолетовый → розовый → синий

Акценты:
- Оранжевый `#E8A531` — линии под шапками, hover кнопок
- Выделение: рамка 3px `#7a34e6`, фон `#e9d5ff`, текст `#4c1d95`

## Структура файлов

```
Woonsh-tools/
├── launcher.pyw              — переключатель Farmer / Woonsh Tools
├── ЗАПУСК.bat                — Windows launcher (git pull + pythonw)
├── woonsh_tools/
│   ├── __init__.py           — VERSION
│   ├── app.py                — главное приложение, sidebar, модули
│   │
│   ├── core/                 — общие модули
│   │   ├── theme.py          — Aurora тема (tkinter/ttk стили)
│   │   ├── sidebar.py        — Sidebar навигация с группами
│   │   ├── ui_helpers.py     — clipboard, LinkDialog
│   │   ├── gemini.py         — Gemini API клиент (MODEL_CHAIN, THINK_LADDER)
│   │   ├── cdp.py            — Chrome DevTools Protocol (WebSocket)
│   │   ├── secure_store.py   — DPAPI шифрование (Windows)
│   │   └── scroll.py         — ScrollableFrame
│   │
│   ├── companies/            — ПОИСК ФИРМ
│   │   ├── panel.py          — UI: пункт "Поиск" (параметры, кнопки, статус)
│   │   ├── geo_panel.py      — UI: пункт "Гео и выдача" (таблица, кнопки)
│   │   ├── flow.py           — управление потоком (старт/стоп/продолжить)
│   │   ├── human_gate.py     — HumanGate (вопросы, автономный режим)
│   │   ├── registry.py       — реестр фирм (бронь 24ч + подтверждение)
│   │   ├── queue.py          — очередь заданий (слово × страна × количество)
│   │   ├── search_dnb.py     — поиск через DnB (Playwright)
│   │   ├── words_gemini.py   — генерация слов через Gemini
│   │   ├── filters.py        — фильтрация результатов (страна, дубли)
│   │   ├── delivery.py       — выдача (папка + платёжки)
│   │   ├── bot_check.py      — проверка у Telegram-бота
│   │   ├── sheets.py         — запись в Google Таблицу
│   │   ├── stats.py          — UI: статистика (бывший stats_panel)
│   │   └── drivers/          — гео-драйверы (19 стран)
│   │       ├── base.py       — ABC: search/open/check/fetch
│   │       ├── registry.py   — реестр драйверов
│   │       ├── czechia.py    — Чехия
│   │       ├── austria.py    — Австрия
│   │       ├── poland.py     — Польша
│   │       └── ...           — остальные 16 стран
│   │
│   ├── ads/                  — ЦСВ ВАЙТ
│   │   ├── panel.py          — UI: генератор CSV (Search / YouTube)
│   │   ├── generator.py      — логика генерации (промпт, варианты)
│   │   ├── validation.py     — валидация (600+ строк)
│   │   ├── banned.py         — banned topics (15 категорий)
│   │   ├── repair.py         — repair loop (рецидивы, обрубки)
│   │   ├── geo.py            — определение гео (country_scores)
│   │   ├── csv_builder.py    — сборка CSV (build_rows, write_csv)
│   │   ├── batch.py          — BatchWindow (canvas-таблица, очередь)
│   │   ├── negatives.py      — BUILTIN_NEG по языкам (от коллеги)
│   │   ├── review_panel.py   — UI: проверка рекламы
│   │   ├── selectors.py      — выбор языка/страны
│   │   └── prompt_gemini.txt — промпт для Search (версионированный)
│   │
│   ├── drive/                — GOOGLE DRIVE
│   │   ├── panel.py          — UI: загрузка PDF на Drive
│   │   └── rclone.py         — rclone обёртка (download, upload, check)
│   │
│   ├── profiles/             — GOOGLE ADS: ПРОФИЛИ
│   │   ├── panel.py          — UI: платёжные профили (Excel/CSV/ссылка)
│   │   ├── store.py          — DPAPI хранение + download
│   │   └── scroll.py         — ScrollFields виджет
│   │
│   ├── documents/            — ДОКУМЕНТАЦИЯ
│   │   ├── panel.py          — UI: документы
│   │   ├── stock.py          — UI: склад документов
│   │   ├── fields.py         — поля документов
│   │   ├── dedup.py          — дедупликация
│   │   ├── reader.py         — чтение документов
│   │   └── archive.py        — архивирование
│   │
│   └── update/               — СИСТЕМА
│       ├── panel.py          — UI: настройки (все конфиги)
│       ├── updater.py        — GitHub Releases обновления
│       └── wizard.py         — мастер первой настройки
│
├── Фирмы/                    — ИСХОДНЫЙ КОД (база для companies/)
│   └── код/                  — 183 файла, ~19500 строк, 83 теста
│
├── ЦСВ Вайт/                 — ИСХОДНЫЙ КОД (база для ads/)
│   ├── ppc_gemini.pyw        — 8129 строк (монолит)
│   └── prompt_gemini.txt     — промпт v99
│
├── X-File/                    — КОД КОЛЛЕГИ (дополнения)
│   ├── ads_generator/        — ThreadPoolExecutor, THINK_LADDER
│   └── ...                   — DnB Playwright, Telegram, etc.
│
└── docs/                      — ДОКУМЕНТАЦИЯ ДЛЯ РАЗРАБОТКИ
    ├── ARCHITECTURE.md        — этот файл
    ├── FIRMS_LOGIC.md         — логика поиска фирм
    ├── CSV_LOGIC.md           — логика ЦСВ Вайт
    ├── MODULE_MAP.md          — откуда что брать (строки → файлы)
    └── IMPLEMENTATION.md      — план реализации по этапам
```

## Настройки (панель)

Все конфиги в одном месте (`update/panel.py`):

```
ФАРМЕР
  Имя фармера           — текст
  Таблица фармера        — Google Sheet ID
  Таблица фирм           — Google Sheet ID

API И ИНТЕГРАЦИИ
  API Gemini             — ключ (маскированный)
  Telegram бот           — bot token
  Telegram chat ID       — ID чата для проверки

ПАПКИ И ФАЙЛЫ
  Папка выписок          — путь + кнопка "Обзор"
  Папка выдачи           — путь + кнопка "Обзор"
  Папка CSV              — путь для сохранения CSV

GOOGLE DRIVE
  ID папки Drive         — Google Drive folder ID
  rclone                 — путь к rclone / скачать

DnB
  Аккаунт DnB           — логин/пароль

ОФОРМЛЕНИЕ
  Тема                   — Aurora (тёмная) / Стандарт (без заливки)

ОБНОВЛЕНИЯ
  Версия                 — текущая + кнопка "Проверить"
  Репозиторий            — URL для git pull
```

## Обновления

`ЗАПУСК.bat` делает `git pull origin <branch>` при каждом запуске.
Приложение стартует всегда из актуальной версии.
Репозиторий: GitHub, ветка задаётся в настройках.

## Ключевые зависимости

- Python 3.10+ (Windows)
- tkinter/ttk (встроено в Python)
- openpyxl — работа с Excel
- playwright — DnB через браузер
- google-api-python-client — Google Sheets API
- python-telegram-bot — Telegram интеграция
- rclone — Google Drive загрузка (скачивается отдельно)
