import os
import time
import pandas as pd
import requests

EU_TAXONOMY_URL = "https://huggingface.co/datasets/jonathanschmoll/eu-taxonomy-dataset/resolve/main/metadata.csv?download=true"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
EU_TAXONOMY_CACHE = os.path.join(CACHE_DIR, "eu_taxonomy_cache.csv")
CACHE_MAX_AGE_DAYS = 7

COUNTRY_MAP = {
    "Germany": "Germany", "France": "France", "Spain": "Spain",
    "Austria": "Austria", "Ireland": "Ireland", "Netherlands": "Netherlands",
    "Belgium": "Belgium",
}


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def download_eu_taxonomy(force: bool = False) -> pd.DataFrame:
    _ensure_cache_dir()
    if not force and os.path.exists(EU_TAXONOMY_CACHE):
        age = time.time() - os.path.getmtime(EU_TAXONOMY_CACHE)
        if age < CACHE_MAX_AGE_DAYS * 86400:
            df = pd.read_csv(EU_TAXONOMY_CACHE, dtype=str)
            if not df.empty:
                return df
    try:
        resp = requests.get(EU_TAXONOMY_URL, timeout=60)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text), dtype=str)
    except Exception as e:
        if os.path.exists(EU_TAXONOMY_CACHE):
            return pd.read_csv(EU_TAXONOMY_CACHE, dtype=str)
        raise Exception(f"Failed to download EU Taxonomy data: {e}")

    if df.empty:
        return pd.DataFrame()

    records = []
    for _, row in df.iterrows():
        company = str(row.get("company_name", "") or "").strip()
        if not company:
            continue
        country = str(row.get("country", "") or "")
        country = COUNTRY_MAP.get(country, country)
        industry_raw = str(row.get("industry", "") or "")
        sector = str(row.get("sector", "") or "")
        industry = industry_raw if industry_raw else sector
        employees_str = str(row.get("number_of_employees", "") or "0")
        try:
            employees = int(float(employees_str)) if employees_str else 0
        except (ValueError, TypeError):
            employees = 0
        revenue_str = str(row.get("revenue", "") or "0")
        turnover_eligible = str(row.get("turnover_total", "") or "")
        turnover_aligned = str(row.get("turnover_aligned_pct", "") or "")
        capex_aligned = str(row.get("capex_aligned_pct", "") or "")
        taxonomy_activities = str(row.get("num_taxonomy_activities", "0") or "0")
        records.append({
            "company": company,
            "website": _generate_website_domain(company),
            "country": country,
            "industry": industry,
            "sector_raw": sector,
            "employees": employees,
            "revenue": revenue_str,
            "eu_turnover_eligible": turnover_eligible,
            "eu_turnover_aligned_pct": turnover_aligned,
            "eu_capex_aligned_pct": capex_aligned,
            "eu_taxonomy_activities": taxonomy_activities,
            "sbti_status": "",
            "region": _map_country_to_region(country),
            "target_year": "",
            "source_flags": "EU-Tax",
        })

    result = pd.DataFrame(records)
    result.to_csv(EU_TAXONOMY_CACHE, index=False)
    return result


def _generate_website_domain(company: str) -> str:
    name = company.lower().strip()
    for suffix in [" se", " ag", " s.a.", " s.a", " sa", " n.v.", " plc",
                   " gmbh", " & co. kgaa", " kgaa", " group", " holding",
                   " gmbh & co. kgaa", " s.e.", " sa.", " s.a.s.", " sas"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.strip().replace(" ", "").replace("-", "").replace("_", "")
    import re as _re
    name = _re.sub(r"[^a-z0-9]", "", name)
    return f"https://www.{name}.com" if name else ""


def _map_country_to_region(country: str) -> str:
    eu_countries = {
        "Germany", "France", "Spain", "Austria", "Ireland", "Netherlands",
        "Belgium", "Italy", "Portugal", "Greece", "Luxembourg", "Finland",
        "Sweden", "Denmark", "Norway", "Poland", "Czechia", "Czech Republic",
        "Hungary", "Romania", "Slovakia", "Slovenia", "Croatia", "Estonia",
        "Latvia", "Lithuania", "Malta", "Cyprus", "Bulgaria",
    }
    if country in eu_countries:
        return "Europe"
    return ""


def merge_eu_taxonomy(sbti_df: pd.DataFrame, eu_df: pd.DataFrame) -> pd.DataFrame:
    if sbti_df is None or sbti_df.empty:
        return eu_df.copy() if eu_df is not None else pd.DataFrame()
    if eu_df is None or eu_df.empty:
        return sbti_df.copy()

    existing_companies = set(sbti_df["company"].dropna().str.lower().str.strip())
    new_rows = eu_df[~eu_df["company"].str.lower().str.strip().isin(existing_companies)]
    enrichment_rows = eu_df[eu_df["company"].str.lower().str.strip().isin(existing_companies)]

    sbti_df = sbti_df.copy()
    for _, row in enrichment_rows.iterrows():
        name = str(row.get("company", "")).strip()
        mask = sbti_df["company"].str.lower().str.strip() == name.lower()
        for col in ["employees", "revenue", "eu_turnover_eligible",
                     "eu_turnover_aligned_pct", "eu_capex_aligned_pct",
                     "eu_taxonomy_activities"]:
            val = row.get(col)
            if val and (sbti_df.loc[mask, col].iloc[0] == "" or
                        sbti_df.loc[mask, col].iloc[0] == "0" or
                        pd.isna(sbti_df.loc[mask, col].iloc[0])):
                sbti_df.loc[mask, col] = val
        existing_sources = str(sbti_df.loc[mask, "source_flags"].iloc[0]) if "source_flags" in sbti_df.columns and sbti_df.loc[mask, "source_flags"].iloc[0] else ""
        if "EU-Tax" not in existing_sources:
            sbti_df.loc[mask, "source_flags"] = (existing_sources + "+EU-Tax" if existing_sources else "EU-Tax")

    result = pd.concat([sbti_df, new_rows], ignore_index=True)
    return result
