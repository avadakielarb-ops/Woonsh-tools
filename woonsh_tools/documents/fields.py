"""
Извлечение полей документов: MRZ-парсинг (TD3/TD1), дат, ФИО.
Из X-File document_fields.py — адаптировано для Woonsh Tools.
"""

import datetime as dt
import re
import unicodedata
from collections import Counter

FIELDS = ('ФИО', 'Действителен до', 'Дата рождения', 'Страна выдачи', 'Вид документа')


def valid_date(value):
    value = value.strip()
    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d',
                '%d %m %Y', '%d %b %Y', '%d %B %Y'):
        try:
            return dt.datetime.strptime(value, fmt).date().strftime('%d.%m.%Y')
        except ValueError:
            pass
    return ''


def mrz_check(text, digit):
    if not digit.isdigit():
        return False
    def number(char):
        return int(char) if char.isdigit() else (ord(char) - 55 if 'A' <= char <= 'Z' else 0)
    return sum(number(c) * [7, 3, 1][i % 3] for i, c in enumerate(text)) % 10 == int(digit)


def mrz_date(value, birth=False):
    today = dt.date.today()
    candidates = []
    for century in (1900, 2000, 2100):
        try:
            date = dt.date(century + int(value[:2]), int(value[2:4]), int(value[4:]))
        except ValueError:
            continue
        if birth and 0 <= (today - date).days <= 110 * 366:
            candidates.append(date)
        elif not birth and today.year - 15 <= date.year <= today.year + 30:
            candidates.append(date)
    if len(candidates) != 1:
        return ''
    return candidates[0].strftime('%d.%m.%Y')


