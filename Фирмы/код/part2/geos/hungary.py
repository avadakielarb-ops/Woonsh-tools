"""
ВЕНГРИЯ — e-cegjegyzek.hu. Драйвер «печать страницы».

Поток (из записи codegen + скриншоты):
  1. /?cegkereses → баннер «Elfogadom» → поле «Cégnév kezdete» (placeholder «név»)
     → кнопка «Keresés»
  2. ⚠ КАПЧА (reCAPTCHA с картинками) — зовём человека, он решает, жмёт «Tovább».
     Дальше может быть галочка «Felhasználási feltételek elfogadása» → «Tovább».
  3. в выдаче ссылка результата: короткое имя + полное имя, ниже адрес,
     Cégjegyzékszám и Adószám → кликаем, попадаем на карточку
  4. карточка: Cégjegyzékszám · Adószám · Székhely (адрес) · имя (короткое + полное)
  5. «Tárolt cégkivonat» → ⚠ КАПЧА ВТОРОЙ РАЗ → «Tovább» → страница выписки
     «Tárolt Cégkivonat» → печатаем в PDF через CDP.

ВАЖНО: это гео с ОБЯЗАТЕЛЬНЫМ человеком — капча тут дважды за фирму, обойти нельзя.
РЕШЕНО (сохранено): ищем по КОРОТКОМУ имени («DIAMOND SHINE Kft.») — поле
«Cégnév kezdete» = «начало названия». Запас: имя без правовой формы.
Номер — Cégjegyzékszám (вида 20-09-063203).
"""
from __future__ import annotations

import re
from pathlib import Path

from part2.core.matching import Candidate, normalize
from part2.core.models import Company
from part2.core.формы import проверить_статус, проверить_форму
from part2.geos.base import GeoDriver

BASE = "https://www.e-cegjegyzek.hu"
# венгерские «стопы» стоят прямо в НАЗВАНИИ фирмы
ПЛОХОЕ_ИМЯ = ("felszámolás", "felszamolas", "végelszámolás", "vegelszamolas",
              "kényszertörlés", "kenyszertorles", "csődeljárás", "csodeljaras")


