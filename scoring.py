HIGH_FIT_INDUSTRIES = [
    "food", "agriculture", "farming", "retail",
    "manufacturing", "logistics", "consumer goods",
    "fashion", "packaging", "food & beverage",
]
MEDIUM_FIT_INDUSTRIES = [
    "real estate", "healthcare", "technology",
    "energy", "utilities", "chemicals",
]
EXCLUDED_INDUSTRIES = [
    "financial services", "government", "professional services",
    "oil", "gas", "banking", "insurance", "consulting",
]

EU_COUNTRIES = [
    "germany", "france", "netherlands", "sweden", "denmark",
    "belgium", "spain", "italy", "finland", "norway",
    "austria", "poland", "ireland", "portugal", "czech republic",
    "czechia", "romania", "hungary", "greece", "switzerland",
    "luxembourg", "bulgaria", "croatia", "slovenia", "slovakia",
    "lithuania", "latvia", "estonia", "cyprus", "malta",
    "united kingdom",
]


def calculate_icp_score(company):
    score = 0
    breakdown = {}

    employees = company.get("employees", 0) or 0
    if isinstance(employees, str):
        try:
            employees = int(float(employees.replace(",", "")))
        except:
            employees = 0

    origin_emp = company.get("origin_employees")
    if origin_emp and isinstance(origin_emp, (int, float)) and origin_emp > employees:
        employees = int(origin_emp)

    # Company Size: 15 if >=200, 0 otherwise
    if employees >= 200:
        score += 15
        breakdown["Company Size"] = "15/15 - Established company"
    else:
        breakdown["Company Size"] = "0/15 - Small company"

    # Industry Fit: High=20, Medium=12, Low=5
    industry_lower = str(company.get("industry", "") or "").lower()
    sector_raw = str(company.get("sector_raw", "") or "").lower()
    combined = industry_lower + " " + sector_raw

    industry_score = 0
    if any(ind in combined for ind in HIGH_FIT_INDUSTRIES):
        industry_score = 20
        breakdown["Industry Fit"] = "20/20 - High fit"
    elif any(ind in combined for ind in MEDIUM_FIT_INDUSTRIES):
        industry_score = 12
        breakdown["Industry Fit"] = "12/20 - Medium fit"
    else:
        industry_score = 5
        breakdown["Industry Fit"] = "5/20 - Low fit"
    score += industry_score

    # Agriculture Bonus: +5 if company is agriculture/farming
    if any(ind in combined for ind in ["agriculture", "farming"]):
        score += 5
        breakdown["Agriculture Focus"] = "5/5 - Agriculture/Farming"

    # Regulatory Pressure: CSRD only (15), no SBTi overlap
    country = str(company.get("country", "") or "").lower()
    if any(eu in country for eu in EU_COUNTRIES):
        score += 15
        breakdown["Regulatory Pressure"] = "15/15 - CSRD applicable"
    else:
        breakdown["Regulatory Pressure"] = "0/15 - No CSRD mandate"

    # SBTi Commitment: Consolidated here (max 25)
    sbti_status = str(company.get("sbti_status", "") or "").lower()
    sbti_score = 0
    if "achieved" in sbti_status:
        sbti_score = 25
        breakdown["SBTi Commitment"] = "25/25 - Net zero achieved"
    elif "targets set" in sbti_status:
        sbti_score = 20
        breakdown["SBTi Commitment"] = "20/25 - Targets set"
    elif "committed" in sbti_status:
        sbti_score = 15
        breakdown["SBTi Commitment"] = "15/25 - Committed"
    else:
        breakdown["SBTi Commitment"] = "0/25 - No commitment"
    score += sbti_score

    # ICP Exclusion: Gate only, no points. Entire score zeroed if excluded.
    if any(exc in combined for exc in EXCLUDED_INDUSTRIES):
        score = 0
        breakdown["Excluded Industry"] = "0/0 - EXCLUDED"

    return min(score, 80), breakdown


def lead_status(score):
    if score >= 55:
        return "HOT"
    elif score >= 30:
        return "WARM"
    return "COLD"


def score_color(score):
    if score >= 70:
        return "#00d4aa"
    elif score >= 40:
        return "#ffa502"
    return "#ff4757"


def score_bg(score):
    if score >= 70:
        return "#0a2e22"
    elif score >= 40:
        return "#2a1f0a"
    return "#2a0a0f"
