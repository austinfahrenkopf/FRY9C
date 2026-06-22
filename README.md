# FR Y-9C Dashboard

Interactive browser dashboard over the Federal Reserve's **FR Y-9C** consolidated financial
statements for bank holding companies (BHCs). Covers 3,000+ top-tier U.S. BHCs, quarterly,
from 1990 through the most recent reporting period.

**Live site:** https://austinfahrenkopf.github.io/FRY9C/

Data source: free public filings from the Fed/FFIEC. No subscription required to rebuild.

---

## What it is

A single-page application that runs entirely in the browser. Data is stored as Parquet files
served from this repo; all SQL queries execute client-side via **DuckDB-WASM** (no server).
The dashboard lets you:

- Browse all ~400 FR Y-9C line items organized by schedule (HI, HC, HC-R, …)
- Chart any measure for any BHC or aggregate (ALL, peer groups, size buckets)
- Compare entities side-by-side, build custom peer groups, export to CSV/Excel
- View KPI tiles (QoQ %, YoY %, total-period Δ) and a quarterly data table

---

## Repo layout

```
/                          GitHub Pages root (served as the live dashboard)
├── index.html             Dashboard application (self-contained HTML + embedded JS + CSS)
├── fry9c_hierarchy.json   FR Y-9C schedule/line-item tree (built from the form PDF + overrides)
├── fry9c_agg.parquet      Aggregate-scope panel (ALL / peer groups) — all quarters
├── fry9c_hist.parquet     Full historical panel (all BHCs, all quarters, ~56 MB)
├── fry9c_active_*.parquet Entity-clustered active-BHC shards by era (3 files, for fast load)
├── _form_by_sched.json    Schedule metadata used by the dashboard engine
├── .nojekyll              Tells GitHub Pages not to run Jekyll processing
├── README.md              This file
├── FRY9C_complete.zip     Convenience zip of the full reproduce/ kit
└── reproduce/             Full reproduction kit — everything needed to rebuild from scratch
    ├── FR_Y-9C20260310_f.pdf           Blank FR Y-9C form (structural reference for the parser)
    ├── requirements.txt                Python dependencies
    ├── download_fry9c_playwright.py    Step 1a: download quarterly filing ZIPs from Fed
    ├── download_fry9c_nic_playwright.py Step 1b: download NIC RSSD lineage data
    ├── build_fry9c_panel.py            Step 2: parse ZIPs → fry9c_panel_long.parquet
    ├── build_fry9c_dictionary.py       Step 3: download MDRM dictionary → fry9c_dictionary.csv
    ├── build_fry9c_topholder.py        Step 4a: build top-holder RSSD map
    ├── build_fry9c_lineage.py          Step 4b: build RSSD lineage JSON
    ├── build_hierarchy_fry9c.py        Step 5: parse PDF + matrix + overrides → fry9c_hierarchy.json
    ├── make_site_fry9c.py              Step 6: build dashboard site_fry9c/ from panel + hierarchy
    ├── validate_build.py               Step 7: gate check (golden cell + DERIV code validation)
    ├── _completeness_gate.py           Step 7b: bidirectional rendered-vs-expected completeness gate
    ├── _qa_final.py                    Step 8: 23-point QA smoke test across all three dashboards
    ├── add_missing_codes.py            Correction utility: add MDRM codes missing from panel
    ├── FINALIZE.ps1                    One-shot rebuild + QA (runs steps 5-8 for all 3 dashboards)
    ├── fry9c_matrix.csv                Curated schedule structure for schedules the PDF can't parse
    ├── fry9c_hierarchy_overrides.json  Force-rows, caption fixes, drop-codes applied post-parse
    ├── fry9c_completeness_exclusions.json  Known-absent codes excluded from the completeness gate
    ├── fry9c_dictionary.csv            MDRM data dictionary (Fed-published)
    └── expected_items.json             Expected line-item set for all 39 schedules (gate reference)
    └── CONTEXT.md                      Design decisions and methodology for future editors
```

---

## Dependencies (one-time setup)

```powershell
pip install -r reproduce/requirements.txt
playwright install chrome
```

Requires **Python 3.10+**. DuckDB is NOT needed server-side — it runs as DuckDB-WASM in
the browser. Playwright is needed only for the data-download steps (Fed endpoints are
Akamai-guarded and require a real Chrome browser).

---

## Full pipeline: rebuild from scratch

Raw data is NOT committed to this repo (the full panel is ~243 MB). To rebuild completely:

### Step 1 — Download raw data  *(skip if you already have `fry9c_panel_long.parquet`)*

```powershell
cd "FR Y-9C"                          # your local project folder
python download_fry9c_playwright.py   # downloads quarterly BHCF ZIPs from the Fed
python download_fry9c_nic_playwright.py  # downloads NIC RSSD lineage data
```

This uses Playwright (real Chrome) because the Fed's NIC Financial Data Download is
Akamai-guarded. Direct HTTP downloads will be blocked. The ZIPs land in `fry9c_zips/`
and NIC data in `fry9c_nic/`.

