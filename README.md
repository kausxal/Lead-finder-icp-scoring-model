# Terrascope ICP Lead Finder

![Terrascope ICP Lead Finder](screenshots/app_screenshot.png)

A desktop application that scores over 15,000 companies from the SBTi database against Terrascope's Ideal Customer Profile, enriches them with real-world data from multiple sources, and provides a complete workflow for filtering, evaluating, and exporting leads.

---

## What This Tool Does

The SBTi (Science Based Targets initiative) publishes a public database of companies that have committed to setting climate targets. This is a rich dataset, but it is raw -- it gives you names, industries, and statuses, but tells you nothing about which companies actually fit your business.

This tool ingests that dataset and transforms it into a lead pipeline. It scores every company against an Ideal Customer Profile so you can immediately see which prospects are worth pursuing, which are borderline, and which are not a fit. It enriches the data with employee counts, revenue, emissions, website validity, and contact information. It lets you slice the data by any combination of filters, save companies to a persistent list, export to multiple formats, and search for sustainability contacts.

The goal is to turn a public spreadsheet into a working sales pipeline with minimal manual effort.

---

## How It Works

```mermaid
flowchart TB
    subgraph Input
        A[SBTi Google Sheets] --> B[Download & Parse]
        C[EU Taxonomy Dataset] --> B
    end

    subgraph "Data Layer"
        B --> D[(CSV Cache)]
        D --> E[Compute ICP Scores]
    end

    subgraph "Enrichment"
        F[OSI API] --> G[Emissions & Revenue]
        H[Origin/SEC API] --> I[Employees & HQ]
        J[Clearbit API] --> K[Domain & Logo]
        L[Wikidata] --> M[Employee Counts]
        N[Apollo API] --> O[Sustainability Contacts]
        P[DNS Validation] --> Q[Website Validity]
    end

    subgraph "Scoring Engine"
        E --> R[Industry Fit: 5-20]
        E --> S[Agriculture Bonus: 0-5]
        E --> T[Regulatory Urgency: 0-40]
        E --> U[SBTi Commitment: 0-25]
        R --> W[Total Score: 0-90]
        S --> W
        T --> W
        U --> W
    end

    subgraph "Interface"
        W --> X[Score Gauge & Breakdown]
        Y[Filter Panel] --> Z[Filter Pipeline]
        D --> Z
        Z --> AA[Results Table]
        AA --> X
        AA --> AB[Detail Panel]
        AB --> AC[Lead Status Override]
        AB --> AD[Notes & Contacts]
    end

    subgraph "Export"
        AA --> AE[CSV Export]
        AA --> AF[Google Sheets CSV]
        AA --> AG[Styled Excel]
        AA --> AH[My List]
    end

    G --> AI[Merge Enrichments]
    I --> AI
    K --> AI
    M --> AI
    Q --> AI
    AI --> D
```

---

## Quick Start

```
pip install customtkinter pandas requests openpyxl
python main.py
```

The first run will prompt you to download the SBTi database. After the download completes, scores are computed automatically and the full dataset appears in the table.

---

## The Scoring Model

The ICP score measures genuine fit. Every point must be earned through real, verifiable signals.

### Score Components (Max 90)

| Component | Max | What It Measures |
|-----------|-----|------------------|
| Industry Fit | 20 | High-fit industries (food, agriculture, retail, manufacturing, logistics, consumer goods, fashion, packaging, food and beverage) score 20. Medium-fit (real estate, healthcare, technology, energy, utilities, chemicals) score 12. All others score 5. |
| Agriculture Bonus | 5 | Additional 5 points on top of industry fit if the company operates in agriculture or farming. |
| Regulatory Urgency | 40 | Scaled by deadline proximity of the most urgent applicable regulation. Urgency 10 (<90 days) = 40pts, 8 (90-180d) = 32pts, 6 (180-365d) = 24pts, 4 (365-730d) = 16pts, 2 (>730d) = 8pts, 0 (no mandate) = 0pts. |
| SBTi Commitment | 25 | Net Zero Achieved = 25. Targets Set = 20. Committed = 15. No commitment = 0. |

### Regulations Tracked

| Market | Regulation | Deadline (May 2026) | Points if Applicable |
|--------|-----------|-------------------|---------------------|
| United States | California SB253 | August 10, 2026 (72 days) | 40 |
| Australia | AASB S2 | Today (active) | 40 |
| European Union | CSRD + CBAM | Active | 40 |
| Singapore | SGX TCFD / IFRS S2 | January 1, 2027 | 24 |
| Japan | SSBJ | March 31, 2027 | 24 |
| South Korea | ESG Disclosure | January 1, 2028 | 16 |

When a company faces multiple regulations, only the highest urgency score is used.

### Score Tiers

The overall score determines the lead status, shown in the table and detail panel.

