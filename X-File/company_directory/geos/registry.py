""""""
from __future__ import annotations
from company_directory.geos.australia import Australia
from company_directory.geos.austria import Austria
from company_directory.geos.belgium import Belgium
from company_directory.geos.bulgaria import Bulgaria
from company_directory.geos.croatia import Croatia
from company_directory.geos.czechia import Czechia
from company_directory.geos.denmark import Denmark
from company_directory.geos.estonia import Estonia
from company_directory.geos.finland import Finland
from company_directory.geos.france import France
from company_directory.geos.hungary import Hungary
from company_directory.geos.latvia import Latvia
from company_directory.geos.netherlands import Netherlands
from company_directory.geos.norway import Norway
from company_directory.geos.poland import Poland
from company_directory.geos.slovenia import Slovenia
from company_directory.geos.switzerland import Switzerland
from company_directory.geos.united_kingdom import UnitedKingdom
from company_directory.geos.usa_florida import USAFlorida
DRIVERS = {d.code: d for d in [Czechia, Switzerland, Norway, Hungary, Slovenia, Austria, Poland, Denmark, UnitedKingdom, Estonia, France, Netherlands, Belgium, Croatia, Latvia, Australia, USAFlorida, Finland, Bulgaria]}
PLAN = {'CZ': ('Чехия', 1, 'download', '✔'), 'NO': ('Норвегия', 1, 'download', '✔'), 'SI': ('Словения', 1, 'download', '✔'), 'AT': ('Австрия', 1, 'download', '✔'), 'PL': ('Польша', 1, 'download', '✔'), 'DK': ('Дания', 1, 'download', '✔'), 'EE': ('Эстония', 1, 'download', '✔'), 'FR': ('Франция', 1, 'download', '✔'), 'UK': ('Британия', 1, 'download', '✔'), 'LV': ('Латвия', 1, 'download', '✔?'), 'US': ('США (Флорида)', 1, 'print', '✔?'), 'CH': ('Швейцария', 2, 'print', '✔'), 'HU': ('Венгрия', 2, 'print', '✔'), 'BE': ('Бельгия', 2, 'print', '✔?'), 'HR': ('Хорватия', 2, 'print', '✔?'), 'BG': ('Болгария', 3, 'print', '✔?'), 'FI': ('Финляндия', 3, 'download', '✔?'), 'AU': ('Австралия', 3, 'download', '✔?'), 'SE': ('Швеция', 4, 'template', '○'), 'NL': ('Нидерланды', 4, 'template', '✔'), 'DE': ('Германия', 0, '—', '✘')}