### Step 2 — Build the panel

```powershell
python build_fry9c_panel.py           # parses ZIPs → fry9c_panel_long.parquet (~243 MB)
python build_fry9c_dictionary.py      # downloads MDRM master dict → fry9c_dictionary.csv
python build_fry9c_topholder.py       # builds top-holder RSSD map
python build_fry9c_lineage.py         # builds RSSD lineage JSON
```

`fry9c_panel_long.parquet` is the source of truth for all entity data. It is NOT
committed to this repo due to size; regenerate from the downloaded ZIPs.

### Step 3 — Build the hierarchy  *(run whenever fry9c_matrix.csv or overrides change)*

```powershell
python build_hierarchy_fry9c.py
```

Reads `FR_Y-9C20260310_f.pdf` (the blank form template) via `pypdf`, extracts the
schedule/line-item structure, then applies `fry9c_matrix.csv` overrides for schedules
the PDF parser can't read (HC-N, HC-C, HC-R, HC-V, …), and finally applies
`fry9c_hierarchy_overrides.json` (force-rows, caption fixes, drop-codes).

Outputs `fry9c_hierarchy.json` — the complete tree used by the dashboard.

### Step 4 — Build and validate the dashboard site

```powershell
python make_site_fry9c.py             # full build → site_fry9c/ (parquets + index.html)
python validate_build.py              # must exit 0 and print "ALL CHECKS PASSED"
```

For a quick HTML-only rebuild (parquets unchanged):
```powershell
python make_site_fry9c.py --html-only
```

### Step 5 — One-shot rebuild (after initial setup)

```powershell
# From the "External Bank Data\" project root:
.\FINALIZE.ps1
```

Runs: Y-9C hierarchy → validate → html-only site rebuild → 002 → Call → 23-point QA.
Prints `FINALIZE COMPLETE - ALL PASSED` on success. Takes ~3 minutes.

### Step 6 — Serve locally

```powershell
cd site_fry9c
python -m http.server 8003
# open http://localhost:8003
```

---

## Typical edit-rebuild loop

For curating a line item or override (the most common change):

```
edit fry9c_matrix.csv  OR  fry9c_hierarchy_overrides.json
  → python build_hierarchy_fry9c.py
  → python validate_build.py
  → python make_site_fry9c.py --html-only
  → reload http://localhost:8003
```

For a code fix in `make_site_fry9c.py` only:
```
edit make_site_fry9c.py
  → python make_site_fry9c.py --html-only
  → reload browser
```

---

## Entity-clustered parquet layout

`make_site_fry9c.py` writes two parquet sets to `site_fry9c/`:

| File | Content | Purpose |
|---|---|---|
| `fry9c_hist.parquet` | All BHCs, all quarters | Loaded on demand for full drill-through |
| `fry9c_active_{era}.parquet` | Active BHCs only, by era (1990–2009, 2010–2019, 2020–) | Fast initial load |
| `fry9c_agg.parquet` | Aggregate scopes (ALL, peer groups) | Loaded first; lightweight |

DuckDB-WASM fetches parquets via HTTP range requests (byte-range fetches), so it only
reads the row-groups it needs for a given entity. Entity-clustering means a single BHC's
data is contiguous in the file — a typical single-entity query fetches only ~0.5–2 MB
even from a 56 MB file.

---

## GitHub Pages deployment

Settings → Pages → Source = Deploy from branch → `main` / `(root)`.

Site goes live at `https://austinfahrenkopf.github.io/FRY9C/` automatically after each push.
The `reproduce/` subfolder is not served as a page — it's just files in the repo. Only
`index.html` at the root is the entry point.

**Size notes:** GitHub warns on files >50 MB and hard-blocks >100 MB.
- `fry9c_hist.parquet` (~56 MB) — advisory warning only, push succeeds
- All other parquets are well under 50 MB
- If `fry9c_hist.parquet` ever exceeds 100 MB, set up Git LFS: `git lfs track "*.parquet"`

---

## Golden validation cell

`validate_build.py` asserts a specific known value:

> **JPMorgan Chase (RSSD 1039502), BHCK2170 @ 2026-03-31 = 4,900,475,000 (thousands)**

This is the bellwether check. If it fails, the panel or parquet build is broken.

---

## Data source

Free public data — no subscription required:

- **FR Y-9C filings:** [NIC Financial Data Download](https://www.ffiec.gov/npw/FinancialReport/ReturnFinancialReport)
  (Fed/FFIEC; requires Playwright to navigate the Akamai-guarded page)
- **MDRM dictionary:** Fed's MDRM bulk download (fetched automatically by `build_fry9c_dictionary.py`)
- **NIC RSSD lineage:** [NIC web service](https://www.ffiec.gov/nicpubweb/) (requires Playwright)

No data is bought or licensed. Everything comes from government public disclosure requirements.