def extract_fields(text):
    """Извлечение полей из OCR-текста документа."""
    result = {field: '' for field in FIELDS}
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    labels = {
        'ФИО': ['full name', 'name of holder', 'фио', 'ф.и.о.'],
        'Дата рождения': ['date of birth', 'birth date', 'дата рождения',
                          'geburtsdatum', 'syntymäaika', 'fecha de nacimiento', 'nacimiento'],
        'Действителен до': ['date of expiry', 'date of expiration', 'expiry date',
                            'valid until', 'действителен до', 'срок действия',
                            'gültig bis', 'voimassa asti', 'validez',
                            'valido hasta', 'válido hasta', 'fecha de caducidad'],
        'Страна выдачи': ['issuing country', 'country of issue', 'страна выдачи',
                          'страна', 'ausstellungsstaat'],
        'Вид документа': ['document type', 'type of document', 'вид документа',
                          'тип документа'],
    }

    extras = {}
    for i, line in enumerate(lines):
        for field, aliases in labels.items():
            for label in aliases:
                match = re.match(
                    r'^' + re.escape(label) + r'\s*(?::|=|\s[-–]\s)\s*(.+)$', line, re.I)
                value = (match.group(1).strip() if match
                         else (lines[i + 1] if line.casefold() == label and i + 1 < len(lines)
                               else ''))
                if value and not result[field]:
                    if field in ('Дата рождения', 'Действителен до'):
                        date = re.search(
                            r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4}'
                            r'|\d{1,2}\s+\w+\s+\d{4})\b', value)
                        value = valid_date(date.group()) if date else ''
                    if value:
                        result[field] = value

        for key, names in {
            'surname': ['surname', 'фамилия', 'nachname', 'familienname',
                         'sukunimi', 'cognome', 'nazwisko', 'apellidos'],
            'given': ['given names', 'given name', 'имя', 'vornamen', 'vorname',
                      'etunimet', 'nome', 'imiona', 'nombre'],
        }.items():
            for label in names:
                match = re.match(
                    r'^' + re.escape(label) + r'\s*[:=]\s*(.+)$', line, re.I)
                value = (match.group(1).strip() if match
                         else (lines[i + 1] if line.casefold().strip(' :') == label
                               and i + 1 < len(lines) else ''))
                if value and not any(c.isdigit() for c in value) and len(value) > 1:
                    extras[key] = value

    if not result['ФИО'] and extras.get('surname') and extras.get('given'):
        result['ФИО'] = extras['surname'] + ' ' + extras['given']

    # TD3 паспорт MRZ: две строки по 44 символа
    for i, line in enumerate(lines[:-1]):
        first = re.sub(r'\s', '', line.upper())
        second = re.sub(r'\s', '', lines[i + 1].upper())
        if (len(first) == 44 and first.startswith('P<')
                and len(second) == 44
                and re.fullmatch(r'[A-Z0-9<]+', first + second)):
            name = first[5:].split('<<', 1)
            if len(name) == 2:
                result['ФИО'] = result['ФИО'] or ' '.join(
                    (name[0] + ' ' + name[1]).replace('<', ' ').split())
            result['Вид документа'] = result['Вид документа'] or 'Паспорт'
            result['Страна выдачи'] = result['Страна выдачи'] or first[2:5]
            if mrz_check(second[13:19], second[19]):
                result['Дата рождения'] = (result['Дата рождения']
                                           or mrz_date(second[13:19], True))
            if mrz_check(second[21:27], second[27]):
                result['Действителен до'] = (result['Действителен до']
                                             or mrz_date(second[21:27]))

    # TD1 ID-карта MRZ: три строки по 30 символов
    for i in range(len(lines) - 2):
        first = re.sub(r'\s', '', lines[i].upper())
        second = re.sub(r'\s', '', lines[i + 1].upper())
        third = re.sub(r'\s', '', lines[i + 2].upper())
        if (len(first) == len(second) == len(third) == 30
                and first[0] in 'IAC'
                and re.fullmatch(r'[A-Z0-9<]+', first + second + third)):
            birth = second[:6]
            expiry = second[8:14]
            if mrz_check(birth, second[6]) and mrz_check(expiry, second[14]):
                name = third.split('<<', 1)
                if len(name) == 2 and all(
                        any(c.isalpha() for c in part) for part in name):
                    result['ФИО'] = ' '.join(
                        (name[0] + ' ' + name[1]).replace('<', ' ').split())
                result['Дата рождения'] = mrz_date(birth, True) or result['Дата рождения']
                result['Действителен до'] = mrz_date(expiry) or result['Действителен до']
                result['Страна выдачи'] = first[2:5]
                result['Вид документа'] = 'ID-карта'
                break

    # Испанский DNI
    folded = unicodedata.normalize('NFKD', text.casefold())
    folded = ''.join(c for c in folded if not unicodedata.combining(c))

    spanish = ('espana' in folded and 'pasaporte' not in folded
               and (('documento' in folded or 'identidad' in folded or 'dni' in folded)
                    and 'apellidos' in folded)
               or (re.search(r'(?m)^\s*ESP\s*$', text)
                   and re.search(r'\b\d{8}[A-Z]\b', text)))

    if spanish:
        result['Страна выдачи'] = result['Страна выдачи'] or 'Испания'
        result['Вид документа'] = result['Вид документа'] or 'ID-карта'
        if not result['ФИО']:
            for i, line in enumerate(lines):
                if line.casefold().strip(' :.') == 'apellidos':
                    names = []
                    for candidate in lines[i + 1:i + 7]:
                        low = candidate.casefold().strip(' :.')
                        if low == 'nombre':
                            continue
                        if (low in ('sexo', 'nacionalidad', 'esp')
                                or len(candidate) < 2
                                or any(c.isdigit() for c in candidate)):
                            break
                        if not re.fullmatch(r"[A-Za-zÀ-ÿ' -]+", candidate):
                            break
                        names.append(candidate)
                        if len(names) == 3:
                            break
                    if len(names) == 3:
                        result['ФИО'] = ' '.join(names)
                        break

        if not result['ФИО']:
            for i, line in enumerate(lines):
                if line.strip() == 'ESP' and i >= 3:
                    candidates = lines[i - 3:i]
                    if all(len(v) > 1 and re.fullmatch(r"[A-Za-zÀ-ÿ' -]+", v)
                           for v in candidates):
                        result['ФИО'] = ' '.join(candidates)
                        break

        dates = []
        for match in re.finditer(
                r'(?<!\d)(\d{2})[ ./-]+(\d{2})[ ./-]+(\d{4})(?!\d)', text):
            date = valid_date('.'.join(match.groups()))
            if date and date not in dates:
                dates.append(date)

        if len(dates) == 2:
            today = dt.date.today()
            past = [d for d in dates
                    if dt.datetime.strptime(d, '%d.%m.%Y').date() < today]
            future = [d for d in dates
                      if dt.datetime.strptime(d, '%d.%m.%Y').date() >= today]
            if len(past) == len(future) == 1:
                result['Дата рождения'] = result['Дата рождения'] or past[0]
                result['Действителен до'] = result['Действителен до'] or future[0]

    # Повторяющиеся имена над ESP
    if not result['ФИО'] and ('espana' in folded or 'españa' in text.casefold()):
        candidates = []
        blocked = {'APELLIDOS', 'NOMBRE', 'NACIONALIDAD', 'SEXO', 'DOCUMENTO',
                   'IDENTIDAD', 'NACIONAL', 'ESPANA', 'ESPAÑA'}
        for i, line in enumerate(lines):
            if line.strip() == 'ESP' and i >= 3:
                values = lines[i - 3:i]
                if all(len(v) > 1
                       and re.fullmatch(r"[A-Za-zÀ-ÿ' -]+", v)
                       and v.upper() not in blocked for v in values):
                    candidates.append(' '.join(' '.join(v.split()) for v in values))
        counts = Counter(candidates)
        repeated = [(name, count) for name, count in counts.items() if count >= 2]
        if repeated:
            repeated.sort(key=lambda pair: pair[1], reverse=True)
            if len(repeated) == 1 or repeated[0][1] > repeated[1][1]:
                result['ФИО'] = repeated[0][0]
                result['Страна выдачи'] = result['Страна выдачи'] or 'Испания'
                result['Вид документа'] = result['Вид документа'] or 'ID-карта'

    # Определение типа по ключевым словам
    if not result['Вид документа']:
        lower = text.casefold()
        for needles, kind in [
            (('passport', 'паспорт', 'reisepass', 'passi', 'pasaporte'), 'Паспорт'),
            (('identity card', 'id card', 'personalausweis', 'henkilökortti'), 'ID-карта'),
            (("driving licence", "driver license", "водительское удостоверение"),
             'Водительское удостоверение'),
        ]:
            if any(word in lower for word in needles):
                result['Вид документа'] = kind
                break

    return result
