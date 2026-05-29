import re
import pandas as pd
from scoring import calculate_icp_score, lead_status, EU_COUNTRIES


EU_PATTERN = re.compile("|".join(re.escape(eu) for eu in EU_COUNTRIES), re.IGNORECASE)
SBTI_ALL_PATTERN = re.compile("committed|targets set|achieved|net zero", re.IGNORECASE)
SBTI_TARGETS_PATTERN = re.compile("targets set|achieved", re.IGNORECASE)

REGION_SBTI_MAP = {
    "Europe": "europe",
    "North America": "northern america",
    "Asia Pacific": "asia|oceania",
    "Latin America": "latin america",
    "Middle East and Africa": "africa|mena",
}


def compute_scores(df):
    if df is None or df.empty:
        return df
    if ("icp_score" in df.columns and "score_breakdown" in df.columns
            and "lead_status" in df.columns):
        sb = df["score_breakdown"].dropna()
        if not sb.empty and isinstance(sb.iloc[0], dict):
            return df
    d = df.copy()
    scores = []
    breakdowns = []
    cols = d.columns.tolist()
    for row in d.itertuples(index=False):
        rec = dict(zip(cols, row))
        sc, br = calculate_icp_score(rec)
        scores.append(sc)
        breakdowns.append(br)
    d["icp_score"] = scores
    d["score_breakdown"] = breakdowns
    d["lead_status"] = [lead_status(s) for s in scores]
    return d


def _build_empty_result():
    return pd.DataFrame()


def apply_filters(df, filters):
    if df is None or df.empty:
        return df

    if "icp_score" not in df.columns:
        df = compute_scores(df)

    result = df.copy()

    industries = filters.get("industries", [])
    if industries:
        pat = "|".join(re.escape(ind.lower()) for ind in industries)
        mask = result["industry"].fillna("").str.lower().str.contains(pat, na=False)
        result = result[mask]
        if result.empty:
            return _build_empty_result()

    excluded = filters.get("excluded_industries", [])
    if excluded:
        combined = result["industry"].fillna("") + " " + result["sector_raw"].fillna("")
        combined_lower = combined.str.lower()
        pat = "|".join(re.escape(exc.lower()) for exc in excluded)
        result = result[~combined_lower.str.contains(pat, na=False)]
        if result.empty:
            return _build_empty_result()

    emp_min = filters.get("employees_min", None)
    emp_max = filters.get("employees_max", None)
    if emp_min is not None or emp_max is not None:
        emp = pd.to_numeric(result["employees"], errors="coerce").fillna(0)
        mask = pd.Series(True, index=result.index)
        if emp_min is not None:
            mask &= emp >= emp_min
        if emp_max is not None:
            mask &= emp <= emp_max
        result = result[mask]
        if result.empty:
            return _build_empty_result()

    regions = filters.get("regions", [])
    if regions and "region" in result.columns:
        pat = "|".join(REGION_SBTI_MAP[reg] for reg in regions if reg in REGION_SBTI_MAP)
        result = result[result["region"].fillna("").str.lower().str.contains(pat, na=False)]
        if result.empty:
            return _build_empty_result()

    regulatory = filters.get("regulatory", [])
    if "CSRD" in regulatory:
        result = result[result["country"].fillna("").str.contains(EU_PATTERN, na=False)]
        if result.empty:
            return _build_empty_result()

    if "SBTi Committed" in regulatory:
        result = result[result["sbti_status"].fillna("").str.contains(SBTI_ALL_PATTERN, na=False)]
        if result.empty:
            return _build_empty_result()

    if "SBTi Targets Set" in regulatory:
        result = result[result["sbti_status"].fillna("").str.contains(SBTI_TARGETS_PATTERN, na=False)]
        if result.empty:
            return _build_empty_result()

    if "SEC Registrant" in regulatory and "origin_ticker" in result.columns:
        result = result[result["origin_ticker"].fillna("").astype(str).str.strip() != ""]
        if result.empty:
            return _build_empty_result()

    if "UK Company" in regulatory:
        result = result[result["country"].fillna("").str.lower() == "united kingdom"]
        if result.empty:
            return _build_empty_result()

    if "EU Company" in regulatory:
        result = result[result["country"].fillna("").str.contains(EU_PATTERN, na=False)]
        if result.empty:
            return _build_empty_result()

    countries = filters.get("countries", [])
    if countries:
        result = result[
            result["country"].fillna("").str.lower().isin([c.lower() for c in countries])
        ]
        if result.empty:
            return _build_empty_result()

    target_year_min = filters.get("target_year_min")
    target_year_max = filters.get("target_year_max")
    if target_year_min is not None or target_year_max is not None:
        ty = pd.to_numeric(result["target_year"], errors="coerce")
        mask = pd.Series(True, index=result.index)
        if target_year_min is not None:
            mask &= ty >= target_year_min
        if target_year_max is not None:
            mask &= ty <= target_year_max
        result = result[mask]
        if result.empty:
            return _build_empty_result()

    icp_score_min = filters.get("icp_score_min")
    icp_score_max = filters.get("icp_score_max")

    if icp_score_min is not None:
        result = result[result["icp_score"] >= icp_score_min]
    if icp_score_max is not None:
        result = result[result["icp_score"] <= icp_score_max]

    lead_statuses = filters.get("lead_statuses", [])
    if lead_statuses:
        result = result[result["lead_status"].isin(lead_statuses)]
        if result.empty:
            return _build_empty_result()

    fetch_from = filters.get("fetch_from", "")
    fetch_to = filters.get("fetch_to", "")
    if fetch_from or fetch_to:
        if "last_sbti_fetch" in result.columns:
            mask = pd.Series(True, index=result.index)
            if fetch_from:
                mask &= result["last_sbti_fetch"].fillna("") >= fetch_from
            if fetch_to:
                mask &= result["last_sbti_fetch"].fillna("") <= fetch_to
            result = result[mask]
            if result.empty:
                return _build_empty_result()

    if result.empty:
        return _build_empty_result()

    result = result.sort_values("icp_score", ascending=False).reset_index(drop=True)
    return result
