# FR Y-9C Dashboard — Design Context for Future Editors

This document distills the standing design decisions, methodology constraints, and
non-obvious implementation choices for the FR Y-9C dashboard. Read this before making
substantive changes to `make_site_fry9c.py`, `build_hierarchy_fry9c.py`, or any curated
input files (`fry9c_matrix.csv`, `fry9c_hierarchy_overrides.json`).

---

## What this project is

A browser dashboard over the Federal Reserve's **FR Y-9C** consolidated financial statements
for bank holding companies. The FR Y-9C is a 71-page regulatory form (~400 line items across
20+ schedules) filed quarterly by ~3,000 top-tier U.S. BHCs.

The dashboard is one of three sibling projects (Y-9C, FFIEC 002, Call Reports). The three
`make_site_*.py` scripts are **clones** of a single explorer engine — they share no module.
Every engine or UI change must be ported to all three files. Never copy a MDRM code from one
form to another without verifying it exists in that form's data panel.

---

## The rendered-vs-PDF standard (the quality bar)

The hierarchy in `fry9c_hierarchy.json` must exactly match what a human sees on the blank
FR Y-9C form PDF (`FR_Y-9C20260310_f.pdf`). The gate is:

> **39/39 schedules rendered correctly** — every schedule's line items (count, numbering,
> nesting, caption) match the PDF page-by-page.

This was verified manually (screenshot each schedule, compare to the PDF) at the time of
final validation (2026-06-22, commit `48b4cf7`). The `_completeness_gate.py` script enforces
this automatically for every subsequent rebuild.

When making changes:
1. Run `build_hierarchy_fry9c.py` after editing matrix/overrides.
2. Run `validate_build.py` (must exit 0, print "ALL CHECKS PASSED").
3. Open the dashboard and visually compare the changed schedule to the PDF.

---

## Hierarchy construction pipeline

`build_hierarchy_fry9c.py` builds `fry9c_hierarchy.json` in three layers:

### Layer 1 — PDF parsing (pypdf)
Reads the blank form PDF to extract schedule structure: item numbers, captions, nesting.
This works well for most schedules (HI, HC, HC-A through HC-M, HC-P, HC-Q, HC-S, HC-V, HC-W).

### Layer 2 — Matrix overrides (fry9c_matrix.csv)
Schedules the PDF parser can't reliably parse are specified manually:
- **HC-N** (past-due/nonaccrual matrix — tabular, not a simple list)
- **HC-C** (loans by category/maturity — nested matrix)
- **HC-R Parts I & II** (regulatory capital — complex multi-column)
- **HC-V** (variable-interest entities)

Edit `fry9c_matrix.csv` to add or correct line items in these schedules.
**Never override matrix rows by copying them from another form** — codes differ between
Y-9C and Call even for similar concepts.

### Layer 3 — JSON overrides (fry9c_hierarchy_overrides.json)
Post-parse corrections applied after PDF parsing and matrix injection:
- `force_rows`: inject specific line items that the parser misses
- `caption_fixes`: correct garbled or truncated captions
- `drop_codes`: remove codes that appeared in an old form version but are no longer reported
- `renames`: standardize item numbering (e.g., "Item 5" → "Item 5a")

Edit this file for surgical corrections; prefer it over changing the matrix for isolated fixes.

---

## Completeness gate (bidirectional, era-aware)

`_completeness_gate.py` runs a bidirectional check:

1. **Forward:** every code in `expected_items.json` must appear in the built hierarchy
   (nothing missing from the rendered dashboard vs. the form).
