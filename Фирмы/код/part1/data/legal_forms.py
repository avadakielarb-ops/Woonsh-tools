"""
ПРАВОВЫЕ ФОРМЫ по странам.

Зачем: если в названии нет правовой формы — это, скорее всего, ИП/физлицо.
У такой фирмы НЕТ записи в реестре, и Часть 2 никогда не скачает на неё выписку.
Значит — жёсткий отсев ещё на входе.

Список заведомо неполный. Именно поэтому есть лист «Лог»: раз в неделю смотришь,
что отсеялось по причине «нет правовой формы», и дописываешь пропущенные формы сюда.
"""

FORMS = {
    "UK": ["ltd", "limited", "plc", "llp", "lp"],
    "US": ["llc", "inc", "corp", "corporation", "co", "ltd", "lp", "llp"],
    "DE": ["gmbh", "ag", "kg", "ohg", "ug", "gmbh & co. kg", "e.k."],
    "AT": ["gmbh", "ag", "kg", "og", "e.u."],
    "CH": ["ag", "gmbh", "sa", "sarl", "sagl"],
    "FR": ["sarl", "sas", "sasu", "sa", "eurl", "sci", "snc"],
    "NL": ["bv", "b.v.", "nv", "n.v.", "vof"],
    "BE": ["bv", "bvba", "nv", "sa", "sprl", "srl"],
    "PL": ["sp. z o.o.", "sp.z o.o.", "spolka z o.o.", "s.a.", "sp. j.", "sp. k."],
    "CZ": ["s.r.o.", "sro", "a.s.", "as", "v.o.s.", "k.s."],
    "SK": ["s.r.o.", "a.s."],
    "HU": ["kft", "kft.", "zrt", "zrt.", "bt", "bt.", "nyrt"],
    "HR": ["d.o.o.", "doo", "d.d.", "j.d.o.o."],
    "SI": ["d.o.o.", "d.d.", "s.p."],
    "BG": ["ood", "ood.", "eood", "ad", "оод", "еоод", "ад"],
    "SE": ["ab", "hb", "kb"],
    "NO": ["as", "asa", "ans", "da"],
    "DK": ["aps", "a/s", "ivs", "k/s"],
    "FI": ["oy", "oyj", "ky"],
    "EE": ["ou", "oü", "as"],
    "LV": ["sia", "as"],
    "LT": ["uab", "ab"],
    "IT": ["srl", "s.r.l.", "spa", "s.p.a.", "snc", "sas"],
    "ES": ["sl", "s.l.", "sa", "s.a."],
    "PT": ["lda", "sa"],
    "IE": ["ltd", "limited", "plc", "dac"],
    "AU": ["pty ltd", "pty. ltd.", "ltd", "limited"],
}
