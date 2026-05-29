import os
import json
import time
import re
import threading
import requests
from urllib.parse import quote

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
OSI_CACHE_FILE = os.path.join(CACHE_DIR, "osi_cache.json")
ORIGIN_CACHE_FILE = os.path.join(CACHE_DIR, "origin_cache.json")
OSI_BASE = "https://api.opensustainabilityindex.org/v1"
ORIGIN_BASE = "https://origin.rootz.global/api"
REQUEST_DELAY = 0.25


def ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache(path):
    ensure_cache()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_cache(path, data):
    ensure_cache()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _normalize(name):
    name = name.lower().strip().strip('"').strip()
    name = re.sub(r'[`\'"ʻʽʼ]', '', name)
    return name


def _slugify(name):
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s-]', '', name)
    name = re.sub(r'\s+', '-', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name


def _match_name(cache_key, company_name):
    ck = _normalize(cache_key)
    cn = _normalize(company_name)
    if ck == cn:
        return True
    if len(ck) > 3 and (ck in cn or cn in ck):
        return True
    ck_short = re.sub(r'[\s,.\-]', '', ck)
    cn_short = re.sub(r'[\s,.\-]', '', cn)
    return ck_short == cn_short


def _try_osi_company_slug(company_name, cache, norm):
    slug = _slugify(company_name)
    if not slug:
        return None
    url = f"{OSI_BASE}/companies/{quote(slug)}?api-key=demo"
    try:
        resp = requests.get(url, headers={"User-Agent": "TerrascopeLeadFinder/1.0"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if data and isinstance(data, dict) and data.get("company_name"):
                result = _parse_osi_result(data)
                cache[norm] = result
                _save_cache(OSI_CACHE_FILE, cache)
                return result
    except:
        pass
    return None


def _try_osi_search(company_name, cache, norm):
    search_url = f"{OSI_BASE}/search?query={quote(company_name)}&api-key=demo"
    try:
        sresp = requests.get(search_url, headers={"User-Agent": "TerrascopeLeadFinder/1.0"}, timeout=10)
        if sresp.status_code == 200:
            results = sresp.json().get("data", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        result = _parse_osi_result(item)
                        cache[norm] = result
                        _save_cache(OSI_CACHE_FILE, cache)
                        return result
                if results and isinstance(results[0], dict):
                    result = _parse_osi_result(results[0])
                    cache[norm] = result
                    _save_cache(OSI_CACHE_FILE, cache)
                    return result
    except:
        pass
    return None


def enrich_osi(company_name, progress_callback=None):
    cache = _load_cache(OSI_CACHE_FILE)
    norm = _normalize(company_name)

    for cached_name, cached_data in cache.items():
        if _match_name(cached_name, company_name):
            cached_data["_cache_hit"] = True
            return cached_data

    result = _try_osi_company_slug(company_name, cache, norm)
    if result:
        return result

    time.sleep(REQUEST_DELAY)

    result = _try_osi_search(company_name, cache, norm)
    if result:
        return result

    cache[norm] = {"_not_found": True}
    _save_cache(OSI_CACHE_FILE, cache)
    return cache[norm]


def _parse_osi_result(data):
    targets = data.get("targets", []) or []
    near_term = [t for t in targets if t.get("target") == "Near-term"]
    target_years = [t.get("target_year") for t in near_term if t.get("target_year")]
    emissions = data.get("total_reported_emission_scope_1_2_3")
    revenue = data.get("revenue")
    intensity = data.get("emission_intensity")

    url = data.get("company_url")
    if url:
        url_str = str(url).strip()
        if url_str.startswith("http"):
            url = url_str
        elif "." in url_str and not url_str.replace(".", "").replace(" ", "").isdigit():
            url = f"https://www.{url_str}"
        else:
            url = None

    return {
        "osi_found": True,
        "osi_company_url": url,
        "osi_revenue": revenue,
        "osi_revenue_currency": data.get("currency"),
        "osi_revenue_year": data.get("year"),
        "osi_emissions_tco2e": emissions,
        "osi_emission_intensity": intensity,
        "osi_hq_country": data.get("hq_country"),
        "osi_industry": data.get("industry"),
        "osi_organization_type": data.get("organization_type"),
        "osi_status": data.get("status"),
        "osi_commitment_deadline": data.get("commitment_deadline"),
        "osi_target_years": target_years,
        "_cache_hit": False,
    }


def enrich_origin(company_name, progress_callback=None):
    cache = _load_cache(ORIGIN_CACHE_FILE)
    norm = _normalize(company_name)

    for cached_name, cached_data in cache.items():
        if _match_name(cached_name, company_name):
            if cached_data.get("_not_found") or cached_data.get("_error"):
                return cached_data
            cached_data["_cache_hit"] = True
            return cached_data

    search_url = f"{ORIGIN_BASE}/search?q={quote(company_name[:100])}"
    try:
        resp = requests.get(search_url, headers={"User-Agent": "TerrascopeLeadFinder/1.0"}, timeout=10)

        if resp.status_code == 200:
            results = resp.json().get("results", {}).get("companies", [])
            best = None
            scores = []
            cn = _normalize(company_name)
            cn_nospec = re.sub(r'[\s,.\-&\'()]', '', cn)
            for c in results:
                cname = c.get("name", "")
                score = 0
                mn = _normalize(cname)
                mn_nospec = re.sub(r'[\s,.\-&\'()]', '', mn)
                if cn == mn:
                    score = 3
                elif cn in mn or mn in cn:
                    score = 2
                elif cn_nospec and (cn_nospec in mn_nospec or mn_nospec in cn_nospec):
                    score = 2
                elif _match_name(cname, company_name):
                    score = 1
                if score > 0:
                    scores.append((score, c))
            if scores:
                scores.sort(key=lambda x: -x[0])
                best = scores[0][1]

            if best:
                ticker = best.get("ticker", "")
                result = {
                    "origin_found": True,
                    "origin_ticker": ticker,
                    "origin_cik": best.get("cik"),
                    "origin_summary": best.get("summary"),
                    "origin_name": best.get("name"),
                    "_cache_hit": False,
                }

                if ticker:
                    time.sleep(REQUEST_DELAY)
                    detail_url = f"{ORIGIN_BASE}/company/{quote(ticker)}"
                    dresp = requests.get(detail_url, headers={"User-Agent": "TerrascopeLeadFinder/1.0"}, timeout=10)

                    if dresp.status_code == 200:
                        detail = dresp.json()
                        identity = detail.get("identity", {})
                        metrics = detail.get("peak_metrics", {})
                        result["origin_headquarters"] = identity.get("headquarters")
                        result["origin_employees"] = metrics.get("employees")
                        result["origin_sic"] = identity.get("sic_description")
                        result["origin_founded"] = identity.get("founded")
                        result["origin_exchange"] = identity.get("exchange")
                        result["origin_employees_date"] = metrics.get("employees_date")

                cache[norm] = result
                _save_cache(ORIGIN_CACHE_FILE, cache)
                return result

        cache[norm] = {"_not_found": True}
        _save_cache(ORIGIN_CACHE_FILE, cache)
        return cache[norm]

    except Exception as e:
        result = {"_error": str(e)}
        cache[norm] = result
        _save_cache(ORIGIN_CACHE_FILE, cache)
        return result


def enrich_company(company_name, progress_callback=None):
    osi = enrich_osi(company_name, progress_callback)
    origin = enrich_origin(company_name, progress_callback)
    merged = {**osi, **origin}
    merged["_enriched"] = True
    return merged


def batch_enrich(companies, progress_callback=None):
    import concurrent.futures
    results = {}
    total = len(companies)
    if total == 0:
        return results
    completed = 0
    lock = threading.Lock() if total > 1 else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(enrich_company, c): c for c in companies}
        for future in concurrent.futures.as_completed(futures):
            c = futures[future]
            try:
                results[c] = future.result()
            except Exception as e:
                results[c] = {"_error": str(e)}
            if lock:
                with lock:
                    completed += 1
            else:
                completed += 1
            if progress_callback and total > 1:
                pct = int((completed / total) * 100)
                progress_callback(f"Enriching {completed}/{total}...", pct)
    if progress_callback:
        progress_callback(f"Done. Enriched {total} companies.", 100)
    return results


def clear_cache():
    for path in [OSI_CACHE_FILE, ORIGIN_CACHE_FILE]:
        if os.path.exists(path):
            os.remove(path)
