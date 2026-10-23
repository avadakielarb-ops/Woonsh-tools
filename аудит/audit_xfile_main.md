# АУДИТ X-FILE — Полный отчёт
Дата: 2026-10-23

## ОБЩАЯ АРХИТЕКТУРА

### x-file.pyw (2252 строки) — Главное приложение
**Роль:** Монолитный GUI-загрузчик выписок на Google Drive.

**Плюсы:**
- Продуманная система ошибок с кодами (E101–E999) + понятные пользователю сообщения
- Единый event-bus через `queue.Queue` — чистый thread→UI паттерн
- Atomic file writes: `save_json()` использует tmp+replace
- `Procs` класс — управление подпроцессами с cancel, lock, timeout
- Система таблиц (проектов) — несколько списков компаний в одной программе
- Автообнаружение формата профилей: `Название | адрес | сайт` и UPPERCASE
- Умное сопоставление PDF→компания: имя файла → текст PDF → OCR
- Fuzzy-matching с учётом: umlauts (ä=ae), правовых форм (GmbH, Ltd), аббревиатур (e.K.)
- Параллельная загрузка на Drive через `ThreadPoolExecutor(max_workers=3)`
- Проверка размера после загрузки перед удалением из папки
- Удаление в корзину Windows (recoverable) через Shell API
- Полный отчёт об ошибке с версией, зависимостями, логом
- Режим `--self-test` для CI — проверка всех вкладок без сети

**Минусы:**
- Монолит: 2252 строки в одном файле — сложно поддерживать
- Дублирование темы Aurora с X-File-первая-версия/x-file.pyw
- Дублирование `enable_clipboard`, `parse_profiles`, Excel функций
- Нет async — всё через threading + queue
- `_TEXT_CACHE` не ограничен по памяти — может расти без лимита
- `find_tesseract()` проверяет hardcoded пути — не универсально

### X-File-первая-версия/x-file.pyw (944 строки) — Оригинал
**Роль:** Первая версия загрузчика — упрощённая.

**Плюсы:**
- Кастомные чекбоксы через PhotoImage (pixel-perfect)
- Проще и понятнее — хороший quick-start
- `rclone_upload_folder` с `--transfers 10 --checkers 16 --drive-chunk-size 64M` — агрессивная параллелизация

**Минусы:**
- Нет Procs-обёртки — subprocess.run блокирует
- `download_rclone` без проверки SHA-256 — уязвимость при MITM
- `match_score` примитивнее: set intersection без fuzzy
- Переименовывает PDF при сопоставлении — деструктивно, нет отката
- Нет системы таблиц/проектов
- Нет отчёта об ошибках

---

## ДОКУМЕНТЫ (Phantom система)

### documents_panel.py (406 строк) — Архив документов
**Плюсы:**
- SHA-256 дедупликация при архивации
- Atomic: temp file → replace
- DPAPI-шифрование реестра документов
- Синхронизация с папками профилей
- OCR через threading+queue — UI не блокируется

**Минусы:**
- Жёстко привязан к Windows (DPAPI, os.startfile)

### document_fields.py (175 строк) — Извлечение полей
**Плюсы:**
- MRZ парсинг: паспорт (44 символа) + ID-карта TD1 (30 символов)
- Проверка контрольных цифр MRZ (`mrz_check`)
- Испанский DNI — специальный парсинг
- Многоязычный: поиск полей на EN/ES/FR/DE/RU

### document_archive.py (100 строк)
**Плюсы:**
- `safe_name()` — защита от path traversal в архивах
- Лимиты: 20MB/файл, 300MB/архив
- ZIP + RAR поддержка

### document_dedup.py (145 строк)
**Плюсы:**
- `consolidate()` делает backup перед слиянием
- `profile_identity()` — SHA-256 нормализованного имени+компании
- copy→verify→commit→remove — атомарная миграция

### gemini_document.py (46 строк)
**Плюсы:**
- Model fallback chain через `engine.model_order()`
- Лимит 12MB на изображение
- JSON-парсинг ответа

### windows_ocr.ps1 (69 строк)
**Плюсы:**
- Windows Runtime OCR — не требует внешних зависимостей
- Скейлинг до 3x для улучшения распознавания
- Overlapping regions (4 региона с перекрытием 30%)
- Мультиязык: English + user profile languages
- Proper disposal (try/finally)

---

## ЗАГРУЗКА НА DRIVE

### rclone_download.py (70 строк)
**Плюсы:**
- SHA-256 верификация скачанного файла
- GitHub API fallback если основной сайт недоступен
- Atomic install: temp → replace
- PE header check (MZ magic) — не подсунуть не-EXE

### Сравнение: Первая версия vs Новая
| Аспект | Первая версия | X-File (новая) |
|--------|---------------|----------------|
| Скачивание rclone | urllib без проверки | SHA-256 + GitHub fallback |
| Загрузка на Drive | `rclone copy` папкой (10 transfers) | `rclone copyto` пофайлно (3 workers) |
| Ошибки Drive | Сырой stderr | Коды E110–E199, понятные сообщения |
| Отмена | `stop_flag` (bool) | `Procs` с kill() + `threading.Event` |
| После загрузки | Ничего | Проверка размера + Корзина |
| Настройка Drive | Нет | OAuth client_id/secret из DPAPI |

**Вывод:** Новая версия значительно лучше по надёжности. Но первая версия загружает папку целиком с 10 потоками — быстрее для большого количества файлов.

---

## ПРОФИЛИ

### profile_panel.py (463 строки)
**Плюсы:**
- `split_information()` — умный парсинг платёжных данных
- Французские адреса — специальная обработка
- Извлечение postcode из запятых
- Копирование в буфер с авто-очисткой через 30с (секретные поля)
- Google Sheets → export URL конвертация
- SharePoint/OneDrive download link extraction

