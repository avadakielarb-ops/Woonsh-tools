# -*- coding: utf-8 -*-
"""Виртуальный прогон №4 — Часть 3 (поиск сайтов, DuckDuckGo): офлайн-логика.

Проверяет НОВУЮ логику: реестры — источник (сайт-поле + адрес), а не ответ;
два адреса (DNB + реестр); подтверждение по любому из них; фильтры."""
import sys
from pathlib import Path
# ПУТЬ ОТ СЕБЯ, а не вписанный: адрес полигона перестал быть корнем проекта.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part3.поиск_сайтов import (
    _домен, _раскрыть_ddg, _мусор, это_реестр, _исключён, годится_как_ответ,
    классифицировать, кандидаты_из_выдачи, извлечь_сайт_из_текста, адрес_из_реестра,
    адрес_совпал, любой_адрес_совпал, имя_в_домене, построить_запрос,
    похоже_на_каталог)

ок = пров = 0
def чек(имя, усл, д=""):
    global ок, пров
    пров += 1
    if усл: ок += 1
    print(("  OK  " if усл else "  !!  ") + имя + (f"  -> {д}" if not усл and д else ""))

print("\n=== домен / раскрытие DDG ===")
чек("_домен убирает www и путь", _домен("https://www.aqua-metal.com/x/y") == "aqua-metal.com")
ддг = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.aquametal.nl%2Fcontact&rut=abc"
чек("раскрывает uddg → реальный url", _раскрыть_ddg(ддг) == "https://www.aquametal.nl/contact", _раскрыть_ddg(ддг))
чек("обычную ссылку не трогает", _раскрыть_ddg("https://x.com/y") == "https://x.com/y")

print("\n=== классификация мусор / реестр / кандидат ===")
чек("поисковик — мусор", _мусор("https://www.bing.com/search?q=x") and _мусор("https://fr.wikipedia.org/wiki/Heat"))
чек("соцсеть — мусор", _мусор("https://www.linkedin.com/company/x"))
чек("annuaire — реестр (не мусор)", это_реестр("https://annuaire-entreprises.data.gouv.fr/entreprise/heat-529") and not _мусор("https://annuaire-entreprises.data.gouv.fr/x"))
чек("infonet/societe/pappers — реестры", это_реестр("https://infonet.fr/entreprises/915-heat") and это_реестр("https://www.societe.com/x") and это_реестр("https://www.pappers.fr/e/915"))
чек("реестр НЕ годится как ответ", not годится_как_ответ("https://infonet.fr/entreprises/915-heat"))
чек("мусор НЕ годится как ответ", not годится_как_ответ("https://www.bing.com/search"))
чек("сайт фирмы годится как ответ", годится_как_ответ("https://www.homechauffage.fr/"))

ссылки = [
    "https://annuaire-entreprises.data.gouv.fr/entreprise/heat-529",  # реестр
    "https://infonet.fr/entreprises/915-heat-logistics/",             # реестр
    "https://www.linkedin.com/company/heat",                          # мусор
    "https://www.homechauffage.fr/",                                  # кандидат ✓
    "https://www.homechauffage.fr/contact",                          # тот же домен — дедуп
    "https://heatlog.fr/about",                                       # кандидат ✓
]
канд, реестры = классифицировать(ссылки)
чек("кандидаты — только реальные сайты фирм",
    канд == ["https://www.homechauffage.fr/", "https://heatlog.fr/about"], канд)
чек("реестры отделены (2 шт.)", len(реестры) == 2, реестры)
чек("дедуп кандидатов по домену (homechauffage один раз)",
    sum(1 for u in канд if _домен(u) == "homechauffage.fr") == 1)
чек("обратная совместимость: кандидаты_из_выдачи == канд",
    кандидаты_из_выдачи(ссылки) == канд)

print("\n=== реестр как источник: сайт-поле + адрес ===")
текст_реестра = ("HEAT LOGISTICS SAS\n27 Rue Maurice Flandin - 69003 Lyon\n"
                 "Dirigeant Samir Benamara\nSite web : www.heat-logistics.fr\nSIREN 915296735")
чек("извлекает сайт из «Site web : …»",
    извлечь_сайт_из_текста(текст_реестра, свой="infonet.fr") == "http://www.heat-logistics.fr",
    извлечь_сайт_из_текста(текст_реестра, свой="infonet.fr"))
чек("«Site web NC» → пусто", извлечь_сайт_из_текста("Site web NC\nautre", свой="infonet.fr") == "")
чек("не берёт свой домен реестра как «сайт»",
    извлечь_сайт_из_текста("Site web : www.infonet.fr/pro", свой="infonet.fr") == "")
чек("не берёт мусор/реестр как «сайт»",
    извлечь_сайт_из_текста("Website: linkedin.com/company/x", свой="infonet.fr") == "")
