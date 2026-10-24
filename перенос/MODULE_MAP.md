# Карта переноса: источник → `woonsh_tools/`

> Принцип: **переносить, а не переписывать.** Логику владельца копировать как есть,
> менять только импорты, пути и места склейки с UI Woonsh.
> Номера строк — на коммит этой ветки от 24.10.2026. Перед переносом сверить `grep -n`.

---

## A. Поиск фирм — `woonsh_tools/companies/`

### A.1 Стратегия: движок владельца целиком, новое — только окно

Код владельца плотно связан (`from common import …`, `from part1 …`, `part2.engine`), покрыт 83 тестами
и журналом решений. Раскладывать его по новым файлам = ломать. Поэтому:

```
woonsh_tools/companies/
├── engine/                  ← КОПИЯ Фирмы/код/ без изменений логики
│   ├── common/              (browser, human, таблица, статусы, пути, тема, диагноз, имена, колонки, номер, ввод, раскладка, files)
│   ├── part1/               (dnb, engine, filters, registry, запас, слова, слова_gemini, слова_проверка, из_реестра, excel_out, models, data/)
│   ├── part2/               (engine, core/, geos/ — ВСЕ файлы, netherlands.py копируется байт-в-байт, НЕ открывать)
│   ├── очередь.py, проверка_ботом.py, перечитать_ответ_бота.py, статистика_слов.py,
│   │   парсер_платёжного_профиля.py, задание_выписок.py, продолжение.py, дозапись.py,
│   │   отметить_отработанные.py, номера_фирмам.py, перенос_в_таблицу.py   ← то, что зовёт окно
│   └── тесты/               (все; прогон: python тесты/прогнать_все.py из папки engine)
├── __init__.py              ← вставляет engine/ в sys.path ОДИН раз
├── search_panel.py          ← пункт «Поиск»       (из окно.py, см. A.2)
├── geo_panel.py             ← пункт «Гео и выдача» (из окно.py, см. A.2)
├── controller.py            ← общее состояние двух панелей: HumanGate, самоход, стоп, лог, запуск фоновой работы
└── bot_auto.py              ← автоматическая проверка ботом (новое, см. A.4)
```

**НЕ переносить:** `part3/поиск_сайтов.py` (удалён по решению владельца), старое `app.py` (легаси, заменено `окно.py`).

**Переносить (решено 24.10.2026):** `окно_очереди.py` → `companies/queue_window.py`, открывается кнопкой «Очередь заданий»
из пункта «Поиск» (сейчас оно открывается только из старого `app.py:1255-1262`). Автоматизация: «Сгенерировать задания»
заполняет очередь сама (слова из запаса/Gemini на выбранные гео × количество), «Запустить всё», продолжение после сбоя.
Этап «сайты» из `ЭТАПЫ` в `очередь.py` убрать; после этапа «выписки» — автоматический бот (`bot_auto.py`).

**Пути (`common/пути.py`)** ищут корень подъёмом до `СТАРТ.bat`. В Woonsh корень данных другой —
поправить ОДНО место: корень = папка данных Woonsh (`%APPDATA%/WoonshTools/firmy` или путь из настроек)
с подпапками `данные/ фирмы/ выписки/ логи/ выдачи/`. Для перехода — кнопка в настройках «Подключить папку Фирм»,
указывающая на существующую рабочую папку владельца (там реестр_фирм.json, запас_слов.json, книги, профиль браузера).
**Реестр и профиль браузера не копировать и не создавать заново** — использовать существующие.

### A.2 Окно владельца → две панели

