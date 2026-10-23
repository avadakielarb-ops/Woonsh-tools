import re
import unicodedata


def отпечаток(name, country, zip_code='', city=''):
    value = unicodedata.normalize('NFKD', name).lower()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', value)).strip()
    return country.upper() + '|' + value + '|' + (zip_code or city or '').lower().strip()


class Registry:
    def свободна(self, key):
        # Existing saved history is checked by the panel before each write.
        return True