- **HOT (63 and above):** These companies face an approaching regulatory deadline and are in the right industry. Highest priority.
- **WARM (36 to 62):** These companies show some fit but lack regulatory urgency, industry alignment, or SBTi commitment. Worth pursuing.
- **COLD (below 36):** These companies lack most ICP signals. Not a current priority.

### Score Display

When you click any company in the results table, the right panel shows a breakdown of exactly where the score came from. Each component is listed with its contribution:

  Industry Fit        20/20  High fit
  Agriculture Bonus    5/5   Agriculture/Farming
  Regulatory Urgency  40/40  California SB253 (72d remaining)
  SBTi Commitment     20/25  Targets set

The score number is color-coded green when the component is performing well, amber when middling, and red when contributing little.


---

## Data Sources and Enrichment

The tool pulls data from multiple sources and merges everything into a single table. Each source fills in information that the others might miss.

| Source | What It Provides | Key Detail |
|--------|------------------|------------|
| SBTi | Core database: company name, industry, country, region, SBTi status, target year, target type | Downloaded from a Google Sheets XLSX export. Cached locally for rapid startup. |
| EU Taxonomy | 190 EU companies with taxonomy alignment percentages | Downloaded from HuggingFace. Merged into the main table. |
| OSI API | Emissions data (scope 1, 2, 3), revenue, commitment deadline | Public demo API. Enriched individually or in batch. |
| Origin/SEC API | Employee count, headquarters, ticker, SIC code, founding year | Free API. Provides the employee data used in Company Size scoring. |
| Clearbit | Real domain name, logo URL, confidence score | Free autocomplete API. Batched with checkpoint-resume for reliability. |
| Wikidata | Employee counts for companies missing this data | Queries the P1128 property. Useful when Origin/SEC has no data. |
| Apollo API | Contact names, titles, email status for sustainability roles | Paid API. Requires an API key. Searches per-company, not in batch. |
| DNS | Website validity (resolves or does not) | Parallel socket resolution with 20 concurrent workers. |

---

## The Data Pipeline

```
Raw SBTi Spreadsheet
        |
        v
  Parse and Normalize
        |
        v
  Merge with Existing Cache
        |
        v
  Compute ICP Scores (background thread)
        |
        v
  Apply Active Filters
        |
        v
  Display Paginated Results
        |
        v
  Enrich (on demand):
    OSI / Origin / Clearbit / Wikipedia / Apollo / DNS
        |
        v
  Merge Enrichments into Cache
        |
        v
  Export or Save to My List
```

The cache is a local CSV file that preserves all computed scores and enrichment data between sessions. Scores are recomputed whenever the data changes or the scoring model is updated.

---

## Filtering

The left panel contains all available filters. Every change triggers a debounced refilter that waits 300 milliseconds after the last input, so you can adjust multiple filters without triggering repeated computations.

| Filter | Type | Behavior |
|--------|------|----------|
| Industries | Dropdown with checkboxes | Select or deselect individual industries. Only matching companies are shown. |
| Exclude | Dropdown with checkboxes | Companies matching any selected exclusion industry are removed from results. |
| Employees | Text range (From / To) | Filters by employee count. Leave blank for no limit. |
| Regions | Dropdown with checkboxes | Matches the region column using pattern-based rules for each region. |
| Country | Dropdown | Single-select from all countries present in the data. |
| Regulatory | Dropdown with checkboxes | CSRD, SBTi Committed, SBTi Targets Set, SEC Registrant, UK Company, EU Company. |
| Commitment | Dropdown | Applied after the main filter pipeline. All, Committed, Targets Set, Achieved Net Zero. |
| Target Year | Text range (From / To) | Filters by the company's target year. Only companies with a target year in range are shown. |
| ICP Score | Text range (Min / Max) | Filters by computed ICP score. |
| Lead Status | Dropdown with checkboxes | HOT, WARM, or COLD. |
| Last Fetched | Text range (From / To) | Filters by the date when SBTi data was last refreshed for each company. |
| Search | Text input | Searches company name, country, and industry with 180ms debounce. |

Memoization is built into the filter pipeline. If the same set of filters is applied twice with the same data version, the cached result is reused without recomputation.

---

## The Interface

The window is divided into three panels.

**Left panel (250px):** Data source controls with download buttons, followed by all filters in a scrollable stack, then bulk action buttons, and finally the Apollo API key input at the bottom.

**Center panel (flexible):** Search bar with My List button at the top, then the results table with pagination controls and a sort dropdown. The table shows company name, country, industry, employees, revenue, SBTi status, region, target year, website, ICP score, and lead status.

**Right panel (330px):** Shows details for the selected company, including a circular score gauge, the numeric score breakdown by component, all data fields (employees, revenue, SBTi status, last fetched date, target year, target type, sector, website), action buttons (Apollo contacts, ESG data, SBTi link, enrich, add to My List), and any stored notes or contacts.

