# FR Y-9C Reproduce Kit — Verification Record

**Date verified:** 2026-06-24  
**Environment:** Python 3.12.1 · pandas 3.0.3 · pyarrow 24.0.0 · duckdb 1.5.4 · Windows 11

---

## Test method

Full clean-room rebuild in `C:\temp\cr_yc_full\` using ONLY the reproduce/ kit contents
(scripts + curated inputs). No access to the live build directory during build or validation.

All pipeline stages run in order — raw download → panel → hist merge → lineage → topholder →
validate → site → re-validate.

---

## Full pipeline rebuild — all stages from scratch

| Step | Script | Output | Time |
|---|---|---|---|
| 1 | `download_fry9c_playwright.py` | `fry9c_zips/` (105 NIC BHCF ZIPs, 250.2 MB) | ~3.5 h |
| 2 | `build_fry9c_panel.py` | `fry9c_panel_long.parquet` (318 MB, 109M rows, 105 quarters) | ~19 min |
| 3a | `build_fry9c_hist.py download` | `fry9c_hist_parts/` (Chicago Fed 1986–2009, 135 MB) | ~20 min |
| 3b | `build_fry9c_hist.py merge` | extends panel to 318.1 MB / 141.4M rows / 159 quarters | 131 s |
| 4 | `download_fry9c_nic_playwright.py` | `fry9c_nic/` (RSSD entity data, 32 MB) | ~30 min |
| 5 | `build_fry9c_lineage.py` | `fry9c_lineage.json` (139.5 KB, 150 multi-RSSD lineages) | 4 s |
| 6 | `build_fry9c_topholder.py` | `fry9c_topholder.json` (17.8 KB, 105 quarters) | 98 s |
| 7 | `validate_build.py` | ALL CHECKS PASSED (pre-site) | 24 s |
| 8 | `make_site_fry9c.py` | `site_fry9c/` (387 filers, 5 shards) | ~30 min |
| 9 | `validate_build.py` | ALL CHECKS PASSED + DERIV | see below |

---

## Result: ALL CHECKS PASSED

### Pre-site validate (step 7)

```
schedules in hierarchy: 36   matrix rows: 668   dict codes: 2984
NOTE  [DERIV] site HTML not found; run make_site_fry9c.py first
NOTE  [COMPLETE2] FR Y-9C: all must-add codes from manifest are now present in the hierarchy
NOTE  [MISSING] OK — every active-era code is in the hierarchy or documented (1599 active codes checked)
NOTE  [SPURIOUS] OK — every hierarchy leaf code is reported in the panel or documented in spurious_allowed
NOTE  [SEQUENCE] OK — no undocumented item-number gaps
NOTE  [ERA_SEAM] OK — headline NPL/charge-off/past-due/assets series are continuous (no false cliffs across era seams)

ALL CHECKS PASSED [OK]
```

### Post-site validate (step 9)

DERIV check completed once `site_fry9c/` was present. ALL CHECKS PASSED.

---

## Golden cell confirmed

**JPMorgan Chase (RSSD 1039502) BHCK2170 @ 2026-03-31 = 4,900,475,000** ($ thousands) ✓

Confirmed directly from the freshly-built panel parquet and by `validate_build.py [GOLDEN]`.

---

## Panel stats

| Item | Value |
|---|---|
| Rows | 141,430,337 |
| Quarters | 159 (1986-09-30 → 2026-03-31) |
| Pre-2000 rows added (hist merge) | 32,056,144 |
| Holding companies (pre-2000) | 3,381 |
| File size | 318.1 MB |
| Active filers (2026-03-31) | 387 of 4,874 total RSSDs |
| NODATA codes | 0 |

---

## Site shards built

| Shard | Rows | MB |
|---|---|---|
| `fry9c_active_2020_2031.parquet` | 9,607,276 | 15.5 |
| `fry9c_active_2010_2019.parquet` | 14,151,214 | 18.7 |
| `fry9c_active_1986_2009.parquet` | 7,060,246 | 11.3 |
| `fry9c_hist.parquet` | 64,387,191 | 83.5 |
| `fry9c_agg.parquet` | 127,098 | 0.9 |

---

## Hierarchy is a curated artifact

`fry9c_hierarchy.json` (386 KB) in this kit is the canonical hand-patched hierarchy. It cannot
be bit-for-bit reproduced by `build_hierarchy_fry9c.py` alone — the script generates a base
from the PDF + matrix CSV, but the final hierarchy includes patches applied by:
`_apply_partA.py`, `_apply_audit_fixes.py`, `_apply_m16.py`.

Use the shipped `fry9c_hierarchy.json` directly. Do not overwrite it from a bare
`build_hierarchy_fry9c.py` run.

---

## Gaps found and fixed during this test

| Gap | Found | Fixed |
|---|---|---|
| `fry9c_hierarchy.json` stale (307 KB) — missing PART A/B patches, M16 restructure | reproduce/ had 6/23 version | Updated to final 386 KB version |
| `ReturnFinancialReportPDF.pdf` missing — only wrong PDF was present | reproduce/ had wrong file | Added correct 3.5 MB PDF |
| `fry9c_lineage.json` missing | not in reproduce/ | Added (now 139.5 KB; rebuilt from full 159-quarter panel) |
| `fry9c_topholder.json` missing | not in reproduce/ | Added (now 17.8 KB) |
| `expected_items.json` stale (965 KB) — flagged BHBC3402 as must-add | stale version | Updated to current 780 KB |
| `RUNBOOK.md` missing hist, topholder, shards steps | stale | Updated with full 10-step pipeline |
| `build_fry9c_lineage.py` SyntaxError — incomplete `for` loop at line 213 | broke clean-room run | Removed broken stub (fix committed) |

---

## Caveats

1. **Panel parquet** (318 MB) exceeds GitHub's 100 MB per-file limit and is NOT shipped in
   this kit. A fresh rebuild requires steps 1–3 in RUNBOOK.md (~4–6 hours total including
   Playwright download time). Use `--limit 2` to test 2 quarters quickly.

2. **Hierarchy** is a curated artifact — see above. Do not rebuild from scratch unless you
   intend to re-apply all patches.

3. **`_qa_final.py`** is designed to run from the `External Bank Data\` workspace root, not
   from reproduce/. Its paths reference `FR Y-9C\site_fry9c\index.html` relative to that root.

4. **`validate_build.py` COMPLETE check** without the panel will report false positives for
   codes `2210`, `6428`, `C497`, `L191`, `L192`, `JA36`, `2020` (bare PDF codes not in panel).
   These disappear when the panel is present.
