"""
ОКНО ОЧЕРЕДИ ЗАДАНИЙ — по образцу «Масового запуску» из Генератора ЦСВ.

Заводишь список, запускаешь всё разом, уходишь. Возвращаешься к таблице:
где сколько взято, где упало и почему. Неудачную строку перезапускаешь ОДНУ,
а не всю очередь.

Окно НЕ transient: Windows держал бы такое поверх главного, и журнал прогона,
который живёт в главном окне, оказывался бы за спиной. Пусть будут независимы.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from common import тема
from part1.data.countries import СПИСОК as СТРАНЫ
from очередь import (Задание, Очередь, ЭТАПЫ,
                     ЖДЁТ, РАБОТАЕТ, ГОТОВО, ОШИБКА, ПРОПУЩЕНО, ОСТАНОВЛЕНО)

ЗНАЧКИ = {ЖДЁТ: "·", РАБОТАЕТ: "▶", ГОТОВО: "✔", ОШИБКА: "✘",
          ПРОПУЩЕНО: "⏭", ОСТАНОВЛЕНО: "■"}


class ОкноОчереди(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.оч = Очередь(log=app._лог_из_потока)

        self.title("Очередь заданий")
        self.geometry("1160x620")
        self.minsize(980, 520)
        self.configure(bg=тема.ТЕМА["bg"])      # ttk красит виджеты, но не окно
        тема.применить(self)

        self._строим()
        self._перерисовать()
        self.after(300, self._спросить_про_оборванные)

    # ---------------- интерфейс ----------------

    def _строим(self):
        верх = ttk.Frame(self, padding=(14, 12, 14, 6))
        верх.pack(fill="x")

        ttk.Label(верх, text="Файл Excel (общий на всю очередь)").grid(
            row=0, column=0, sticky="w")
        self.поле_файл = ttk.Entry(верх, width=44)
        self.поле_файл.grid(row=0, column=1, columnspan=3, sticky="we", padx=8)
        self.поле_файл.insert(0, self.оч.файл_excel)
        self.поле_файл.bind("<FocusOut>", self._запомнить_файл)
        верх.columnconfigure(1, weight=1)

        # --- строка добавления задания ---
        доб = ttk.LabelFrame(self, text="Новое задание", padding=(12, 8))
        доб.pack(fill="x", padx=14, pady=(6, 4))

        ttk.Label(доб, text="Слово").grid(row=0, column=0, sticky="w")
        self.поле_слово = ttk.Entry(доб, width=18)
        self.поле_слово.grid(row=0, column=1, padx=(6, 14))
        self.поле_слово.bind("<Return>", lambda *_: self._добавить())

        ttk.Label(доб, text="Страна").grid(row=0, column=2, sticky="w")
        self.поле_страна = ttk.Combobox(доб, values=СТРАНЫ, width=18, state="readonly")
        self.поле_страна.grid(row=0, column=3, padx=(6, 14))
        self.поле_страна.set("France")

        ttk.Label(доб, text="Сколько").grid(row=0, column=4, sticky="w")
        self.поле_сколько = ttk.Spinbox(доб, from_=1, to=500, width=6)
        self.поле_сколько.grid(row=0, column=5, padx=(6, 14))
        self.поле_сколько.set(10)

        self.без_сайта = tk.BooleanVar(value=False)
        ttk.Checkbutton(доб, text="Фирмы БЕЗ сайта",
                        variable=self.без_сайта).grid(row=0, column=6, padx=(0, 14))

        этапы = ttk.Frame(доб)
        этапы.grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Label(этапы, text="Этапы:").pack(side="left", padx=(0, 8))
        self.галки = {}
        for ключ, подпись in ЭТАПЫ:
            v = tk.BooleanVar(value=(ключ == "собрать"))
            self.галки[ключ] = v
            ttk.Checkbutton(этапы, text=подпись, variable=v).pack(side="left", padx=(0, 14))

        ttk.Button(доб, text="＋  Добавить в очередь", command=self._добавить,
                   style="Пуск.TButton").grid(row=1, column=6, sticky="e", pady=(8, 0))

        # СЛОВА САМИ. Вбивать их руками на каждую страну — главная рутина
        # прогона. Кнопка берёт по слову на страну из словаря имён-токенов,
        # минуя всё, что уже гонялось, и всё, что запрещено политикой Ads.
        сам = ttk.Frame(доб)
        сам.grid(row=2, column=0, columnspan=7, sticky="we", pady=(10, 0))
        ttk.Label(сам, text="Слова сами:").pack(side="left", padx=(0, 8))
        ttk.Label(сам, text="стран").pack(side="left")
        self.поле_стран = ttk.Spinbox(сам, from_=1, to=40, width=5)
        self.поле_стран.pack(side="left", padx=(6, 14))
        self.поле_стран.set(18)
        ttk.Label(сам, text="слов на страну").pack(side="left")
        self.поле_слов = ttk.Spinbox(сам, from_=1, to=10, width=5)
        self.поле_слов.pack(side="left", padx=(6, 14))
        self.поле_слов.set(1)
        ttk.Button(сам, text="🎲  Сгенерировать задания",
                   command=self._сгенерировать).pack(side="left")
        ttk.Button(сам, text="🤖  Пополнить запас (Gemini)",
                   command=self._пополнить_запас).pack(side="left", padx=(8, 0))
        self.подсказка_слов = ttk.Label(сам, text="",
                                        foreground=тема.ТЕМА["muted"])
        self.подсказка_слов.pack(side="left", padx=10)
        self._показать_запас()

        # --- таблица заданий ---
        рамка = ttk.Frame(self)
        рамка.pack(fill="both", expand=True, padx=14, pady=(6, 4))
        колонки = ("№", "слово", "страна", "сколько", "этапы", "статус",
                   "взято", "скачано", "заметка")
        self.таблица = ttk.Treeview(рамка, columns=колонки, show="headings", height=11)
        # «Этапы» — самая длинная колонка: три этапа со стрелками не влезали
        # в 240 и обрезались многоточием, а именно по ним читается смысл строки.
        ширины = {"№": 34, "слово": 120, "страна": 116, "сколько": 66, "этапы": 320,
                  "статус": 96, "взято": 56, "скачано": 66, "заметка": 210}
        для_центра = {"№", "сколько", "статус", "взято", "скачано"}
        for к in колонки:
            self.таблица.heading(к, text=к.capitalize() if к != "№" else "№")
            self.таблица.column(к, width=ширины[к],
                                anchor="center" if к in для_центра else "w")
        self.таблица.pack(side="left", fill="both", expand=True)
        полоса = ttk.Scrollbar(рамка, command=self.таблица.yview)
        полоса.pack(side="right", fill="y")
        self.таблица.config(yscrollcommand=полоса.set)
        self.таблица.bind("<Double-1>", lambda *_: self._прогнать(одну=True))

        # Treeview ttk красит не полностью — фон строк и выделение задаём сами
        ст = ttk.Style(self)
        ст.configure("Treeview", background=тема.ТЕМА["surface"],
                     fieldbackground=тема.ТЕМА["surface"], foreground=тема.ТЕМА["ink"],
                     bordercolor=тема.ТЕМА["line"], rowheight=24)
        ст.map("Treeview", background=[("selected", тема.AURORA[0])],
               foreground=[("selected", "#ffffff")])
        ст.configure("Treeview.Heading", background=тема.ТЕМА["surface2"],
                     foreground=тема.ТЕМА["muted"], relief="flat")
        ст.map("Treeview.Heading", background=[("active", тема.ТЕМА["surface2"])])
        for имя, цвет in ((ГОТОВО, тема.УСПЕХ), (ОШИБКА, тема.ОПАСНОСТЬ),
                          (РАБОТАЕТ, тема.AURORA[1]), (ПРОПУЩЕНО, тема.ЗОЛОТО),
                          (ОСТАНОВЛЕНО, тема.ТЕМА["muted"])):
            self.таблица.tag_configure(имя, foreground=цвет)

        # --- кнопки ---
        низ = ttk.Frame(self, padding=(14, 4, 14, 12))
        низ.pack(fill="x")
        ttk.Button(низ, text="▶  Запустить очередь",
                   command=lambda: self._прогнать(одну=False),
                   style="Пуск.TButton").pack(side="left")
        ttk.Button(низ, text="▶  Только выбранную",
                   command=lambda: self._прогнать(одну=True)).pack(side="left", padx=6)
        ttk.Separator(низ, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(низ, text="▲", width=3,
                   command=lambda: self._сдвинуть(-1)).pack(side="left")
        ttk.Button(низ, text="▼", width=3,
                   command=lambda: self._сдвинуть(1)).pack(side="left", padx=(4, 10))
        ttk.Button(низ, text="✕  Удалить строку",
                   command=self._удалить).pack(side="left")
        ttk.Button(низ, text="↻  Сбросить статусы",
                   command=self._сбросить).pack(side="left", padx=6)
        self.итог = ttk.Label(низ, text="", foreground=тема.ТЕМА["muted"])
        self.итог.pack(side="right")

    # ---------------- данные ----------------

    def _запомнить_файл(self, *_):
        имя = self.поле_файл.get().strip()
        if имя and имя != self.оч.файл_excel:
            self.оч.файл_excel = имя
            self.оч.сохранить()

    def _добавить(self):
        слово = self.поле_слово.get().strip()
        if not слово:
            messagebox.showwarning("Пусто", "Введи слово", parent=self)
            return
        страна = self.поле_страна.get()
        этапы = {к: v.get() for к, v in self.галки.items()}
        if not any(этапы.values()):
            messagebox.showwarning("Нет этапов", "Отметь хотя бы один этап", parent=self)
            return

        # ПОВТОР: то же слово и та же страна уже гонялись — показываем цифры
        прошлые = self.оч.прошлые(слово, страна)
        if прошлые:
            п = прошлые[-1]
            ответ = messagebox.askyesnocancel(
                "Такое уже гонялось",
                f"«{слово}» × {страна} уже отрабатывало {п['дата']},\n"
                f"взято {п['взято']} из {п['сколько']}.\n\n"
                "Фирмы будут ДРУГИЕ — реестр те же не отдаст, то есть это добор.\n\n"
                "Да — добавить ещё раз\n"
                "Нет — не добавлять\n"
                "Отмена — ничего не делать",
                parent=self)
            if ответ is not True:
                return

        self.оч.добавить(Задание(слово=слово, страна=страна,
                                 сколько=int(self.поле_сколько.get()),
                                 без_сайта=self.без_сайта.get(),
                                 этапы=этапы))
        self.поле_слово.delete(0, "end")
        self.поле_слово.focus_set()
        self._перерисовать()

    @property
    def буфер(self):
        """Запас слов от Gemini. Создаём лениво: файла может ещё не быть."""
        if getattr(self, "_буфер", None) is None:
            from part1.запас import Запас
            self._буфер = Запас(log=self.app._лог_из_потока)
        return self._буфер

    def _показать_запас(self):
        try:
            self.подсказка_слов.config(text=f"запас: {self.буфер.сводка()}")
        except Exception:
            pass

    def _обновить_подпись(self):
        """
        Обновить подпись ИЗ ФОНОВОГО ПОТОКА — безопасно.

        `self.after()` из чужого потока роняет tkinter с «main thread is not in
        main loop», и на замере это оборвало пополнение ПОСЛЕ ПЕРВОЙ СТРАНЫ:
        поток умер, остальные семнадцать не получили ни слова. Подпись — вещь
        косметическая, ради неё терять работу нельзя.
        """
        try:
            self.after(0, self._показать_запас)
        except Exception:
            pass

    def _страны_для_генерации(self, сколько_стран: int):
        """Страны с написанным драйвером Части 2 — собирать там, откуда потом
        не выйдет скачать выписку, значит работать впустую."""
        from part1.data.countries import to_code
        from part2.geos.registry import DRIVERS
        с_драйвером = [с for с in СТРАНЫ if to_code(с) in DRIVERS]
        return [(с, to_code(с)) for с in с_драйвером[:сколько_стран]]

    def _пополнить_запас(self):
        """
        Сходить к Gemini и набить буфер словами — по сотне на страну.

        В ОТДЕЛЬНОМ ПОТОКЕ: страна занимает 15–30 секунд, восемнадцать стран —
        это минуты, и окно не должно всё это время висеть замороженным.
        """
        import threading
        from part1 import слова_gemini as ген

        стран = int(self.поле_стран.get() or 1)
        цель = simpledialog.askinteger(
            "Пополнить запас", "Сколько слов на страну держать в запасе?",
            initialvalue=100, minvalue=10, maxvalue=300, parent=self)
        if not цель:
            return
        страны = self._страны_для_генерации(стран)
        лог = self.app._лог_из_потока

        def работа():
            try:
                ключ = ген.ключ()
            except ген.НетКлюча as e:
                лог(f"✘ Gemini: {e}")
                return
            # ВИДЕЛИ — общий на весь заход: без него модель отдаёт одни и те же
            # английские слова каждой стране подряд (свои же примеры из промпта).
            видели: set[str] = set()
            for имя, гео in страны:
                видели |= self.буфер.все_известные(гео)
            всего = 0
            for имя, гео in страны:
                if self.буфер.свободно(гео) >= цель:
                    лог(f"· {гео}: в запасе уже {self.буфер.свободно(гео)} — пропускаю")
                    continue
                надо = цель - self.буфер.свободно(гео)
                лог(f"🤖 {гео} ({имя}): прошу {надо} слов")
                катег: dict = {}
                try:
                    новые = ген.сгенерировать(гео, надо, исключить=видели,
                                              log=лог, api_key=ключ,
                                              категории=катег)
                except Exception as e:
                    лог(f"  ✘ {гео}: {type(e).__name__}: {e}")
                    continue
                добавлено = self.буфер.пополнить(гео, новые, катег)
                видели |= {с.lower() for с in новые}
                всего += добавлено
                лог(f"  ✔ {гео}: +{добавлено} (в запасе {self.буфер.свободно(гео)})")
                self._обновить_подпись()
            лог(f"🤖 Запас пополнен: +{всего} слов. {self.буфер.сводка()}")
            self.after(0, self._показать_запас)

        лог(f"🤖 Пополняю запас слов через Gemini: {len(страны)} стран по {цель}")
        threading.Thread(target=работа, daemon=True).start()

    def _сгенерировать(self):
        """
        Заполнить очередь заданиями «слово × страна» без единого ввода руками.

        Слово берётся из словаря имён-токенов (part1/слова.py): сперва
        английское, потом на языке страны. Всё, что уже гонялось по этой стране,
        и всё, что дало меньше трёх фирм, пропускается — повтор выдал бы те же
        забронированные фирмы, то есть сожжённый прогон.

        Страны берём ТОЛЬКО те, для которых написан драйвер Части 2: собрать
        фирмы там, откуда потом не выйдет скачать выписку, — работа впустую.
        """
        # импорт ЗДЕСЬ: part2 тянет за собой все драйверы гео, а окно очереди
        # должно открываться мгновенно
        from part1 import слова as словарь
        from part1.data.countries import to_code

        сколько_стран = int(self.поле_стран.get() or 1)
        слов_на_страну = int(self.поле_слов.get() or 1)
        сколько_фирм = int(self.поле_сколько.get() or 10)
        этапы = {к: v.get() for к, v in self.галки.items()}
        if not any(этапы.values()):
            messagebox.showwarning("Нет этапов", "Отметь хотя бы один этап",
                                   parent=self)
            return

        # УЖЕ СТОЯЩЕЕ В ОЧЕРЕДИ тоже исключаем. История пишется только ПОСЛЕ
        # прогона, поэтому по одной истории второй клик по кнопке выдавал те же
        # слова заново — в очередь ложились дубли, которые сожгли бы прогон.
        в_очереди: dict[str, set[str]] = {}
        for з in self.оч.задания:
            в_очереди.setdefault(to_code(з.страна), set()).add(з.слово.lower())

        добавлено, пусто, занятые = 0, [], set()
        for страна, гео in self._страны_для_генерации(сколько_стран):
            новые = словарь.предложить(
                гео, слов_на_страну, self.оч.история,
                занятые=занятые | в_очереди.get(гео, set()),
                буфер=self.буфер)
            if not новые:
                пусто.append(f"{гео}")
                continue
            for слово in новые:
                занятые.add(слово.lower())
                в_очереди.setdefault(гео, set()).add(слово.lower())
                self.оч.задания.append(Задание(
                    слово=слово, страна=страна, сколько=сколько_фирм,
                    без_сайта=self.без_сайта.get(), этапы=dict(этапы)))
                добавлено += 1
        self.оч.сохранить()
        self._перерисовать()

        хвост = (f"  ·  слов не нашлось: {', '.join(пусто)}" if пусто else "")
        self.подсказка_слов.config(
            text=f"добавлено {добавлено} заданий  ·  запас: "
                 f"{self.буфер.сводка()}{хвост}")
        if not добавлено:
            messagebox.showinfo(
                "Слов не осталось",
                "По всем выбранным странам слова кончились: и запас от Gemini, "
                "и встроенный словарь уже отработаны.\n\n"
                "Нажми «🤖 Пополнить запас (Gemini)».",
                parent=self)

    def _выбранный(self) -> int | None:
        выд = self.таблица.selection()
        if not выд:
            return None
        return int(self.таблица.item(выд[0], "values")[0]) - 1

    def _удалить(self):
        i = self._выбранный()
        if i is None:
            messagebox.showinfo("Не выбрано", "Выдели строку в таблице", parent=self)
            return
        self.оч.удалить(i)
        self._перерисовать()

    def _сдвинуть(self, куда: int):
        i = self._выбранный()
        if i is None:
            return
        новый = self.оч.сдвинуть(i, куда)
        self._перерисовать()
        дети = self.таблица.get_children()
        if новый < len(дети):
            self.таблица.selection_set(дети[новый])

    def _сбросить(self):
        if messagebox.askyesno("Сбросить статусы",
                               "Все строки снова станут «ждёт», счётчики обнулятся.\n"
                               "Сами задания останутся. Продолжить?", parent=self):
            self.оч.очистить_статусы()
            self._перерисовать()

    def _перерисовать(self):
        self.таблица.delete(*self.таблица.get_children())
        for i, з in enumerate(self.оч.задания, 1):
            статус = f"{ЗНАЧКИ.get(з.статус, '·')} {з.статус}"
            слово = з.слово + ("  (без сайта)" if з.без_сайта else "")
            self.таблица.insert(
                "", "end", tags=(з.статус,),
                values=(i, слово, з.страна, з.сколько, з.этапы_текст, статус,
                        з.взято or "", з.скачано or "", з.заметка[:60]))
        всего = sum(з.сколько for з in self.оч.задания)
        взято = sum(з.взято for з in self.оч.задания)
        self.итог.config(text=f"строк: {len(self.оч.задания)}   "
                              f"нужно фирм: {всего}   взято: {взято}")

    # ---------------- возобновление ----------------

    def _спросить_про_оборванные(self):
        """
        Строка осталась в статусе «работает» — значит прошлый прогон не закрылся
        сам. При нормальном конце статус всегда меняется, так что это признак
        падения (свет, Chrome умер, закрыли окно).
        """
        оборв = self.оч.оборванные()
        if not оборв:
            return
        строки = "\n".join(
            f"   • «{self.оч.задания[i].слово}» × {self.оч.задания[i].страна}: "
            f"взято {self.оч.задания[i].взято} из {self.оч.задания[i].сколько}"
            for i in оборв)
        ответ = messagebox.askyesno(
            "Прошлый прогон не закончился",
            f"Эти строки остались в работе — похоже, прогон упал:\n\n{строки}\n\n"
            "Продолжить с места обрыва? Уже взятые фирмы засчитаны, доберём только "
            "недостающие.\n\nНет — просто пометить как остановленные.",
            parent=self)
        for i in оборв:
            if not ответ:
                self.оч.задания[i].статус = ОСТАНОВЛЕНО
                self.оч.задания[i].заметка = "прогон оборвался"
            else:
                self.оч.задания[i].статус = ЖДЁТ
        self.оч.сохранить()
        self._перерисовать()
        if ответ:
            self._прогнать(одну=False)

    # ---------------- запуск ----------------

    def _прогнать(self, одну: bool):
        if not self.app._свободен():
            return
        self._запомнить_файл()
        только = self._выбранный() if одну else None
        if одну and только is None:
            messagebox.showinfo("Не выбрано", "Выдели строку в таблице", parent=self)
            return
        if not self.оч.задания:
            messagebox.showinfo("Пусто", "В очереди нет заданий", parent=self)
            return

        import очередь as модуль

        def обновить():
            # прогон идёт в другом потоке — трогать виджеты только через after
            self.after(0, self._перерисовать)

        self.app._старт(lambda h: модуль.прогон(
            self.оч, h, log=self.app._лог_из_потока, stop=self.app.стоп,
            pause=self.app.пауза, только=только, на_изменение=обновить))
        self.app.lift()          # журнал прогона живёт в главном окне