At the bottom of the window, a status bar shows the data source, the current status message, counts for total companies, filtered companies, and My List size, and export buttons.

---

## Exports

| Format | File Pattern | Notes |
|--------|-------------|-------|
| CSV | terrascope_leads_TIMESTAMP.csv | UTF-8 with BOM. Excludes the score_breakdown column. |
| Google Sheets | terrascope_leads_sheets_TIMESTAMP.csv | Optimized for Google Sheets import. |
| Excel | terrascope_leads_TIMESTAMP.xlsx | Styled with openpyxl, auto-filter enabled. Falls back to CSV if openpyxl is not installed. |
| My List CSV | Same format as CSV export | Exports only the companies saved to My List. |

---

## My List

A persistent JSON file at `data/my_list.json` stores companies you have saved. You can add individual companies from the detail panel, or add all currently filtered companies in bulk. The My List popup shows saved companies with the option to remove individual entries or export the entire list.

---

## Batch Operations

The left panel provides several bulk action buttons:

- Enrich All: Runs OSI and Origin enrichment on all currently filtered companies using 5 parallel workers.
- Add Filtered: Adds all filtered companies to My List in one click.
- Validate Sites: Checks website validity for all filtered companies using 20 parallel DNS workers.
- Clearbit Batch: Runs Clearbit autocomplete enrichment with checkpoint resume.
- Wikipedia Employees: Fills missing employee counts from Wikidata using 15 parallel workers.
- Apollo API Key: Text input that auto-saves the key to `data/app_config.json`. Clicking the key input opens Apollo.io in your browser.

---

## Threading Model

All long-running operations run in background threads with `daemon=True`, so the interface remains responsive and threads are cleaned up on exit. UI updates are dispatched to the main thread using `self.after(0, callback)`.

| Operation | Internal Parallelism |
|-----------|---------------------|
| SBTi and EU Taxonomy download | Single thread |
| Score computation | Single thread (runs at startup and after any data change) |
| Filtering | Single thread (pre-computed scores) |
| OSI + Origin batch enrichment | ThreadPoolExecutor with 5 workers |
| Clearbit batch | Sequential (rate-limited to 0.35 seconds per request) |
| DNS website validation | ThreadPoolExecutor with 20 workers |
| Wikipedia employee lookup | ThreadPoolExecutor with 15 workers |
| Apollo contact search | Single thread per company |

---

## File Structure

```
terrascope_lead_finder/
  main.py                    Entry point with automatic dependency installation
  gui.py                     Full UI (TerrascopeApp class, ~2200 lines)
  data_handler.py            SBTi download, cache management, My List, website validation
  filters.py                 Filter pipeline and score computation
  scoring.py                 ICP scoring algorithm, color functions, country lists
  regulatory_urgency.py      Regulation database, deadline mapping, urgency calculation
  exporter.py                CSV, Google Sheets CSV, and styled Excel export
  enrichment.py              OSI and Origin/SEC API enrichment clients
  clearbit_enricher.py       Clearbit Autocomplete batch with checkpoint resume
  eu_taxonomy.py             EU Taxonomy dataset download and merge
  wikipedia_enricher.py      Wikidata employee count lookup with checkpoint
  apollo_api.py              Apollo.io people search API client
  apollo_helper.py           URL builders for Apollo, ESG, and SBTi links
  README.md
  run.bat                    Windows launcher
  cache/
    sbti_data.csv            Cached SBTi database (all computed scores included)
    cache_meta.json          Cache date metadata
    eu_taxonomy_cache.csv
    osi_cache.json           OSI API response cache
    origin_cache.json        Origin/SEC API response cache
    clearbit_cache.json
    clearbit_checkpoint.csv
    website_validation.json
    wikipedia_employees.json
    wikipedia_checkpoint.csv
    apollo_contacts.json
  data/
    my_list.json             Persisted saved companies
    app_config.json          Apollo API key and webhook URL
```

---

## Color Reference

| Token | Hex Value | Usage |
|-------|-----------|-------|
| BG | `#0f1117` | Main window background |
| CARD | `#1a1f2e` | Section backgrounds |
| CARD_LIGHT | `#232838` | Buttons, hover states, input backgrounds |
| ACCENT | `#00d4aa` | Primary accent color |
| TEXT | `#ffffff` | Primary text |
| TEXT_SECONDARY | `#8892a4` | Secondary and label text |
| DANGER | `#ff4757` | Destructive actions, cold lead status |
| WARNING | `#ffa502` | Warning state, warm lead status |

Score colors follow the same pattern: 63 and above uses the accent green, 36 to 62 uses amber, and below 36 uses red.
