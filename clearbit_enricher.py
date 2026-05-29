import json
import os
import time
import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CLEARBIT_CACHE = os.path.join(CACHE_DIR, "clearbit_cache.json")
CHECKPOINT_FILE = os.path.join(CACHE_DIR, "clearbit_checkpoint.csv")
RATE_LIMIT = 0.35
MAX_RETRIES = 3


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache():
    _ensure_cache_dir()
    if os.path.exists(CLEARBIT_CACHE):
        try:
            with open(CLEARBIT_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    with open(CLEARBIT_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def lookup_clearbit(company_name: str) -> dict:
    cache = _load_cache()
    norm = company_name.lower().strip()
    if norm in cache:
        return cache[norm]

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                "https://autocomplete.clearbit.com/v1/companies/suggest",
                params={"query": company_name},
                timeout=10,
            )
            if resp.status_code == 429:
                time.sleep(2)
                continue
            if resp.status_code in (503, 502):
                time.sleep(1)
                continue
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    best = data[0]
                    domain = best.get("domain", "")
                    name = best.get("name", "")
                    logo = best.get("logo", "")
                    result = {
                        "domain": domain,
                        "clearbit_name": name,
                        "logo": logo,
                        "confidence": "high" if domain else "not_found",
                    }
                else:
                    result = {"domain": "", "confidence": "not_found"}
                cache[norm] = result
                _save_cache(cache)
                return result
        except requests.RequestException:
            time.sleep(1)
            continue

    result = {"domain": "", "confidence": "not_found"}
    cache[norm] = result
    _save_cache(cache)
    return result


def run_batch(df: pd.DataFrame, progress_callback=None) -> pd.DataFrame:
    _ensure_cache_dir()
    cache = _load_cache()

    if "company" not in df.columns:
        raise ValueError("DataFrame must have a 'company' column")

    companies = df["company"].dropna().unique().tolist()
    companies = [c for c in companies if str(c).strip()]

    checkpoint_df = pd.DataFrame()
    if os.path.exists(CHECKPOINT_FILE):
        try:
            checkpoint_df = pd.read_csv(CHECKPOINT_FILE, dtype=str)
            done = set(checkpoint_df["company"].dropna().str.lower().str.strip())
            companies = [c for c in companies if c.lower().strip() not in done]
        except Exception:
            checkpoint_df = pd.DataFrame()

    total = len(companies)
    completed = len(checkpoint_df) if not checkpoint_df.empty else 0
    resumed = completed > 0

    if progress_callback:
        progress_callback(completed, completed + total, resumed, 0, 0)

    results = []
    start_time = time.time()

    for i, company in enumerate(companies):
        norm = company.lower().strip()
        if norm in cache:
            result = cache[norm]
        else:
            result = lookup_clearbit(company)
            time.sleep(RATE_LIMIT)

        results.append({"company": company, **result})

        if (i + 1) % 100 == 0 or (i + 1) == len(companies):
            batch_df = pd.DataFrame(results)
            if not checkpoint_df.empty:
                combined = pd.concat([checkpoint_df, batch_df], ignore_index=True)
            else:
                combined = batch_df
            combined.to_csv(CHECKPOINT_FILE, index=False)

        if progress_callback:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total - i - 1) / rate if rate > 0 else 0
            progress_callback(completed + i + 1, completed + total, resumed, rate, remaining)

    final = pd.DataFrame(results)
    if not checkpoint_df.empty:
        final = pd.concat([checkpoint_df, final], ignore_index=True)
    final.to_csv(CHECKPOINT_FILE, index=False)

    return final


def get_progress() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            df = pd.read_csv(CHECKPOINT_FILE, dtype=str)
            return {"completed": len(df), "file": CHECKPOINT_FILE}
        except Exception:
            pass
    return {"completed": 0, "file": CHECKPOINT_FILE}
