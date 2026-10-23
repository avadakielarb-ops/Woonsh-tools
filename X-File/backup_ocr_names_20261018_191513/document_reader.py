"""Shared offline text extraction for single documents and paired stock."""
from pathlib import Path
import tempfile
from native_ocr import image_text
from document_fields import extract_fields, FIELDS


def read_text(app,path):
    if str(path).lower().endswith('.pdf'):
        pages,note=app.read_document_pdf(str(path))
        text='\n'.join(pages)
        if not text.strip() and app.document_fitz:
            with app.document_fitz.open(str(path)) as pdf, tempfile.TemporaryDirectory() as temp:
                output=[]
                for i in range(min(len(pdf),3)):
                    image=Path(temp)/('%d.png'%i)
                    pdf[i].get_pixmap(matrix=app.document_fitz.Matrix(2,2)).save(str(image))
                    output.append(image_text(image,regions=True))
                text='\n'.join(output)
        return text
    exe=app.find_document_ocr()
    text=app.ocr_document_image(exe,str(path)) if exe else ''
    if len([value for value in extract_fields(text).values() if value])<3:
        try:text+='\n'+image_text(path,regions=True)
        except Exception:
            if not text.strip():raise
    return text


def paired_fields(app,paths):
    texts=[]
    for path in paths:
        try:texts.append(read_text(app,path))
        except Exception:texts.append('')
    # Back MRZ is processed first; its checked dates and consistent names
    # take precedence over unlabelled suggestions from the front.
    result=extract_fields('\n'.join(reversed(texts)))
    for text in texts:
        values=extract_fields(text)
        for field in FIELDS:
            if not result.get(field):result[field]=values.get(field,'')
    return result