class Hungary(GeoDriver):
    code, title = "HU", "Венгрия"
    url = f"{BASE}/?cegkereses"
    method = "print"

    def __init__(self, br, human):
        super().__init__(br, human)
        self.имя = ""
        self.адрес = ""
        self.cegjegyzek = ""

    # ---------- поиск ----------

    def search(self, c: Company) -> list[Candidate]:
        # ОДИН поиск (сайт капчит КАЖДЫЙ запрос — второй заход = вторая капча,
        # из-за этого он «заново вводил поиск»). Не нашли/застряли → человек.
        self._заглушить_печать()                        # убрать нативный диалог печати
        self.br.goto(self.url)
        # из записи codegen: клик по центру страницы (снимает оверлей/ставит фокус)
        try:
            центр = self.page.locator("#kozep").first
            if центр.count():
                центр.click(timeout=2000)
        except Exception:
            pass
        self._cookie()
        try:
            поле = self.page.get_by_placeholder("név", exact=True).first
            поле.click()
            поле.fill(c.name)
            self.page.get_by_role("button", name="Keresés", exact=True).first.click()
        except Exception:
            self.human.stuck("вбей имя фирмы в «Cégnév kezdete», нажми Keresés и "
                             "«Продолжить».", c.name)
        self.page.wait_for_timeout(1500)
        self.log("  · жду капчу (реши её и нажми «Продолжить»)")
        self._капча_и_дальше(c.name)                    # капча → Tovább → условия → Tovább
        cands = self.кандидаты_страницы()
        self.log(f"  · после капчи/условий вижу {len(cands)} фирм в выдаче")
        if not cands and (self._есть_условия() or self._есть_tovabb()):
            self.human.stuck(
                "доведи шаг вручную: пролистай условия ВНИЗ, поставь галку "
                "«Felhasználási feltételek elfogadása», нажми Tovább, дождись списка "
                "фирм и нажми «Продолжить».", c.name)
            cands = self.кандидаты_страницы()
        return cands

    def _заглушить_печать(self) -> None:
        """
        Страница «Tárolt Cégkivonat» сама зовёт window.print() → выскакивает
        НАТИВНЫЙ диалог печати Chrome (модальный, всё блокирует, требует руками
        вписать имя и нажать «Сохранить»). Глушим его на всех будущих навигациях —
        а PDF сохраняем сами через CDP (тихо, в файл, именем фирмы).
        """
        if getattr(self, "_печать_заглушена", False):
            return
        try:
            self.page.add_init_script("window.print = function(){};")
            self._печать_заглушена = True
        except Exception:
            pass

    def _cookie(self) -> None:
        try:
            b = self.page.get_by_role("button", name="Elfogadom").first
            if b.count() and b.is_visible():
                b.click()
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    def _капча_и_дальше(self, фирма: str) -> None:
        """
        СТРОГО как в записи: капча (человек) → Tovább (1×) → [условия: галка → Tovább 1×].
        НЕ жмём Tovább жадно — лишний Tovább после условий уводил на главную.
        """
        # ЖДЁМ появления капчи до 10 с. Здесь она будет ТОЧНО — сайт капчит
        # каждый запрос, — но виджет reCAPTCHA рисуется скриптом не мгновенно.
        # Проверяя страницу сразу, мы звали человека показывать пустоту.
        self.br.check_captcha(фирма, ждать_мс=10000)   # человек решает reCAPTCHA
        self._нажать_tovabb()                          # 1× Tovább (модалка капчи)
        self.page.wait_for_timeout(1000)
        # модалка условий (только 1-й раз за сессию) — галка + Tovább, по ОДНОМУ разу
        if self._принять_условия():
            self._нажать_tovabb()                      # 1× Tovább (модалка условий)
            self.page.wait_for_timeout(1000)

    def _есть_условия(self) -> bool:
        try:
            h = self.page.get_by_text("Felhasználási feltételek elfogadása").first
            return bool(h.count()) and h.is_visible()
        except Exception:
            return False

    def _есть_tovabb(self) -> bool:
        try:
            b = self.page.get_by_role("button", name="Tovább").first
            return bool(b.count()) and b.is_visible()
        except Exception:
            return False

    def _принять_условия(self) -> bool:
        """
        Модалка условий. Галка/кнопка ВНИЗУ за прокруткой — сначала ПРОКРУЧИВАЕМ
        к галке, потом клик по тексту «Felhasználási feltételek elfogadása» (ровно
        как ты вручную) + force-check. Идемпотентно: стоит — не трогаем.
        True = модалка условий была.
        """
        if not self._есть_условия():
            return False
        метка = self.page.get_by_text("Felhasználási feltételek elfogadása").first
        try:
            метка.scroll_into_view_if_needed(timeout=3000)   # ПРОКРУТКА вниз к галке
        except Exception:
            pass
        self.page.wait_for_timeout(200)
        # уже отмечено — не трогаем (повторный клик снял бы)
        try:
            cb0 = self.page.locator("input[type=checkbox]:visible").last
            if cb0.count() and cb0.is_checked():
                return True
        except Exception:
            pass
        try:
            метка.click(timeout=2500)
        except Exception:
            try:
                метка.click(force=True, timeout=2500)
            except Exception:
                pass
        self.page.wait_for_timeout(300)
        try:
            cb = self.page.locator("input[type=checkbox]:visible").last
            if cb.count() and not cb.is_checked():
                cb.check(force=True, timeout=2500)
        except Exception:
            pass
        return True

    def _нажать_tovabb(self) -> bool:
        """Нажать «Tovább», ПРЕДВАРИТЕЛЬНО прокрутив к ней (она внизу модалки)."""
        try:
            b = self.page.get_by_role("button", name="Tovább").first
            if b.count() and b.is_visible() and b.is_enabled():
                try:
                    b.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                b.click(timeout=3000)
                self.page.wait_for_timeout(700)
                return True
        except Exception:
            pass
        return False

    # имя-фирма ОБЯЗАНА иметь венгерскую форму (Kft./Zrt./Bt./Kkt.…) — так отсекаем
    # шапку сайта «IGAZSÁGÜGYI MINISZTÉRIUM» и навигацию. \b — чтобы «Rt» не ловилось внутри слов.
    _ФОРМА_РЕ = re.compile(r"\b(Kft|Zrt|Nyrt|Bt|Kkt|Rt|Kht|Kdt)\b\.?|\bTársaság\b", re.I)

    def кандидаты_страницы(self) -> list[Candidate]:
        """
        Результат-фирма = ссылка, в чьём НЕБОЛЬШОМ блоке есть Cégjegyzékszám
        (XX-XX-XXXXXX) и венгерская форма (Kft/Zrt/Társaság). Ссылки тут JS-овые
        (href='#'), поэтому ref = САМ ЛОКАТОР (кликаем), а не URL.
        Навигацию/кнопки отсекаем: короткое имя без формы + огромный блок = не фирма.
        """
        cands: list[Candidate] = []
        виденные: set[str] = set()
        ссылки = self.page.locator("a")
        for i in range(min(ссылки.count(), 150)):
            ссылка = ссылки.nth(i)
            try:
                имя = (ссылка.inner_text() or "").strip().split("\n")[0].strip()
            except Exception:
                continue
            if not имя or len(имя) < 4:
                continue
            # имя фирмы ОБЯЗАНО иметь форму (Kft./Zrt.…). Без формы — это шапка/навигация.
            if not self._ФОРМА_РЕ.search(имя):
                continue
            блок = ссылка.locator("xpath=ancestor::*[contains(.,'Cégjegyzékszám')][1]")
            if not блок.count():
                continue
            try:
                текст = блок.inner_text()
            except Exception:
                continue
            if len(текст) > 900:                   # это не карточка результата, а вся страница
                continue
            mnum = re.search(r"\b(\d{2}-\d{2}-\d{6})\b", текст)
            if not mnum or mnum.group(1) in виденные:
                continue
            виденные.add(mnum.group(1))
            href = (ссылка.get_attribute("href") or "").strip()
            # href='#'/пусто/javascript → ссылка JS-овая; кликать будем ПО ИМЕНИ
            # (маркер "CLICK"), а НЕ по позиции — позиция на SPA «плывёт».
            ref = href if (href and href != "#"
                           and not href.lower().startswith("javascript")) else "CLICK"
            cands.append(Candidate(name=имя,
                                   address=re.sub(r"\s+", " ", текст).strip(), ref=ref))
        return cands

    # ---------- карточка ----------

    def open(self, cand: Candidate) -> None:
        if cand.ref == "HUMAN":
            self.log("  · фирму выбрал человек")
            return
        ref = cand.ref
        if isinstance(ref, str) and ref.startswith("http"):
            self.br.goto(ref)                      # редкий случай: реальный URL
        else:                                      # JS-ссылка → клик ПО ИМЕНИ фирмы
            self.log(f"  · кликаю по фирме: «{cand.name}»")
            self._кликнуть_результат(cand.name)
        # ждём КАРТОЧКУ: на ней появляется Cégjegyzékszám (XX-XX-XXXXXX)
        try:
            self.page.wait_for_function(
                "() => /\\d{2}-\\d{2}-\\d{6}/.test(document.body.innerText)",
                timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
        # диагностика: куда попали
        try:
            тело = self.page.inner_text("body")
            m = re.search(r"\b\d{2}-\d{2}-\d{6}\b", тело)
            if m:
                self.log(f"  · открылась карточка (Cégjegyzékszám {m.group(0)})")
            else:
                загол = next((s.strip() for s in тело.split("\n") if s.strip()), "")[:50]
                self.log(f"  · это НЕ карточка, на экране: «{загол}…»")
        except Exception:
            pass

    def _кликнуть_результат(self, имя: str) -> None:
        """Клик по результату ПО ИМЕНИ (стабильно). Позиционный клик на SPA плыл."""
        for тип, loc in (("link", self.page.get_by_role("link", name=имя)),
                         ("text", self.page.get_by_text(имя, exact=False))):
            try:
                эл = loc.first
                if эл.count():
                    try:
                        эл.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    эл.click(timeout=6000)
                    self.log(f"  · клик по результату ({тип})")
                    return
            except Exception:
                continue
        self.log("  · НЕ нашёл ссылку результата для клика!")

    def check(self, c: Company) -> tuple[bool, str]:
        текст = self.page.inner_text("body")

        # GUARD: мы должны быть на КАРТОЧКЕ фирмы — там есть Cégjegyzékszám вида
        # XX-XX-XXXXXX. Нет его → нас унесло не туда (главная и т.п.), не качаем.
        if not re.search(r"\b\d{2}-\d{2}-\d{6}\b", текст):
            return False, "не карточка фирмы (нет Cégjegyzékszám) — открылась не та страница"

        # ИМЯ: на карточке две строки — короткое («… Kft.») и ПОЛНОЕ. Это две
        # последние непустые строки ПЕРЕД «Cégjegyzékszám» (h1 читаем как запас).
        до = [s.strip() for s in текст.split("Cégjegyzékszám")[0].split("\n") if s.strip()]
        полное = до[-1] if до else ""
        короткое = до[-2] if len(до) >= 2 else ""
        if not полное:
            h1 = self.page.locator("h1").first
            полное = h1.inner_text().strip() if h1.count() else c.name
        self.имя = полное or короткое or c.name

        # венгерские стопы стоят В НАЗВАНИИ («… felszámolás alatt») —
        # проверяем ОБА варианта имени
        низ = f"{полное} {короткое}".lower()
        for плохо in ПЛОХОЕ_ИМЯ:
            if плохо in низ:
                return False, f"в названии стоп-статус: {плохо}"
        причина = проверить_статус(self.имя) or проверить_форму("HU", self.имя)
        if причина:
            return False, причина

        self.cegjegyzek = self._поле(текст, "Cégjegyzékszám")
        self.адрес = self._поле(текст, "Székhely")
        return True, ""

    @staticmethod
    def _поле(текст: str, подпись: str) -> str:
        m = re.search(rf"\b{re.escape(подпись)}\b:?\s*\n?\s*([^\n]+)", текст, re.I)
        if not m:
            return ""
        # у адреса в конце бывает ссылка «Térkép» — отрезаем
        return re.sub(r"\s*Térkép\s*$", "", m.group(1)).strip()

    def номер(self) -> str:
        return self.cegjegyzek

    def данные_реестра(self) -> dict:
        return {"имя": self.имя, "адрес": self.адрес}

    # ---------- выписка ----------

    def fetch(self, c: Company, dest: Path) -> Path:
        # ШАГ 1: открыть саму выписку «Tárolt cégkivonat» (кнопка/ссылка) + капча №2
        self.log("  · жму «Tárolt cégkivonat»")
        try:
            кн = self.page.get_by_role("link", name="Tárolt cégkivonat").first
            if not (кн.count() and кн.is_visible()):
                кн = self.page.get_by_role(
                    "button", name="Tárolt cégkivonat").first
            if кн.count():
                кн.click(timeout=5000)
                self.page.wait_for_timeout(800)
        except Exception:
            pass
        self.log("  · капча №2 (реши и нажми «Продолжить»)")
        self._капча_и_дальше(c.name)          # ⚠ капча ВТОРОЙ раз → Tovább

        # ШАГ 2: убеждаемся, что перед нами ИМЕННО выписка (а не главная/карточка).
        # Признак выписки — заголовок «Tárolt Cégkivonat» + Cégjegyzékszám в тексте.
        for _ in range(2):
            if self._на_выписке():
                break
            # не выписка → человек доводит вручную (капча/Tovább/кнопка) и жмёт «Продолжить»
            self.human.stuck(
                "открой выписку «Tárolt cégkivonat» (реши капчу, нажми Tovább), "
                "чтобы на экране был текст «Tárolt Cégkivonat» и данные фирмы, "
                "потом нажми «Продолжить». Сохранять НЕ надо — я сам.", c.name)

        # ШАГ 3: ТИХОЕ сохранение в PDF (это и есть «Ctrl+P → Сохранить как PDF»,
        # но без системного диалога) — именем фирмы. window.print уже заглушён.
        try:
            self.page.evaluate("window.print = function(){};")
        except Exception:
            pass
        return self.br.print_to_pdf(dest)

    def _на_выписке(self) -> bool:
        """На экране действительно «Tárolt Cégkivonat» (заголовок + Cégjegyzékszám)?"""
        try:
            текст = self.page.inner_text("body")
        except Exception:
            return False
        return ("Tárolt Cégkivonat" in текст
                and bool(re.search(r"\b\d{2}-\d{2}-\d{6}\b", текст)))
