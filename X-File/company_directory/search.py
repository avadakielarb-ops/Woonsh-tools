"""DnB search ported from the supplied loader, without Gemini or document creation."""
import datetime
import re
from .browser import Browser, HumanGate
from .dnb import DnB
from .data.countries import to_name, to_code
from .filters import этаж_1
from .fingerprints import Registry


def discover(folder, country, keyword, count, stop, ask, log, emit):
    country_name = to_name(country)
    code = to_code(country)
    seen = set()
    accepted = []
    human = HumanGate(ask)
    log('DnB: открываю каталог. Gemini и API-ключ не используются.')
    with Browser(folder / 'dnb_browser', human, stop) as browser:
        source = DnB(browser, human, log)
        if not source.search(keyword, country_name):
            human.stuck('Выберите в окне Edge страну '+country_name+' и запустите поиск. После появления таблицы нажмите ОК. Если результатов нет, нажмите Отмена.', keyword)
            valid, reason = source.страна_выдачи_совпадает(country_name)
            if not valid:
                raise RuntimeError('DnB не подтвердил страну: '+reason)

        for page_number in range(10):
            if stop.is_set():
                break
            rows = source.rows()
            if not rows:
                break
            for firm in rows:
                if stop.is_set() or len(accepted) >= count:
                    break
                identity = re.sub(r'\s+', ' ', firm.name.casefold()).strip()
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                valid, reason = этаж_1(firm, code, Registry())
                if not valid:
                    log('Пропущено: ' + firm.name + ' — ' + reason)
                    continue
                aliases = source.СИНОНИМЫ_СТРАН.get(country_name.lower(), (country_name.lower(),))
                if not any(alias in firm.address.lower() for alias in aliases):
                    log('Пропущено: страна строки не подтверждена — ' + firm.name)
                    continue
                log('Читаю карточку: ' + firm.name)
                firm = source.enrich_website(firm, code)
                if stop.is_set():
                    break
                # payment_profile contains the original full address; enrichment splits firm.address.
                match = re.search(r'Address:\s*(.*?)(?:\nWebsite:|$)', firm.payment_profile, re.S)
                address = match.group(1).strip() if match else firm.address.strip()
                row = {'name': firm.name, 'address': address, 'site': firm.website,
                       'country': country, 'source': firm.url, 'registry': '',
                       'website': 'Не проверен' if firm.website else 'Не найден',
                       'bot': 'Не проверена', 'pdf': 'Не получена',
                       'created': datetime.datetime.now().astimezone().isoformat(),
                       'sources': [{'title': 'DnB', 'uri': firm.url}], 'provider': 'DnB'}
                accepted.append(row)
                emit(row)
            if len(accepted) >= count or stop.is_set() or not source.next_page():
                break
    if not accepted and not stop.is_set():
        raise RuntimeError('DnB не вернул компаний с подтверждённой страной. Проверьте слово, страну и доступ к каталогу. Это не ошибка Gemini.')
    return accepted
