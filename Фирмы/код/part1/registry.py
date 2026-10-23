"""
РЕЕСТР ФИРМ.

Два состояния (решение из концепции v2):
    БРОНЬ         — Часть 1 взяла фирму в работу (живёт 24 часа)
    ИСПОЛЬЗОВАНА  — Часть 2 реально скачала выписку (навсегда, по ОФИЦИАЛЬНОМУ номеру)
Часть 2 не смогла -> бронь СНИМАЕТСЯ, фирма снова свободна. Ни одна фирма не горит зря.

Интерфейс нарочно узкий — четыре метода. Сегодня за ними локальный JSON (один человек,
один компьютер — этого честно достаточно). Когда дойдёт до нескольких человек, пишем
ServerRegistry с теми же четырьмя методами — остальной код не трогаем вообще.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

БРОНЬ_ЖИВЁТ = 24 * 3600      # секунд
ПАПКА_БЭКАПОВ = ".реестр_бэкап"
СКОЛЬКО_БЭКАПОВ = 30         # снимков храним; один снимок = один запуск


class РеестрПовреждён(RuntimeError):
    """
    Файл реестра есть, но не читается, и ни один бэкап не подошёл.

    Отдельное исключение, потому что обрабатывать это надо ГРОМКО. Молча
    начать с пустого реестра — худшее, что можно сделать: все ранее
    использованные фирмы разом станут «свободны», и они пойдут в работу
    повторно. Лучше не запуститься совсем.
    """


def отпечаток(name: str, country: str, zip_code: str = "", city: str = "") -> str:
    """
    Временный ключ Части 1: страна + имя без формы + индекс (или город).
    ДЫРА №4: DnB даёт индекс не всегда — тогда падаем на город, иначе только имя.
    """
    s = unicodedata.normalize("NFKD", name).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    хвост = (zip_code or city or "").lower().strip()
    return f"{country.upper()}|{s}|{хвост}"


def ключ_номера(country: str, number: str) -> str:
    """Постоянный ключ: страна + официальный номер реестра. Имя может смениться — номер нет."""
    return f"{country.upper()}#{re.sub(r'[^0-9A-Za-z]', '', number)}"


class Registry(ABC):
    @abstractmethod
    def свободна(self, key: str) -> bool: ...
    @abstractmethod
    def забронировать(self, key: str) -> None: ...
    @abstractmethod
    def подтвердить(self, key: str, номер_ключ: str) -> None: ...
    @abstractmethod
    def снять_бронь(self, key: str) -> None: ...


class LocalFileRegistry(Registry):
    def __init__(self, path: Path | None = None, log=None):
        from common.пути import данные
        path = Path(path) if path else данные("реестр_фирм.json")
        self.path = path
        self.бэкапы = path.parent / ПАПКА_БЭКАПОВ
        self.log = log or (lambda s: None)
        self.данные = {"брони": {}, "использованы": []}

        if path.exists():
            прочитано = self._прочитать(path)
            if прочитано is None:
                # Файл есть, но битый. Раньше здесь стоял «except: pass», и работа
                # продолжалась с ПУСТЫМ реестром — то есть все использованные фирмы
                # молча становились свободными. Теперь лезем в бэкапы.
                прочитано = self._поднять_из_бэкапа()
                if прочитано is None:
                    raise РеестрПовреждён(
                        f"Реестр {path} не читается, и ни один бэкап не подошёл.\n"
                        f"Бэкапы лежат в {self.бэкапы}.\n"
                        "Запуск остановлен НАМЕРЕННО: с пустым реестром все ранее "
                        "использованные фирмы пойдут в работу повторно.")
            self.данные = прочитано

        self.данные.setdefault("брони", {})
        self.данные.setdefault("использованы", [])
        self.данные.setdefault("непригодны", {})
        self._снимок("запуск")      # снимок ДО работы: один на прогон
        self._чистка()

    # ---------- чтение и бэкапы ----------

    @staticmethod
    def _прочитать(p: Path):
        """JSON или None, если файл не читается / не той формы."""
        try:
            д = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        return д if isinstance(д, dict) and "использованы" in д else None

    def _поднять_из_бэкапа(self):
        """Самый свежий читаемый снимок. Нет таких — None."""
        if not self.бэкапы.exists():
            return None
        for снимок in sorted(self.бэкапы.glob("реестр_*.json"), reverse=True):
            д = self._прочитать(снимок)
            if д is not None:
                self.log(f"⚠ Реестр не читался — поднял из бэкапа {снимок.name} "
                         f"(использованных фирм: {len(д.get('использованы', []))})")
                return д
        return None

    def _снимок(self, повод: str) -> None:
        """
        Копия реестра перед работой. Снимаем ПЕРЕД, а не после: важно сохранить
        состояние, которое точно было целым. Раз в запуск, не после каждой фирмы —
        иначе снимков будут тысячи, а толку столько же.
        """
        if not self.path.exists():
            return
        try:
            self.бэкапы.mkdir(exist_ok=True)
            куда = self.бэкапы / f"реестр_{datetime.now():%Y-%m-%d_%H-%M-%S}_{повод}.json"
            shutil.copy2(self.path, куда)
            старые = sorted(self.бэкапы.glob("реестр_*.json"), reverse=True)
            for лишний in старые[СКОЛЬКО_БЭКАПОВ:]:
                лишний.unlink(missing_ok=True)
        except Exception as e:
            self.log(f"(не смог снять бэкап реестра: {e})")

    def _чистка(self) -> None:
        сейчас = time.time()
        self.данные["брони"] = {
            k: t for k, t in self.данные["брони"].items() if сейчас - t < БРОНЬ_ЖИВЁТ
        }

    def _save(self) -> None:
        """
        Атомарная запись: сначала во временный файл, потом подмена одним движением.
        Раньше писали прямо в реестр — и смерть процесса посреди записи (Chrome
        упал, нажали Стоп) оставляла обрезанный файл, то есть потерю всей истории.
        os.replace на одном диске атомарен и на Windows тоже.
        """
        врем = self.path.with_suffix(self.path.suffix + ".tmp")
        текст = json.dumps(self.данные, ensure_ascii=False, indent=1)
        with open(врем, "w", encoding="utf-8") as f:
            f.write(текст)
            f.flush()
            os.fsync(f.fileno())        # данные на диске, а не в кэше ОС
        os.replace(врем, self.path)

    def свободна(self, key: str) -> bool:
        return (key not in self.данные["брони"]
                and key not in self.данные["использованы"]
                and key not in self.данные.get("непригодны", {}))

    def забронировать(self, key: str) -> None:
        self.данные["брони"][key] = time.time()
        self._save()

    def непригодна(self, key: str, причина: str) -> None:
        """
        Пометить фирму НАВСЕГДА непригодной — Часть 1 больше её не предложит.

        Зачем. Часть 2 отбраковывает фирму по ПОСТОЯННОЙ причине (ассоциация,
        ликвидация, в реестре её нет) и снимает бронь — то есть фирма снова
        «свободна», Часть 1 берёт её в следующий раз, Часть 2 снова тратит на
        неё время и снова отказывает. По швейцарскому прогону так возвращались
        бы 4 фирмы из 10 — каждый раз.

        Сюда попадают ТОЛЬКО постоянные причины. Таймауты, капчи и сбои сети
        временные: за них бронь просто снимается, фирма остаётся живой.
        """
        if not key:
            return
        self.данные.setdefault("непригодны", {})[key] = {
            "причина": причина,
            "когда": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.данные["брони"].pop(key, None)
        self._save()

    def почему_непригодна(self, key: str) -> str:
        запись = self.данные.get("непригодны", {}).get(key)
        return (запись or {}).get("причина", "")

    def подтвердить(self, key: str, номер_ключ: str) -> None:
        self.данные["брони"].pop(key, None)
        for k in (key, номер_ключ):
            if k and k not in self.данные["использованы"]:
                self.данные["использованы"].append(k)
        self._save()

    def снять_бронь(self, key: str) -> None:
        self.данные["брони"].pop(key, None)
        self._save()

    def очистить(self) -> int:
        """
        Забыть ВСЕ фирмы (брони + использованные). Для тестовых прогонов.
        Снимок ОБЯЗАТЕЛЬНО: это единственная кнопка, стирающая всю историю
        использованных фирм, и нажать её случайно — потерять тысячи записей.
        """
        self._снимок("перед-очисткой")
        n = (len(self.данные.get("брони", {}))
             + len(self.данные.get("использованы", []))
             + len(self.данные.get("непригодны", {})))
        self.данные = {"брони": {}, "использованы": [], "непригодны": {}}
        self._save()
        self.log(f"Реестр очищен ({n} записей). Снимок до очистки — в {self.бэкапы}")
        return n


class ServerRegistry(Registry):
    """Заглушка на будущее (несколько человек): те же 4 метода, внутри HTTP или SQL."""
    def свободна(self, key): raise NotImplementedError("подключим при переходе на команду")
    def забронировать(self, key): raise NotImplementedError
    def подтвердить(self, key, номер_ключ): raise NotImplementedError
    def снять_бронь(self, key): raise NotImplementedError
