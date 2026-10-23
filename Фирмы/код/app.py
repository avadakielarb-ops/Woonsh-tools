"""
ПРИЛОЖЕНИЕ «ФИРМЫ И ВЫПИСКИ» — одно окно, две зоны.

ЛЕВАЯ зона: вкладки (1. Найти фирмы / 2. Скачать выписки / Настройки) + «Ход работы».
ПРАВАЯ зона: «НУЖЕН ЧЕЛОВЕК» — панель ВНУТРИ окна (не всплывающее окно!).
    Пока вмешательство не нужно — серая с подсказкой. Когда движок застрял
    (капча, вход, выбор фирмы) — краснеет и показывает крупные кнопки.

Лог пишется АВТОМАТИЧЕСКИ в папку «логи/» на каждый прогон.
Движок крутится в отдельном потоке, окно не подвисает.

Сборка в .exe:  сборка_exe.bat
"""
from __future__ import annotations

import queue
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from threading import Event

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from common.human import HumanGate, HumanChoice, AbortRun
from common import тема, ввод, пути
from part1 import engine as движок1
from part1.data.countries import СПИСОК as СТРАНЫ
from part1.registry import LocalFileRegistry
from part2 import engine as движок2
from part2.geos.registry import DRIVERS, PLAN
from part3 import поиск_сайтов as движок3

ГЕО = sorted(DRIVERS)

