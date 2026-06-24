# FR Y-9C Dashboard — Build & Release Runbook

Reproducible pipeline from free FFIEC/Fed data to the dashboard. Run from this folder.
Setup once: `pip install pandas pyarrow pypdf playwright` and `playwright install chrome`.

## Pipeline (in order)

| # | Command | Produces | Notes |
|---|---|---|---|
| 1 | `python download_fry9c_playwright.py` | `fry9c_zips/` (quarterly BHCF zips) | real-Chrome, Akamai-safe. Resumable. `--limit 2` to test. |
| 2 | `python build_fry9c_panel.py` | `fry9c_panel_long.parquet`, `fry9c_roster.csv` | long panel; keeps consolidated BH**** codes for filers reporting BHCK2170. |
| 3 | `python build_fry9c_dictionary.py` | `fry9c_dictionary.csv` | MDRM code → caption (from Fed MDRM.zip). |
| 4 | `python download_fry9c_nic_playwright.py` | `fry9c_nic/` (transformations, relationships, attributes) | RSSD-lineage source. Small, fast. |
| 5 | `python build_fry9c_lineage.py` | `fry9c_lineage.json` | stitches predecessor RSSDs (TD, Barclays …) into continuous histories. |
| 6 | **`python build_hierarchy_fry9c.py`** | `fry9c_hierarchy.json` | the form tree. Reads `fry9c_matrix.csv` (curated matrices) + the PDF + dictionary. |
| 7 | **`python validate_build.py`** | (exit 0 = pass) | **automated QA gate — run after step 6.** Fails the release if anything regressed. |
| 8 | `python make_site_fry9c.py` | `site_fry9c/index.html` + parquet | the dashboard. `--html-only` to regenerate just the HTML fast. |

Typical edit-rebuild loop after curating `fry9c_matrix.csv`: **6 → 7 → 8**, then reload the page.

## ⚠️ Critical process note (caused a data-loss incident)
**Never edit `fry9c_matrix.csv` with shell `>>`/append from a tool whose filesystem view can lag.**
Mixing shell appends with editor edits on the same file caused a stale copy to overwrite ~145 curated
rows (HC-R Part I 20–69, HC-V, HI-C, HC-B). **Edit the CSV with a normal editor only.** After any edit,
run step 7 — it will catch missing schedules/codes immediately.

## What `fry9c_matrix.csv` holds
Curated "matrix" schedules (rows × fixed columns) the text parser can't read: HC-N, HI-B (+Part II),
HC-C, HC-L, HC-Q, HC-S, HC-R (Part I + Part II), HC-V, HI-C, HC-B. Format:
`schedule,item,caption,header,colA,colB,colC,codes,labels`. Single-column rows use colA; N-column rows
use pipe-separated `codes` + `labels`. The builder natural-sorts rows, so CSV row order doesn't matter.
Everything else (HC, HI, HC-D incl. HC-E, HC-F, HC-G, HC-H, HC-I, HC-K, HC-M, HC-P, HI-A) is built
automatically by the text parser in `build_hierarchy_fry9c.py`.

## Schedule attribution (parser)
A schedule header is `Schedule X—Title` (em-dash). Body refs like "Schedule HC, item 12" or
"Totals From Schedule HC" are ignored. Single-header page → whole page; 2+ headers → split per header;
no header → carry forward. HC-E (Deposit Liabilities) shares page 30 with HC-D and is folded into HC-D.

## Lineage
Picking any RSSD of a multi-RSSD institution charts the full predecessor→successor chain under the
latest name, with a dashed "RSSD change" marker at each seam. Rebuild lineage = steps 4 → 5 → 8.
