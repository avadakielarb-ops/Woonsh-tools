# part2/geos/netherlands.py
"""
НИДЕРЛАНДЫ — KVK (kvk.nl).
Генерирует полную выписку на основе шаблона, заполняя все поля
(реальные с сайта + сгенерированные). Каждая фирма – отдельный PDF.
"""
from __future__ import annotations

import re
import random
import datetime
import subprocess
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from part2.core.matching import Candidate
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

ФОРМА_РЕ = (r"(Besloten Vennootschap|Naamloze Vennootschap|Eenmanszaak|"
            r"Vennootschap onder firma|Commanditaire vennootschap|Maatschap|"
            r"Coöperatie|Stichting|Vereniging)")

class Netherlands(GeoDriver):
    code, title = "NL", "Нидерланды"
    url = "https://www.kvk.nl/en/search/"
    method = "pdf"

    ШАБЛОН = __import__("common.пути", fromlist=["ШАБЛОНЫ"]).ШАБЛОНЫ / "Нидерланды_шаблон.docx"

    # ПУТЬ К docx2pdf.exe (ЕСЛИ НЕ РАБОТАЕТ – ПОМЕНЯЙТЕ НА СВОЙ)
    DOCX2PDF_PATH = r"C:\Users\Мандарин\AppData\Local\Python\pythoncore-3.14-64\Scripts\docx2pdf.exe"

    def __init__(self, br, human):
        super().__init__(br, human)
        self._блок = ""
        self.имя = ""
        self.адрес = ""
        self.kvk = ""
        self.форма = ""
        self.vestiging = ""
        self.handelsnamen = ""
        self.statutaire = ""
        self.activiteiten = ""
        self.generated = {}

    # ---------- поиск и парсинг ----------
    def search(self, c: Company) -> list[Candidate]:
        self.log("  · открываю kvk.nl/en/search")
        self.br.goto(self.url)
        self.page.wait_for_timeout(1200)
        if self._cookie():
            self.log("  · куки приняты (Accept all)")
        else:
            self.log("  · кнопку куки не нашёл (возможно, уже принято)")
        try:
            поле = self.page.get_by_placeholder("Search in kvk.nl").first
            поле.wait_for(state="visible", timeout=8000)
            поле.click()
            поле.fill(c.name)
            self.log(f"  · вбил «{c.name}», жму Search")
            self.page.get_by_role("button", name="Search").first.click(timeout=6000)
        except Exception as e:
            self.log(f"  · поиск не сработал ({type(e).__name__}) — зову человека")
            self.human.stuck("вбей имя в поиск kvk.nl, нажми Search и «Продолжить».", c.name)
        self.page.wait_for_timeout(2000)
        self._раскрыть()
        cands = self.кандидаты_страницы()
        self.log(f"  · нашёл {len(cands)} фирм в выдаче")
        if not cands:
            self.human.stuck(
                "не вижу результатов на kvk.nl — доведи поиск руками (имя → Search), "
                "дождись списка фирм и нажми «Продолжить».", c.name)
            cands = self.кандидаты_страницы()
            self.log(f"  · после человека: {len(cands)} фирм")
        return cands

    def _cookie(self) -> bool:
        for _ in range(3):
            for loc in (self.page.get_by_role("button", name="Accept all"),
                        self.page.get_by_role("button", name="Accepteren"),
                        self.page.get_by_role("button", name="Alles accepteren"),
                        self.page.locator("#onetrust-accept-btn-handler")):
                try:
                    b = loc.first
                    if b.count() and b.is_visible():
                        b.click(timeout=3000)
                        self.page.wait_for_timeout(600)
                        return True
                except Exception:
                    continue
            self.page.wait_for_timeout(700)
        return False

    def _раскрыть(self) -> None:
        try:
            кнопки = self.page.get_by_role("button", name="Show more")
            for i in range(min(кнопки.count(), 10)):
                try:
                    кнопки.nth(i).click(timeout=1500)
                    self.page.wait_for_timeout(150)
                except Exception:
                    continue
        except Exception:
            pass

    def кандидаты_страницы(self) -> list[Candidate]:
        блоки = self.page.locator("[data-ui-test-class='search-result']")
        тексты: list[str] = []
        if блоки.count():
            for i in range(блоки.count()):
                try:
                    тексты.append(блоки.nth(i).inner_text())
                except Exception:
                    continue
        else:
            ссылки = self.page.locator("[aria-label*='met nummer']")
            for i in range(min(ссылки.count(), 30)):
                a = ссылки.nth(i)
                try:
                    бл = a.locator("xpath=ancestor::*[contains(.,'KVK number')][1]")
                    тексты.append(бл.inner_text() if бл.count() else (a.inner_text() or ""))
                except Exception:
                    continue
        cands: list[Candidate] = []
        виденные: set[str] = set()
        for текст in тексты:
            kvk = self._поле(текст, r"KVK number:?\s*(\d{8})")
            ключ = kvk + "|" + self._поле(текст, r"Branch number:?\s*(\d+)")
            if not kvk or ключ in виденные:
                continue
            виденные.add(ключ)
            имя = текст.strip().split("\n")[0].strip()
            cands.append(Candidate(name=имя, address=self._адрес(текст), ref=текст))
        return cands

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            self._блок = self.page.inner_text("body")
        else:
            self._блок = str(cand.ref)
            self.имя = cand.name

    def check(self, c: Company) -> tuple[bool, str]:
        т = self._блок or ""
        self.форма = self._поле(т, ФОРМА_РЕ)
        причина = проверить_форму("NL", self.форма) or проверить_статус(self.форма)
        if причина:
            return False, причина
        низ = т.lower()
        for плохо in ("faillissement", "opgeheven", "ontbonden", "surseance",
                      "uitgeschreven"):
            if плохо in низ:
                return False, f"статус-стоп: {плохо}"
        self.kvk = self._поле(т, r"KVK number:?\s*(\d{8})")
        self.vestiging = self._поле(т, r"Branch number:?\s*(\d+)")
        self.адрес = self._адрес(т)
        self.handelsnamen = self._поле(т, r"Trade names?:\s*([^\n]+)")
        self.statutaire = self._поле(т, r"Name given in the articles:\s*([^\n]+)")
        self.activiteiten = self._деятельность(т)
        if not self.имя:
            self.имя = т.strip().split("\n")[0].strip() or c.name
        return True, ""

    @staticmethod
    def _поле(текст: str, pattern: str) -> str:
        m = re.search(pattern, текст, re.I)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _адрес(текст: str) -> str:
        for строка in текст.split("\n"):
            if re.search(r"\b\d{4} ?[A-Z]{2}\b", строка):
                ч = строка.strip()
                if ч and not re.match(r"(KVK|Branch|RSIN)", ч, re.I):
                    return ч
        return ""

    @staticmethod
    def _деятельность(текст: str) -> str:
        m = re.search(r"\n(De uitoefening[^\n]+|[^\n]*(?:bureau|handel|exploitatie|"
                      r"advies|consultancy|productie|dienstverlening)[^\n]+)", текст, re.I)
        return m.group(1).strip() if m else ""

    def номер(self) -> str:
        return self.kvk

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    # ---------- Генерация недостающих данных ----------
    def _generate_missing(self) -> dict:
        now = datetime.date.today()
        start_date = self._random_date(now - datetime.timedelta(days=365*20), now)
        is_bv = "besloten" in self.форма.lower() or "bv" in self.форма.lower()

        data = {
            "rsin": self._generate_rsin(),
            "statutaire_zetel": self._extract_city(self.адрес) or "Amsterdam",
            "datum_akte": start_date.strftime("%d-%m-%Y"),
            "datum_statuten": self._random_date(start_date, now).strftime("%d-%m-%Y") if random.choice([True, False]) else "—",
            "rechtsvormwijziging": "—",
            "geplaatst_kapitaal": "—",
            "gestort_kapitaal": "—",
            "deponering_jaarstuk": self._random_date(now - datetime.timedelta(days=365), now).strftime("%d-%m-%Y"),
            "startdatum": start_date.strftime("%d-%m-%Y"),
            "werkzame_personen": str(random.randint(0, 500)),
            "datum_vestiging": start_date.strftime("%d-%m-%Y"),
            "sinds": start_date.strftime("%d-%m-%Y"),
            "enig_aandeelhouder_naam": "—",
            "enig_aandeelhouder_adres": "—",
            "enig_aandeelhouder_registratie": "—",
        }

        if is_bv:
            geplaatst = random.randint(1000, 100000)
            gestort = random.randint(geplaatst // 2, geplaatst)
            data["geplaatst_kapitaal"] = f"EUR {geplaatst:,.2f}".replace(",", ".")
            data["gestort_kapitaal"] = f"EUR {gestort:,.2f}".replace(",", ".")

            # Акционер
            first_names = ["Johannes", "Maria", "Petrus", "Anna", "Willem", "Catharina", "Jan", "Eva"]
            last_names = ["Jansen", "de Vries", "van Dijk", "Bakker", "Visser", "Smit", "Bos", "Dekker"]
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            streets = ["Keizersgracht", "Prinsengracht", "Herengracht", "Singel", "Rozengracht"]
            street = random.choice(streets)
            number = random.randint(1, 200)
            postal = f"{random.randint(1000, 9999)}{random.choice(['AA','AB','AC','AD'])}"
            city = random.choice(["Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven"])
            address = f"{street} {number}, {postal} {city}"
            reg = f"Handelsregister KvK {self.kvk or 'XXXXX'}" if random.choice([True, False]) else f"Commercial Register, {city}"
            data["enig_aandeelhouder_naam"] = name
            data["enig_aandeelhouder_adres"] = address
            data["enig_aandeelhouder_registratie"] = reg

        return data

    @staticmethod
    def _generate_rsin() -> str:
        return ''.join(str(random.randint(0, 9)) for _ in range(9))

    @staticmethod
    def _random_date(start: datetime.date, end: datetime.date) -> datetime.date:
        delta = end - start
        random_days = random.randint(0, delta.days)
        return start + datetime.timedelta(days=random_days)

    @staticmethod
    def _extract_city(address: str) -> str:
        if not address:
            return ""
        parts = address.split(',')
        if len(parts) > 1:
            last = parts[-1].strip()
            words = last.split()
            if words:
                return words[-1]
        return ""

    # ---------- Основной метод fetch – создание PDF ----------
    def fetch(self, c: Company, dest: Path) -> Path:
        self.generated = self._generate_missing()

        safe_name = re.sub(r'[^\w\-_.]', '_', self.имя)[:50]
        docx_path = dest.parent / f"{safe_name}.docx"
        pdf_path = docx_path.with_suffix('.pdf')
        docx_path.parent.mkdir(parents=True, exist_ok=True)

        # Создаём DOCX из шаблона
        шаблон_путь = self.ШАБЛОН
        if not шаблон_путь.exists():
            self.log("  ⚠️ Шаблон не найден, создаю документ с нуля")
            doc = Document()
        else:
            doc = Document(str(шаблон_путь))

        self._fill_template(doc)
        doc.save(str(docx_path))

        # Конвертируем DOCX → PDF через внешнюю команду docx2pdf (хардкодный путь)
        try:
            result = subprocess.run(
                [self.DOCX2PDF_PATH, str(docx_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0 and pdf_path.exists():
                self.log(f"  · сохранено PDF: {pdf_path.name}")
                # Удаляем промежуточный DOCX (раскомментируйте, если не нужен)
                # docx_path.unlink()
                return pdf_path
            else:
                self.log(f"  ⚠️ Конвертация не удалась (код {result.returncode}). Сохранён DOCX.")
                if result.stderr:
                    self.log(f"     stderr: {result.stderr.strip()}")
                return docx_path
        except FileNotFoundError:
            self.log(f"  ⚠️ docx2pdf не найдена по пути {self.DOCX2PDF_PATH}. Сохранён DOCX.")
            return docx_path
        except subprocess.TimeoutExpired:
            self.log("  ⚠️ Конвертация превысила таймаут. Сохранён DOCX.")
            return docx_path
        except Exception as e:
            self.log(f"  ⚠️ Ошибка конвертации: {e}. Сохранён DOCX.")
            return docx_path

    def _fill_template(self, doc: Document) -> None:
        vals = {
            "KVK_NUMMER": self.kvk or "—",
            "RSIN": self.generated.get("rsin", "—"),
            "RECHTSVORM": self.форма or "—",
            "STATUTAIRE_NAAM": self.statutaire or self.имя or "—",
            "STATUTAIRE_ZETEL": self.generated.get("statutaire_zetel", "—"),
            "DATUM_AKTE": self.generated.get("datum_akte", "—"),
            "DATUM_STATUTEN": self.generated.get("datum_statuten", "—"),
            "RECHTSVORMWIJZIGING": self.generated.get("rechtsvormwijziging", "—"),
            "GEplaatst_KAPITAAL": self.generated.get("geplaatst_kapitaal", "—"),
            "GESTORT_KAPITAAL": self.generated.get("gestort_kapitaal", "—"),
            "DEPONERING_JAARSTUK": self.generated.get("deponering_jaarstuk", "—"),
            "HANDELSNAAM": self.имя or "—",
            "HANDELSNAMEN": self.handelsnamen or "—",
            "STARTDATUM": self.generated.get("startdatum", "—"),
            "ACTIVITEITEN": self.activiteiten or "—",
            "WERKZAME_PERSONEN": self.generated.get("werkzame_personen", "—"),
            "VESTIGINGSNUMMER": self.vestiging or "—",
            "BEZOEKADRES": self.адрес or "—",
            "DATUM_VESTIGING": self.generated.get("datum_vestiging", "—"),
            "SINDS": self.generated.get("sinds", "—"),
            "ENIG_AANDEELHOUDER_NAAM": self.generated.get("enig_aandeelhouder_naam", "—"),
            "ENIG_AANDEELHOUDER_ADRES": self.generated.get("enig_aandeelhouder_adres", "—"),
            "ENIG_AANDEELHOUDER_REGISTRATIE": self.generated.get("enig_aandeelhouder_registratie", "—"),
        }

        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, vals)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._replace_in_paragraph(paragraph, vals)

    def _replace_in_paragraph(self, paragraph, values: dict):
        full_text = paragraph.text
        if not full_text:
            return
        changed = False
        for key, val in values.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in full_text:
                full_text = full_text.replace(placeholder, val)
                changed = True
        if changed:
            paragraph.clear()
            paragraph.add_run(full_text)