# Цвета правой панели по состоянию — из общей темы, чтобы панель была частью
# окна, а не отдельным ярким пятном. Тревога при этом читается: тёмное вино
# на фиолетовом фоне видно сразу.
ЦВЕТ_ПОКОЙ = тема.ПАНЕЛЬ_ПОКОЙ
ЦВЕТ_ЧЕЛОВЕК = тема.ПАНЕЛЬ_ЧЕЛОВЕК
ЦВЕТ_ДОБОР = тема.ПАНЕЛЬ_ДОБОР


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Фирмы и выписки")
        self.geometry("1240x700")
        self.minsize(1040, 580)
        тема.применить(self)

        self.очередь = queue.Queue()          # сообщения из потока движка в окно
        self.стоп = Event()
        self.пауза = Event()                  # взведён = движок стоит на паузе
        self.поток: threading.Thread | None = None
        self.human: HumanGate | None = None
        self.лог_путь: Path | None = None      # текущий файл автолога
        self._лог_ф = None                     # его открытый дескриптор
        self.папка_выписок: Path | None = None  # папка последнего прогона Части 2

        # низ (Стоп + папки) — прибиваем к низу ДО основной части
        нижн = ttk.Frame(self)
        нижн.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        # Очередь — слева: это не служебная кнопка, а основной способ работы,
        # когда стран много. Разовые запуски остаются на вкладках.
        ttk.Button(нижн, text="🗂  Очередь заданий",
                   command=self._открыть_очередь).pack(side="left")
        ttk.Button(нижн, text="📂 Открыть папку логов",
                   command=self._открыть_логи).pack(side="right", padx=(6, 0))
        self.стоп_кн = ttk.Button(нижн, text="■  Стоп", command=self._стоп, state="disabled")
        self.стоп_кн.pack(side="right")
        self.пауза_кн = ttk.Button(нижн, text="⏸  Пауза", command=self._пауза,
                                   state="disabled")
        self.пауза_кн.pack(side="right", padx=(0, 6))

        # корпус: слева вкладки+лог, справа панель человека
        корпус = ttk.Frame(self)
        корпус.pack(side="top", fill="both", expand=True)

        правая = ttk.Frame(корпус, width=360)
        правая.pack(side="right", fill="y", padx=(0, 10), pady=6)
        правая.pack_propagate(False)          # держать ширину, не сжиматься под контент

        левая = ttk.Frame(корпус)
        левая.pack(side="left", fill="both", expand=True)

        self._вкладки(левая)
        self._лог_панель(левая)
        self._человек_панель(правая)
        self.after(100, self._тик)

    # ---------------- вкладки ----------------

    def _вкладки(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="x", padx=10, pady=(10, 6))

        # --- Часть 1 ---
        f1 = ttk.Frame(nb, padding=12)
        nb.add(f1, text="  1. Найти фирмы  ")
        ttk.Label(f1, text="Слово (пусто = возьму само)").grid(row=0, column=0,
                                                               sticky="w")
        self.слово = ttk.Entry(f1, width=24)
        self.слово.grid(row=0, column=1, padx=6)

        ttk.Label(f1, text="Страна").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.страна = ttk.Combobox(f1, values=СТРАНЫ, width=20, state="readonly")
        self.страна.grid(row=0, column=3, padx=6)
        self.страна.set("Poland")
        self.страна.bind("<<ComboboxSelected>>", self._страна_в_имя_файла)

        ttk.Label(f1, text="Сколько фирм").grid(row=0, column=4, sticky="w", padx=(14, 0))
        self.сколько = ttk.Spinbox(f1, from_=1, to=500, width=6,
                                   command=lambda: self._обновить_подпись_мг())
        self.сколько.grid(row=0, column=5, padx=6)
        self.сколько.set(10)

        ttk.Label(f1, text="Файл Excel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.файл1 = ttk.Entry(f1, width=52)
        self.файл1.grid(row=1, column=1, columnspan=3, sticky="we", padx=6, pady=(10, 0))
        self.файл1.insert(0, "Poland.xlsx")
        ttk.Button(f1, text="Обзор…", command=lambda: self._выбрать(self.файл1)) \
            .grid(row=1, column=4, pady=(10, 0))

        # --- Мультигео: одно слово, несколько стран, ОДИН файл ---
        # Каждая страна ложится на свой лист («23-08 PL»), а Часть 2 потом
        # обходит все листы за один запуск — ради этого файл и общий.
        мг = ttk.Frame(f1)
        мг.grid(row=2, column=0, columnspan=6, sticky="w", pady=(12, 0))
        self.мультигео = tk.BooleanVar(value=False)
        self.мультигео_страны: list[str] = []
        ttk.Checkbutton(мг, text="🌍  Мультигео — несколько стран подряд",
                        variable=self.мультигео,
                        command=self._переключить_мультигео).pack(side="left")
        self.кн_страны = ttk.Button(мг, text="Выбрать страны…",
                                    command=self._выбрать_страны, state="disabled")
        self.кн_страны.pack(side="left", padx=(10, 0))
        self.подпись_мг = ttk.Label(f1, text="", foreground=тема.ТЕМА["muted"])
        self.подпись_мг.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))

        # Обратная задача: собрать фирмы, у которых сайта НЕТ — их потом дожимает
        # Часть 3 (ищет сайт поиском). Пишутся на лист «Без сайта», в реестр не
        # бронируются: без сайта фирма для Google Ads пока не годится.
        self.без_сайта_режим = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1, text="🔎  Искать фирмы БЕЗ сайта (лист «Без сайта», "
                                 "потом Часть 3)",
                        variable=self.без_сайта_режим,
                        command=self._обновить_подпись_мг) \
            .grid(row=4, column=0, columnspan=6, sticky="w", pady=(6, 0))

        self.пуск1 = ttk.Button(f1, text="▶  Найти фирмы", command=self._пуск1,
                                style="Пуск.TButton")
        self.пуск1.grid(row=5, column=0, columnspan=2, sticky="we", pady=(14, 0))

        # --- Часть 2 ---
        f2 = ttk.Frame(nb, padding=12)
        nb.add(f2, text="  2. Скачать выписки  ")
        ttk.Label(f2, text="Гео").grid(row=0, column=0, sticky="w")
        self.гео = ttk.Combobox(f2, values=ГЕО, width=8, state="readonly")
        self.гео.grid(row=0, column=1, padx=6)
        self.гео.set("CZ")
        self.гео.bind("<<ComboboxSelected>>", self._подпись_гео)
        self.гео.bind("<<ComboboxSelected>>", self._гео_в_имя_файла2, add="+")
        self.гео.bind("<<ComboboxSelected>>", self._обновить_листы, add="+")
        self.подпись = ttk.Label(f2, text="", foreground=тема.ТЕМА["muted"])
        self.подпись.grid(row=0, column=2, sticky="w", padx=10)
        self._подпись_гео()

        ttk.Label(f2, text="Файл Excel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.файл2 = ttk.Entry(f2, width=52)
        self.файл2.grid(row=1, column=1, columnspan=3, sticky="we", padx=6, pady=(10, 0))
        from part1.data.countries import CODE_TO_NAME
        self.файл2.insert(0, f"{CODE_TO_NAME.get('CZ', 'Czechia')}.xlsx")
        ttk.Button(f2, text="Обзор…", command=lambda: self._выбрать(self.файл2, self._обновить_листы)) \
            .grid(row=1, column=4, pady=(10, 0))

        ttk.Label(f2, text="Лист").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.лист2 = ttk.Combobox(f2, width=30, state="readonly")
        self.лист2.grid(row=2, column=1, sticky="w", padx=6, pady=(10, 0))
        ttk.Button(f2, text="↻ Обновить листы", command=self._обновить_листы) \
            .grid(row=2, column=2, sticky="w", pady=(10, 0))

        # МУЛЬТИЛИСТ: на одном листе все страны сразу, страна каждой строки —
        # в колонке «Гео». Гео из выпадашки тогда не нужен: он берётся построчно.
        self.мультилист = tk.BooleanVar(value=False)
        ttk.Checkbutton(f2, text="📚  Мультилист — все страны с одного листа за раз "
                                 "(гео берётся из колонки «Гео»)",
                        variable=self.мультилист,
                        command=self._переключить_мультилист) \
            .grid(row=3, column=0, columnspan=5, sticky="w", pady=(10, 0))

        # Без этого на прогоне из 18 стран человек сидит и жмёт «пропустить»
        # по каждой уже готовой стране. Прогон на то и прогон.
        self.только_недостающие = tk.BooleanVar(value=True)
        self.кн_недостающие = ttk.Checkbutton(
            f2, text="⏭  Только недостающие — полностью скачанные гео пропускать "
                     "молча, недокачанные добирать",
            variable=self.только_недостающие, state="disabled")
        self.кн_недостающие.grid(row=4, column=0, columnspan=5, sticky="w",
                                 pady=(2, 0), padx=(24, 0))

        self.пуск2 = ttk.Button(f2, text="▶  Скачать выписки", command=self._пуск2,
                                style="Пуск.TButton")
        self.пуск2.grid(row=5, column=0, columnspan=2, sticky="we", pady=(14, 0))
        # ТРИ ОТДЕЛЬНЫЕ КНОПКИ вместо одной. Одна кнопка «Список фирм и
        # исключения» открывала окно всегда на одной вкладке, и было непонятно,
        # где ты сейчас — исключения или замена. Теперь каждая ведёт прямо туда,
        # куда нужно; окно одно и то же, меняется только открытая вкладка.
        кн_список = ttk.Frame(f2)
        кн_список.grid(row=5, column=2, columnspan=3, sticky="w",
                       padx=(10, 0), pady=(14, 0))
        ttk.Button(кн_список, text="📋  Список фирм",
                   command=lambda: self._список_фирм()).pack(side="left")
        ttk.Button(кн_список, text="⊘  Исключения",
                   command=lambda: self._список_фирм("исключения")
                   ).pack(side="left", padx=6)
        ttk.Button(кн_список, text="🔁  Замена",
                   command=lambda: self._список_фирм("дубликаты")).pack(side="left")

        # кнопки: открыть логи и открыть выписки (последний прогон)
        кн2 = ttk.Frame(f2)
        кн2.grid(row=6, column=0, columnspan=5, sticky="w", pady=(10, 0))
        ttk.Button(кн2, text="📂 Открыть логи",
                   command=self._открыть_логи).pack(side="left")
        ttk.Button(кн2, text="📁 Открыть выписки",
                   command=self._открыть_выписки).pack(side="left", padx=(6, 0))

        # --- Часть 3: найти сайты ---
        f_поиск = ttk.Frame(nb, padding=12)
        nb.add(f_поиск, text="  3. Найти сайты  ")
        ttk.Label(f_поиск, text="Файл Excel (лист «Без сайта»)").grid(row=0, column=0, sticky="w")
        self.файл3 = ttk.Entry(f_поиск, width=52)
        self.файл3.grid(row=0, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Button(f_поиск, text="Обзор…",
                   command=lambda: self._выбрать(self.файл3)).grid(row=0, column=4)
        ttk.Label(f_поиск, text="Страна").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.страна3 = ttk.Combobox(f_поиск, values=СТРАНЫ, width=22, state="readonly")
        self.страна3.grid(row=1, column=1, sticky="w", padx=6, pady=(10, 0))
        self.страна3.set("France")
        ttk.Label(f_поиск, foreground=тема.ТЕМА["muted"],
                  text="Ищет сайт в DuckDuckGo по имени+адресу+стране, сверяет адрес → лист «Нашли сайт».") \
            .grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))
        self.пуск3 = ttk.Button(f_поиск, text="▶  Найти сайты", command=self._пуск3,
                                style="Пуск.TButton")
        self.пуск3.grid(row=3, column=0, columnspan=2, sticky="we", pady=(14, 0))
        кн3 = ttk.Frame(f_поиск)
        кн3.grid(row=4, column=0, columnspan=5, sticky="w", pady=(10, 0))
        ttk.Button(кн3, text="📂 Открыть логи",
                   command=self._открыть_логи).pack(side="left")

        # --- Настройки ---
        f3 = ttk.Frame(nb, padding=12)
        nb.add(f3, text="  Настройки  ")
        ttk.Label(f3, text="Правила отсева — правь и сохраняй:").pack(anchor="w")
        for подпись, файл in [
            ("Чёрный список отраслей (Google Ads)", "part1/data/blacklist_industries.txt"),
            ("Минус-лист брендов", "part1/data/brands.txt"),
            ("Не считать сайтом (соцсети и агрегаторы)", "part1/data/not_a_website.txt"),
            ("Правовые формы по странам", "part1/data/legal_forms.py"),
        ]:
            строка = ttk.Frame(f3)
            строка.pack(fill="x", pady=3)
            ttk.Label(строка, text=подпись, width=42).pack(side="left")
            ttk.Button(строка, text="Открыть",
                       command=lambda p=файл: self._открыть_файл(p)).pack(side="left")
        ttk.Separator(f3).pack(fill="x", pady=8)
        ttk.Button(f3, text="Установить браузер (нужно один раз)",
                   command=self._поставить_браузер).pack(anchor="w", pady=2)
        ttk.Button(f3, text="🗑 Очистить реестр (забыть все фирмы — для тестов)",
                   command=self._очистить_реестр).pack(anchor="w", pady=2)
        ttk.Separator(f3).pack(fill="x", pady=8)
        # Вход руками — в ОБЫЧНОМ Chrome: сайты (Google в первую очередь) не пускают
        # браузер с автоматизацией. Логинимся тут, профиль потом берёт прогон.
        ttk.Label(f3, text="Вход на сайты (Google и прочие не пускают браузер "
                           "с автоматизацией):",
                  foreground=тема.ТЕМА["muted"]).pack(anchor="w")
        ttk.Button(f3, text="🔑 Войти руками — обычный Chrome на профиле гео",
                   command=self._войти_руками).pack(anchor="w", pady=2)
        # ОКНО ПОД CLOUDFLARE. Бывает, что проверка не пропускает вовсе. Тогда
        # порядок такой: открыть окно этой кнопкой, пройти проверку САМОМУ,
        # окно НЕ закрывать — и запустить прогон. Прогон подключается к этому
        # окну и работает в нём, проверка уже пройдена.
        ttk.Button(f3, text="🌐 Открыть Chrome для dnb — пройти проверку самому "
                            "(окно не закрывать!)",
                   command=self._окно_для_dnb).pack(anchor="w", pady=2)
        ttk.Separator(f3).pack(fill="x", pady=8)
        ttk.Label(f3, text="Новое гео — записать действия руками (Playwright codegen):",
                  foreground=тема.ТЕМА["muted"]).pack(anchor="w")
        ttk.Button(f3, text="🎬 Запись действий — Часть 2 (сайт реестра)",
                   command=self._запись).pack(anchor="w", pady=2)
        ttk.Button(f3, text="🎬 Запись действий — Часть 1 (dnb.com)",
                   command=lambda: self._запись(
                       "https://www.dnb.com/business-directory.html")).pack(anchor="w", pady=2)

    def _подпись_гео(self, *_):
        код = self.гео.get()
        имя, волна, способ, _ = PLAN.get(код, ("?", 0, "?", ""))
        как = {"download": "скачивание файла", "print": "печать страницы",
               "template": "заполнение шаблона"}.get(способ, способ)
        self.подпись.config(text=f"{имя} — {как}")

    # ---------------- лог ----------------

    def _лог_панель(self, parent):
        рамка = ttk.LabelFrame(parent, text="Ход работы", padding=6)
        рамка.pack(fill="both", expand=True, padx=10, pady=6)
        # tk.Text ttk не красит — красим сами через общую тему
        self.лог = тема.покрасить(
            tk.Text(рамка, height=14, font=("Consolas", 10), wrap="word"),
            поверхность="surface")
        self.лог.pack(fill="both", expand=True, side="left")
        # копирование из лога тоже должно работать при русской раскладке
        ввод.включить(self.лог, self.слово, self.файл1, self.файл2, self.файл3)
        полоса = ttk.Scrollbar(рамка, command=self.лог.yview)
        полоса.pack(side="right", fill="y")
        self.лог.config(yscrollcommand=полоса.set)
        # Цветные метки строк: глазами видно, где взяли, где отсеяли, где беда.
        self.лог.tag_config("успех", foreground=тема.УСПЕХ)
        self.лог.tag_config("отсев", foreground=тема.ТЕМА["muted"])
        self.лог.tag_config("беда", foreground=тема.ОПАСНОСТЬ)
        self.лог.tag_config("важное", foreground=тема.ЗОЛОТО)
        self.лог.tag_config("раздел", foreground=тема.AURORA[1])

    @staticmethod
    def _метка_строки(текст: str) -> str:
        """По первому символу строки понятно, чем она была — этим и красим."""
        t = текст.lstrip()
        if t.startswith("✔"):
            return "успех"
        if t.startswith("✘"):
            return "беда"
        if t.startswith(("⚠", "⏭")):
            return "важное"
        if t.startswith(("═", "─", "[")) or t.startswith("СВОДКА") or t.startswith("РАЗБОР"):
            return "раздел"
        if t.startswith("·") or t.startswith("  ·"):
            return "отсев"
        return ""

    # ---------------- панель человека (ВНУТРИ окна, справа) ----------------

    def _человек_панель(self, parent):
        self.чп_рамка = tk.Frame(parent, bg=ЦВЕТ_ПОКОЙ)
        self.чп_рамка.pack(fill="both", expand=True)
        self.чп_шапка = tk.Label(self.чп_рамка, bg=ЦВЕТ_ПОКОЙ, fg="white",
                                 font=("Segoe UI", 13, "bold"), wraplength=330,
                                 justify="left", anchor="w")
        self.чп_шапка.pack(side="top", fill="x", padx=14, pady=(14, 6))
        # КНОПКИ прижаты к НИЗУ панели — всегда на виду, даже если текста много
        self.чп_тело = tk.Frame(self.чп_рамка, bg=ЦВЕТ_ПОКОЙ)
        self.чп_тело.pack(side="bottom", fill="x", padx=14, pady=(6, 14))
        # СООБЩЕНИЕ — прокручиваемое (длинный список фирм не выдавит кнопки за экран)
        self.чп_обёртка = tk.Frame(self.чп_рамка, bg=ЦВЕТ_ПОКОЙ)
        self.чп_обёртка.pack(side="top", fill="both", expand=True, padx=(14, 4), pady=(0, 4))
        self.чп_текст = tk.Text(self.чп_обёртка, bg=ЦВЕТ_ПОКОЙ, fg=тема.ТЕМА["ink"],
                                bd=0, highlightthickness=0, wrap="word",
                                cursor="arrow", font=("Segoe UI", 10),
                                selectbackground=тема.AURORA[0],
                                selectforeground="#ffffff")
        self.чп_текст.pack(side="left", fill="both", expand=True)
        self.чп_полоса = ttk.Scrollbar(self.чп_обёртка, command=self.чп_текст.yview)
        self.чп_текст.configure(yscrollcommand=self.чп_полоса.set, state="disabled")
        self._idle_человек()

    def _чп_состояние(self, цвет, шапка, текст):
        """Перекрасить панель, поставить заголовок/сообщение (прокручиваемое), очистить кнопки."""
        for w in (self.чп_рамка, self.чп_шапка, self.чп_тело, self.чп_обёртка):
            w.configure(bg=цвет)
        self.чп_шапка.configure(text=шапка)
        self.чп_текст.configure(bg=цвет, state="normal")
        self.чп_текст.delete("1.0", "end")
        self.чп_текст.insert("1.0", текст)
        self.чп_текст.configure(state="disabled")
        self.after(30, self._обновить_полосу)   # показать полосу, только если не влезло
        for w in self.чп_тело.winfo_children():
            w.destroy()

    def _сигнал(self):
        """
        Позвать человека: звук + окно наверх + МИГАНИЕ в панели задач.

        Раньше здесь был ещё focus_force(), и это вредило: человек решает капчу
        в Chrome, а окно в этот момент выдёргивает клавиатуру себе — символы
        уходят не туда. Поднимаем окно, чтобы вопрос было видно, но фокус не
        отбираем. Мигание нужно на случай, когда человек вообще в другом окне:
        прогон на десять стран идёт часами, и сидеть над ним никто не будет.
        """
        try:
            self.bell()
            self.lift()
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                            ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                            ("dwTimeout", wintypes.DWORD)]

            FLASHW_ALL, FLASHW_TIMERNOFG = 0x00000003, 0x0000000C
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            инфо = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd,
                              FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(инфо))
        except Exception:
            pass          # не Windows или не дали — звука и подъёма достаточно

    def _обновить_полосу(self):
        try:
            if self.чп_текст.yview() != (0.0, 1.0):
                self.чп_полоса.pack(side="right", fill="y")
            else:
                self.чп_полоса.pack_forget()
        except Exception:
            pass

    def _idle_человек(self):
        self._чп_состояние(
            ЦВЕТ_ПОКОЙ, "🧑‍💻  Зона человека",
            "Пока вмешательство не требуется.\n\n"
            "Во время прогона здесь появятся вопросы (капча, вход на сайт, выбор "
            "фирмы) и кнопки. Браузер тоже будет виден — действия делаешь прямо в нём.")

    def _кнопка(self, текст, цвет, актив, команда):
        # relief="flat" вместо "raised": объёмная рамка на тёмной теме выглядит
        # как деталь из другой эпохи и спорит с плоским ttk рядом.
        b = tk.Button(self.чп_тело, text=текст, bg=цвет, fg="white",
                      activebackground=актив, activeforeground="white",
                      font=("Segoe UI", 12, "bold"), relief="flat", bd=0,
                      height=2, cursor="hand2", command=команда)
        b.pack(fill="x", pady=5)
        return b

    def _кнопка_снимка(self, message: str):
        """
        Путь к снимку в тексте почти бесполезен — его надо копировать и искать.
        Если снимок есть, даём кнопку, открывающую его просмотрщиком.
        """
        for строка in message.splitlines():
            if "📸" in строка and ":" in строка:
                путь = строка.split(":", 1)[1].strip()
                if len(путь) > 2 and путь[1] == ":":      # «C:\...» — двоеточие диска
                    путь = строка.split("Снимок экрана:", 1)[-1].strip()
                if Path(путь).exists():
                    self._btn_в_теле("📸  Открыть снимок экрана", *тема.КН_НЕЙТРАЛЬ,
                                     команда=lambda p=путь: self._открыть_в_системе(p))
                return

    def _показать_человека(self, шапка, message):
        self._чп_состояние(ЦВЕТ_ЧЕЛОВЕК, "⏸  " + шапка, message)
        self._кнопка_снимка(message)
        self._кнопка("✓  Продолжить", *тема.КН_УСПЕХ,
                     команда=lambda: self._ответ(HumanChoice.CONTINUE))
        self._кнопка("↷  Пропустить фирму", *тема.КН_НЕЙТРАЛЬ,
                     команда=lambda: self._ответ(HumanChoice.SKIP))
        # Бросить всю страну, но не весь прогон — для мультилиста, где иначе
        # приходилось выбирать между «мучиться» и «остановить 18 стран».
        self._кнопка("⏭  Пропустить всю страну", *тема.КН_ДЕЙСТВИЕ,
                     команда=lambda: self._ответ(HumanChoice.SKIP_GEO))
        self._кнопка("■  Стоп (весь прогон)", *тема.КН_ОПАСНОСТЬ,
                     команда=lambda: self._ответ(HumanChoice.ABORT))
        self._сигнал()

    def _показать_ввод_слова(self, message):
        self._чп_состояние(ЦВЕТ_ДОБОР, "➕  Добор фирм", message)
        поле = tk.Entry(self.чп_тело, font=("Segoe UI", 12),
                        bg=тема.ТЕМА["field"], fg=тема.ТЕМА["field_ink"],
                        insertbackground=тема.ТЕМА["ink"], relief="flat",
                        highlightthickness=1, highlightbackground=тема.ТЕМА["line"],
                        highlightcolor=тема.AURORA[0])
        поле.pack(fill="x", pady=(0, 8), ipady=4)
        поле.focus_set()

        ввод.включить(поле)          # вставка при русской раскладке

        def отправить(*_):
            """
            Вписал слово — ищем по нему. Оставил пусто — берём из запаса.

            Раньше обе кнопки делали одно и то же, и пустое поле означало
            «закончить». Из-за этого добор упирался в человека: чтобы просто
            продолжить, надо было каждый раз придумывать и вбивать слово.
            """
            текст = поле.get().strip()
            self._idle_человек()
            if self.human:
                self.human.answer_keyword(текст)

        def хватит(*_):
            self._idle_человек()
            if self.human:
                from part1.engine import СТОП_ДОБОРА
                self.human.answer_keyword(СТОП_ДОБОРА)

        self._btn_в_теле("🔍  Искать ещё (пусто = возьму из запаса)",
                         *тема.КН_ДЕЙСТВИЕ, команда=отправить)
        self._btn_в_теле("■  Хватит", *тема.КН_НЕЙТРАЛЬ, команда=хватит)
        поле.bind("<Return>", отправить)
        self._сигнал()

    def _btn_в_теле(self, текст, цвет, актив, команда):
        tk.Button(self.чп_тело, text=текст, bg=цвет, fg="white",
                  activebackground=актив, activeforeground="white",
                  font=("Segoe UI", 12, "bold"), relief="flat", bd=0,
                  height=2, cursor="hand2", command=команда).pack(fill="x", pady=5)

    def _показать_меню(self, шапка, message, варианты):
        """Панель с ПРОИЗВОЛЬНЫМИ кнопками (напр. перелистнуть / новое слово)."""
        self._чп_состояние(ЦВЕТ_ЧЕЛОВЕК, "⏸  " + шапка, message)
        self._кнопка_снимка(message)
        цвета = [тема.КН_УСПЕХ, тема.КН_ДЕЙСТВИЕ, тема.КН_НЕЙТРАЛЬ, тема.КН_ОПАСНОСТЬ]
        for i, (ключ, подпись) in enumerate(варианты):
            цвет, актив = цвета[min(i, len(цвета) - 1)]
            self._btn_в_теле(подпись, цвет, актив,
                             команда=lambda k=ключ: self._ответ_меню(k))
        self._сигнал()

    def _ответ_меню(self, ключ: str):
        self._idle_человек()
        if self.human:
            self.human.answer_menu(ключ)

    def _ответ(self, выбор: HumanChoice):
        self._idle_человек()
        if self.human:
            self.human.answer(выбор)

    def _спросить_человека(self, title, message, company):
        """Зовётся из ПОТОКА движка — только кладём в очередь, трогать tk нельзя."""
        self.очередь.put(("человек", (title, message, company)))

    def _спросить_меню(self, title, message, варианты, company):
        """Меню с произвольными кнопками (из потока движка)."""
        self.очередь.put(("меню", (title, message, варианты, company)))

    def _спросить_слово(self, message):
        """Добор: попросить новое слово (из потока)."""
        self.очередь.put(("слово", message))

    # ---------------- запуск ----------------

    # ---------------- мультигео ----------------

    def _переключить_мультигео(self):
        вкл = self.мультигео.get()
        self.кн_страны.config(state="normal" if вкл else "disabled")
        self.страна.config(state="disabled" if вкл else "readonly")
        if вкл:
            from datetime import date
            self.файл1.delete(0, "end")
            self.файл1.insert(0, f"Мультигео {date.today():%d-%m}.xlsx")
            if not self.мультигео_страны:
                self._выбрать_страны()
        else:
            self.подпись_мг.config(text="")
            self._страна_в_имя_файла()
        self._обновить_подпись_мг()

    def _обновить_подпись_мг(self):
        без = getattr(self, "без_сайта_режим", None)
        что = "фирм БЕЗ САЙТА" if (без is not None and без.get()) else "фирм"
        if not self.мультигео.get():
            self.подпись_мг.config(
                text=("Режим: ищу фирмы БЕЗ сайта → лист «Без сайта»"
                      if что != "фирм" else ""))
            return
        if not self.мультигео_страны:
            self.подпись_мг.config(text="Страны не выбраны — нажми «Выбрать страны…»")
            return
        сколько = self.сколько.get()
        куда = ("всё на лист «Без сайта», страна в колонке «Гео»"
                if что != "фирм" else
                "всё в ОДИН лист с датой, страна в колонке «Гео»")
        self.подпись_мг.config(
            text=f"По очереди ({len(self.мультигео_страны)}): "
                 f"{', '.join(self.мультигео_страны)}  —  по {сколько} {что} "
                 f"на страну, {куда}")

    def _выбрать_страны(self):
        """Окошко со списком стран. Порядок обхода — как в списке, сверху вниз."""
        окно = tk.Toplevel(self)
        окно.title("Мультигео: какие страны")
        окно.transient(self)
        окно.grab_set()
        окно.configure(bg=тема.ТЕМА["bg"])   # ttk красит виджеты, но не само окно
        ttk.Label(окно, text="Отметь страны (Ctrl — по одной, Shift — диапазоном).\n"
                             "Часть 1 пройдёт их сверху вниз.",
                  justify="left").pack(anchor="w", padx=12, pady=(12, 6))

        рамка = ttk.Frame(окно)
        рамка.pack(fill="both", expand=True, padx=12)
        полоса = ttk.Scrollbar(рамка)
        полоса.pack(side="right", fill="y")
        # tk.Listbox ttk не красит — как и tk.Text, красим через общую тему
        список = тема.покрасить(
            tk.Listbox(рамка, selectmode="extended", height=14, width=30,
                       exportselection=False, yscrollcommand=полоса.set,
                       activestyle="none", font=("Segoe UI", 10)))
        список.pack(side="left", fill="both", expand=True)
        полоса.config(command=список.yview)
        for с in СТРАНЫ:
            список.insert("end", с)
        for i, с in enumerate(СТРАНЫ):
            if с in self.мультигео_страны:
                список.selection_set(i)

        def ок():
            выбрано = [СТРАНЫ[i] for i in список.curselection()]
            if not выбрано:
                messagebox.showwarning("Пусто", "Отметь хотя бы одну страну", parent=окно)
                return
            self.мультигео_страны = выбрано
            self._обновить_подпись_мг()
            окно.destroy()

        кн = ttk.Frame(окно)
        кн.pack(fill="x", padx=12, pady=12)
        ttk.Button(кн, text="ОК", command=ок).pack(side="left")
        ttk.Button(кн, text="Отмена", command=окно.destroy).pack(side="left", padx=6)
        окно.wait_window()

    def _переключить_мультилист(self):
        """
        В мультилисте лист выбирается руками (тот, что с датой), а гео — нет:
        оно стоит в колонке «Гео» у каждой строки.

        Заодно ПОДСТАВЛЯЕМ нужный файл. Иначе в полях остаётся обычный режим
        («Czech Republic.xlsx», лист «22-07 CZ»), человек жмёт «Скачать» и
        получает «на листе нет колонки Гео» — защита срабатывает правильно,
        но подводить к ней не должно.
        """
        вкл = self.мультилист.get()
        self.гео.config(state="disabled" if вкл else "readonly")
        self.кн_недостающие.config(state="normal" if вкл else "disabled")
        if вкл:
            свежий = self._свежий_мультифайл()
            if свежий:
                self.файл2.delete(0, "end")
                self.файл2.insert(0, свежий)
            else:
                self._лог_из_потока(
                    "Файлов «Мультигео *.xlsx» рядом нет. Сначала собери фирмы "
                    "Частью 1 с галочкой «Мультигео», либо укажи файл вручную.")
        else:
            self._гео_в_имя_файла2()
        self._обновить_листы()

    # ---------------- запуск ----------------

    def _пуск1(self):
        if not self._свободен():
            return
        слово = self.слово.get().strip()
        сколько, файл = int(self.сколько.get()), self._книга(self.файл1)
        без_сайта = self.без_сайта_режим.get()

        if self.мультигео.get():
            if not self.мультигео_страны:
                messagebox.showwarning("Нет стран", "Выбери страны для мультигео")
                return
            страны = list(self.мультигео_страны)
            if not слово:
                слово = self._слово_само(страны[0])
                if not слово:
                    return
            self._старт(lambda h: движок1.run_мультигео(
                слово, страны, сколько, файл, h,
                log=self._лог_из_потока, stop=self.стоп, pause=self.пауза,
                искать_без_сайта=без_сайта))
            return

        if not слово:
            слово = self._слово_само(self.страна.get())
            if not слово:
                return
        self._старт(lambda h: движок1.run(слово, self.страна.get(), сколько, файл, h,
                                          log=self._лог_из_потока, stop=self.стоп,
                                          pause=self.пауза,
                                          искать_без_сайта=без_сайта))

    ФАЙЛ_НОВЫХ = пути.данные("последняя_замена.json")

    def _запомнить_новые(self, лист: str, строки: list[int]) -> None:
        """
        Сохранить, какие строки закрылись последним добором.

        На диск, а не только в память: между добором и проверкой человек может
        закрыть приложение, и список новых фирм не должен пропасть — иначе
        придётся отдавать на проверку весь лист.
        """
        import json
        try:
            self.ФАЙЛ_НОВЫХ.write_text(
                json.dumps({"лист": лист, "строки": строки}, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            self._лог_из_потока(f"(не смог запомнить список новых: {e})")

    def _новые_строки(self, лист: str) -> set:
        import json
        try:
            д = json.loads(self.ФАЙЛ_НОВЫХ.read_text(encoding="utf-8"))
        except Exception:
            return set()
        return set(д.get("строки", [])) if д.get("лист") == лист else set()

    def _добрать_замену(self, файл: Path, лист: str, по_гео: dict) -> None:
        """
        Найти замену освобождённым местам и вписать её В ТЕ ЖЕ СТРОКИ.

        Это третий шаг цикла: вставил дубликаты → освободили места → ДОБРАЛИ
        замену → снова показали список на проверку. Раньше цикл обрывался на
        втором шаге, и человеку предлагалось идти запускать Часть 1 руками,
        выбирая страну и слово на каждую из семи стран.

        Слово на каждую страну берём из запаса (то, что нагенерил Gemini):
        вбивать по слову на страну — та же ручная работа, от которой уходим.
        """
        from part1.data.countries import to_code, СПИСОК as СТРАНЫ_СПИСОК
        from part2 import дубликаты as дуб

        имя_страны = {to_code(с): с for с in СТРАНЫ_СПИСОК}
        задачи = []
        for гео, сколько in sorted(по_гео.items()):
            страна = имя_страны.get(гео)
            if not страна:
                self._лог_из_потока(f"⏭ {гео}: не знаю такой страны — пропускаю")
                continue
            задачи.append((гео, страна, сколько))
        if not задачи:
            return

        всего = sum(с for _, _, с in задачи)
        self._лог_из_потока(
            f"🔎 Ищу замену: {всего} фирм в {len(задачи)} странах "
            + ", ".join(f"{г} {с}" for г, _, с in задачи))

        # какие строки были свободны ДО добора — по ним потом поймём, что нового
        плановые: list[int] = []
        строка_гео: dict[int, str] = {}
        for гео, _, сколько in задачи:
            for р in дуб.свободные_места(файл, лист, гео)[:сколько]:
                плановые.append(р)
                строка_гео[р] = гео

        def работа(h):
            for гео, страна, сколько in задачи:
                if self.стоп.is_set():
                    self._лог_из_потока("Остановлено — остальные страны пропущены.")
                    break
                места = дуб.свободные_места(файл, лист, гео)[:сколько]
                if not места:
                    continue
                слово = self._слово_само(страна)
                if not слово:
                    continue
                self._лог_из_потока(
                    f"\n── {гео} ({страна}): добираю {len(места)} по слову «{слово}»")
                try:
                    # авто_слова: слово дало ноль или кончилось — движок сам
                    # берёт следующее и идёт дальше. Замена на семь стран с
                    # вопросом на каждое слово — это часы вместо минут.
                    движок1.run(слово, страна, len(места), файл, h,
                                log=self._лог_из_потока, stop=self.стоп,
                                pause=self.пауза, лист=лист, свободные=места,
                                авто_слова=True)
                except Exception as e:
                    self._лог_из_потока(f"✘ {гео}: {type(e).__name__}: {e}")
            осталось = {}
            for гео, _, _ in задачи:
                n = len(дуб.свободные_места(файл, лист, гео))
                if n:
                    осталось[гео] = n
            # ЗАПОМИНАЕМ, КАКИЕ СТРОКИ ЗАКРЫЛИСЬ. Это и есть «новонайденные»:
            # были свободны до добора, теперь заняты. Без этого списка человеку
            # пришлось бы отдавать на проверку ВЕСЬ лист — а там сплошь фирмы,
            # которые он уже проверял, и всё покажется дублем.
            новые = sorted(р for р in плановые
                           if р not in set(дуб.свободные_места(
                               файл, лист, строка_гео.get(р, ""))))
            self._запомнить_новые(лист, новые)
            движок2.пересобрать_книги_листа(файл, лист, log=self._лог_из_потока)
            self._лог_из_потока(
                "\n✔ Замена добрана."
                + (f"  ОСТАЛОСЬ НЕЗАКРЫТО: {sum(осталось.values())} "
                   f"({', '.join(f'{г} {n}' for г, n in sorted(осталось.items()))})"
                   if осталось else "  Все места закрыты.")
                + f"\n   Новых фирм: {len(новые)}. Открываю список — включи "
                  "галочку «только новые» и проверь их на дубли.")
            self.after(0, self._список_фирм)

        self._старт(работа)

    def _слово_само(self, страна: str) -> str:
        """
        Слово, когда поле оставлено ПУСТЫМ.

        Раз запас уже настроен, вбивать слово руками на каждый запуск незачем.
        Берём из буфера (то, что нагенерил Gemini), а если он для этой страны
        пуст — тут же просим пополнить. Слово сразу подставляем в поле: видно,
        по чему пошёл прогон, и можно поправить до следующего запуска.
        """
        from part1 import слова as словарь
        from part1.data.countries import to_code
        from part1.запас import Запас
        from очередь import Очередь

        гео = to_code(страна) or страна
        буфер = Запас(log=self._лог_из_потока)
        история = Очередь(log=lambda s: None).история

        if not буфер.свободно(гео):
            self._лог_из_потока(f"🤖 Запас слов для {гео} пуст — прошу у Gemini…")
            try:
                from part1 import слова_gemini as ген
                новые = ген.сгенерировать(гео, 100,
                                          исключить=буфер.все_известные(гео),
                                          log=self._лог_из_потока)
                буфер.пополнить(гео, новые)
            except Exception as e:
                self._лог_из_потока(f"   Gemini не помог ({type(e).__name__}: {e}) "
                                    "— беру из встроенного словаря")

        взято = словарь.предложить(гео, 1, история, буфер=буфер)
        if not взято:
            messagebox.showwarning(
                "Слов не осталось",
                f"Для {гео} кончились и запас, и встроенный словарь.\n\n"
                "Пополни запас: «Очередь заданий» → «🤖 Пополнить запас».")
            return ""
        слово = взято[0]
        self.слово.delete(0, "end")
        self.слово.insert(0, слово)
        self._лог_из_потока(f"🎲 Слово взято само: «{слово}» ({гео}). "
                            f"В запасе осталось: {буфер.свободно(гео)}")
        return слово

    def _пуск2(self):
        if not self._свободен():
            return
        файл = self._книга(self.файл2)
        if not файл.exists():
            messagebox.showwarning("Нет файла", f"Не нахожу {файл}")
            return

        if self.мультилист.get():
            лист = self.лист2.get()
            if not лист:
                messagebox.showwarning(
                    "Нет листа",
                    "Выбери лист с датой — тот, что сделала Часть 1 в мультигео.\n"
                    "Если списка нет, нажми «↻ Обновить листы».")
                return
            недостающие = self.только_недостающие.get()
            self._старт(lambda h: движок2.run_мультилист(
                файл, лист, пути.ВЫПИСКИ, h,
                log=self._лог_из_потока, stop=self.стоп, pause=self.пауза,
                только_недостающие=недостающие))
            return

        лист = self.лист2.get() or None
        self._старт(lambda h: движок2.run(self.гео.get(), файл, пути.ВЫПИСКИ, h,
                                          log=self._лог_из_потока, sheet=лист,
                                          stop=self.стоп, pause=self.пауза))

    def _список_фирм(self, вкладка: str = "исключения"):
        """
        Показать, ЧТО именно пойдёт в работу, и дать список исключений рядом.

        Раньше единственный способ узнать состав прогона — запустить его и
        смотреть в лог по одной фирме. А заведомо ненужные (школы, союзы, уже
        забракованные руками) приходилось терпеть каждый раз: скрипт лез в
        реестр, тратил минуты и всё равно отказывал.
        """
        from part2.исключения import Исключения
        файл = self._книга(self.файл2)
        self._искл_путь = Исключения().path        # чтобы было видно в логе
        if not файл.exists():
            messagebox.showwarning("Нет файла", f"Не нахожу {файл}")
            return
        лист = self.лист2.get() or None
        фильтр = None if self.мультилист.get() else self.гео.get()

        try:
            строки = движок2.состав_прогона(файл, лист, фильтр)
        except Exception as e:
            messagebox.showwarning("Не прочитал", f"{type(e).__name__}: {e}")
            return

        искл = Исключения()
        окно = tk.Toplevel(self)
        окно.title(f"Состав прогона — {файл.name}"
                   + (f", лист «{лист}»" if лист else ""))
        окно.geometry("1000x620")
        тема.покрасить(окно)

        рамка = ttk.Frame(окно, padding=10)
        рамка.pack(fill="both", expand=True)
        рамка.columnconfigure(0, weight=3)
        рамка.columnconfigure(1, weight=2)
        рамка.rowconfigure(1, weight=1)

        # ЛЕВАЯ ПАНЕЛЬ — ТОЛЬКО НАЗВАНИЯ, по одному в строке, без гео и пометок.
        # Она нужна для копипаста: список уходит на сторону, там проверяется, не
        # брали ли эти фирмы раньше, и возвращается обратно. Любая приписка
        # («⊘», код страны) этот путь ломает — её пришлось бы вычищать руками.
        шапка_л = ttk.Frame(рамка)
        шапка_л.grid(row=0, column=0, sticky="we")
        ttk.Label(шапка_л, text="Гео:").pack(side="left")
        выбор_гео = ttk.Combobox(шапка_л, width=8, state="readonly",
                                 values=["все"] + sorted({с["гео"] for с in строки
                                                          if с["гео"]}))
        выбор_гео.set("все")
        выбор_гео.pack(side="left", padx=(4, 12))
        только_рабочие = tk.BooleanVar(value=True)
        ttk.Checkbutton(шапка_л, text="только те, что пойдут в работу",
                        variable=только_рабочие).pack(side="left")
        # ТОЛЬКО НОВЫЕ — те, что подобрались последним добором. Отдавать на
        # проверку весь лист бессмысленно: там сплошь уже проверенные фирмы,
        # и в ответ придёт «всё дубль». Нужны именно новонайденные.
        новые_строки = self._новые_строки(лист or "")
        только_новые = tk.BooleanVar(value=bool(новые_строки))
        кн_новые = ttk.Checkbutton(
            шапка_л, text=f"⭐ только НОВЫЕ ({len(новые_строки)})",
            variable=только_новые,
            state=("normal" if новые_строки else "disabled"))
        кн_новые.pack(side="left", padx=(12, 0))
        счёт = ttk.Label(шапка_л, text="", foreground=тема.ТЕМА["muted"])
        счёт.pack(side="left", padx=10)

        правая = ttk.Notebook(рамка)
        стр_искл = ttk.Frame(правая)
        стр_дубли = ttk.Frame(правая)
        правая.add(стр_искл, text="  ⊘ Исключения  ")
        правая.add(стр_дубли, text="  🔁 Замена  ")
        правая.select(1 if вкладка == "дубликаты" else 0)

        левый = tk.Text(рамка, wrap="none", height=25)
        левый.grid(row=1, column=0, sticky="nsew", pady=(4, 6))
        тема.покрасить(левый)
        правая.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(4, 6))

        ttk.Label(стр_искл, text="Не искать вовсе. Вставляй списком (Ctrl+V)",
                  foreground=тема.ТЕМА["muted"]).pack(anchor="w", padx=6, pady=(6, 2))
        правый = tk.Text(стр_искл, wrap="none", width=40)
        правый.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        тема.покрасить(правый)
        правый.insert("end", искл.как_текст())

        ttk.Label(стр_дубли,
                  text="Уже использовались. Найду гео, освобожу место,\n"
                       "уберу старые выписки — Часть 1 доберёт замену.",
                  foreground=тема.ТЕМА["muted"]).pack(anchor="w", padx=6, pady=(6, 2))
        дубли = tk.Text(стр_дубли, wrap="none", width=40)
        дубли.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        тема.покрасить(дубли)

        # БУФЕР ОБМЕНА. Tk вешает Ctrl+V на СИМВОЛ «v»; на русской раскладке та
        # же клавиша шлёт «м», и вставка не работает вообще — ни сочетанием, ни
        # правой кнопкой. Привязываем по КОДУ клавиши и добавляем явную кнопку.
        ввод.включить(правый, дубли, левый)

        def кнопки_поля(родитель, поле, чистить=True):
            ряд = ttk.Frame(родитель)
            ряд.pack(fill="x", padx=6, pady=(0, 6))

            def вставить():
                n = ввод.вставить(поле)
                self._лог_из_потока(
                    f"📥 Вставлено строк: {n}" if n
                    else "📥 Буфер обмена пуст — нечего вставлять.")

            def убрать_выделенные():
                """Ошибочно вставил — убери. Без этого исправить список можно
                было только вычистив поле целиком и набрав заново."""
                д = поле.tag_ranges("sel")
                if not д:
                    messagebox.showinfo("Ничего не выделено",
                                        "Выдели строки в списке мышкой.",
                                        parent=окно)
                    return
                убрано = len([с for с in поле.get(д[0], д[1]).splitlines()
                              if с.strip()])
                поле.delete(д[0], д[1])
                # подчистить пустые строки, оставшиеся от удаления
                текст = "\n".join(с for с in poле_строки(поле) if с.strip())
                поле.delete("1.0", "end")
                поле.insert("end", текст)
                self._лог_из_потока(f"🗑 Убрано строк: {убрано}. "
                                    "Нажми «Сохранить и проверить».")

            ttk.Button(ряд, text="📥 Вставить",
                       command=вставить).pack(side="left")
            ttk.Button(ряд, text="🗑 Убрать выделенные",
                       command=убрать_выделенные).pack(side="left", padx=4)
            if чистить:
                ttk.Button(ряд, text="🧹 Очистить всё",
                           command=lambda: поле.delete("1.0", "end")).pack(side="left")

        def poле_строки(поле):
            return поле.get("1.0", "end").splitlines()

        кнопки_поля(стр_искл, правый)
        кнопки_поля(стр_дубли, дубли)

        видимые: list[dict] = []

        def сколько_свободно() -> dict:
            """
            Освобождённые места по гео: строка с «№» и «Гео», но без фирмы.

            Это ГЛАВНЫЙ показатель после чистки дубликатов — сколько ещё надо
            добрать Частью 1. Без него состояние листа не видно вовсе: фирма
            исчезла, а понять, осталось ли за ней место, было нельзя.
            """
            from part2 import дубликаты as дуб
            итог = {}
            for г in sorted({с["гео"] for с in строки if с["гео"]}):
                n = len(дуб.свободные_места(файл, лист or "", г))
                if n:
                    итог[г] = n
            return итог

        def перерисовать(*_):
            искл.загрузить()
            г = выбор_гео.get()
            видимые.clear()
            for с in строки:
                if г != "все" and с["гео"] != г:
                    continue
                if только_новые.get() and с["строка"] not in новые_строки:
                    continue
                if только_рабочие.get() and искл.исключена(с["имя"], с["гео"]):
                    continue
                видимые.append(с)
            левый.delete("1.0", "end")
            левый.insert("end", "\n".join(с["имя"] for с in видимые))
            всего = len(строки)
            мимо = sum(1 for с in строки if искл.исключена(с["имя"], с["гео"]))
            своб = сколько_свободно()
            хвост = ""
            if своб:
                хвост = ("  ·  СВОБОДНО МЕСТ " + str(sum(своб.values())) + ": "
                         + ", ".join(f"{г} {n}" for г, n in sorted(своб.items())))
            метка = "⭐ НОВЫЕ" if только_новые.get() else "показано"
            счёт.config(text=f"{метка} {len(видимые)}  ·  на листе {всего}"
                             f"  ·  исключено {мимо}{хвост}")

        выбор_гео.bind("<<ComboboxSelected>>", перерисовать)
        только_рабочие.trace_add("write", lambda *_: перерисовать())
        только_новые.trace_add("write", lambda *_: перерисовать())
        перерисовать()

        низ = ttk.Frame(рамка)
        низ.grid(row=2, column=0, columnspan=2, sticky="we")

        def копировать():
            текст = "\n".join(с["имя"] for с in видимые)
            self.clipboard_clear()
            self.clipboard_append(текст)
            self._лог_из_потока(f"📋 Скопировал {len(видимые)} названий "
                                "в буфер обмена (чистые, без гео).")

        def применить():
            """
            Сохранить вставленный список и СРАЗУ показать, что он поймал.

            Проверка идёт ПО ГЕО: у вставленных названий страны нет, поэтому
            сопоставляем их с листом и говорим, сколько фирм отсеялось в каждой
            стране. Иначе вставил двести строк — и не знаешь, попали они хоть
            во что-нибудь или ты скопировал не тот столбец.
            """
            новый = правый.get("1.0", "end").strip()
            # ЗАЩИТА ОТ СЛУЧАЙНОГО ОБНУЛЕНИЯ. Пустое поле при непустом файле —
            # почти всегда промах (открыл окно, поработал в другой вкладке,
            # нажал «Сохранить»). Восемнадцать записей с гео так и пропали.
            if not новый and искл.строки:
                if not messagebox.askyesno(
                        "Стереть все исключения?",
                        f"Поле пустое, а в файле {len(искл.строки)} записей.\n"
                        "Сохранить пустой список — значит стереть их все.\n\n"
                        "Точно стереть?", parent=окно):
                    return
            искл.сохранить(новый)
            по_гео: dict[str, int] = {}
            for с in строки:
                if искл.исключена(с["имя"], с["гео"]):
                    по_гео[с["гео"] or "--"] = по_гео.get(с["гео"] or "--", 0) + 1
            всего = sum(по_гео.values())
            разбивка = ", ".join(f"{г} {n}" for г, n in sorted(по_гео.items()))
            self._лог_из_потока(
                f"⊘ Исключения сохранены: {len(искл.строки)} строк → {искл.path}\n"
                f"   Поймано на листе: {всего} фирм" +
                (f"  ({разбивка})" if разбивка else
                 "  — НИ ОДНОЙ. Проверь, те ли названия вставлены."))
            перерисовать()

        def выделенные_в(поле):
            """Выделенные слева строки — в правое поле. Без этого добавить
            одну неподошедшую фирму можно было только перепечатав её руками."""
            диапазон = левый.tag_ranges("sel")
            if not диапазон:
                messagebox.showinfo("Ничего не выделено",
                                    "Выдели строки слева мышкой.", parent=окно)
                return
            имена = [с.strip() for с in
                     левый.get(диапазон[0], диапазон[1]).splitlines() if с.strip()]
            if not имена:
                return
            хвост = "\n" if поле.get("1.0", "end").strip() else ""
            поле.insert("end", хвост + "\n".join(имена))
            self._лог_из_потока(f"   добавлено строк: {len(имена)}")

        def заменить_дубликаты():
            """
            Дубликаты → освободить места и убрать их выписки.

            Скачивание здесь НЕ запускаем намеренно: сперва Часть 1 доберёт
            замену, потом список снова уходит на проверку, и только когда в нём
            не останется использованных — качаем. Так просил хозяин, и так
            правильно: качать выписки на фирму, которую потом выкинут, — это
            выброшенные минуты и сожжённая бронь.
            """
            from part2 import дубликаты as дуб
            имена = [с.strip() for с in дубли.get("1.0", "end").splitlines()
                     if с.strip()]
            if not имена:
                # ПУСТОЕ ПОЛЕ + ЕСТЬ СВОБОДНЫЕ МЕСТА = «просто добери».
                # Часть 2 сама освобождает строки, когда фирма ликвидирована,
                # с негодной формой или не нашлась. Вставлять туда нечего —
                # список уже пуст, — а места стоят и ждут. Раньше кнопка на это
                # отвечала «вставь названия», и добор приходилось запускать
                # окольным путём.
                свободно = сколько_свободно()
                if свободно:
                    свод = ", ".join(f"{г} {n}" for г, n in sorted(свободно.items()))
                    if messagebox.askyesno(
                            "Добрать замену",
                            f"Список дубликатов пуст, но на листе есть "
                            f"освобождённые места:\n\n"
                            f"СВОБОДНО {sum(свободно.values())}  ({свод})\n\n"
                            "Их освободила Часть 2 — там фирмы оказались "
                            "ликвидированы, с негодной формой или не нашлись.\n\n"
                            "Добрать замену сейчас?", parent=окно):
                        окно.destroy()
                        self._добрать_замену(файл, лист or "", свободно)
                    return
                messagebox.showinfo(
                    "Пусто", "Вставь названия дубликатов — или дождись, пока "
                    "Часть 2 освободит места сама.", parent=окно)
                return
            итог = дуб.найти(файл, лист or "", имена)
            нашли, не_нашли = итог["нашли"], итог["не_нашли"]
            if не_нашли:
                self._лог_из_потока(
                    f"🔁 На листе не нашлось {len(не_нашли)} названий: "
                    + ", ".join(не_нашли[:5]) + ("…" if len(не_нашли) > 5 else ""))
            if not нашли:
                # ПО ИМЕНАМ НЕ НАШЛОСЬ — но это ещё не тупик.
                # После освобождения строка на листе ПУСТАЯ, и найти её по имени
                # нельзя в принципе. Раньше здесь показывалось «проверь, тот ли
                # лист», человек жал кнопку снова и снова, а работа стояла.
                # Главное — есть ли СВОБОДНЫЕ МЕСТА: если есть, значит освобождение
                # уже прошло и надо просто добирать замену. Это и предлагаем.
                свободно = сколько_свободно()
                if свободно:
                    свод = ", ".join(f"{г} {n}" for г, n in sorted(свободно.items()))
                    if messagebox.askyesno(
                            "Места уже освобождены",
                            f"По именам ничего не нашлось — эти строки уже "
                            f"освобождены раньше, поэтому по названию они не "
                            f"ищутся.\n\n"
                            f"СВОБОДНО МЕСТ: {sum(свободно.values())}  ({свод})\n\n"
                            "Добрать замену прямо сейчас?", parent=окно):
                        дубли.delete("1.0", "end")
                        окно.destroy()
                        self._добрать_замену(файл, лист or "", свободно)
                    return
                messagebox.showwarning(
                    "Ни одного совпадения",
                    "Ни одно из названий не нашлось на листе, и свободных мест "
                    "тоже нет.\n"
                    "Проверь, тот ли лист выбран и те ли названия вставлены.",
                    parent=окно)
                return
            разбивка = {}
            for с in нашли:
                разбивка[с["гео"]] = разбивка.get(с["гео"], 0) + 1
            текст = ", ".join(f"{г}: {n}" for г, n in sorted(разбивка.items()))
            if not messagebox.askyesno(
                    "Заменить дубликаты",
                    f"Нашёл на листе: {len(нашли)} фирм\n{текст}\n\n"
                    "Что будет:\n"
                    "1. данные этих строк сотрутся (место за страной останется)\n"
                    "2. их старые выписки удалятся\n"
                    "3. Часть 1 найдёт замену и впишет её в эти же строки\n"
                    "4. покажу обновлённый список — проверишь его на дубли\n\n"
                    "Выписки НЕ качаются: сперва список должен стать чистым.\n\n"
                    "Продолжить?", parent=окно):
                return
            папка = движок2.папка_листа(пути.ВЫПИСКИ, лист or "")
            по_гео = дуб.освободить(файл, лист or "", нашли, папка,
                                    log=self._лог_из_потока)
            # книга в папке выписок — копия рабочей. Заменили фирму в листе —
            # значит и из копии она должна исчезнуть, иначе в Ads уедет фирма,
            # которой в работе уже нет.
            движок2.пересобрать_книги_листа(файл, лист or "",
                                            log=self._лог_из_потока)
            искл.сохранить(искл.как_текст() + "\n"
                           + "\n".join(f"{с['гео']}: {с['имя']}" for с in нашли))
            правый.delete("1.0", "end")
            правый.insert("end", искл.как_текст())
            дубли.delete("1.0", "end")
            свод = ", ".join(f"{г} {n}" for г, n in sorted(по_гео.items()))
            self._лог_из_потока(
                f"🔁 Освобождено мест: {sum(по_гео.values())}  ({свод})\n"
                "   Они добавлены в исключения — второй раз не попадутся.")
            окно.destroy()
            self._добрать_замену(файл, лист or "", по_гео)

        ttk.Button(низ, text="📋 Копировать названия",
                   command=копировать).pack(side="left")
        ttk.Button(низ, text="⊘ Выделенные → в исключения",
                   command=lambda: выделенные_в(правый)).pack(side="left", padx=6)
        ttk.Button(низ, text="🔁 Выделенные → в дубликаты",
                   command=lambda: выделенные_в(дубли)).pack(side="left")
        ttk.Button(низ, text="💾 Сохранить и проверить", command=применить,
                   style="Пуск.TButton").pack(side="left", padx=(12, 0))
        ttk.Button(низ, text="🔁 Заменить дубликаты",
                   command=заменить_дубликаты).pack(side="left", padx=6)
        ttk.Button(низ, text="Закрыть", command=окно.destroy).pack(side="right")

    def _пуск3(self):
        if not self._свободен():
            return
        файл = self._книга(self.файл3)
        if not файл.exists():
            messagebox.showwarning("Нет файла", f"Не нахожу {файл}")
            return
        страна = self.страна3.get().strip()
        self._старт(lambda h: движок3.run(файл, h, страна=страна,
                                          log=self._лог_из_потока,
                                          stop=self.стоп, pause=self.пауза))

    def _открыть_очередь(self):
        """
        Окно очереди одно на приложение: два списка заданий на один файл
        состояния — верный способ затереть один другим.
        """
        окно = getattr(self, "_окно_очереди", None)
        if окно is not None and окно.winfo_exists():
            окно.deiconify()
            окно.lift()
            окно.focus_force()
            return
        from окно_очереди import ОкноОчереди
        self._окно_очереди = ОкноОчереди(self)

    def _свободен(self) -> bool:
        if self.поток and self.поток.is_alive():
            messagebox.showinfo("Занято", "Дождись конца текущего прогона или нажми «Стоп»")
            return False
        return True

    def _старт(self, работа, книга=None, лист=None):
        """
        Запустить прогон в потоке.

        книга/лист — что выгрузить в таблицу ПОСЛЕ прогона. Выгрузка живёт
        здесь, а не в каждой кнопке, потому что через _старт проходит любой
        режим: одиночное гео, мультигео, мультилист, добор. Забыть её в одном
        из них — значит снова получить «приложение что-то делает, а картины в
        таблице нет».
        """
        self.лог.delete("1.0", "end")
        self.стоп.clear()
        self.пауза.clear()
        self.пауза_кн.config(text="⏸  Пауза", state="normal")
        self._открыть_автолог()
        self.human = HumanGate(ui_ask=self._спросить_человека,
                               ui_keyword=self._спросить_слово,
                               ui_menu=self._спросить_меню)
        self.пуск1.config(state="disabled")
        self.пуск2.config(state="disabled")
        self.пуск3.config(state="disabled")
        self.стоп_кн.config(state="normal")

        def обёртка():
            выгружать = False
            try:
                рез = работа(self.human)
                if isinstance(рез, dict) and рез.get("папка"):
                    self.очередь.put(("папка", рез["папка"]))
                выгружать = True
            except AbortRun:
                # ОСТАНОВКА — НЕ ПАДЕНИЕ. Человек нажал «Стоп» на середине:
                # найденное уже лежит в Excel, и в таблице ему тоже место.
                self.очередь.put(("лог", "Остановлено."))
                выгружать = True
            except Exception as e:
                # А вот после падения не выгружаем: состояние неясное, лучше
                # разобраться, чем закрепить половину результата.
                self.очередь.put(("лог", f"ОШИБКА: {type(e).__name__}: {e}"))
            finally:
                if книга and лист and выгружать:
                    try:
                        from выгрузка import выгрузить
                        выгрузить(Path(книга), лист, self._лог_из_потока)
                    except Exception as e:
                        self.очередь.put((
                            "лог", f"⚠ в таблицу не выгрузилось: "
                                   f"{type(e).__name__}: {e}\n"
                                   f"   Данные в Excel на месте, "
                                   f"выгрузку можно повторить."))
                self.очередь.put(("конец", None))

        self.поток = threading.Thread(target=обёртка, daemon=True)
        self.поток.start()

    def _пауза(self):
        """Одна кнопка-переключатель: Пауза ⇄ Возобновить."""
        if self.пауза.is_set():
            self.пауза.clear()
            self.пауза_кн.config(text="⏸  Пауза")
            self._лог_из_потока("▶ Продолжаю.")
        else:
            self.пауза.set()
            self.пауза_кн.config(text="▶  Возобновить")
            self._лог_из_потока("⏸ Пауза: доработаю текущую фирму и встану.")

    def _стоп(self):
        self.стоп.set()
        self.пауза.clear()                 # снимаем паузу, иначе движок не дойдёт до стопа
        if self.human:
            self.human.answer(HumanChoice.ABORT)
        self._лог_из_потока("Останавливаюсь…")

    def _лог_из_потока(self, текст):
        self.очередь.put(("лог", str(текст)))

    # ---------------- автолог ----------------

    def _открыть_автолог(self):
        """Начать писать лог прогона в файл автоматически."""
        try:
            папка = Path("логи")
            папка.mkdir(exist_ok=True)
            self.лог_путь = папка / f"лог_{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
            self._лог_ф = open(self.лог_путь, "w", encoding="utf-8")
            self._лог_из_потока(f"📝 Лог пишется автоматически: {self.лог_путь}")
        except Exception as e:
            self.лог_путь, self._лог_ф = None, None
            self._лог_из_потока(f"(не удалось открыть файл лога: {e})")

    def _закрыть_автолог(self):
        if self._лог_ф:
            try:
                self._лог_ф.close()
            except Exception:
                pass
        self._лог_ф = None

    def _открыть_логи(self):
        self._открыть_в_проводнике(Path("логи"))

    def _открыть_выписки(self):
        # папка последнего прогона Части 2; если ещё не было — корень «выписки»
        цель = self.папка_выписок if (self.папка_выписок and self.папка_выписок.exists()) \
            else пути.ВЫПИСКИ
        if not цель.exists():
            messagebox.showinfo("Нет выписок",
                                "Папка выписок появится после первого прогона Части 2.")
            return
        self._открыть_в_проводнике(цель)

    @staticmethod
    def _открыть_в_проводнике(папка: Path):
        папка.mkdir(parents=True, exist_ok=True)
        p = str(папка.resolve())
        if sys.platform == "win32":
            subprocess.Popen(["explorer", p])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])

    # ---------------- насос очереди (главный поток) ----------------

    def _тик(self):
        while not self.очередь.empty():
            вид, данные = self.очередь.get()
            if вид == "лог":
                self.лог.insert("end", данные + "\n", self._метка_строки(данные))
                self.лог.see("end")
                if self._лог_ф:                       # дублируем строку в файл
                    try:
                        self._лог_ф.write(данные + "\n")
                        self._лог_ф.flush()
                    except Exception:
                        pass
            elif вид == "человек":
                title, message, company = данные
                шапка = f"{title}" + (f"  ·  {company}" if company else "")
                self._показать_человека(шапка, message)
            elif вид == "меню":
                title, message, варианты, company = данные
                шапка = f"{title}" + (f"  ·  {company}" if company else "")
                self._показать_меню(шапка, message, варианты)
            elif вид == "слово":
                self._показать_ввод_слова(данные)
            elif вид == "папка":                      # папка выписок последнего прогона
                try:
                    self.папка_выписок = Path(данные)
                except Exception:
                    pass
            elif вид == "конец":
                self.пуск1.config(state="normal")
                self.пуск2.config(state="normal")
                self.пуск3.config(state="normal")
                self.стоп_кн.config(state="disabled")
                self.пауза.clear()
                self.пауза_кн.config(text="⏸  Пауза", state="disabled")
                self._idle_человек()
                self._закрыть_автолог()
        self.after(100, self._тик)

    # ---------------- мелочи ----------------

    def _книга(self, поле) -> Path:
        """
        Книга Excel из поля ввода.

        В поле обычно голое имя («Мультигео 23-08.xlsx»), а книги лежат в папке
        «фирмы». Раз рабочая папка — корень проекта, голое имя искалось бы в
        корне и не находилось. Полный путь (после «Обзор…») оставляем как есть.
        """
        сырое = (поле.get() or "").strip()
        п = Path(сырое)
        return п if п.parent != Path(".") else пути.фирмы(сырое)

    def _выбрать(self, поле, после=None):
        p = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if p:
            поле.delete(0, "end")
            поле.insert(0, p)
            if после:
                после()

    def _открыть_файл(self, путь):
        """Открыть В РЕДАКТОРЕ — для списков правил (txt, py)."""
        p = Path(путь)
        if not p.exists():
            messagebox.showwarning("Нет файла", str(p))
            return
        if sys.platform == "win32":
            subprocess.Popen(["notepad", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _открыть_в_системе(self, путь):
        """
        Открыть тем, чем открывает система. Отдельно от _открыть_файл, потому
        что тот зовёт БЛОКНОТ — правильно для правил-txt и мусор для PNG.
        """
        p = Path(путь)
        if not p.exists():
            messagebox.showwarning("Нет файла", str(p))
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(p))          # ассоциация Windows
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showwarning("Не открылось", f"{p}\n\n{e}")

    def _обновить_листы(self, *_):
        """
        Прочитать листы выбранного Excel-файла в выпадающий список.

        В режиме МУЛЬТИЛИСТА показываем ТОЛЬКО листы с колонкой «Гео» — по
        остальным Часть 2 работать не может, и подсовывать их в выбор значит
        подводить человека под ошибку «нет заполненной колонки Гео».
        """
        файл = self._книга(self.файл2)
        if not файл.exists():
            self.лист2["values"] = []
            self.лист2.set("")
            return
        мульти = getattr(self, "мультилист", None) is not None and self.мультилист.get()
        try:
            from openpyxl import load_workbook
            wb = load_workbook(файл, read_only=True)
            все = [s for s in wb.sheetnames if s not in ("Лог", "Без сайта", "Нашли сайт")]
            листы = []
            for имя in все:
                if not мульти:
                    листы.append(имя)
                    continue
                шапка = next(wb[имя].iter_rows(min_row=1, max_row=1), ())
                if any((c.value or "") == "Гео" for c in шапка):
                    листы.append(имя)
            wb.close()
            self.лист2["values"] = листы
            if not листы:
                self.лист2.set("")
                if мульти:
                    self._лог_из_потока(
                        f"В файле {файл.name} нет мультилистов (листов с колонкой «Гео»). "
                        "Их делает Часть 1 с галочкой «Мультигео».")
                return
            if мульти:
                self.лист2.set(листы[-1])          # самый свежий мультилист
            else:
                гео = self.гео.get()
                свои = [s for s in листы if s.endswith(f" {гео}")]
                self.лист2.set(свои[-1] if свои else листы[-1])
        except Exception as e:
            self.лист2["values"] = []
            messagebox.showwarning("Не читается", f"Не смог прочитать листы:\n{e}")

    def _гео_в_имя_файла2(self, *_):
        """При выборе гео в Части 2 имя файла = стране (совпадает с Частью 1)."""
        if getattr(self, "мультилист", None) is not None and self.мультилист.get():
            return          # в мультилисте файл общий — не перетираем именем страны
        from part1.data.countries import CODE_TO_NAME
        имя = CODE_TO_NAME.get(self.гео.get(), "")
        if имя:
            self.файл2.delete(0, "end")
            self.файл2.insert(0, f"{имя}.xlsx")

    def _свежий_мультифайл(self) -> str:
        """
        Самый свежий файл мультигео в папке проекта. Его делает Часть 1,
        имя вида «Мультигео 23-08.xlsx».
        """
        файлы = sorted(пути.ФИРМЫ.glob("Мультигео *.xlsx"),
                       key=lambda p: p.stat().st_mtime)
        return файлы[-1].name if файлы else ""

    def _страна_в_имя_файла(self, *_):
        """При выборе страны имя Excel-файла становится = стране."""
        if getattr(self, "мультигео", None) is not None and self.мультигео.get():
            return          # в мультигео файл общий — не перетираем его именем страны
        имя = self.страна.get().strip()
        if имя:
            self.файл1.delete(0, "end")
            self.файл1.insert(0, f"{имя}.xlsx")

    def _очистить_реестр(self):
        реестр = LocalFileRegistry(log=self._лог_из_потока)
        n = реестр.очистить()
        messagebox.showinfo(
            "Реестр очищен",
            f"Забыто фирм: {n}. Теперь программа снова найдёт те же фирмы.\n\n"
            f"Снимок ДО очистки сохранён в {реестр.бэкапы} — если нажал случайно, "
            "оттуда можно вернуть.")

    def _запись(self, стартовый_url: str = ""):
        """
        Playwright codegen: открывает браузер + окно записи. Человек делает шаги
        руками (поиск, клики, скачивание) — Playwright пишет готовый Python-код.
        Этот код пользователь присылает — из него делаем драйвер гео.
        стартовый_url — для Части 1 передаём dnb.com.
        """
        from tkinter import simpledialog
        from part2.geos.registry import DRIVERS
        гео = self.гео.get()
        гео_url = стартовый_url or (
            getattr(DRIVERS.get(гео), "url", "") if гео in DRIVERS else "")
        # подставляем СКОПИРОВАННЫЙ адрес из буфера обмена, если это ссылка
        буфер = ""
        try:
            буфер = (self.clipboard_get() or "").strip()
        except Exception:
            буфер = ""
        # для Части 1 адрес задан явно — он важнее буфера
        дефолт = стартовый_url or (буфер if буфер.startswith("http")
                                   else (гео_url or "https://"))
        url = simpledialog.askstring(
            "Запись действий (для нового гео)",
            "Адрес сайта. Скопированную ссылку можно вставить (Ctrl+V) — она уже "
            "подставлена, если была в буфере.\n\n"
            "Запись начнётся СРАЗУ, жать ничего не надо. Просто делай шаги руками.\n"
            "Код сам сохранится в файл — закрой браузер, файл откроется.",
            initialvalue=дефолт)
        if not url:
            return
        if not self._свободен():
            return
        профиль = гео if гео in DRIVERS else "dnb"
        self._лог_из_потока(
            f"🎬 Запись действий: {url}\n"
            "   Профиль тот же, что у прогона, — логины на месте.\n"
            "   ВАЖНО: закрой другие окна этого браузера (прогон, «Войти руками») —\n"
            "   профиль можно занимать только одним окном.\n"
            "   Запись идёт с первого клика. Закончил — просто ЗАКРОЙ браузер.")
        threading.Thread(target=lambda: self._писать_действия(профиль, url),
                         daemon=True).start()

    def _писать_действия(self, профиль: str, url: str):
        """
        Запись через `playwright codegen` НА НАШЕМ постоянном профиле.

        Было `page.pause()`. Технически работало — Inspector открывался, профиль
        с логинами подхватывался, — но пользоваться этим было мучительно:
          · запись НЕ включена, надо сперва найти и нажать «Record». Не нажал —
            делаешь все шаги, а кода нет;
          · готовый код надо копировать кнопкой «Copy» и куда-то вставлять;
          · окно Inspector открывается ЗА окном браузера и теряется.

        `playwright codegen` пишет с первого клика и сам кладёт код в файл.
        Раньше его не брали, потому что он «всегда поднимает чистый профиль» —
        это устарело: в 1.62 у него есть `--user-data-dir`, проверено
        (`playwright codegen --help`). Значит логины на месте и здесь.
        """
        import subprocess
        from datetime import datetime
        from common.browser import профиль_гео, держат_профиль, освободить_профиль
        папка = профиль_гео(профиль).resolve()
        # профиль можно занимать только одним запуском: чистим хвосты прошлой
        # записи и окна «Войти руками», иначе codegen просто не поднимется
        занято = держат_профиль(папка)
        if занято:
            self._лог_из_потока(
                f"   Профиль держат {len(занято)} процессов Chrome — освобождаю.")
            освободить_профиль(папка, self._лог_из_потока)
        файл = (Path("логи") /
                f"запись_{профиль}_{datetime.now():%Y-%m-%d_%H-%M}.py").resolve()
        файл.parent.mkdir(parents=True, exist_ok=True)
        аргументы = [sys.executable, "-m", "playwright", "codegen",
                     "--user-data-dir", str(папка),
                     "--channel", "chrome", "--target", "python",
                     "-o", str(файл)]
        if url and url.startswith("http"):
            аргументы.append(url)
        self._лог_из_потока(f"   Код пишется в файл: {файл}")
        try:
            р = subprocess.run(аргументы, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        except Exception as e:
            self._лог_из_потока(f"Запись не открылась: {type(e).__name__}: {e}")
            return
        finally:
            # Chrome закрыт человеком, но дочерние процессы переживают родителя
            # и держат профиль. Не убрать их — следующий прогон не стартует.
            освободить_профиль(папка, self._лог_из_потока)
        if р.returncode != 0:
            хвост = ((р.stderr or "") + (р.stdout or "")).strip()[:300]
            занят = "user data directory" in хвост.lower() or "profile" in хвост.lower()
            self._лог_из_потока(
                "Запись не открылась." +
                ("\n   Похоже, ПРОФИЛЬ ЗАНЯТ: закрой окна браузера, открытые "
                 "прогоном или кнопкой «Войти руками», и повтори." if занят else "") +
                (f"\n   {хвост}" if хвост else ""))
            return
        if файл.exists() and файл.stat().st_size > 0:
            строк = файл.read_text(encoding="utf-8", errors="replace").count("\n") + 1
            self._лог_из_потока(
                f"🎬 Запись закончена. Код сохранён: {файл} ({строк} строк).\n"
                "   Пришли мне этот файл — из него сделаю драйвер гео.")
            self._открыть_в_системе(файл)
        else:
            self._лог_из_потока(
                "🎬 Браузер закрыт, но код пуст.\n"
                "   Скорее всего, шаги делались ДО начала записи или окно закрыли "
                "сразу. Открой запись снова и повтори шаги.")

    def _войти_руками(self):
        """
        Открыть ОБЫЧНЫЙ Chrome на ОБЩЕМ профиле — залогиниться руками.

        Сайты (Google в первую очередь) отказывают во входе, когда видят
        автоматизацию. Поэтому вход делаем в чистом Chrome, а прогон и запись
        потом поднимают ТОТ ЖЕ профиль и получают готовую сессию.

        Профиль ОДИН на все гео: вход делается один раз и работает везде.
        """
        from common.browser import открыть_для_входа
        from part2.geos.registry import DRIVERS
        гео = self.гео.get()
        адрес = getattr(DRIVERS.get(гео), "url", "") if гео in DRIVERS else ""
        вышло, что = открыть_для_входа(гео, адрес)
        if not вышло:
            messagebox.showwarning("Не открылось", что)
            return
        self._лог_из_потока(
            "🔑 Обычный Chrome на ОБЩЕМ профиле открыт.\n"
            "   Залогинься где нужно. Окно можно оставить открытым: прогон\n"
            "   подключится прямо к нему.\n"
            "   Профиль один на все гео — вход сработает и в Части 1, и в любой стране.\n"
            f"   Профиль: {что}")
        messagebox.showinfo(
            "Вход руками",
            "Открыт обычный Chrome на ОБЩЕМ профиле.\n\n"
            "Залогинься, где надо. Окно закрывать НЕ обязательно — прогон\n"
            "теперь подключается к уже открытому окну и работает в нём.\n\n"
            "Профиль один на все гео и на Часть 1 — входить под каждую страну "
            "отдельно не нужно.")

    def _окно_для_dnb(self):
        """
        Открыть окно, в котором человек САМ пройдёт проверку Cloudflare,
        а прогон потом продолжит работать в этом же окне.

        Зачем: 06.09.2026 dnb.com перестал пускать вообще — Cloudflare не
        пропускал даже после нажатой руками галочки. Причина в navigator.
        webdriver=True, который Playwright выставляет, когда САМ запускает
        браузер. Теперь браузер запускается как обычная программа, а прогон к
        нему подключается — но если проверка всё же встала, её можно пройти
        руками ЗАРАНЕЕ, прямо здесь, и запустить поиск уже по чистой дороге.

        Своим рабочим Chrome это сделать нельзя: с Chrome 136 отладка на
        профиле по умолчанию запрещена (замер: окно закрывается сразу). Поэтому
        окно — на профиле проекта, со всеми накопленными в нём куками.
        """
        from common.browser import открыть_для_входа, ПОРТ_ОТЛАДКИ
        вышло, что = открыть_для_входа("dnb",
                                       "https://www.dnb.com/business-directory.html")
        if not вышло:
            messagebox.showwarning("Не открылось", что)
            return
        self._лог_из_потока(
            "🌐 Chrome на профиле проекта открыт (если окно уже было — открылась "
            "вкладка в нём).\n"
            "   1) Зайди на dnb.com и пройди проверку «Подтвердите, что вы человек».\n"
            "   2) Окно НЕ закрывай.\n"
            "   3) Жми «Найти фирмы» — прогон продолжит в этом же окне.\n"
            f"   Профиль: {что} (порт {ПОРТ_ОТЛАДКИ})")
        messagebox.showinfo(
            "Окно для dnb",
            "Chrome на профиле проекта открыт.\n\n"
            "1. Пройди проверку Cloudflare, если она появилась.\n"
            "2. НЕ закрывай это окно.\n"
            "3. Запускай «Найти фирмы» — работать буду прямо в нём,\n"
            "   проверку заново проходить не придётся.")

    def _поставить_браузер(self):
        """
        Работаем на настоящем Google Chrome — его ставить не надо, он уже в системе.
        Эта кнопка ставит запасной Chromium: на него прогон откатывается, если Chrome
        вдруг не найдётся.
        """
        self._лог_из_потока("Основной браузер — твой Google Chrome, его ставить не нужно.\n"
                            "Ставлю запасной Chromium… (пара минут)")
        threading.Thread(target=lambda: (
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"]),
            self.очередь.put(("лог", "Запасной браузер готов."))
        ), daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
