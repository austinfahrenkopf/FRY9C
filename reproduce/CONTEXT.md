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

## DYN subtotals

Two distinct DYN mechanisms exist:

**1. Tree-click DYN (Y-9C only):** Clicking a schedule header creates `DYN['SUB:code']` summing
non-PCTC leaf descendants in real time. Implemented via `descCodes()` in JS. This mechanism does
NOT exist in 002 or Call — their hierarchies are too flat.

**2. `buildLGMEAS()` DYN entries (all three repos, since §NORMDEN-LEAGUE-FRY9C/CALL/002):**
`buildLGMEAS()` walks the full HIER tree via `nest(emitSchedule(sch))` and pre-computes
`DYN['SUB:'+nd.code]` for every header node. These are used by the League table's `perFilerValues()`
(which reads `let d=DERIV[measCode]||DYN[measCode]`). This IS in all three repos — do not confuse
with tree-click DYN. Never remove the `||DYN[measCode]` fallback in `perFilerValues()`.

`pct` flag for DERIV loop: use `d.type==='ratio'` (not `d.type!=='sum'`) to avoid marking sum-type
DYN entries as percentage. This was corrected in all three repos at §NORMDEN-LEAGUE.

---

## Denominator dropdown (`#normden`, `NORM_DEN_LABELS`) — §NORMDEN-LEAGUE-FRY9C

Replaced the single `÷ assets` checkbox with a compound control: same `#normbyassets` checkbox
plus a `#normden` `<select>` with 4 presets. Key implementation details:

- **`NORM_DEN_LABELS`** constant maps code → human label for axis suffix (assets / loans / deposits / equity).
- **Presets (MDRM):** `BHCK2170` (Total assets, default), `BHCK2122` (Total loans & leases),
  `S_DEP` (Total deposits — DERIV sum; see below), `BHCK3210` (Total equity capital).
- **`window._normDenCd`:** Current denominator code stored on `window` (not `let`) so it is
  accessible from `page.evaluate()` in Playwright. Never change this to a `let`.
- **`recompute()`** reads `#normden.value` → `window._normDenCd`; `draw()` and `drawExtraChart()`
  both use `NORM_DEN_LABELS[normDen]` for the axis label.
- **Link-chart sync:** `_getLinkTfm()` carries `normDen` in the transform object; `_applyLinkedTfm()`
  applies it to extra charts. Always update both when porting.
- **localStorage:** `fry9c_normden` (selected code) + `fry9c_normbyassets` (on/off). Restored on init.

**Y-9C total deposits (`S_DEP`):** No single `BHCK2200` code exists on the Y-9C form. Deposits are
split across `BHDM6631 + BHDM6636 + BHFN6631 + BHFN6636`. The engine defines
`DERIV['S_DEP'] = {type:'sum', plus:['BHDM6631','BHDM6636','BHFN6631','BHFN6636']}`.
`seriesFor()` handles DERIV sums transparently. Never use a single `BHCK2200` on Y-9C.

---

## League table — full measure set (`buildLGMEAS`) — §NORMDEN-LEAGUE-FRY9C

`buildLGMEAS()` builds the league's measure dropdown by walking the full `HIER` tree:

```
nest(emitSchedule(sch))  →  DYN['SUB:'+nd.code]  for every header node
```

- Creates `{type:'sum', plus:[...leaf codes]}` DYN entries for tree headers.
- **HC-N row 9 special case:** uses `hybrid_sum` with `_HCN9_A/B/C` parts (mirrors the tree-click
  handler). Must be preserved when porting to other dashboards; check the target form's HIER first.
- Result: 453 league measure options (Y-9C). Includes all raw codes + all tree-subtotals + all DERIV.
- **`perFilerValues()` hybrid branch:** `hybrid_sum`/`hybrid_ratio` types use `.parts` array with
  `{reported, components}` per segment; reported value preferred over sum of components; single grouped
  DuckDB query per measure. Keep this branch when porting; it handles Y-9C's HC-N reporting gaps.

---

## `hybrid_sum` subtotals — §HCN9-HYBRID + §SUBTOTAL-AUDIT-FIX

Several Y-9C sub-totals cannot be read directly from the panel (no single code exists or the
reported code is zero/absent for some filers). These use `type:'hybrid_sum'` in DERIV:

