"""Настройки прогона."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    geo: str                              # код гео: "CZ", "CH", "HU", ...
    excel_path: Path                      # Excel из Части 1
    sheet: str | None = None              # лист (по умолчанию — последний)
    out_dir: Path = Path("./выписки")     # куда складывать PDF
    templates_dir: Path = __import__("common.пути", fromlist=["ШАБЛОНЫ"]).ШАБЛОНЫ

    headless: bool = False                # ВАЖНО: всегда False.
                                          # Человек должен видеть браузер, чтобы
                                          # решить капчу / залогиниться.
    timeout_ms: int = 30_000
    slow_mo_ms: int = 0
    human_timeout_s: int = 0              # 0 = ждать человека бесконечно

    def geo_dir(self) -> Path:
        d = self.out_dir / self.geo
        d.mkdir(parents=True, exist_ok=True)
        return d
