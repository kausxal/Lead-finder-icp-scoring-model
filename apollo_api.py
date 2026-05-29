import json
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CONTACTS_CACHE = os.path.join(CACHE_DIR, "apollo_contacts.json")
ORG_CACHE = os.path.join(CACHE_DIR, "apollo_org_cache.json")
MAX_WORKERS = 5
REQUEST_DELAY = 0.5

SUSTAINABILITY_TITLES = [
    "Chief Sustainability Officer",
    "Sustainability Manager",
    "Head of Sustainability",
    "ESG Manager",
    "Carbon Manager",
    "Director of Sustainability",
    "VP Sustainability",
    "CSO",
    "Sustainability Director",
    "ESG Director",
    "Environmental Manager",
    "Climate Manager",
    "Net Zero Manager",
    "Sustainability Coordinator",
    "ESG Analyst",
    "Corporate Sustainability Lead",
]


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache():
    _ensure_cache()
    if os.path.exists(CONTACTS_CACHE):
        try:
            with open(CONTACTS_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _save_cache(cache):
    with open(CONTACTS_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def search_company_contacts(company_name: str, api_key: str) -> list:
    cache = _load_cache()
    norm = company_name.lower().strip()
    if norm in cache and cache[norm].get("contacts") is not None:
        return cache[norm]["contacts"]

    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
    }
    all_people = []
    page = 1
    max_pages = 3

    while page <= max_pages:
        payload = {
            "api_key": api_key,
            "q_organization_names": [company_name],
            "person_titles": SUSTAINABILITY_TITLES,
            "page": page,
            "per_page": 25,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 401:
                return {"error": "Invalid API key"}
            if resp.status_code == 429:
                time.sleep(2)
                continue
            if resp.status_code != 200:
                break
            data = resp.json()
            people = data.get("people", [])
            if not people:
                break
            for p in people:
                last = p.get("last_name") or p.get("last_name_obfuscated", "")
                all_people.append({
                    "id": p.get("id", ""),
                    "name": f"{p.get('first_name', '')} {last}".strip(),
                    "first_name": p.get("first_name", ""),
                    "last_name": last,
                    "title": p.get("title", ""),
                    "email": p.get("email", ""),
                    "has_email": p.get("has_email", False),
                    "phone": p.get("phone", ""),
                    "linkedin_url": p.get("linkedin_url", ""),
                    "photo_url": p.get("photo_url", ""),
                    "city": (p.get("city") or "") or "",
                    "state": (p.get("state") or "") or "",
                    "country": (p.get("country") or "") or "",
                })
            total_pages = data.get("paginator", {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
        except requests.RequestException:
            break

    result = {"contacts": all_people, "count": len(all_people)}
    cache[norm] = result
    _save_cache(cache)
    return all_people


ORG_FIELDS = [
    "employee_count", "estimated_num_employees", "estimated_revenue",
    "revenue_range", "revenue", "founded_year", "industry",
    "logo_url", "primary_phone", "city", "state", "country",
    "short_description", "annual_contract_value", "project_type",
]


def _load_org_cache():
    _ensure_cache()
    if os.path.exists(ORG_CACHE):
        try:
            with open(ORG_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _save_org_cache(cache):
    with open(ORG_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def search_company_org(company_name: str, api_key: str) -> dict:
    cache = _load_org_cache()
    norm = company_name.lower().strip()
    if norm in cache:
        return cache[norm]

    url = "https://api.apollo.io/api/v1/organizations/search"
    headers = {"Content-Type": "application/json"}

    result = {"employee_count": None, "revenue": None, "revenue_range": None, "founded_year": None, "industry": None}
    try:
        resp = requests.post(url, json={"api_key": api_key, "q_organization_name": company_name, "page": 1, "per_page": 1}, headers=headers, timeout=15)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 429:
            time.sleep(2)
        if resp.status_code == 200:
            data = resp.json()
            orgs = data.get("organizations", [])
            if orgs:
                org = orgs[0]
                emp = org.get("employee_count") or org.get("estimated_num_employees")
                if emp is not None:
                    try:
                        result["employee_count"] = int(float(emp))
                    except (ValueError, TypeError):
                        pass
                rev = org.get("estimated_revenue") or org.get("revenue")
                if rev is not None:
                    try:
                        result["revenue"] = int(float(rev))
                    except (ValueError, TypeError):
                        pass
                result["revenue_range"] = org.get("revenue_range", "")
                result["founded_year"] = org.get("founded_year", "")
                result["industry"] = org.get("industry", "")
    except requests.RequestException:
        pass

    cache[norm] = result
    _save_org_cache(cache)
    time.sleep(REQUEST_DELAY)
    return result


def batch_search_contacts(companies: list, api_key: str, progress_callback=None):
    _ensure_cache()
    cache = _load_cache()

    pending = [c for c in companies if c.lower().strip() not in cache or cache[c.lower().strip()].get("contacts") is None]
    total = len(pending)
    done_count = len(companies) - total
    start_time = time.time()

    results = {}

    def _search(name):
        try:
            contacts = search_company_contacts(name, api_key)
            return name, contacts
        except Exception:
            return name, []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_search, name): name for name in pending}
        for i, f in enumerate(as_completed(futures)):
            name, contacts = f.result()
            results[name] = contacts
            if progress_callback:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (total - i - 1) / rate if rate > 0 else 0
                progress_callback(done_count + i + 1, done_count + total, rate, remaining)

    for name in companies:
        if name in results:
            pass
        elif name.lower().strip() in cache:
            results[name] = cache[name.lower().strip()].get("contacts", [])

    return results
