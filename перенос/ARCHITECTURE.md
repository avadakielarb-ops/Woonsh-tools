# Woonsh Tools — архитектура

## Обзор

Настольное приложение, tkinter/ttk, Windows. Запуск — `ЗАПУСК.bat` (git pull + `pythonw launcher.pyw`).
`launcher.pyw` — выбор режима:
- **Multi-Tool Farmer** — `X-File/x-file.pyw` коллеги, как есть, со своими обновлениями;
- **Woonsh Tools** — `woonsh_tools.app.main()`.

## Меню

```
[Multi-Tool Farmer ◄► Woonsh Tools]

ПОИСК ФИРМ
  Поиск                      companies/search_panel.py
  Гео и выдача               companies/geo_panel.py

GOOGLE ADS
  Профили                    profiles/panel.py
  Компании                   ads/panel.py            (= ЦСВ Вайт, Search / YouTube)

ЗАГРУЗКА GOOGLE DISK
  1 Компании                 drive/companies.py
  2 Сопоставление PDF        drive/match_pdf.py
  3 Загрузка на Drive        drive/panel.py

ДОКУМЕНТАЦИЯ
  Документы                  documents/panel.py
  Склад                      documents/stock.py

⚙ Настройки                  update/panel.py         (внизу слева, отдельно)
```

## Тема Aurora (спецификация владельца, «как в таблицах Wunsh»)

Тема всей CRM. В Настройках переключается на «Стандарт» — без заливки.

Основной градиент 90°, слева направо: `#7a34e6` фиолетовый → `#d6389e` малиново-розовый → `#3b74ed` синий.

Где стоит:
- **Шапки таблиц:** градиент на всю строку, текст белый жирный, шрифт **Comic Sans MS**, снизу оранжевая линия 3 px `#E8A531`.
- **Заголовок страницы:** текст залит градиентом, под полосой страницы — градиентная линия 3 px.
- **Основные кнопки, активный пункт меню, активная вкладка, кнопка подтверждения:** фон градиентом, текст белый. У активной вкладки ещё оранжевая рамка.
- **Шапка панели «История»:** тот же градиент, Comic Sans, оранжевая линия снизу.
- **Полоса выбора строк:** тот же градиент, повёрнутый 180°, линия 4 px слева.

Градиент по колонкам (`auroraColor`): каждая ячейка шапки — свой цвет на пути фиолетовый → розовый → синий
(первая `#7a34e6`, средняя `#d6389e`, последняя `#3b74ed`, между — плавно).

Акценты: оранжевый `#E8A531` — линии под шапками и hover основной кнопки;
выделение ячеек — рамка 3 px `#7a34e6`; номер выбранной строки — фон `#e9d5ff`, текст `#4c1d95`.

Технические приёмы tkinter (из `Фирмы/доки/CLAUDE.md`): ttk красится только через `clam`; `tk.Text/Listbox/Canvas`
красить отдельно; выпадашка Combobox — через `option_add("*TCombobox*Listbox…")`; галочки — свои картинки 16×16;
Toplevel красит себя сам.

## Структура файлов (целевая)

```
Woonsh-tools/
├── launcher.pyw, ЗАПУСК.bat, requirements.txt
├── CLAUDE.md                   ← вход для ИИ (ведёт в перенос/)
├── перенос/                       ← вся документация проекта
├── woonsh_tools/
│   ├── app.py                  главное окно, меню
│   ├── core/                   theme, sidebar, ui_helpers, scroll, secure_store, cdp, gemini, telegram_login (новое)
│   ├── companies/              ПОИСК ФИРМ
│   │   ├── engine/             копия Фирмы/код (common, part1, part2, очередь, бот, тесты) — логика владельца
│   │   ├── controller.py       состояние, HumanGate, запуск работ (из окно.py)
│   │   ├── search_panel.py     пункт «Поиск»
│   │   ├── geo_panel.py        пункт «Гео и выдача»
│   │   └── bot_auto.py         автоматическая проверка ботом
│   ├── ads/                    КОМПАНИИ (ЦСВ Вайт, нарезка ppc_gemini.pyw)
│   │   ├── paths, constants, prompts, variants, schema, landing, history
│   │   ├── browser_gen.py          (Gemini-клиент — общий core/gemini.py)
│   │   ├── banned.py, text_rules.py, geo.py, validation.py, repair.py
│   │   ├── csv_builder.py, negatives.py, rework.py
│   │   ├── panel.py, batch.py
│   │   └── prompts/            prompt_gemini.txt, prompt_aggregator.txt, (prompt_youtube.txt)
│   ├── drive/                  companies, match_pdf, panel, rclone
│   ├── profiles/               panel, store, scroll
│   ├── documents/              panel, stock, fields, dedup, reader, archive
│   └── update/                 panel (настройки), updater, wizard
├── Фирмы/  ЦСВ Вайт/  X-File/  …   ← ИСХОДНИКИ, не удалять до конца переноса
└── не трогать/                 ← НЕ ЧИТАТЬ
```

## Настройки (один экран)

```
ФАРМЕР
  Имя фармера
  Таблица фирм         адрес Apps Script + ключ (как Фирмы/данные/ключи.json)
  Таблица фармера      (уточнить у владельца)
  Папка Фирм           рабочая папка владельца: данные/, фирмы/, выписки/, выдачи/, логи/, .профиль_браузера/

API
  Gemini API key       (DPAPI)
  Telegram             api_id, api_hash, вход (код / QR / 2FA) → сессия; бот @usedcompaniesarb_bot

ЦСВ
  Папка «Готові РК»    (chosen_root)
  Chrome для режима Браузер

GOOGLE DRIVE
  ID папки, rclone (путь / скачать), подключить Drive

ОФОРМЛЕНИЕ             Aurora / Стандарт
ОБНОВЛЕНИЯ             версия, проверить (см. открытый вопрос о приватном репо)
```

## Потоки и события

UI — только главный поток. Фоновые работы шлют события в `queue.Queue`, UI забирает их `after(100…250)`.
Из фонового потока tkinter не трогать (в т.ч. `after()` — роняет tkinter, см. журнал владельца).

## Зависимости

Python **3.12**; playwright ≥ 1.62 (+ playwright-stealth), установленный Google Chrome; openpyxl; python-docx;
telethon < 2; PyMuPDF и OCR — как у коллеги для документов; rclone (скачивается программой).
