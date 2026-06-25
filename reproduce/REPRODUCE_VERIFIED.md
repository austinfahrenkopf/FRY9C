# FR Y-9C Reproduce Kit — Verification Record

**Date verified:** 2026-06-25 (re-run after pipeline corrections; see §Re-run below)  
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
| 6 | `build_fry9c_topholder.py --from-panel` | `fry9c_topholder.json` (59.6 KB, 159 quarters) | 14 s |
| 7 | `validate_build.py` | ALL CHECKS PASSED (pre-site) | 24 s |
| 8 | `make_site_fry9c.py` | `site_fry9c/` (4,874 filers, 5 shards) | ~30 min |
| 9 | `validate_build.py` | ALL CHECKS PASSED | see below |

---

## Result: ALL CHECKS PASSED

### Post-site validate (step 9)

```
schedules in hierarchy: 36   matrix rows: 668   dict codes: 2984
NOTE  [COMPLETE2] FR Y-9C: all must-add codes from manifest are now present in the hierarchy
NOTE  [MISSING] OK — every active-era code is in the hierarchy or documented (1599 active codes checked)
NOTE  [SPURIOUS] OK — every hierarchy leaf code is reported in the panel or documented in spurious_allowed
NOTE  [SEQUENCE] OK — no undocumented item-number gaps
NOTE  [ERA_SEAM] OK — headline NPL/charge-off/past-due/assets series are continuous (no false cliffs across era seams)

ALL CHECKS PASSED [OK]
```

---

## Golden cell confirmed

**JPMorgan Chase (RSSD 1039502) BHCK2170 @ 2026-03-31 = 4,900,475,000** ($ thousands) ✓

Confirmed directly from the freshly-built panel parquet and implicitly by `validate_build.py [GOLDEN]`
(no NOTE = matched expected value).

---

## ALL-aggregate corrected (key re-run verification)

The full-population ALL aggregate was confirmed correct in the clean-room build:

| Quarter | ALL BHCK2170 (clean-room) | Notes |
|---|---|---|
| 1986-09-30 | **$2,400,663,060 K ≈ $2.40T** | Was $264B with the old `df_active` bug |
| 2026-03-31 | **$30,560,316,000 K ≈ $30.6T** | Current era, matches live dashboard |

The fix is in two places in the pipeline:
1. `build_fry9c_shards.py` `_write_agg`: aggregates over `df_all` (full panel) not `df_active` (current roster).
2. `make_site_fry9c.py` line 142: `df_agg_src=df.copy()` (durability — `--html-only` re-runs also produce correct agg).

De-nesting (excluding nested sub-holding filers via `fry9c_topholder.json`) is still applied to both paths.

---

## Nested-filer exclusion map

| | Prior kit (105-quarter) | This build (159-quarter) |
|---|---|---|
| Topholder command | `build_fry9c_topholder.py` | `build_fry9c_topholder.py --from-panel` |
| Quarters covered | 105 (2000-Q1 to 2026-Q1 only) | 159 (1986-Q3 to 2026-Q1) |
| Excluded filer-quarters | 1,583 | 5,757 |
| Embedded in HTML | 109 RSSDs / 105 quarters | 329 RSSDs / 159 quarters |

`--from-panel` is required for full history coverage. The default mode (no flag) reads only NIC ZIPs
(2000+); the panel-based mode covers every quarter where BHCK2170 is reported.

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
| `fry9c_active_2020_2031.parquet` | 9,607,276 | 16.2 |
| `fry9c_active_2010_2019.parquet` | 14,151,214 | 19.6 |
| `fry9c_active_1986_2009.parquet` | 7,060,246 | 11.8 |
| `fry9c_hist.parquet` | 64,387,191 | 87.6 |
| `fry9c_agg.parquet` | 127,115 | 0.9 |

---

## Hierarchy is a curated artifact

`fry9c_hierarchy.json` (386 KB) in this kit is the canonical hand-patched hierarchy. It cannot
be bit-for-bit reproduced by `build_hierarchy_fry9c.py` alone — the script generates a base
from the PDF + matrix CSV, but the final hierarchy includes patches applied by:
`_apply_partA.py`, `_apply_audit_fixes.py`, `_apply_m16.py`.

Use the shipped `fry9c_hierarchy.json` directly. Do not overwrite it from a bare
`build_hierarchy_fry9c.py` run.

---

## Gaps found and fixed during clean-room rebuilds

| Gap | Session found | Fixed |
|---|---|---|
| `fry9c_hierarchy.json` stale (307 KB) — missing PART A/B patches, M16 restructure | 2026-06-24 | Updated to final 386 KB version |
| `ReturnFinancialReportPDF.pdf` missing — only wrong PDF was present | 2026-06-24 | Added correct 3.5 MB PDF |
| `fry9c_lineage.json` missing | 2026-06-24 | Added (now 139.5 KB; rebuilt from full 159-quarter panel) |
| `fry9c_topholder.json` missing | 2026-06-24 | Added (was 17.8 KB / 105 quarters) |
| `expected_items.json` stale (965 KB) — flagged BHBC3402 as must-add | 2026-06-24 | Updated to current 780 KB |
| `RUNBOOK.md` missing hist, topholder, shards steps | 2026-06-24 | Updated with full 10-step pipeline |
| `build_fry9c_lineage.py` SyntaxError — incomplete `for` loop at line 213 | 2026-06-24 | Removed broken stub (fix committed) |
| `reproduce/fry9c_hierarchy.json` not updated in commit 731585f (HC-D 3.z still present) | 2026-06-25 | Synced from live workspace (7-line removal) |
| `reproduce/fry9c_topholder.json` only covered 105 quarters (NIC ZIPs only) | 2026-06-25 | Rebuilt with `--from-panel` → 159 quarters, 59.6 KB |
| `RUNBOOK.md` step 7 missing `--from-panel` flag | 2026-06-25 | Updated |

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
