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

    if any(ind in combined for ind in ["agriculture", "farming"]):
        score += 5
        breakdown["Agriculture Focus"] = "5/5 - Agriculture/Farming"

    country = str(company.get("country", "") or "").lower()
    from regulatory_urgency import get_regulatory_urgency
    urg, label, desc = get_regulatory_urgency(country)
    urg_pts = urg * 4
    if urg_pts:
        desc_part = f"  ({desc})" if desc else ""
        breakdown["Regulatory Urgency"] = f"{urg_pts}/40 - {label}{desc_part}"
    else:
        breakdown["Regulatory Urgency"] = "0/40 - No mandate"
    score += urg_pts

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

    return min(score, 90), breakdown


def lead_status(score):
    if score >= 63:
        return "HOT"
    elif score >= 36:
        return "WARM"
    return "COLD"


def score_color(score):
    if score >= 63:
        return "#00d4aa"
    elif score >= 36:
        return "#ffa502"
    return "#ff4757"


def score_bg(score):
    if score >= 63:
        return "#0a2e22"
    elif score >= 36:
        return "#2a1f0a"
    return "#2a0a0f"
