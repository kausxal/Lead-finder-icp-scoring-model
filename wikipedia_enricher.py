import json
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
WIKI_CACHE = os.path.join(CACHE_DIR, "wikipedia_employees.json")
CHECKPOINT_FILE = os.path.join(CACHE_DIR, "wikipedia_checkpoint.csv")
MAX_WORKERS = 15
REQUEST_DELAY = 0.1


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache():
    _ensure_cache()
    if os.path.exists(WIKI_CACHE):
        try:
            with open(WIKI_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _save_cache(cache):
    with open(WIKI_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


HEADERS = {"User-Agent": "TerrascopeLeadFinder/1.0 (https://terrascope.com; contact@terrascope.com)"}


def _search_wikidata(company_name):
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": company_name,
        "language": "en",
        "limit": 5,
        "format": "json",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("search", [])
    except requests.RequestException:
        pass
    return []


def _get_employee_count(entity_id):
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        entity = data.get("entities", {}).get(entity_id, {})
        claims = entity.get("claims", {})
        p1128 = claims.get("P1128", [])
        if not p1128:
            return None
        for claim in p1128:
            mainsnak = claim.get("mainsnak", {})
            if mainsnak.get("datatype") == "quantity":
                datavalue = mainsnak.get("datavalue", {})
                value = datavalue.get("value", {})
                amount = value.get("amount")
                if amount:
                    try:
                        return int(float(amount))
                    except (ValueError, TypeError):
                        pass
            elif mainsnak.get("datatype") == "string":
                datavalue = mainsnak.get("datavalue", {})
                val = datavalue.get("value", "")
                if val and val.isdigit():
                    return int(val)
        return None
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        return None


def lookup_employee_count(company_name):
    cache = _load_cache()
    norm = company_name.lower().strip()
    if norm in cache:
        return cache[norm]

    entities = _search_wikidata(company_name)
    count = None
    for ent in entities:
        eid = ent.get("id", "")
        if eid:
            count = _get_employee_count(eid)
            if count is not None:
                break

    result = {"employees": count, "wikidata_id": entities[0].get("id", "") if entities else ""}
    cache[norm] = result
    _save_cache(cache)
    return result


def run_batch(companies, progress_callback=None):
    _ensure_cache()
    cache = _load_cache()

    import pandas as pd

    done_set = set()
    if os.path.exists(CHECKPOINT_FILE):
        try:
            ckpt = pd.read_csv(CHECKPOINT_FILE, dtype=str)
            ckpt = ckpt.drop_duplicates(subset="company", keep="first")
            done_set = set(ckpt["company"].dropna().str.lower().str.strip())
        except Exception:
            pass

    pending = [c for c in companies if c.lower().strip() not in done_set]
    total = len(pending)
    completed = len(done_set)
    resumed = completed > 0

    results = []
    start_time = time.time()

    def _lookup(name):
        norm = name.lower().strip()
        if norm in cache:
            return {"company": name, **cache[norm]}
        result = lookup_employee_count(name)
        time.sleep(REQUEST_DELAY)
        return {"company": name, **result}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_lookup, name): name for name in pending}
        for i, f in enumerate(as_completed(futures)):
            r = f.result()
            results.append(r)
            if (i + 1) % 50 == 0 or (i + 1) == total:
                df_ckpt = pd.DataFrame(results)
                if os.path.exists(CHECKPOINT_FILE):
                    try:
                        existing = pd.read_csv(CHECKPOINT_FILE, dtype=str)
                        df_ckpt = pd.concat([existing, df_ckpt], ignore_index=True)
                    except Exception:
                        pass
                df_ckpt.to_csv(CHECKPOINT_FILE, index=False, na_rep="")

            if progress_callback:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (total - i - 1) / rate if rate > 0 else 0
                progress_callback(completed + i + 1, completed + total, resumed, rate, remaining)

    final = pd.DataFrame(results)
    if os.path.exists(CHECKPOINT_FILE):
        try:
            existing = pd.read_csv(CHECKPOINT_FILE, dtype=str)
            final = pd.concat([existing, final], ignore_index=True)
        except Exception:
            pass
    final.to_csv(CHECKPOINT_FILE, index=False, na_rep="")

    return final


def get_progress():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            import pandas as pd
            df = pd.read_csv(CHECKPOINT_FILE, dtype=str)
            return {"completed": len(df), "file": CHECKPOINT_FILE}
        except Exception:
            pass
    return {"completed": 0, "file": CHECKPOINT_FILE}
