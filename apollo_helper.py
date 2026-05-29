from urllib.parse import quote


def build_apollo_contact_url(contact_id: str) -> str:
    return f"https://app.apollo.io/#/people/{contact_id}"


def build_apollo_url(company_name):
    titles = [
        "Chief Sustainability Officer",
        "Sustainability Manager",
        "Head of Sustainability",
        "ESG Manager",
        "Carbon Manager",
        "Director of Sustainability",
        "VP Sustainability",
        "CSO",
    ]
    encoded_org = quote(company_name)
    titles_param = "&".join(
        f"titles[]={quote(t)}" for t in titles
    )
    url = (
        f"https://app.apollo.io/#/people"
        f"?organizationNames[]={encoded_org}"
        f"&{titles_param}"
    )
    return url


def build_esg_search_url(company_name):
    query = quote(f"{company_name} sustainability report 2024")
    return f"https://www.google.com/search?q={query}"


def build_sbti_profile_url(company_name):
    query = quote(company_name)
    return f"https://sciencebasedtargets.org/companies-taking-action?q={query}"
