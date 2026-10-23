"""
БУФЕР ОБМЕНА В ПОЛЯХ ВВОДА — чтобы работал при РУССКОЙ РАСКЛАДКЕ.

Tk привязывает Ctrl+V к СИМВОЛУ «v». На русской раскладке та же клавиша шлёт
«м», привязка не срабатывает, и вставка не работает вообще: ни Ctrl+V, ни
правой кнопкой. Со стороны выглядит как «поле не принимает текст».

Лечится привязкой по КОДУ КЛАВИШИ — код от раскладки не зависит:
    V=86  C=67  X=88  A=65
Тот же приём уже отработан в «Генераторе ЦСВ», где на этом обожглись первыми.

Плюс правая кнопка мыши: «Вставить / Копировать / Вырезать / Выделить всё».
"""
from __future__ import annotations

import tkinter as tk

КОД_V, КОД_C, КОД_X, КОД_A = 86, 67, 88, 65


def _выделить_всё(w) -> None:
    try:
        if isinstance(w, tk.Text):
            w.tag_add("sel", "1.0", "end-1c")
            w.mark_set("insert", "1.0")
        else:
            w.select_range(0, "end")
    except Exception:
        pass


def _выделенное(w) -> str:
    try:
        if isinstance(w, tk.Text):
            д = w.tag_ranges("sel")
            return w.get(д[0], д[1]) if д else ""
        return w.selection_get() if w.selection_present() else ""
    except Exception:
        return ""


def _убрать_выделенное(w) -> None:
    try:
        if isinstance(w, tk.Text):
            if w.tag_ranges("sel"):
                w.delete("sel.first", "sel.last")
        elif w.selection_present():
            w.delete("sel.first", "sel.last")
    except Exception:
        pass


def вставить_в_курсор(w) -> None:
    """
    Вставить буфер В МЕСТО КУРСОРА, заменив выделенное.

    Делаем РУКАМИ, а не через `event_generate("<<Paste>>")`: виртуальное событие
    молча не срабатывает, когда окно ещё не отрисовано или фокус на другом
    виджете — на проверке так и вышло, «break» вернулся, а поле осталось пустым.
    Здесь же всё явно и предсказуемо.
    """
    try:
        текст = w.clipboard_get()
    except Exception:
        return
    if not текст:
        return
    _убрать_выделенное(w)
    try:
        w.insert("insert", текст)
    except Exception:
        pass


def _по_коду(e):
    """Ctrl+буква по КОДУ клавиши, а не по символу."""
    w = e.widget
    if e.keycode == КОД_V:
        вставить_в_курсор(w)
        return "break"
    if e.keycode in (КОД_C, КОД_X):
        текст = _выделенное(w)
        if текст:
            w.clipboard_clear()
            w.clipboard_append(текст)
            if e.keycode == КОД_X:
                _убрать_выделенное(w)
        return "break"
    if e.keycode == КОД_A:
        _выделить_всё(w)
        return "break"
    return None


def вставить(w) -> int:
    """
    Вставить содержимое буфера обмена в поле. Возвращает число вставленных строк.

    Отдельной функцией, потому что на неё вешается ЯВНАЯ КНОПКА: даже с
    исправленными привязками человеку нужен видимый способ вставить список,
    а не гадать, работает ли сочетание клавиш.
    """
    try:
        текст = w.clipboard_get()
    except Exception:
        return 0
    if not текст:
        return 0
    if isinstance(w, tk.Text):
        уже = w.get("1.0", "end").strip()
        w.insert("end", ("\n" if уже else "") + текст.strip())
    else:
        w.insert("end", текст.strip())
    return len([с for с in текст.splitlines() if с.strip()])


def меню_по_правой(w) -> None:
    def копировать(вырезать=False):
        текст = _выделенное(w)
        if текст:
            w.clipboard_clear()
            w.clipboard_append(текст)
            if вырезать:
                _убрать_выделенное(w)

    м = tk.Menu(w, tearoff=0)
    м.add_command(label="Вставить", command=lambda: вставить(w))
    м.add_command(label="Копировать", command=копировать)
    м.add_command(label="Вырезать", command=lambda: копировать(True))
    м.add_separator()
    м.add_command(label="Выделить всё", command=lambda: _выделить_всё(w))

    def показать(e):
        try:
            w.focus_set()
            м.tk_popup(e.x_root, e.y_root)
        finally:
            м.grab_release()

    w.bind("<Button-3>", показать)


def включить(*поля) -> None:
    """Включить нормальный буфер обмена в перечисленных полях."""
    for w in поля:
        try:
            w.bind("<Control-KeyPress>", _по_коду)
            меню_по_правой(w)
        except Exception:
            continue