г, и = адрес_из_реестра(текст_реестра)
чек("вытащил адрес реестра (69003 Lyon)", (г, и) == ("Lyon", "69003"), (г, и))
чек("нет адреса → пусто", адрес_из_реестра("нет тут индекса") == ("", ""))

print("\n=== подтверждение адресом (два адреса) ===")
стр = "HEAT LOGISTICS\n27 Rue Maurice Flandin\n69003 Lyon\nTel: ...\ncontact@heat-logistics.fr"
чек("совпал по индексу (69003)", адрес_совпал(стр, "Lyon", "69003") is True)
чек("совпал по городу (Lyon)", адрес_совпал(стр, "Lyon", "0000") is True)
чек("индекс с пробелом тоже ловится", адрес_совпал("... 1015 CJ Amsterdam ...", "Amsterdam", "1015CJ") is True)
чек("чужой адрес НЕ совпал", адрес_совпал(стр, "Rotterdam", "3000") is False)
чек("пустой адрес → не совпал", адрес_совпал("", "Lyon", "69003") is False)
# два адреса: DNB (устаревший, Paris) + реестр (текущий, Lyon) — совпадёт по реестру
адреса = [("Paris", "75001"), ("Lyon", "69003")]
чек("любой_адрес_совпал ловит по адресу реестра", любой_адрес_совпал(стр, адреса) is True)
чек("любой_адрес_совпал: оба чужие → False", любой_адрес_совпал(стр, [("Nice", "06000"), ("Brest", "29200")]) is False)

print("\n=== имя в домене (бонус-сигнал) ===")
чек("имя фирмы в домене → True", имя_в_домене("HEAT LOGISTICS", "https://www.heatlog.fr") is True)
чек("правовая форма не считается", имя_в_домене("MAISON SARL", "https://www.sarl-services.fr") is False)
чек("нет пересечения → False", имя_в_домене("HEAT LOGISTICS", "https://www.xyz-transport.fr") is False)

print("\n=== детектор каталога по СОДЕРЖИМОМУ (главная защита) ===")
# hoodspot / e-pro / petitesaffiches — каталоги из живого прогона
hoodspot = ("RUE DE L INDUSTRIE, SORBIERS 42290\n27 entreprises et 12 adresses\n"
            "RESTAURANT LE REGAL\nAfficher le numéro\nAjouter à une liste\n"
            "Trier par Pertinence\nVoir toutes les adresses\nCréer un compte")
epro = ("PIPELINE INDUCTION HEAT\nRoute Departementale 929\n60530 Neuilly En Thelle\n"
        "L'annuaire qui référence les TPE/PME\nAfficher le numéro\n"
        "À qui appartient ce numéro\nSignaler une anomalie\nBouche à oreille")
petites = ("HEAT LOGISTICS\n27 Rue Maurice Flandin, 69003 Lyon\nAfficher le téléphone\n"
           "Ajouter à une liste\nLaisser le 1er avis\nC'est votre entreprise ?")
чек("hoodspot — каталог (≥2 слабых)", похоже_на_каталог(hoodspot, "https://hoodspot.fr/adresse/rue-de-l-industrie-42290-sorbiers/") is True)
чек("e-pro — каталог (сильная фраза)", похоже_на_каталог(epro, "https://batiment.e-pro.fr/oise/pipeline-induction-heat_f5356656") is True)
чек("petitesaffiches — каталог (сильная фраза)", похоже_на_каталог(petites, "https://annuaire.petitesaffiches.fr/transport-de-fret/heat-logistics-91529673500011/") is True)
чек("SIREN(14) в URL → каталог", похоже_на_каталог("любой текст", "https://x.fr/heat-logistics-91529673500011/") is True)
чек("annuaire в URL → каталог", похоже_на_каталог("текст", "https://annuaire.x.fr/y") is True)
# настоящий сайт фирмы (ISOPLUS) — НЕ каталог
isoplus = ("ISOPLUS Group\nApplications Products Service & support References Newsroom\n"
           "Your local contacts\nISOPLUS France\nZAC du Chapotin 69970 Chaponnay")
чек("isoplus.group — НЕ каталог (настоящий сайт)", похоже_на_каталог(isoplus, "https://isoplus.group/isoplus-group/locations/filter/france/") is False)
чек("обычный сайт с контактами — НЕ каталог",
    похоже_на_каталог("HEAT LOGISTICS\nNos services\nContactez-nous\n69003 Lyon", "https://heatlog.fr/") is False)

print("\n=== запрос: имя + адрес + город + СТРАНА ===")
q = построить_запрос("HOME", "12 rue des Lilas", "LYON", "France")
чек("запрос содержит страну, город и адрес", "France" in q and "LYON" in q and "rue des Lilas" in q, q)
чек("пустые части не попадают", построить_запрос("HOME", "", "", "France") == "HOME France")

print(f"\n===== ИТОГ: {ок}/{пров} проверок пройдено =====")
sys.exit(0 if ок == пров else 1)