2. **Backward:** every code in the built hierarchy must either be in `expected_items.json`
   or in `fry9c_completeness_exclusions.json` (nothing rendered that shouldn't be).

`fry9c_completeness_exclusions.json` contains codes that are legitimately absent from
the data (retired codes, memo items not collected in certain eras, etc.). When the gate
fails on a new "missing" code, diagnose first:
- Is the code actually on the form? (Check the PDF.)
- Is it present in `fry9c_panel_long.parquet`? (Check with DuckDB or pandas.)
- If it's on the form but absent from the data (reporting not required in this era), add
  it to `fry9c_completeness_exclusions.json` with a comment explaining why.

**Era-awareness:** some codes only appear in certain date ranges (codes added or retired
between form revisions). The exclusion file tracks these. Do not add a blanket exclusion
for a code that *should* be present in recent data.

---

## Aggregated ratio rule (Σnum / Σden, never average-of-ratios)

For DERIV-type measures (ratios), the dashboard computes:

```
aggregate_ratio = sum(numerators) / sum(denominators)
```

**Never** `mean(individual_ratios)`. This is enforced in the `seriesFor()` JS function
via `type:'ratio'` dispatch. Violating this produces nonsensical aggregate capital ratios
(e.g., an average of individual CET1 ratios is meaningless; the correct aggregate is
total system CET1 capital / total system RWA).

DERIV measures are defined in `make_site_fry9c.py` as part of the `DERIVED` dict. Each
entry specifies `num` (numerator MDRM code), `den` (denominator MDRM code), and optionally
`annualize: true` for income-flow measures that should be shown on an annualized basis.

---

## PCTC codes (non-additive percentages)

Some FR Y-9C codes are raw percentage ratios published directly by the filer (e.g., HC-R
capital ratio disclosures). These use MDRM prefixes BHCA/BHCW and specific suffixes
(7204, 7205, 7206, P793, H036, …). There are ~33 such codes.

**PCTC codes must not be summed across entities** — the aggregate of "capital ratio" is
meaningless. The engine blocks PCTC codes for aggregate scopes (`isRawPct()` + `isAggScope()`
guards in JS). If you add a new HC-R code, check whether it is a raw ratio (PCTC) or a
dollar amount. When in doubt, look up the MDRM description in `fry9c_dictionary.csv`.

---

## DYN subtotals (Y-9C only, not in 002/Call)

Clicking a schedule header in the Y-9C dashboard creates a dynamic subtotal (`DYN['SUB:code']`)
that sums the non-PCTC leaf descendants of that node. This is implemented via `descCodes()` in
`make_site_fry9c.py`'s embedded JS.

DYN does not exist in the 002 or Call dashboards (their hierarchies are flat enough that it
isn't needed). Do not port DYN to 002/Call without validating that the hierarchy supports it.

---

## Entity-clustered parquet layout

`make_site_fry9c.py` writes parquets sorted by `(id_rssd, quarter_end)` and split into:

- `fry9c_active_{era}.parquet` — active BHCs only, one file per era
- `fry9c_hist.parquet` — full dataset for all BHCs (including historical/defunct)
- `fry9c_agg.parquet` — aggregate scopes (ALL, type groups, size buckets)

The clustering means DuckDB-WASM's HTTP range requests fetch only the row-groups for
the entity the user selected, typically 0.5–2 MB of actual transfer. **Do not sort by
quarter first** — that defeats the clustering and makes single-entity queries fetch the
entire file.

---

## The three-dashboard clone constraint

`make_site_fry9c.py`, `make_site_002.py`, `make_site_call.py` are clones. When you change
the engine (JS or Python build logic):

1. Make the change in one file first and test it.
2. Port the change to all three — copy exactly the modified function/block.
3. Adjust for form-specific differences (MDRM prefixes, schedule names, PCTC sets).
4. Validate all three with `FINALIZE.ps1`.

**Common porting mistake:** copying a MDRM code that exists in Y-9C but not in 002/Call.
Always verify a code exists in the target form's panel parquet before wiring it.

---

## Data source constraints

All data is free public government disclosure:
- Fed/FFIEC NIC Financial Data Download (quarterly BHCF ZIP files)
- FFIEC CDR (Call Reports)
- Chicago Fed (FFIEC 002)

**Akamai constraint:** The NIC Financial Data Download page is behind Akamai WAF.
Direct HTTP requests (requests, curl, wget) are blocked. Use `download_fry9c_playwright.py`
which drives a real Chrome browser via Playwright. Do not add retry loops that hit the
endpoint rapidly — Akamai will rate-limit the IP.

No paid data sources. No WRDS. No Bloomberg. Everything comes from public filing requirements.

---

## Validation checkpoints

| Check | Tool | Pass condition |
|---|---|---|
| Golden cell | `validate_build.py` | JPMorgan RSSD 1039502, BHCK2170 @ 2026-03-31 = 4,900,475,000 |
| DERIV codes resolve | `validate_build.py` | All DERIV num/den codes present in panel |
| Bidirectional completeness | `_completeness_gate.py` | 0 missing, 0 unexpected codes |
| Rendered-vs-PDF | Manual + `_validate_hierarchy_vs_pdf.py` | 39/39 schedules match form |
| Engine smoke test | `_qa_final.py` | 23/23 QA checks pass |
| Full suite | `FINALIZE.ps1` | Prints "FINALIZE COMPLETE - ALL PASSED" |

Run `validate_build.py` after every hierarchy rebuild. Run `FINALIZE.ps1` before any push.

---

## Key files and what to edit

| Want to... | Edit this |
|---|---|
| Add/fix a line item in a matrix schedule | `fry9c_matrix.csv` |
| Fix a caption, force a row, drop an old code | `fry9c_hierarchy_overrides.json` |
| Add a derived ratio (e.g., new capital metric) | `DERIVED` dict in `make_site_fry9c.py` |
| Change dashboard UI or query logic | `make_site_fry9c.py` (then port to 002/Call) |
| Change what codes are excluded from the completeness gate | `fry9c_completeness_exclusions.json` |
| Add a new expected line item | `expected_items.json` |
| Update for a new form revision | Re-run `build_hierarchy_fry9c.py` with new PDF; audit diff |