| `окно.py` (строки) | Что | Куда |
|---|---|---|
| 63–130 | `_линия_в_флаг`, `тек_время`, `имена_из_платёжек`, `первая_строка` | `controller.py` |
| 131–181 `__init__` | состояние: `самоход`, `ускоренно`, `ручное`, очереди событий | `controller.py` |
| 182–333 `_настройка` | «Что ищем»: С сайтом/Без сайта, Автономно, Ускоренно, источник, Сколько, Гео, Слова, СТАРТ, Продолжить | `search_panel.py` (+ режим работы, + строка «Язык слов», мультигео-попап) |
| 334–365 `показать_остаток`, `продолжить` | «Продолжить прерванный» | `search_panel.py` |
| 366–394 `_переключить_самоход` | Автономно на ходу | `controller.py` |
| 395–465 `_показать_источник`, `_свернуть_список`, `_гео_из_поля`, `_выбор`, `выбранные_гео`, `_сколько` | видимость источника, выбор гео | `search_panel.py` (гео-список → попап «Мультигео») |
| 466–532 `_шаги`, `_отметить_шаг` | «Ход работы» 1–4 | `search_panel.py`, порядок: Поиск → Выписки → Бот → Выдача |
| 533–614 `_лог_панель`, `_человек*`, `_чп_кнопка` | лог, панель человека | `search_panel.py` (правая панель) |
| 615–877 `_цифры_*`, `обновить_счётчики`, `_прибрать_застрявших`, `_показать_счётчики`, `_строка_гео`, `_ширины_по_содержимому` | гео-таблица с цифрами | `geo_panel.py` |
| 878–1062 `старт`, `_из_реестра`, `_после_поиска` | запуск поиска | `controller.py` (+ после поиска в режиме Стандартный → выписки → бот) |
| 1063–1260 `_книга_и_лист`, `скачать_выписки`, `_сколько_выписок`, `_после_выписок` | выписки | `geo_panel.py` кнопка «Докачать»; `controller.py` логика |
| 1261–1559 `проверить_у_бота` | 2-шаговое окно бота | `bot_auto.py` (автомат) + ручная кнопка в `geo_panel.py` |
| 1560–1733 `пересмотреть_слова` | «Выхлоп по словам» | `search_panel.py` (диалог как есть) |
| 1734–1970 `взять_в_работу`, `_отметить`, `_собрать_папку` | выдача | `geo_panel.py` + `controller.py` |
| 1971–2101 `_включить_шаги`, `_шлюз`, `_запустить`, `стоп_всё`, `_лог_поток` | HumanGate, фоновые задачи, стоп | `controller.py` |
| 2102–2224 статус-строка, лог в файл, разбор очереди | | `controller.py` |
| 2225–2385 `_вопрос*`, `_ручное_переключить`, `_приказать`, `_чп_повтор`, `_повторить_действие`, `_ответ*`, `_показать_отметку` | вопросы человеку, ручное управление | `controller.py` + правая панель |

Тема: окно владельца красится `common/тема.py`; Woonsh — `core/theme.py`. Палитра одна (Aurora). Брать `core/theme.py`,
но сохранить приёмы владельца: картинки галочек 16×16, `тема.покрасить()` для Text/Listbox/Canvas, раскраска лога по первому символу.

### A.3 Что из X-File коллеги

| Источник | Куда | Зачем |
|---|---|---|
| `X-File/company_search.py:390-420` (Telethon `conversation`, `send_message`, `get_entity(BOT)`) | `bot_auto.py` | транспорт к `@usedcompaniesarb_bot` |
| `X-File/telegram_auth.py` (`CodeDialog`, `QRDialog`, `delivery`) | `woonsh_tools/core/telegram_login.py` | вход в Telegram из GUI (код / QR / 2FA) |
| `X-File/company_directory/*` | **ничего** | это копия кода владельца без скачивания выписок |
| `X-File/company_gemini.py`, `company_keywords.py` | **ничего** | MyMemory-перевод и Grounded Search владелец не просил |

### A.4 `bot_auto.py` (новое — единственный по-настоящему новый модуль фирм)

```
def проверить(гео: list[str], линия: str, stop: Event, log) -> dict:
    # 1. выбрать фирмы как в проверка_ботом.py «список» (статус «выписка», имена без формы, латиница)
    # 2. порциями по 50: Telethon → бот → ответ (таймаут, 1 повтор через 30 с)
    # 3. применить как в проверка_ботом.py «ответ --писать»: дубли → отклонена/Недостойные/удалить файл; прочие → годная
    # 4. вернуть {"годных": n, "отклонено": m, "без ответа": k}
```
Логику шагов 1 и 3 **импортировать** из `проверка_ботом.py`, а не копировать.

