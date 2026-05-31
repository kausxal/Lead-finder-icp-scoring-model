import json
import os
import re
import socket
import urllib.parse
import requests
import pandas as pd
from datetime import datetime, timedelta

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "sbti_data.csv")
CACHE_META = os.path.join(CACHE_DIR, "cache_meta.json")
SBTI_XLSX_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTn5UZIBmOxWKNFpmQGWWDczMvdBJ74l2_j0emUH9mxEKylHqh3oMLhu2FXtAV7-bqDxy9Yz_hkWzu8/pub?output=xlsx"
SBTI_FALLBACK_URLS = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTn5UZIBmOxWKNFpmQGWWDczMvdBJ74l2_j0emUH9mxEKylHqh3oMLhu2FXtAV7-bqDxy9Yz_hkWzu8/pub?output=csv",
    "https://sciencebasedtargets.org/resources/files/SBTi-Progress-Report-2023-Annex.xlsx",
]
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MY_LIST_FILE = os.path.join(DATA_DIR, "my_list.json")
DEFAULT_CACHE_AGE = 7


def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)


def get_cache_age_days():
    if not os.path.exists(CACHE_META):
        return None
    try:
        with open(CACHE_META, "r") as f:
            meta = json.load(f)
        cached_date = datetime.fromisoformat(meta.get("date", ""))
        return (datetime.now() - cached_date).days
    except:
        return None


def get_cache_date_str():
    if not os.path.exists(CACHE_META):
        return None
    try:
        with open(CACHE_META, "r") as f:
            meta = json.load(f)
        d = datetime.fromisoformat(meta.get("date", ""))
        return d.strftime("%b %d, %Y")
    except:
        return None


def set_cache_meta():
    with open(CACHE_META, "w") as f:
        json.dump({"date": datetime.now().isoformat()}, f)


def _find_column(df, candidates):
    col_lower = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower().strip() in col_lower:
            return col_lower[cand.lower().strip()]
    return None


def _parse_employees(val):
    if pd.isna(val):
        return 0
    s = str(val).replace(",", "").replace("+", "").strip()
    try:
        return int(float(s))
    except:
        return 0


