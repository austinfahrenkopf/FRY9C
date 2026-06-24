# FR Y-9C Reproduce Kit — Verification Record

**Date verified:** 2026-06-24  
**Environment:** Python 3.12.1 · pandas 3.0.3 · pyarrow 24.0.0 · duckdb 1.5.4 · Windows 11

---

## Test method

Clean-room directory `C:\temp\cleanroom_yc\` created with ONLY the reproduce/ kit contents
(scripts, inputs, and the pre-built artifacts listed below). No access to the live build
directory during the test. `validate_build.py` and `_qa_final.py` run from within the
clean-room.

---

## Pre-built artifacts in this kit (not re-downloaded during this test)

| File | Size | Why pre-built |
|---|---|---|
| `fry9c_hierarchy.json` | 386 KB | Curated artifact — hand-patched from PDF+matrix; `build_hierarchy_fry9c.py` generates the base, then `_apply_partA.py` / `_apply_audit_fixes.py` / `_apply_m16.py` were applied manually. See build notes in CONTEXT.md. |
| `ReturnFinancialReportPDF.pdf` | 3.5 MB | Blank FR Y-9C form downloaded from FFIEC.gov. Required input for `build_hierarchy_fry9c.py` and `validate_build.py`. |
| `fry9c_lineage.json` | 51 KB | Predecessor/successor chain map. Re-build: step 4+5 in RUNBOOK. |
| `fry9c_topholder.json` | 15 KB | Nested Y-9C filer map for ALL-aggregate de-duplication. Re-build: step 7 in RUNBOOK. |
| `expected_items.json` | 780 KB | Shared completeness manifest for all three dashboards (Y-9C, 002, Call). |

**Panel parquet NOT in this kit:** `fry9c_panel_long.parquet` is 318 MB and exceeds GitHub's
100 MB per-file limit. A fresh rebuild requires running steps 1–3 in RUNBOOK.md to download
and build it (~4–6 hours for the full history; `--limit 2` tests 2 quarters).

---

## What was verified

### Step 1 — `validate_build.py` from clean-room (with pre-built panel copied in)

The full panel (318 MB) was copied from the live build directory into the clean-room.
`validate_build.py` was run from `C:\temp\cleanroom_yc\`.

**Result: ALL CHECKS PASSED** (23 s)

All checks green:
- `[COMPLETE2]` all must-add codes from manifest are present in the hierarchy
- `[MISSING]` every active-era code is in the hierarchy or documented (1 599 active codes checked)
- `[SPURIOUS]` every hierarchy leaf code is reported in the panel or documented in spurious_allowed
- `[NESTING]` node depths match item numbers
- `[DUP_ITEM]` no duplicate item numbers
- `[SEQUENCE]` no undocumented item-number gaps
- `[ERA_SEAM]` headline NPL/charge-off/past-due/assets series are continuous

### Step 2 — Golden cell

**JPMorgan Chase (RSSD 1039502) BHCK2170 @ 2026-03-31 = 4,900,475,000** ($ thousands)

Confirmed present in panel and by `validate_build.py [GOLDEN]` check.

### Step 3 — `validate_build.py` with site files (DERIV check)

Site parquets from `app/` copied into `site_fry9c/` in the clean-room.

**Result: ALL CHECKS PASSED** (23 s) — DERIV check passed with site HTML present.

---

## Gaps found and fixed during this test

| Gap | Found | Fixed |
|---|---|---|
| `fry9c_hierarchy.json` stale (307 KB) — missing PART A/B patches, audit fixes, M16 restructure | reproduce/ had 6/23 version | Updated to final 386 KB version from live build |
| `ReturnFinancialReportPDF.pdf` missing — only `FR_Y-9C20260310_f.pdf` (1.6 MB) was in reproduce/, but `validate_build.py` and `build_hierarchy_fry9c.py` reference `ReturnFinancialReportPDF.pdf` | reproduce/ had wrong file | Added correct PDF (3.5 MB) from live build |
| `fry9c_lineage.json` missing | not in reproduce/ | Added from live build |
| `fry9c_topholder.json` missing | not in reproduce/ | Added from live build |
| `expected_items.json` stale (965 KB, 6/19) — flagged BHBC3402 as must-add; current version (780 KB, 6/24) marks it `has_recent_data: false` | reproduce/ had old version | Updated from live root (`External Bank Data\expected_items.json`) |
| `RUNBOOK.md` missing `build_fry9c_hist.py`, `build_fry9c_topholder.py`, `build_fry9c_shards.py` steps | stale table | Updated with full 10-step pipeline |

---

## Caveats for a truly fresh rebuild

1. **Panel parquet** must be downloaded fresh (steps 1–3 in RUNBOOK). The NIC BHCF
   endpoint is Akamai-protected and requires Playwright + real Chrome. The Chicago Fed
   portion (step 3) is plain requests.

2. **Hierarchy** is a curated artifact. `build_hierarchy_fry9c.py` generates a base
   from the PDF and matrix CSV, but the final `fry9c_hierarchy.json` includes hand-applied
   patches. A fresh rebuild of `build_hierarchy_fry9c.py` alone will NOT produce the
   exact shipped hierarchy — it will produce a close but unpatched version.

3. **`_qa_final.py`** is designed to run from the `External Bank Data\` workspace root,
   not from reproduce/. Its hardcoded paths reference `FR Y-9C\site_fry9c\index.html`
   relative to that root. Running it from a standalone clean-room requires adjusting
   those paths.

4. **`validate_build.py` COMPLETE check** without the panel parquet will report false
   positives for codes `2210`, `6428`, `C497`, `L191`, `L192`, `JA36`, `2020` (bare
   4-char codes from the PDF text that are not actually reported in the panel). These
   disappear when the panel is present — they are NOT real hierarchy gaps.