### A.5 Текущие файлы агентов

`woonsh_tools/companies/panel.py`, `search.py`, `stats.py` — **удалить** после переноса (владелец отверг).

---

## B. Компании (ЦСВ Вайт) — `woonsh_tools/ads/`

### B.1 Стратегия: разрезать монолит по строкам, логику не трогать

Окно (`class App` 5256–6615) и `BatchWindow` (6638–8076) — tkinter `Tk`/`Toplevel`. В Woonsh окно ЦСВ должно стать
`ttk.Frame` внутри Sidebar. Минимальная правка: `App.__init__(self, root)` уже принимает корень —
передать Frame вместо Tk, убрать `root.title/geometry`. BatchWindow остаётся Toplevel.

| `ppc_gemini.pyw` строки | Что | Куда |
|---|---|---|
| 1–66 | импорты, пути BASE_DIR/OUTPUT_DIR/HISTORY_DIR/AGG_DIR/BATCH_FILE | `ads/paths.py` (корень = папка данных Woonsh или выбранная, `chosen_root` 86) |
| 67–119 | `ident_folder`, `short_path`, `chosen_root`, `output_dir`, `rework_dir` | `ads/paths.py` |
| 120–212 | константы лимитов, KEYWORD_TYPES, HEADLINE_TYPES, бюджет, CSV_HEADERS | `ads/constants.py` |
| 213–381 | DEFAULT_SYSTEM_PROMPT | `ads/prompts.py` |
| 382–539 | AURORA, THEMES, `apply_theme` | **не переносить** — `core/theme.py` |
| 540–596 | `resolve_amount`, `format_amount` | `ads/csv_builder.py` |
| 598–696 | история | `ads/history.py` |
| 697–1007 | STRUCTURES … ACCENTS, `pick_variant`, AGGREGATOR_BRIEF, `variant_brief`, DEFAULT_AGG_PROMPT | `ads/variants.py` (+ агрегатный промпт в `ads/prompts.py`) |
| 1008–1057 | версия и загрузка промпта | `ads/prompts.py` |
| 1058–1126 | RESPONSE_SCHEMA | `ads/schema.py` |
| 1127–1195 | `page_text`, `fetch_landing`, `domain_of`, `load_config`, `save_config` | `ads/landing.py` (+ конфиг → общий cfg Woonsh) |
| 1196–1474 | RateLimited, `_retry_delay`, `_request`, `list_models`, AUTO_MODEL, MODEL_CHAIN, `auto_chain`, `_call_model`, `generate_draft` | `ads/gemini_api.py` — **именно этот код**, сверить и заменить им `core/gemini.py` там, где расходится |
| 1475–2258 | WebSocket, Tab, chrome/CDP, JS_*, `parse_model_json`, FIX_FORMAT_NOTE, `extract_json`, `browser_generate` | `core/cdp.py` (уже перенесено 1475–2016, сверить) + `ads/browser_gen.py` (`browser_generate` 2017–2258) |
| 2259–3165 | DKI_RE, `effective_len`, все BANNED_*, SOFT_*, BANNED_TOPICS, TOPICS_SUSPEND, GEO_SUSPENDED, `_scan_*`, gambling, `scrub_description`, AMBIGUOUS_CATEGORY, SOCIAL_CASINO, FREE_PLAY | `ads/banned.py` |
| 3138–3280 | SNIPPET_TYPES, INFO_INTENT, STRUCTURAL_RE, `_covers_object`, корни слов, `item_keywords`, `headlines_with_keyword`, `bad_symbols`, `shouty_words` | `ads/text_rules.py` |
| 3281–3765 | NON_LATIN_LANGS, COUNTRY_*, LANG_TO_COUNTRY, ENGLISH_MARKERS, `english_ratio`, `country_scores`, TLD_COUNTRY, заметки-гео, TECH_REPAIR, `geo_signals`, `normalize_location`, `defold` | `ads/geo.py` |
| 3766–4342 | `validate`, `_validate_ad`, `_validate_assets` | `ads/validation.py` (+ телефон и ссылка из X-File `policy_issue`) |
| 4343–4484 | `all_ad_texts`, `find_truncations`, `repair_snapshot`, COUNTING_RULE, `build_repair_notes` | `ads/repair.py` |
| 4485–4679 | `render_table`, `tidy_name`, `safe_filename`, `build_rows`, `write_many_csv`, `free_path`, `write_csv` | `ads/csv_builder.py` (+ BUILTIN_NEG) |
| 4680–5124 | AD_SHAPE, AD_SCHEMA, источники, `ad_brief`, `match_groups`, `validate_ads`, `build_ad_rows`, `write_ads_csv` | `ads/rework.py` |
| 5125–5184 | clipboard, контекстное меню | **не переносить** — `core/ui_helpers.py` |
| 5185–5255 | `prompt_is_base`, `show_start_notice` | `ads/panel.py` |
| 5256–6615 | `class App` | `ads/panel.py` → `CompaniesAdsPanel(ttk.Frame)` + переключатель Search/YouTube |
| 6616–6637 | `render_ads` | `ads/panel.py` |
| 6638–8076 | `class BatchWindow` | `ads/batch.py` (+ режим 2/3 колонки, + параллельный `_runner` для API) |
| 8077–8129 | `read_table`, `domain_short` | `ads/batch.py` |
| `prompt_gemini.txt`, `prompt_aggregator.txt` | промпты | `ads/prompts/` (копировать, не править) |