def _parse_target_year(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    try:
        return int(float(s))
    except:
        return None


KNOWN_DOMAINS = {
    "nestlé": "nestle.com",
    "nestle": "nestle.com",
    "walmart": "walmart.com",
    "amazon": "amazon.com",
    "mcdonald's": "mcdonalds.com",
    "mcdonalds": "mcdonalds.com",
    "pepsico": "pepsico.com",
    "coca-cola": "coca-cola.com",
    "cocacola": "coca-cola.com",
    "unilever": "unilever.com",
    "toyota": "toyota.com",
    "mitsubishi": "mitsubishi.com",
    "kellogg's": "kelloggs.com",
    "kellogg": "kelloggs.com",
    "general mills": "generalmills.com",
    "mondelez": "mondelez.com",
    "kraft heinz": "kraftheinz.com",
    "danone": "danone.com",
    "tesla": "tesla.com",
    "nike": "nike.com",
    "adidas": "adidas.com",
    "ikea": "ikea.com",
    "carrefour": "carrefour.com",
    "tesco": "tesco.com",
    "aldi": "aldi.com",
    "lidl": "lidl.com",
    "costco": "costco.com",
    "target": "target.com",
    "home depot": "homedepot.com",
    "lowes": "lowes.com",
    "walgreens": "walgreens.com",
    "cvs": "cvs.com",
    "uber": "uber.com",
    "lyft": "lyft.com",
    "starbucks": "starbucks.com",
    "burger king": "bk.com",
    "kfc": "kfc.com",
    "domino's": "dominos.com",
    "dell": "dell.com",
    "hp": "hp.com",
    "ibm": "ibm.com",
    "microsoft": "microsoft.com",
    "google": "google.com",
    "apple": "apple.com",
    "meta": "meta.com",
    "pfizer": "pfizer.com",
    "johnson & johnson": "jnj.com",
    "johnson": "jnj.com",
    "abbott": "abbott.com",
    "samsung": "samsung.com",
    "sony": "sony.com",
    "panasonic": "panasonic.com",
    "lg": "lg.com",
    "bmw": "bmw.com",
    "mercedes": "mercedes-benz.com",
    "volkswagen": "volkswagen.com",
    "audi": "audi.com",
    "porsche": "porsche.com",
    "ferrari": "ferrari.com",
    "honda": "honda.com",
    "hyundai": "hyundai.com",
    "kfc": "kfc.com",
}


def _generate_website(company_name):
    import re
    name = str(company_name).strip()
    name_lower = name.lower().strip()

    for key, domain in KNOWN_DOMAINS.items():
        if key in name_lower:
            return f"https://www.{domain}"

    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'"[^"]*"', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    suffixes = [
        r'\s+(?:Inc|Ltd|LLC|GmbH|AG|BV|NV|SA|Sp\.\s*z\.?\s*o\.?\s*o\.?|Co\.|Corp|PLC|Pty|S\.A\.|S\.L\.|S\.p\.\s*A\.)'
        r'(?:\.|\s|$)', r'\s+(?:Group|Holdings|International|Corporation|Company|Limited|Enterprises|Industries|PLC)',
        r'\s+&\s+Co\.?$',
    ]
    for pat in suffixes:
        name = re.sub(pat, '', name, flags=re.IGNORECASE)
    name = name.strip().rstrip('.')
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', '', name)
    name = name.lower().strip()
    if not name or len(name) < 2:
        return None
    name = name[:50]
    return f"https://www.{name}.com"


def _map_industry(sector):
    if pd.isna(sector):
        return "Unknown"
    s = str(sector).lower().strip()
    mapping = {
        "food": "Food and Beverage",
        "beverage": "Food and Beverage",
        "food & beverage": "Food and Beverage",
        "agriculture": "Agriculture",
        "farming": "Agriculture",
        "retail": "Retail",
        "manufacturing": "Manufacturing",
        "logistics": "Logistics",
        "consumer": "Consumer Goods",
        "consumer goods": "Consumer Goods",
        "real estate": "Real Estate",
        "fashion": "Fashion",
        "apparel": "Fashion",
        "textile": "Fashion",
        "packaging": "Packaging",
        "healthcare": "Healthcare",
        "technology": "Technology",
        "energy": "Energy",
        "utilities": "Utilities",
        "chemical": "Chemicals",
        "materials": "Manufacturing",
        "financial": "Financial Services",
        "banking": "Financial Services",
        "insurance": "Financial Services",
        "professional": "Professional Services",
        "consulting": "Professional Services",
        "government": "Government",
        "oil": "Oil and Gas",
        "gas": "Oil and Gas",
        "services": "Professional Services",
        "transport": "Logistics",
        "pharma": "Healthcare",
        "biotech": "Healthcare",
    }
    for key, val in mapping.items():
        if key in s:
            return val
    return str(sector).title()


def _map_status(status_val):
    if pd.isna(status_val):
        return "Unknown"
    s = str(status_val).lower().strip()
    if "achieved" in s or "net zero" in s:
        return "Achieved Net Zero"
    if "targets set" in s or "target" in s:
        return "Targets Set"
    if "committed" in s:
        return "Committed"
    return str(status_val).strip()


def _try_download_xlsx(url, temp_path, callback, start_pct, end_pct):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=60, stream=True)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(temp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size:
                pct = start_pct + int((downloaded / total_size) * (end_pct - start_pct))
                callback(f"Downloading... {downloaded//1024}KB", pct)

    return temp_path


def _try_download_csv(url, temp_path, callback):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    with open(temp_path, "wb") as f:
        f.write(resp.content)
    return temp_path


def _find_combined_status(row, status_cols):
    statuses = []
    for col in status_cols:
        if col and pd.notna(row.get(col)):
            statuses.append(str(row[col]).strip())
    if not statuses:
        return "", ""
    best = statuses[0]
    if "targets set" in best.lower():
        return best, best
    if "committed" in best.lower():
        for s in statuses:
            if "targets set" in s.lower():
                return s, s
        return best, best
    return statuses[0], statuses[0]


def _parse_sbti_dataframe(df):
    company_col = _find_column(df, [
        "company name", "company", "organization", "organisation",
        "name", "entity", "company_name", "business_name"
    ])
    country_col = _find_column(df, [
        "location", "country", "country/region", "region",
        "country_code", "headquarters", "country_code_alpha_2"
    ])
    region_col = _find_column(df, [
        "region", "country/region"
    ])
    sector_col = _find_column(df, [
        "sector", "industry", "primary sector", "industry sector",
        "business sector", "type", "sector_industry"
    ])
    near_term_status_col = _find_column(df, [
        "near_term_status", "near term status"
    ])
    long_term_status_col = _find_column(df, [
        "long_term_status", "long term status"
    ])
    net_zero_status_col = _find_column(df, [
        "net_zero_status", "net zero status"
    ])
    status_col = _find_column(df, [
        "status", "target status", "sbti status", "commitment status",
        "validation status", "stage", "company_status", "targets_status"
    ])
    year_col = _find_column(df, [
        "near_term_target_year", "near term target year",
        "target year", "year", "commitment year", "validation year",
        "base year", "target_year", "first_target_year"
    ])
    target_col = _find_column(df, [
        "near_term_target_classification", "near term target classification",
        "target type", "type", "scope", "target", "commitment type",
        "absolute or intensity target", "target_classification"
    ])

    if not company_col:
        return None

    all_status_cols = [status_col, near_term_status_col, long_term_status_col, net_zero_status_col]
    all_status_cols = [c for c in all_status_cols if c]

    records = []
    for _, row in df.iterrows():
        company = str(row[company_col]).strip() if pd.notna(row[company_col]) else ""
        if not company or company.lower() in ("nan", "", "none"):
            continue

        sector_raw = str(row[sector_col]) if sector_col and pd.notna(row[sector_col]) else ""
        country = str(row[country_col]) if country_col and pd.notna(row[country_col]) else ""
        region = str(row[region_col]) if region_col and pd.notna(row[region_col]) else ""

        if all_status_cols:
            status_raw, sbti_status_raw = _find_combined_status(row, all_status_cols)
        else:
            status_raw = ""
            sbti_status_raw = ""

        target_year = _parse_target_year(row[year_col]) if year_col else None
        target_type = str(row[target_col]) if target_col and pd.notna(row[target_col]) else ""

        today = datetime.now().strftime("%Y-%m-%d")
        records.append({
            "company": company,
            "website": _generate_website(company),
            "country": country,
            "region": region,
            "industry": _map_industry(sector_raw),
            "sector_raw": sector_raw,
            "sbti_status": _map_status(sbti_status_raw),
            "status_raw": status_raw,
            "target_year": target_year,
            "target_type": target_type,
            "employees": 0,
            "last_sbti_fetch": today,
        })

    if not records:
        return None

    df_out = pd.DataFrame(records)
    df_out = df_out.drop_duplicates(subset=["company"], keep="first")
    return df_out


def download_sbti_data(progress_callback=None):
    ensure_dirs()
    temp_path = os.path.join(CACHE_DIR, "temp_sbti")

    def callback(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)

    callback("Connecting to SBTi database...", 3)

    urls_to_try = [SBTI_XLSX_URL] + SBTI_FALLBACK_URLS
    last_error = None

    for idx, url in enumerate(urls_to_try):
        try:
            callback(f"Connecting to data source {idx+1}/{len(urls_to_try)}...", 5)

            is_csv = url.endswith(".csv") or "output=csv" in url
            ext = ".csv" if is_csv else ".xlsx"
            dl_path = temp_path + ext

            if is_csv:
                _try_download_csv(url, dl_path, callback)
                callback("Processing CSV records...", 50)
                df = pd.read_csv(dl_path, encoding="utf-8-sig")
            else:
                _try_download_xlsx(url, dl_path, callback, 10, 45)
                callback("Processing Excel records...", 50)
                df = pd.read_excel(dl_path, engine="openpyxl")

            result = _parse_sbti_dataframe(df)
            if result is not None:
                callback("Building company profiles...", 75)
                result.to_csv(CACHE_FILE, index=False, encoding="utf-8")
                set_cache_meta()

                if os.path.exists(dl_path):
                    os.remove(dl_path)

                callback(f"Done. Loaded {len(result)} companies.", 100)
                return result

            last_error = "Could not find expected columns in data"

        except Exception as e:
            last_error = str(e)
            continue

    callback(f"Error: {last_error}", -1)
    raise Exception(f"Failed to download SBTi data: {last_error}")


def load_cached_data():
    ensure_dirs()
    if os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE, encoding="utf-8")
        import ast
        if "score_breakdown" in df.columns:
            def _parse(v):
                if pd.isna(v):
                    return {}
                try:
                    return ast.literal_eval(v) if isinstance(v, str) else v
                except:
                    return {}
            df["score_breakdown"] = df["score_breakdown"].apply(_parse)
        today = datetime.now().strftime("%Y-%m-%d")
        if "last_sbti_fetch" in df.columns and df["last_sbti_fetch"].isna().all():
            df["last_sbti_fetch"] = today
            out = df.copy()
            if "score_breakdown" in out.columns:
                out["score_breakdown"] = out["score_breakdown"].apply(
                    lambda v: json.dumps(v) if isinstance(v, dict) else v
                )
            out.to_csv(CACHE_FILE, index=False, encoding="utf-8")
        return df
    return None


