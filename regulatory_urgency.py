from datetime import date
from scoring import EU_COUNTRIES

REGULATIONS = {
    "SB253": {
        "countries": ["united states"],
        "deadline": date(2026, 8, 10),
        "label": "California SB253",
    },
    "AASB_S2": {
        "countries": ["australia"],
        "deadline": date(2026, 7, 1),
        "label": "Australia AASB S2",
    },
    "SSBJ": {
        "countries": ["japan"],
        "deadline": date(2027, 3, 31),
        "label": "Japan SSBJ",
    },
    "SGX_TCFD": {
        "countries": ["singapore"],
        "deadline": date(2027, 1, 1),
        "label": "Singapore SGX TCFD",
    },
    "ESG_Disclosure": {
        "countries": ["south korea"],
        "deadline": date(2028, 1, 1),
        "label": "South Korea ESG Disclosure",
    },
}

CSRD_LABEL = "CSRD + CBAM"


def _days_until(dl):
    return (dl - date.today()).days


def _urgency_from_days(days):
    if days < 90:
        return 10
    if days < 180:
        return 8
    if days < 365:
        return 6
    if days < 730:
        return 4
    return 2


def get_regulatory_urgency(country):
    if not country:
        return (0, None, None)

    c = country.lower().strip()
    urgencies = []

    for reg_id, reg in REGULATIONS.items():
        if any(c == co or co in c or c in co for co in reg["countries"]):
            days = _days_until(reg["deadline"])
            urg = _urgency_from_days(days)
            urgencies.append((urg, reg_id, days))

    if c in EU_COUNTRIES:
        urgencies.append((10, "CSRD_CBAM", 0))

    if not urgencies:
        return (0, None, None)

    best = max(urgencies, key=lambda x: x[0])
    urg, reg_id, days = best

    if reg_id == "CSRD_CBAM":
        label = CSRD_LABEL
        desc = "active"
    else:
        reg = REGULATIONS[reg_id]
        label = reg["label"]
        desc = f"{days}d remaining"

    return (urg, label, desc)
