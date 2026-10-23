"""Local document-side ranking; no face recognition or remote requests."""
import re
import unicodedata
from document_reader import read_text


def classify_text(text):
    folded=unicodedata.normalize('NFKD',text.upper())
    folded=''.join(c for c in folded if not unicodedata.combining(c))
    compact=re.sub(r'[^A-Z]','',folded)
    front_words=('APELLIDOS','NOMBRE','NACIMIENTO','VALIDEZ','SURNAME','GIVENNAMES',
                 'DATEOFBIRTH','DATEOFEXPIRY','PASSPORT','IDENTITYCARD','IDENTIDAD','ESPANA')
    back_words=('DOMICILIO','LUGARDENACIMIENTO','LUGARNACIMIENTO','HIJODE','EQUIPO',
                'ADDRESS','RESIDENCE','PADRE','MADRE')
    front=sum(word in compact for word in front_words)
    back=sum(word in compact for word in back_words)
    mrz_lines=[line for line in folded.splitlines() if len(line)>18 and line.count('<')>=3]
    mrz=bool(mrz_lines or re.search(r'\bI[D<]ESP[A-Z0-9<]{5}',folded))
    if mrz:
        return {'side':'back','score':20+min(len(mrz_lines),5),'reason':'MRZ / оборот'}
    if back>=2 and back>=front:
        return {'side':'back','score':back*3,'reason':'Поля оборотной стороны'}
    if front>=2:
        return {'side':'front','score':front*3,'reason':'Поля лицевой стороны'}
    if back>=1:
        return {'side':'back','score':back,'reason':'Слабое совпадение; проверьте'}
    return {'side':'unknown','score':0,'reason':'Документ не определён'}


def classify_file(app,path):
    try:return classify_text(read_text(app,path))
    except Exception:return {'side':'unknown','score':0,'reason':'Текст не прочитан'}