def save_cached_data(df):
    ensure_dirs()
    out = df.copy()
    if "score_breakdown" in out.columns:
        out["score_breakdown"] = out["score_breakdown"].apply(
            lambda v: json.dumps(v) if isinstance(v, dict) else v
        )
    out.to_csv(CACHE_FILE, index=False, encoding="utf-8")


SBTI_COMPARE_COLUMNS = ["sbti_status", "target_year", "target_type", "sector_raw", "country", "region", "industry"]


def merge_sbti_update(current_df, fresh_df):
    if current_df is None or current_df.empty:
        fresh_df = fresh_df.copy()
        if "last_sbti_fetch" not in fresh_df.columns:
            fresh_df["last_sbti_fetch"] = datetime.now().strftime("%Y-%m-%d")
        return fresh_df, len(fresh_df), len(fresh_df)

    current = current_df.copy()
    fresh = fresh_df.copy()
    today = datetime.now().strftime("%Y-%m-%d")

    if "last_sbti_fetch" not in current.columns or current["last_sbti_fetch"].isna().all():
        current["last_sbti_fetch"] = today

    current["_key"] = current["company"].fillna("").str.lower().str.strip()
    fresh["_key"] = fresh["company"].fillna("").str.lower().str.strip()
    current = current.set_index("_key")
    fresh = fresh.set_index("_key")

    new_keys = set(fresh.index) - set(current.index)
    changed_keys = set()
    for key in set(fresh.index) & set(current.index):
        for col in SBTI_COMPARE_COLUMNS:
            if col in fresh.columns and col in current.columns:
                fv = str(fresh.loc[key, col]) if pd.notna(fresh.loc[key, col]) else ""
                cv = str(current.loc[key, col]) if pd.notna(current.loc[key, col]) else ""
                if fv != cv:
                    changed_keys.add(key)
                    break

    for key in changed_keys:
        for col in SBTI_COMPARE_COLUMNS:
            if col in fresh.columns:
                current.loc[key, col] = fresh.loc[key, col]
        current.loc[key, "last_sbti_fetch"] = today

    new_rows = fresh.loc[list(new_keys)].copy()
    new_rows["last_sbti_fetch"] = today
    for col in current.columns:
        if col not in new_rows.columns and col != "_key":
            new_rows[col] = None

    result = pd.concat([current, new_rows], ignore_index=False)
    result = result.reset_index(drop=True)
    result.drop(columns=["_key"], inplace=True, errors="ignore")

    updated_count = len(changed_keys)
    new_count = len(new_keys)
    return result, updated_count, new_count


