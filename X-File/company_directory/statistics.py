from pathlib import Path
from .fallback import COUNTRIES
from .data.countries import to_code


def summarize(rows):
    result={country:[0]*8 for country in COUNTRIES}
    for row in rows:
        if row.get('country') not in result:continue
        values=result[row['country']]
        site=bool(row.get('site','').strip())
        pdf=bool(row.get('pdf_path') and Path(row['pdf_path']).is_file())
        checked=row.get('bot') in ('Уже есть','Добавлена')
        accepted=row.get('bot')=='Добавлена'
        for index,flag in enumerate((True,site,site and pdf,not site,not site and pdf,site and pdf and accepted,checked,not checked)):
            values[index]+=int(flag)
    return [(('IS' if c=='Iceland' else to_code(c)),c,*v) for c,v in result.items()]
