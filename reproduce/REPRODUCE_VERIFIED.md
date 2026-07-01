# FR Y-9C Reproduce Kit — Verification Record

**Date verified:** 2026-07-01 (re-run against commit `332848c`)
**Environment:** Python 3.12.1 · pandas 3.0.3 · pyarrow 24.0.0 · duckdb 1.5.4 · Windows 11

---

## Test method

Clean-room rebuild in `C:\temp\cr_yc_20260701\` using ONLY the reproduce/ kit files (committed
at `332848c`). Engine: `reproduce/make_site_fry9c.py`. Data: committed `app/*.parquet` shards.
No access to `fry9c_panel_long.parquet` or any other working-dir artifacts during the HTML rebuild.

---

## Result: HTML-ONLY REBUILD PASS (functionally equivalent; known cosmetic differences documented)

```
python make_site_fry9c.py --html-only
Exit code: 0
Output: site_fry9c/index.html  518,123 bytes
```

**Committed `app/index.html`**: 518,029 bytes (built 2026-07-01 07:02 from working dir with full panel)

**Size delta: +94 bytes.** Two known, expected differences:

| Line | Committed | Clean-room rebuild | Reason |
|------|-----------|-------------------|--------|
| 222 (timestamp) | `Built 2026-07-01 07:02` | `Built 2026-07-01 10:25` | Every run stamps current time |
| 275 (EMPTY_CODES) | `new Set([])` | `new Set(["BHBC3368","BHBC3402","BHBC3516","BHBC3519","BHCK4653","BHCK4654","BHCK4663","BHCK4664",...])` | Without `fry9c_panel_long.parquet`, `--html-only` uses only active-era shards; historical-only codes (reported only by defunct BHCs) have no rows in the shards and are correctly flagged as EMPTY. Working-dir build has the full 318 MB panel so all codes are present. |

All other content is identical. EMPTY_CODES affects cosmetic display (codes hidden from picker, not charted) — dashboard queries, hierarchy, aggregation, and all feature logic are unaffected. This is documented behavior for `--html-only` without the full panel.

---

## Validators PASS

### validate_build.py (from working dir — requires full panel for [COMPLETE] check)

```
schedules in hierarchy: 36   matrix rows: 668   dict codes: 2984
NOTE  [COMPLETE2] FR Y-9C: all must-add codes from manifest are now present in the hierarchy
NOTE  [MISSING] OK — every active-era code is in the hierarchy or documented (1599 active codes checked)
NOTE  [SPURIOUS] OK — every hierarchy leaf code is reported in the panel or documented in spurious_allowed
NOTE  [SEQUENCE] OK — no undocumented item-number gaps
NOTE  [ERA_SEAM] OK — headline NPL/charge-off/past-due/assets series are continuous

ALL CHECKS PASSED [OK]
```

### _qa_final.py (from External Bank Data/ workspace root)

23/23 checks PASSED.

### Golden cell confirmed

**JPMorgan Chase (RSSD 1039502) BHCK2170 @ 2026-03-31 = 4,900,475,000** ($ thousands) ✓

---

## Commit `332848c` — features verified in committed engine

All features through §NORMDEN-LEAGUE-FRY9C (2026-07-01) are confirmed present in
`reproduce/make_site_fry9c.py` and the deployed `app/index.html`:

| Feature | Marker | Count |
|---|---|---|
| Denominator dropdown (`#normden`) | `NORM_DEN_LABELS` | 4 occurrences |
| `window._normDenCd` (Playwright) | `window._normDenCd` | present |
| League full measure set (`buildLGMEAS`) | `function buildLGMEAS` | 1 occurrence; 453 options at runtime |
| S_DEP deposits DERIV sum | `'S_DEP'` | 4 occurrences |
| HC-N row 9 `hybrid_sum` | `hybrid_sum` | 18 occurrences |
| `perFilerValues` hybrid branch | `isHybrid` | present |
| Export Builder fidelity (`ebRawCodes`) | `ebRawCodes` | 2 occurrences |
| NESTED topholder (nested-filer exclusion) | `NESTED` | present |
| DYN subtotals (tree-click + league) | `DYN[measCode]` | present |

---

## Data-pipeline scripts — all confirmed committed in reproduce/

| Script | Present | Purpose |
|---|---|---|
| `download_fry9c_playwright.py` | ✓ | Quarterly BHCF ZIP pull via real Chrome (Akamai-safe) |
| `build_fry9c_panel.py` | ✓ | CDR ZIPs → `fry9c_panel_long.parquet` long panel |
| `build_fry9c_hist.py` | ✓ | Chicago Fed 1986–2009 historical extension (download + merge) |
| `download_fry9c_nic_playwright.py` | ✓ | NIC entity data (RSSD relationships, attributes) |
| `build_fry9c_lineage.py` | ✓ | Predecessor/successor chains → `fry9c_lineage.json` |
| `build_fry9c_topholder.py` | ✓ | Top-holder dedup map → `fry9c_topholder.json` (use `--from-panel`) |
| `build_fry9c_dictionary.py` | ✓ | MDRM dictionary from Fed MDRM.zip |
| `build_hierarchy_fry9c.py` | ✓ | Form tree from PDF + matrix CSV + `fry9c_hierarchy_overrides.json` |
| `build_fry9c_shards.py` | ✓ | Internal shard-writing helper (called by make_site_fry9c.py) |
| `_write_site_parquets.py` | ✓ | Internal parquet-write helper |
| `add_missing_codes.py` | ✓ | Utility for adding codes to hierarchy |
| `make_site_fry9c.py` | ✓ | Dashboard builder → `site_fry9c/index.html` + parquets |
| `validate_build.py` | ✓ | Automated QA gate (must pass before any push) |
| `_qa_final.py` | ✓ | Deployed-HTML feature verification (run from workspace root) |
| `_completeness_gate.py` | ✓ | Bidirectional completeness gate |
| `fry9c_hierarchy_overrides.json` | ✓ | Surgical hierarchy patches (mis-nests, captions, force_rows) |

---

## Full data-rebuild path (from scratch — RUNBOOK.md steps)

| Step | Script | Produces | Notes |
|---|---|---|---|
| 1 | `download_fry9c_playwright.py` | `fry9c_zips/` (quarterly BHCF ZIPs) | Real Chrome, Akamai-safe. `--limit 2` to test. |
| 2 | `build_fry9c_panel.py` | `fry9c_panel_long.parquet`, `fry9c_roster.csv` | Long panel; ~19 min |
| 3a | `build_fry9c_hist.py download` | `fry9c_hist_parts/` (Chicago Fed 1986–2009) | ~20 min |
| 3b | `build_fry9c_hist.py merge` | Extends panel back to 1986, 159 quarters | ~2 min |
| 4 | `download_fry9c_nic_playwright.py` | `fry9c_nic/` (entity structure) | ~30 min |
| 5 | `build_fry9c_lineage.py` | `fry9c_lineage.json` (150 multi-RSSD chains) | 4 s |
| 6 | `build_fry9c_topholder.py --from-panel` | `fry9c_topholder.json` (159 quarters) | 14 s — `--from-panel` required for full history |
| 7 | `build_fry9c_dictionary.py` | `fry9c_dictionary.csv` | MDRM titles |
| 8 | `build_hierarchy_fry9c.py` | `fry9c_hierarchy.json` | Uses `fry9c_hierarchy_overrides.json`; see CONTEXT.md |
| 9 | `validate_build.py` | exit 0 = pass | Gate — must pass before site build |
| 10 | `make_site_fry9c.py` | `site_fry9c/index.html` + parquets | `--html-only` to regenerate HTML only |

Typical edit loop (after editing `fry9c_matrix.csv` or overrides): **8 → 9 → 10 --html-only**

---

## Hierarchy — curated artifact, not purely reproducible from scratch

`fry9c_hierarchy.json` (290,962 bytes) is the canonical hand-patched hierarchy. `build_hierarchy_fry9c.py`
generates a base from the PDF + matrix CSV, but the final hierarchy includes patches applied via
`fry9c_hierarchy_overrides.json` (mis-nest fixes, force_rows, caption_fixes). Use the shipped
`fry9c_hierarchy.json` directly. Do not overwrite from a bare `build_hierarchy_fry9c.py` run
without also applying the overrides.

---

## All-time repair log (gaps fixed during prior clean-room rebuilds)

| Gap | Session found | Fixed |
|---|---|---|
| `fry9c_hierarchy.json` stale (307 KB) — missing PART A/B patches, M16 restructure | 2026-06-24 | Updated to final 386→291 KB |
| `ReturnFinancialReportPDF.pdf` missing or wrong | 2026-06-24 | Added correct 3.5 MB PDF |
| `fry9c_lineage.json` missing | 2026-06-24 | Added (123 KB; rebuilt from full 159-quarter panel) |
| `fry9c_topholder.json` missing | 2026-06-24 | Added (61 KB / 159 quarters via `--from-panel`) |
| `expected_items.json` stale | 2026-06-24 | Updated to current version |
| `RUNBOOK.md` missing hist, topholder, shards steps | 2026-06-24 | Updated |
| `build_fry9c_lineage.py` SyntaxError at line 213 | 2026-06-24 | Fixed |
| `reproduce/fry9c_hierarchy.json` not updated (HC-D 3.z still present) | 2026-06-25 | Synced |
| `reproduce/fry9c_topholder.json` only covered 105 quarters | 2026-06-25 | Rebuilt with `--from-panel` |
| `RUNBOOK.md` step 7 missing `--from-panel` flag | 2026-06-25 | Updated |

---

## Caveats

1. **Panel parquet** (318 MB) exceeds GitHub's 100 MB per-file limit — NOT committed. Fresh rebuild
   requires steps 1–3 (~4–6 hours including Playwright download time). Use `--limit 2` to test 2 quarters.

2. **EMPTY_CODES**: `--html-only` without the full panel marks historical-only codes as empty
   (no rows in active-era shards). This changes the committed HTML by ~94 bytes. Cosmetic difference;
   no effect on dashboard data or feature logic.

3. **`_qa_final.py`** is designed to run from `External Bank Data\` workspace root, not from reproduce/.
   Its paths reference `FR Y-9C\site_fry9c\index.html` relative to that root.

4. **`validate_build.py` COMPLETE check** without the panel will report false positives for codes
   `2210`, `6428`, `C497`, `L191`, `L192`, `JA36`, `2020` (bare PDF codes not in panel shards). These
   disappear when the full panel is present.

5. **`FINALIZE.ps1`** in this reproduce/ folder runs from the `External Bank Data\` dev workspace,
   not from a fresh clone of this repo. See the warning at the top of that file. From a fresh clone,
   run steps in RUNBOOK.md directly.
