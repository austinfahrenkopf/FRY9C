# FR Y-9C Dashboard — Build & Release Runbook

Reproducible pipeline from free FFIEC/Fed data to the dashboard. Run from this folder.
Setup once: `pip install pandas pyarrow pypdf playwright requests duckdb` and `playwright install chrome`.

## What's pre-built in this kit

- `fry9c_hierarchy.json` — final curated form tree (may be used as-is; re-run step 8 only when editing overrides/matrix).
- `ReturnFinancialReportPDF.pdf` — blank FR Y-9C form PDF (required by steps 6 and 8).
- `fry9c_lineage.json`, `fry9c_topholder.json` — entity metadata (re-run steps 4+5+7 only on quarterly refresh).

## Pipeline (full rebuild from scratch)

| # | Command | Produces | Notes |
|---|---|---|---|
| 1 | `python download_fry9c_playwright.py` | `fry9c_zips/` (quarterly BHCF ZIPs, 2000-Q1+) | real-Chrome, Akamai-safe. Resumable. `--limit 2` to test. |
| 2 | `python build_fry9c_panel.py` | `fry9c_panel_long.parquet`, `fry9c_roster.csv` | long panel; keeps consolidated BH**** codes for BHCK2170 filers. |
| 3a | `python build_fry9c_hist.py download` | `fry9c_hist_parts/` (Chicago Fed CSVs 1986-Q3 to 2009-Q4) | plain requests, no Playwright. Resumable. |
| 3b | `python build_fry9c_hist.py merge` | extends `fry9c_panel_long.parquet` back to 1986 | folds pre-2000 history into the existing panel. |
| 4 | `python download_fry9c_nic_playwright.py` | `fry9c_nic/` (transformations, relationships, attributes) | RSSD entity-structure source. |
| 5 | `python build_fry9c_lineage.py` | `fry9c_lineage.json` | predecessor/successor chains (TD, Barclays, etc.). |
| 6 | `python build_fry9c_dictionary.py` | `fry9c_dictionary.csv` | MDRM code → caption (from Fed MDRM.zip). |
| 7 | `python build_fry9c_topholder.py --from-panel` | `fry9c_topholder.json` | nested Y-9C filer map — `--from-panel` covers all 159 quarters (1986+) via the panel; default (no flag) only covers 2000+ NIC zips. |
| 8 | **`python build_hierarchy_fry9c.py`** | `fry9c_hierarchy.json` | form tree. Reads `fry9c_matrix.csv` + `ReturnFinancialReportPDF.pdf` + dictionary. |
| 9 | **`python validate_build.py`** | (exit 0 = pass) | **automated QA gate — run after step 8. Must pass before site build.** |
| 10 | `python make_site_fry9c.py` | `site_fry9c/index.html` + parquets | the dashboard. `--html-only` to regenerate just the HTML fast. |

Typical curate loop after editing `fry9c_matrix.csv`: **8 → 9 → 10 --html-only**.

## Golden cell (proof the rebuild is correct)

JPMorgan Chase (RSSD 1039502) BHCK2170 at 2026-03-31 = **4,900,475,000** ($ thousands).
`validate_build.py` checks this automatically. `_qa_final.py` re-checks from the deployed site.

## ⚠️ Critical process note (caused a data-loss incident)
**Never edit `fry9c_matrix.csv` with shell `>>`/append from a tool whose filesystem view can lag.**
Mixing shell appends with editor edits on the same file caused a stale copy to overwrite ~145 curated
rows (HC-R Part I 20–69, HC-V, HI-C, HC-B). **Edit the CSV with a normal editor only.** After any edit,
run step 9 — it will catch missing schedules/codes immediately.

## What `fry9c_matrix.csv` holds
Curated "matrix" schedules (rows × fixed columns) the text parser can't read: HC-N, HI-B (+Part II),
HC-C, HC-L, HC-Q, HC-S, HC-R (Part I + Part II), HC-V, HI-C, HC-B. Format:
`schedule,item,caption,header,colA,colB,colC,codes,labels`. Single-column rows use colA; N-column rows
use pipe-separated `codes` + `labels`. Everything else (HC, HI, HC-D incl. HC-E, HC-F, HC-G, HC-H,
HC-I, HC-K, HC-M, HC-P, HI-A) is built automatically by the text parser in `build_hierarchy_fry9c.py`.

## Schedule attribution (parser)
A schedule header is `Schedule X—Title` (em-dash). Single-header page → whole page; 2+ headers →
split per header; no header → carry forward. HC-E (Deposit Liabilities) shares page 30 with HC-D and
is folded into HC-D.

## Lineage
Picking any RSSD of a multi-RSSD institution charts the full predecessor→successor chain under the
latest name, with a dashed "RSSD change" marker at each seam. Rebuild lineage = steps 4 → 5 → 10.