| Sub-total | DERIV key | Mechanism |
|---|---|---|
| HC-N row 9 (total past-due/nonaccrual) | `_HCN9_A/_HCN9_B/_HCN9_C` parts | `hybrid_sum` with 3 column-sets; reports column sums across the HC-N matrix |
| HC-C 10.A lease-financing | `BHCK2165` | `hybrid_sum`, `preferMax:false` (false-zero fix: some filers report 0 for a non-zero lease portfolio; use sum of components instead of reported value for those filers) |
| HC-F row 3 | `BHCKHT80` | `hybrid_sum` |
| HC-L row 1.e.2 | `BHCKJ458` | `hybrid_sum` |

**`preferMax:false` fix (HC-C 10.A):** Without this, filers who report `BHCK2165=0` (a false zero
meaning "not separately disclosed") would show $0 lease financing when their component codes sum to
a non-zero value. `preferMax:false` means the sum of components wins over the reported value when
the reported value is lower. Do not remove this flag for lease-financing.

---

## Mis-nest override mechanism (`item=""`, `depth=1`) — §MISNEST-FIX-YC + §HCD-MEMO-FIX

Several Y-9C codes appear mis-nested in `fry9c_hierarchy_overrides.json` using the override:
```json
{ "code": "BHCKXXXX", "item": "", "depth": 1 }
```
This sets the item number to empty and depth to 1, making the code a standalone (un-indented) entry
rather than a child of a preceding header. Use this pattern for surgical de-parenting.

Known mis-nests fixed and committed in `fry9c_hierarchy_overrides.json`:

| Codes | Schedule | Problem | Fix |
|---|---|---|---|
| ~24 HC-D Memo codes | HC-D Memo | Incorrectly nested under wrong header | `item=""` `depth=1` overrides |
| `BHCKS489`, `BHCKS484` | HC-R Part II | Mis-nested under wrong HC-R Part II header | `item=""` `depth=1` |
| `BHCKG387`, `BHCKG388` | HC-D Memo item 4 | Mis-nested under different memo section | `item=""` `depth=1` |

**Workflow:** apply surgical `force_rows` / `caption_fixes` / `item=""`+`depth=1` overrides in
`fry9c_hierarchy_overrides.json`; always run `build_hierarchy_fry9c.py` → `validate_build.py` after
any change. Never edit `fry9c_hierarchy.json` directly; it is rebuilt from the PDF + matrix + overrides.

---

## Export Builder fidelity — §EXPORT-FIX-YC

The Export Builder (JS module) was redesigned to route all codes correctly:

- **`ebRawCodes()`:** simplified to `out.add(c)` for all measure types. DERIV/DYN now count as
  one code each (not silently dropped). `hybrid_sum` no longer dropped.
- **`runExport()`:** partitions measure codes into `derivKeys` (DERIV/DYN/COMB — routed through
  `seriesFor()`) and `rawOnly` (pure MDRM — goes to raw SQL). Applied to BOTH the "codes" scope
  and the "schedules" scope.
- **Schedules scope:** RCFD/RCON codes in the schedules scope are converted to COMB before DERIV
  lookup. This is a Y-9C/Call pattern — always check the schedule-scope path when porting.

Before this fix, `hybrid_sum` measures and COMB codes exported null. After the fix, all measure
types produce correct exported values.

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
| Engine smoke test | `_qa_final.py` | 32/32 QA checks pass (includes normden/league checks) |
| Full suite | `FINALIZE.ps1` | Prints "FINALIZE COMPLETE - ALL PASSED" |

Run `validate_build.py` after every hierarchy rebuild. Run `FINALIZE.ps1` before any push.

---

## Key files and what to edit

| Want to... | Edit this |
|---|---|
| Add/fix a line item in a matrix schedule | `fry9c_matrix.csv` |
| Fix a caption, force a row, drop an old code | `fry9c_hierarchy_overrides.json` |
| Add a derived ratio or DERIV code | `DERIVED` dict in `make_site_fry9c.py` |
| Fix a mis-nest (standalone an incorrectly-nested code) | `fry9c_hierarchy_overrides.json`: add `{"code":"BHCKXXXX","item":"","depth":1}` |
| Add a denominator preset to the ÷ dropdown | `NORM_DEN_LABELS` dict in `make_site_fry9c.py` |
| Change dashboard UI or query logic | `make_site_fry9c.py` (then port to 002/Call) |
| Change what codes are excluded from the completeness gate | `fry9c_completeness_exclusions.json` |
| Add a new expected line item | `expected_items.json` |
| Update for a new form revision | Re-run `build_hierarchy_fry9c.py` with new PDF; audit diff |
