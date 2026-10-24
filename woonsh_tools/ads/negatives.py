"""Встроенные минус-слова по языкам (из X-File/ads_generator/app.py коллеги)."""

_NEG = {
    "en": "free|freebie|download|torrent|crack|pirated|jobs|job|careers|vacancy|vacancies|salary|hiring|resume|cv|internship|"
          "volunteer|diy|how to|tutorial|wiki|wikipedia|pdf|forum|reddit|youtube|video|meaning|definition|what is|example|"
          "template|sample|essay|homework|lyrics|quotes|images|pictures|wallpaper|for kids|game|games|movie|movies|porn|xxx|"
          "scam|complaint|complaints|lawsuit|phone number|login|sign in|news|memes",
    "ru": "бесплатно|скачать|торрент|взлом|вакансии|работа|зарплата|резюме|стажировка|своими руками|как сделать|"
          "учебник|реферат|курсовая|википедия|форум|ютуб|видео|смотреть онлайн|фото|картинки|обои|игра|игры|фильм|порно|"
          "жалоба|развод|мошенники|что такое|значение|определение|пример|шаблон|образец|вход|личный кабинет|"
          "песня|текст песни|стихи|анекдоты|сочинение|новости|мемы",
    "uk": "безкоштовно|завантажити|торрент|вакансії|робота|зарплата|резюме|стажування|власноруч|як зробити|підручник|"
          "реферат|вікіпедія|форум|відео|дивитися онлайн|фото|картинки|шпалери|гра|ігри|фільм|порно|скарга|шахраї|"
          "що таке|значення|визначення|приклад|шаблон|зразок|вхід|пісня|вірші|анекдоти|новини|меми",
    "de": "kostenlos|gratis|download|herunterladen|torrent|jobs|stellenangebote|gehalt|lebenslauf|praktikum|selber machen|"
          "anleitung|wikipedia|forum|video|bilder|spiel|film|porno|beschwerde|was ist|bedeutung|definition|beispiel|"
          "vorlage|muster|login|nachrichten",
    "es": "gratis|descargar|torrent|empleo|trabajo|salario|curriculum|prácticas|hazlo tú mismo|tutorial|wikipedia|foro|"
          "vídeo|imágenes|juego|película|porno|queja|qué es|significado|definición|ejemplo|plantilla|login|noticias",
    "fr": "gratuit|télécharger|torrent|emploi|offre d'emploi|salaire|cv|stage|faire soi-même|tutoriel|wikipédia|forum|"
          "vidéo|images|jeu|film|porno|plainte|qu'est-ce que|signification|définition|exemple|modèle|connexion|actualités",
    "pl": "za darmo|darmowe|pobierz|torrent|praca|oferty pracy|wynagrodzenie|cv|staż|zrób to sam|poradnik|wikipedia|forum|"
          "wideo|zdjęcia|gra|film|porno|skarga|co to jest|znaczenie|definicja|przykład|wzór|logowanie|wiadomości",
    "lv": "bezmaksas|lejupielādēt|darbs|vakances|alga|cv|prakse|pašam|vikipēdija|forums|video|attēli|spēle|filma|porno|"
          "sūdzība|kas ir|nozīme|piemērs|paraugs|ziņas",
}
BUILTIN_NEG = {k: v.split("|") for k, v in _NEG.items()}


def merge(lang, model_words=(), custom=()):
    base = (lang or "en").split("-")[0].lower()
    seen, out = set(), []
    for w in list(BUILTIN_NEG.get(base, BUILTIN_NEG["en"])) + list(model_words) + list(custom):
        k = w.strip().casefold()
        if k and k not in seen:
            seen.add(k)
            out.append(w.strip())
    return out
