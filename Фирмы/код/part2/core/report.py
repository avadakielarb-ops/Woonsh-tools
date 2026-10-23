"""
Отчёт в конце прогона.

Часть 2 пока НИЧЕГО сама не чинит и не ищет замену — она только докладывает:
«скачано 7 из 10, 3 не вышло + причина». Автозамена — потом, когда обе части
отлажены по отдельности.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from part2.core.models import Result, Status

RU = {
    Status.OK: "скачано",
    Status.NOT_FOUND: "не найдено в реестре",
    Status.AMBIGUOUS: "несколько кандидатов, выбор не сделан",
    Status.INACTIVE: "фирма неактивна",
    Status.SKIPPED: "пропущено человеком",
    Status.ERROR: "ошибка",
}


def print_report(results: list[Result], geo: str, log=print) -> None:
    """
    Отчёт по стране — В ЛОГ ПРОГОНА, а не в голый print.

    ПОЧЕМУ ЭТО ВАЖНО. Приложение запускается через pythonw, а вывод уходит в
    файл: у дочернего процесса sys.stdout берёт кодировку СИСТЕМЫ (cp1251),
    и первый же знак «✘» роняет печать с UnicodeEncodeError. Замер
    10.09.2026: семь французских выписок скачались, отчёт упал на этой
    строке, ошибку поймал общий except, и в сводке значилось «скачано 0 из
    0». То есть работа сделана, а приложение доложило обратное — худший
    вид вранья.

    Лог окна пишет в UTF-8 и на экран, поэтому по умолчанию отчёт идёт туда.
    """
    ok = [r for r in results if r.status is Status.OK]
    log("\n" + "=" * 60)
    log(f"ГЕО {geo}: скачано {len(ok)} из {len(results)}")
    log("=" * 60)
    for r in results:
        if r.status is Status.OK:
            renamed = ""
            if r.final_name and r.final_name != r.company.name:
                renamed = f"  [в таблице переименовано в: {r.final_name}]"
            log(f"  ✔ {r.company.name}{renamed}")
        else:
            log(f"  ✘ {r.company.name} — {RU[r.status]}: {r.reason}")
    if any(r.human_steps for r in results):
        log("\nРучные вмешательства:")
        for r in results:
            for s in r.human_steps:
                log(f"  · {s}")


def save_report(results: list[Result], geo: str, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Отчёт {geo}"
    ws.append(["№ строки", "Фирма", "Статус", "Причина", "Файл", "Имя в реестре"])
    for r in results:
        ws.append([r.company.row, r.company.name, RU[r.status], r.reason,
                   r.file_path or "", r.final_name or ""])
    wb.save(path)
    return path