### B.2 Что из X-File

| Источник | Куда |
|---|---|
| `X-File/ads_generator/app.py:51-75` `_NEG`, `BUILTIN_NEG` | `ads/negatives.py` |
| `X-File/ads_generator/app.py:305-320` THINK_LADDER | `ads/gemini_api.py` (только API) |
| `X-File/ads_generator/app.py:251, 743` ThreadPoolExecutor | `ads/batch.py` `_runner` |
| `X-File/ads_generator/app.py` `policy_issue()` — телефон, ссылка/e-mail | `ads/validation.py` |

### B.3 Текущие файлы агентов

`woonsh_tools/ads/panel.py, generator.py, validation.py, settings.py, selectors.py, countries.json` —
это генератор коллеги, владелец отверг. **Заменить** переносом B.1. `ads_countries.json` не нужен (гео у владельца своё).

---

## C. Загрузка Google Disk — `woonsh_tools/drive/` (= коллеге)

| `X-File/x-file.pyw` | Что | Куда |
|---|---|---|
| 1214–1246 `_build_tab_companies` + его обработчики (`on_*` компаний, таблицы Новая/Переименовать/Удалить 1133–1140) | Компании из платёжных профилей | `drive/companies.py` |
| 1247–1304 `_build_tab_match` + сопоставление | Сопоставление PDF | `drive/match_pdf.py` |
| 1305–… `_build_tab_drive`, 289–452 (`find_rclone`, `drive_folder_id`, отмена процессов, `explain_rclone_error` E110–E199, `check_drive`), 851 ссылки в Excel | Загрузка на Drive | `drive/panel.py`, `drive/rclone.py` (дополнить: отмена, понятные ошибки, ссылки в Excel) |
| `rclone_download.py` | скачать rclone | `drive/rclone.py` (есть) |

Разбор «Платёжной информации» — **парсер владельца** `Фирмы/код/парсер_платёжного_профиля.py` (точнее коллеги).

## D. Остальное (= коллеге, уже перенесено)

`profiles/` ← `profile_panel.py`, `profile_store.py`, `profile_scroll.py`;
`documents/` ← `documents_panel.py`, `document_*.py`, `gemini_document.py`, `native_ocr.py`, `windows_ocr.ps1`;
`update/` ← `setup_wizard.py`, `app_update.py`, `installation.py`;
`core/theme.py` ← `visual_system.py` + `apply_theme`; `core/sidebar.py` ← `sidebar_navigation.py`.
