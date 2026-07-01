# PORT_DIFF — Y-9C features ported onto FFIEC 002 and Call (first pass)

Date: 2026-06-19. Source of truth = `FR Y-9C\make_site_fry9c.py` (the most advanced clone).
Targets = `FFIEC 002\make_site_002.py`, `FFIEC 031\make_site_call.py`.
Backup before changes: `_archive\20260619_051423\` (and a duplicate `_archive\20260619_051317\`)
holds the prior `make_site_*.py` + full `site_*\` output for all three.

**Status: edits applied via file tools (authoritative). NOT yet rebuilt** — the sandbox cannot run
Python (no pyarrow + no network), and the bash mount serves stale copies of freshly-edited files,
so builds must run in your PowerShell (commands at the bottom). Don't consider this done until you've
rebuilt, loaded each site, and reviewed this list.

---

## Features PORTED (now at parity in all three)

| # | Feature | What it does | 002 change | Call change |
|---|---|---|---|---|
| 1 | **🏆 League table** | New modal: rank every entity by a measure for a chosen quarter, with QoQ / YoY deltas and click-to-sort columns; CSV export. | Added `🏆 League table` button, `#leaguemodal` markup, `LGMEAS`, `perFilerValues()`, `renderLeague()`, `openLeague()`, `lgSortField/lgSortDir`, and init wiring. Ranks **filers** by `id_rssd`. | Same, but ranks **individual banks** (`kind='bank'`) by `entity_id`; labels via `id2lbl`. |
| 2 | **Chart point markers + hover tooltips** | Every data point is a hoverable dot showing `quarter · series: value`. | `pane()` rewritten (adds `<circle class="pt">` + `<title>`); CSS `svg circle.pt:hover{r:5}`. | Same. |
| 3 | **Zero baseline + %-axis anchoring** | $ and % panes anchor to 0; a distinct zero line is drawn whenever the range crosses 0. | In rewritten `pane()`. *(visual only)* | Same. |
| 4 | **Matrix caption prefix-trim** | Repeated matrix rows (e.g. RC-N 30-89 / 90+ / nonaccrual) trim their shared caption prefix so the distinguishing column shows; full caption on hover. | `renderNodes()` builds a `disp` map; `rowEl()` gains a `dispCap` arg + `.cap` span; `.trow` CSS switched to flex with ellipsis. | Same. |
| 5 | **Detachable Entities panel** | "⧉ Detach" floats the Entities panel so Items + Entities are usable at once; draggable; "⧈ Dock" returns it. | Added `#entdetach` button, `entfloat` CSS, `entFloating`, `detachEnts()`, `dockEnts()`, reworked `switchTab()`, drag handler. | Same. |
| 6 | **Popped-rail layout bugfix** | Y-9C fixed `.app.popped` from `0 0 1fr` (which collapsed #main to ~36px) to `1fr`. | CSS fix applied. | CSS fix applied. |
| 7 | **Floating-rail / modal resize** | Floating rail and modals are now freely resizable (fixed height + `overflow:hidden` + `resize:both`, min sizes). | CSS applied. | CSS applied. |
| 8 | **`--html-only` build flag** | Regenerate only `index.html` from the existing site parquet — fast UI iteration without re-reading the big source. | Build script wrapped. | Build script wrapped. |

---

## Features DEFERRED (not ported — by design)

- **RSSD predecessor lineage / "Link predecessor RSSDs" + chart splice markers.** Y-9C embeds
  `fry9c_lineage.json`. There is **no lineage file for 002 or Call**, so the feature would be inert;
  and Call's pre-computed `entity_id` tool-dataset model is structurally incompatible with per-RSSD
  predecessor stitching without rebuilding the dataset. Revisit if/when lineage files are built.
- **Clickable grouping/total tree rows → chart sum of descendants (Y-9C `header` nodes / `SUB:`/
  `DYN`, nested `SEC:` sub-sections).** Depends on Y-9C-style hierarchies that carry `header` rows;
  002/Call hierarchies are flat per schedule, so there's nothing to hang it on yet.
- **Call ROA/ROE/net-income in the league.** Net income is `RIAD`-prefixed and does not resolve
  through the `COMB/RCFD/RCON` coalesce these dashboards use, so those measures were left out of
  Call's league to avoid empty columns. This is the same income/aggregation area you're auditing.

---

## ⚠️ Flags for the aggregation audit (per your steering note)

Corrected Y-9C aggregation is coming, so anything below must be reconciled across all three later:

1. **League `perFilerValues()` (002 + Call).** Reuses the **same `coalesce()` + sum-then-divide ratio
   logic** as `seriesFor()`. Each league row is a **single entity** (no cross-entity sum), but the
   ratio/coalesce pattern is the engine logic under review — kept **structurally identical** to Y-9C
   so your fix drops in uniformly.
2. **Pre-existing aggregation untouched.** I did **not** change 002/Call's existing `ALL` / type /
   size-bucket / peer summation in `seriesFor()` (the "double-count nested entities" and "summed raw
   % cells" issues you flagged). Those remain as they were and should be corrected in the same pass.
3. **%-axis change is visual only** (anchoring to 0 / zero line) — no effect on computed values.

---

## Rebuild + verify (run in PowerShell — uses `;`, not `&&`)

```powershell
# FFIEC 002
cd "C:\Users\Austin Fahrenkopf\Desktop\Claude\External Bank Data\FFIEC 002"
python make_site_002.py
cd site_002 ; python -m http.server 8002    # open http://localhost:8002 ; Ctrl+C to stop

# Call reports (031/041/051)
cd "C:\Users\Austin Fahrenkopf\Desktop\Claude\External Bank Data\FFIEC 031"
python make_site_call.py
cd site_call ; python -m http.server 8001    # open http://localhost:8001

# FR Y-9C (unchanged this session — rebuild only to confirm parity baseline)
cd "C:\Users\Austin Fahrenkopf\Desktop\Claude\External Bank Data\FR Y-9C"
python make_site_fry9c.py
cd site_fry9c ; python -m http.server 8003   # open http://localhost:8003
```

After `python make_site_002.py` / `make_site_call.py` print `wrote .../index.html`, paste the console
output back. Then in each browser tab spot-check: 🏆 League table opens + sorts; chart dots show
tooltips; ⧉ Detach floats the Entities panel; tree captions trim on matrix rows; pop-out keeps the
chart full-width. Roll back from `_archive\` if anything regresses.