def load_my_list():
    ensure_dirs()
    if os.path.exists(MY_LIST_FILE):
        try:
            with open(MY_LIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_to_my_list(company_data):
    ensure_dirs()
    my_list = load_my_list()
    existing_names = {item.get("company", "").lower() for item in my_list}
    name = company_data.get("company", "").lower()
    if name not in existing_names:
        clean = {k: (None if pd.isna(v) else v) for k, v in company_data.items()}
        clean = {k: (int(v) if isinstance(v, (int, float)) and not pd.isna(v) else v)
                 for k, v in clean.items()}
        my_list.append(clean)
        with open(MY_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(my_list, f, indent=2, default=str)
    return len(my_list)


def remove_from_my_list(company_name):
    my_list = load_my_list()
    my_list = [item for item in my_list if item.get("company", "") != company_name]
    with open(MY_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(my_list, f, indent=2, default=str)
    return len(my_list)


def needs_refresh():
    age = get_cache_age_days()
    if age is None:
        return True
    return age >= DEFAULT_CACHE_AGE


ENRICHMENT_COLUMNS = [
    "osi_found", "osi_company_url", "osi_revenue", "osi_revenue_currency",
    "osi_revenue_year", "osi_emissions_tco2e", "osi_emission_intensity",
    "osi_hq_country", "osi_industry", "osi_organization_type",
    "osi_status", "osi_commitment_deadline",
    "origin_found", "origin_ticker", "origin_cik", "origin_summary",
    "origin_headquarters", "origin_employees", "origin_sic",
    "origin_founded", "origin_exchange",
]


def merge_enrichment(df, enrichment_results):
    if df is None or df.empty:
        return df

    df = df.copy()
    for col in ENRICHMENT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    enrichment_results = enrichment_results or {}
    if not enrichment_results:
        return df

    enrich_df = pd.DataFrame.from_dict(enrichment_results, orient="index")
    enrich_df.index.name = "company"
    enrich_df = enrich_df.reset_index()
    enrich_df["_key"] = enrich_df["company"].fillna("").str.lower().str.strip()

    df["_key"] = df["company"].fillna("").str.lower().str.strip()

    merged = df[["_key"]].merge(
        enrich_df[["_key"] + ENRICHMENT_COLUMNS + ["origin_employees", "osi_company_url"]],
        on="_key", how="left", suffixes=("", "_enrich")
    )

    for col in ENRICHMENT_COLUMNS:
        src = merged[col + "_enrich"] if col + "_enrich" in merged.columns else merged.get(col)
        if src is None:
            continue
        mask = src.notna()
        if not mask.any():
            continue
        vals = src[mask]
        if vals.dtype == object and vals.iloc[:1].apply(lambda x: isinstance(x, list)).any():
            vals = vals.apply(lambda x: json.dumps(x) if isinstance(x, list) else x)
        df.loc[mask, col] = vals

    emp_mask = merged["origin_employees"].notna() & merged["origin_employees"].apply(lambda x: isinstance(x, (int, float)))
    if emp_mask.any():
        origin_emps = merged.loc[emp_mask, "origin_employees"].astype(int)
        current_emps = pd.to_numeric(df.loc[emp_mask, "employees"], errors="coerce").fillna(0).astype(int)
        update_mask = origin_emps > current_emps
        if update_mask.any():
            update_idx = df.index[emp_mask][update_mask.values]
            df.loc[update_idx, "employees"] = origin_emps[update_mask.values].values

    url_mask = merged["osi_company_url"].notna() & merged["osi_company_url"].astype(str).str.startswith("http")
    if url_mask.any():
        df.loc[url_mask, "website"] = merged.loc[url_mask, "osi_company_url"]

    df.drop(columns=["_key"], inplace=True, errors="ignore")
    return df


def validate_website(url: str, timeout: int = 5) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc and "/" in url:
        parsed = urllib.parse.urlparse("https://" + url)
    hostname = parsed.netloc or url.split("/")[0]
    try:
        socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except socket.gaierror:
        return False


def batch_validate_websites(company_website_pairs, checkpoint_path=None, max_workers=20):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache = {}
    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, ValueError):
            cache = {}

    remaining = []
    for co, site in company_website_pairs:
        if co not in cache:
            remaining.append((co, site))

    if not remaining:
        return cache

    def _check(item):
        co, site = item
        try:
            return co, validate_website(site)
        except Exception:
            return co, False

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, item): item for item in remaining}
        done = 0
        total = len(remaining)
        for f in as_completed(futures):
            co, valid = f.result()
            cache[co] = valid
            done += 1
            if checkpoint_path and done % 25 == 0:
                with open(checkpoint_path, "w", encoding="utf-8") as fout:
                    json.dump(cache, fout, indent=2)

    if checkpoint_path:
        with open(checkpoint_path, "w", encoding="utf-8") as fout:
            json.dump(cache, fout, indent=2)

    return cache
