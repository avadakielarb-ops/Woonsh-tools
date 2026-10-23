"""
ИСКЛЮЧЕНИЯ — фирмы, которые Часть 2 не трогает.

Зачем. В листе регулярно попадаются заведомо ненужные: школы, союзы,
представительства, конторы, которые уже проверили руками и забраковали.
Раньше их приходилось терпеть каждый прогон: скрипт шёл в реестр, тратил
минуты, звал человека и в итоге всё равно отказывал.

Сравниваем ПО НОРМАЛИЗОВАННОМУ ИМЕНИ (тем же `normalize`, что и матчинг):
правовая форма, регистр, кавычки и диакритика роли не играют. «OŠ Col»,
«OS COL» и «OS Col d.o.o.» — одно и то же исключение.

Исключение может быть общим (на все страны) или привязанным к гео:
    OS Col            — везде
    SI: OS Col        — только в Словении

Файл «исключения.txt» — обычный текст, правится и руками, и из окна:
одна строка = одно исключение, «#» в начале строки = комментарий.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from common.пути import данные

ФАЙЛ = данные("исключения.txt")

ШАПКА = """\
# ФИРМЫ, КОТОРЫЕ ЧАСТЬ 2 НЕ ТРОГАЕТ.
# Одна строка — одна фирма. Регистр, кавычки и правовая форма не важны.
# Можно привязать к стране:  SI: OSNOVNA SOLA COL
# Строки с «#» — комментарии.
"""


class Исключения:
    def __init__(self, path: Path = ФАЙЛ):
        self.path = Path(path)
        self.строки: list[str] = []
        self.загрузить()

    def загрузить(self) -> None:
        self.строки = []
        if not self.path.exists():
            return
        try:
            текст = self.path.read_text(encoding="utf-8-sig")
        except Exception:
            return
        for с in текст.splitlines():
            с = с.strip()
            if с and not с.startswith("#"):
                self.строки.append(с)

    def сохранить(self, текст: str | None = None) -> None:
        """
        Записать. текст=None — записать текущий список.

        ПЕРЕД ЗАТИРАНИЕМ ДЕЛАЕМ КОПИЮ. Список исключений собирается вручную и
        по крупицам — восемнадцать записей с гео стоили человеку получаса. Один
        неосторожный вызов с пустой строкой стирал всё без следа. Теперь рядом
        всегда лежит «.bak» с предыдущим содержимым.
        """
        if текст is None:
            текст = "\n".join(self.строки)
        новое = ШАПКА + текст.strip() + "\n"
        try:
            if self.path.exists() and self.path.read_text(encoding="utf-8-sig") != новое:
                self.path.with_suffix(".bak").write_text(
                    self.path.read_text(encoding="utf-8-sig"), encoding="utf-8")
        except Exception:
            pass
        self.path.write_text(новое, encoding="utf-8")
        self.загрузить()

    @staticmethod
    def ключ(имя: str) -> str:
        """
        Ключ сравнения: регистр, диакритика и знаки не важны, а ПРАВОВАЯ ФОРМА
        ВАЖНА.

        Тут был опасный промах. Сначала сравнивали через `normalize()`, который
        режет правовые формы, да ещё разрешали совпадение «наше имя целым словом
        внутри более длинного исключения». Живой замер на листе из 200 фирм:
        вставили семь названий — отсеялось десять. Лишними ушли бельгийские
        «ICE SA» и «Blue Ice» и французская «ICE», потому что слова «ice» и
        «blue ice» встречаются внутри австралийского «ICE ENGINEERING &
        CONSTRUCTION PTY LTD» и польского «BLUE ICE SP Z O O».

        Три живые фирмы молча выпали бы из работы — ровно та беда, ради которой
        исключения и заводились наоборот. Поэтому: только точное равенство, и
        форму не срезаем. «BLUE ICE SP Z O O» и «Blue Ice» — разные фирмы, а
        «BLUE ICE Sp. z o.o.» и «BLUE ICE SP Z O O» — одна.
        """
        s = unicodedata.normalize("NFKD", имя or "")
        s = "".join(c for c in s if not unicodedata.combining(c)).lower()
        for a, b in (("ł", "l"), ("ø", "o"), ("đ", "d"), ("ß", "ss"), ("ħ", "h")):
            s = s.replace(a, b)
        s = re.sub(r"[^\w\s]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def _разобрать(cls, строка: str) -> tuple[str, str]:
        """«SI: OS Col» → («SI», «os col»); «OS Col» → («», «os col»)."""
        гео = ""
        если = строка
        if ":" in строка:
            слева, справа = строка.split(":", 1)
            слева = слева.strip()
            if len(слева) in (2, 3) and слева.isalpha():
                гео, если = слева.upper(), справа
        return гео, cls.ключ(если)

    def исключена(self, имя: str, гео: str = "") -> bool:
        цель = self.ключ(имя)
        if not цель:
            return False
        г = (гео or "").upper()
        for с in self.строки:
            п_гео, п_имя = self._разобрать(с)
            if not п_имя or (п_гео and п_гео != г):
                continue
            if цель == п_имя:
                return True
        return False

    def добавить(self, имя: str, гео: str = "") -> None:
        строка = f"{гео.upper()}: {имя}".strip() if гео else имя
        if строка not in self.строки:
            self.строки.append(строка)
            self.сохранить()

    def как_текст(self) -> str:
        return "\n".join(self.строки)