### profile_store.py (74 строки)
**Плюсы:**
- Windows DPAPI через ctypes — шифрование привязано к пользователю ОС
- JSON + DPAPI — просто и надёжно
- Google Sheets export URL conversion

---

## ПОИСК ФИРМ (X-File)

### company_search.py (476 строк)
**Плюсы:**
- 3 источника: DnB → Реестр → Gemini+Google Search
- Telegram бот (Used Companies) для проверки
- QR-вход + код + 2FA password
- DPAPI для сессии Telegram и Gemini-ключа
- CSV экспорт
- Кэширование проверок через Telegram
- Перевод ключевых слов через MyMemory API
- Сводная таблица по странам с статистикой
- `read_only` mode если хранилище не читается

**Минусы:**
- `importlib.util.spec_from_file_location` для загрузки engine — хрупко
- `urllib.request` для проверки сайтов — нет SSL verification настройки
- `flood_sleep_threshold=0` в Telethon — может привести к бану

### company_directory/search.py (66 строк) — DnB поиск
**Плюсы:**
- Чистое разделение: DnB ищет, фильтр проверяет, emit сохраняет
- Проверка страны по адресу с синонимами
- Обработка payment_profile для полного адреса

### company_directory/dnb.py (391 строка) — Скрапер DnB
**Плюсы:**
- Playwright-автоматизация с fallback на человека (`HumanGate`)
- Закрытие cookie-попапов: TrustArc, OneTrust, generic Close
- Пагинация: 10+ селекторов для кнопки Next
- `enrich_website()` — открывает карточку для сайта и адреса
- `сменить_слово()` — быстрая перезагрузка без перезахода на сайт
- Фильтрация мусора из имени (Business Credit Reports)
- Проверка: `это_сайт_фирмы()` с blocklist

**Минусы:**
- Cyrillic identifiers (`_закрыть_попапы`, `ячейки`) — может путать IDE
- Жёсткие CSS-селекторы DnB — сломаются при редизайне сайта

### company_directory/fallback.py (134 строки) — Реестры стран
**Плюсы:**
- Драйверы для ~20 стран (Finland, UK, Poland, Austria, etc.)
- AI-оценка сайтов: скачивает страницу, отправляет в Gemini с quoted evidence
- `web_candidate()` — blocklist для нерелевантных доменов
- Ручной fallback: если автопоиск не работает, человек вводит данные

---

## UI/СИСТЕМА

### visual_system.py (132 строки)
**Плюсы:**
- Авто-скиннинг через `<Map>` bind + periodic tick (1.2с)
- Авто-назначение Accent/Danger стилей по тексту кнопки
- Замена `messagebox._show` — кастомные диалоги в теме
- Рекурсивный skin для новых виджетов

### sidebar_navigation.py (77 строк)
**Плюсы:**
- Замена стандартного Notebook на sidebar с группировкой
- Секции: ПОИСК ФИРМЫ / Загрузка Google Disk / Google ADS / Документация

### ui_helpers.py (97 строк)
**Плюсы:**
- `clipboard_support()` — Ctrl+A/C/V/X + right-click menu
- `LinkDialog` — ввод URL с кнопкой вставки

### app_update.py (248 строк)
**Плюсы:**
- GitHub Releases updater с SHA-256 проверкой
- PowerShell helper: wait→verify→replace→restart→watchdog(60s)
- Rollback при неудачном обновлении
- `confirm_start()` — токен файл после успешного запуска

**Минусы:**
- GitHub API без аутентификации — не работает в приватном репо
- Нет rate-limit обработки для GitHub API

### build_release.py (60 строк)
**Плюсы:**
- PyInstaller с явным allowlist модулей/данных
- Отклоняет сборку с системными DLL (ucrtbase.dll, api-ms-win-*)
- SHA256SUMS.txt генерация

### installation.py (113 строк)
**Плюсы:**
- Per-user install location management
- `redirect()` — upgrade с любого места запуска

### setup_wizard.py (291 строк)
**Плюсы:**
- 7 шагов: Welcome → rclone → Drive → Gemini → Telegram → Table → Finish
- Анимированный progress bar
- Каждый шаг необязателен, можно пропустить

### telegram_auth.py (76 строк)
**Плюсы:**
- `CodeDialog` с определением метода доставки
- Auto-expire, resend cooldown
- `QRDialog` с qrcode+PIL

---

## КЛЮЧЕВЫЕ ПАТТЕРНЫ ДЛЯ СЛИЯНИЯ

### Что взять из X-File:
1. **Система ошибок E-кодов** — понятные сообщения, отчёт разработчику
2. **Procs класс** — управление подпроцессами с cancel
3. **Документы Phantom** — полная система (MRZ, OCR, DPAPI, дедуп)
4. **Windows OCR** — PowerShell, без внешних зависимостей
5. **rclone_download** с SHA-256 + PE check + GitHub fallback
6. **Setup Wizard** — 7-шаговый мастер
7. **Обновление через GitHub** с rollback
8. **visual_system.py** — авто-скиннинг темы
9. **sidebar_navigation** — вместо tabs
10. **Поиск фирм: DnB + реестры 20 стран** — Playwright автоматизация
11. **Telegram интеграция** — проверка через бота

### Что НЕ брать:
1. Монолитный x-file.pyw — разбить на модули
2. Дублирование кода темы/буфера обмена — вынести в shared
3. Hardcoded Tesseract paths
4. `_TEXT_CACHE` без лимита
5. Cyrillic identifiers в коде (для читаемости за пределами команды)
