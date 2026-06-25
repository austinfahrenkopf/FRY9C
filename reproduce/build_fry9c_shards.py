#!/usr/bin/env python3
"""
build_fry9c_shards.py - Standalone era-shard builder for the FR Y-9C dashboard.

Reads fry9c_panel_long.parquet and writes entity-clustered era parquets into
site_fry9c/, matching the shard naming/splitting logic in make_site_fry9c.py
(so html-only rebuilds will pick them up correctly).

Era buckets (NIC data available from 2000-Q1 onward):
  fry9c_active_2020_2031.parquet  - recent active filers (loaded at startup)
  fry9c_active_2010_2019.parquet  - older active era (lazy-loaded)
  fry9c_active_1990_2009.parquet  - oldest active era, 2000-Q1+ (lazy-loaded)
  fry9c_hist.parquet              - historical/inactive filers (lazy-loaded)
  fry9c_agg.parquet               - ALL pre-aggregated sums (loaded at startup)

Run after build_fry9c_panel.py produces fry9c_panel_long.parquet.
Safe to run while make_site_fry9c.py is being edited by another session -
this writes to site_fry9c/ directly without touching the engine.

Usage:
  python build_fry9c_shards.py          # use default panel path
  python build_fry9c_shards.py --panel fry9c_panel_long.parquet
  python build_fry9c_shards.py --agg-only   # re-build only fry9c_agg.parquet
"""
from __future__ import annotations
import argparse, json, os, sys
import pandas as pd

SRC     = "fry9c_panel_long.parquet"
SITE    = "site_fry9c"
MAXBYTES = 95 * 1024 * 1024   # 95 MB GitHub LFS hard limit
_PQARGS = dict(index=False, compression='zstd', row_group_size=50_000)


def load_display_codes() -> set:
    """Codes the hierarchy actually uses - filter panel to this set before sharding."""
    h_path = "fry9c_hierarchy.json"
    codes: set = {"BHCK2122", "BHCK2170", "BHCK3210", "BHCK4340", "BHCK3123",
                  "BHDM2122", "BHFN2122"}
    if os.path.exists(h_path):
        H = json.load(open(h_path, encoding="utf-8"))
        for items in H.values():
            for it in items:
                c = it.get("mdrm")
                if c:
                    codes.add(c)
    return codes


def load_topholder_exclusions() -> list[tuple[str, int]]:
    """Nested sub-holding-company exclusions for the ALL aggregate."""
    tp_path = "fry9c_topholder.json"
    if not os.path.exists(tp_path):
        return []
    nm = json.load(open(tp_path))
    ne = nm.get("nested", nm)
    return [(q, int(r)) for q, rs in ne.items() for r in rs]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=SRC)
    ap.add_argument("--agg-only", action="store_true",
                    help="Rebuild only fry9c_agg.parquet (fast)")
    args = ap.parse_args()

    os.makedirs(SITE, exist_ok=True)

    print(f"Loading {args.panel} -")
    df = pd.read_parquet(args.panel)
    keep = [c for c in ["quarter_end","id_rssd","institution_name","mdrm","value"]
            if c in df.columns]
    df = df[keep]
    print(f"  {len(df):,} rows  |  {df['id_rssd'].nunique():,} entities  |  "
          f"{df['quarter_end'].nunique()} quarters  "
          f"({df['quarter_end'].min()} - {df['quarter_end'].max()})")

    # Filter to hierarchy display codes only
    disp = load_display_codes()
    if disp:
        before = len(df)
        df = df[df["mdrm"].isin(disp)].reset_index(drop=True)
        print(f"  display-code filter: {before:,} - {len(df):,} rows ({len(disp)} codes)")

    # Active vs historical split
    _max_q = df["quarter_end"].max()
    active_rssds = set(int(x) for x in df.loc[df["quarter_end"] == _max_q, "id_rssd"].unique())
    print(f"  active filers ({_max_q}): {len(active_rssds):,}")

    # Sort for entity-clustering (DuckDB range-request pruning)
    df = df.sort_values(["id_rssd", "mdrm", "quarter_end"]).reset_index(drop=True)

    df_active = df[df["id_rssd"].isin(active_rssds)].reset_index(drop=True)
    df_hist   = df[~df["id_rssd"].isin(active_rssds)].reset_index(drop=True)
    print(f"  df_active: {len(df_active):,} rows  |  df_hist: {len(df_hist):,} rows")

    if args.agg_only:
        _write_agg(df, active_rssds)
        return

    # -- Era shards (active filers only) --------------------------------------
    yr_a = df_active["quarter_end"].str[:4].astype(int)
    era_buckets = [
        (2020, 2031, True),    # recent - loaded at startup
        (2010, 2019, False),   # mid era - lazy-loaded
        (1986, 2009, False),   # oldest era (Chicago Fed BHC data back to 1986-Q3) - lazy-loaded
    ]
    parts: list[str] = []
    old_active_parts: list[str] = []

    for lo, hi, is_recent in era_buckets:
        sub = df_active[(yr_a >= lo) & (yr_a <= hi)].reset_index(drop=True)
        if sub.empty:
            print(f"  [skip] {lo}-{hi}: no active-filer data")
            continue
        fn = f"fry9c_active_{lo}_{hi}.parquet"
        path = os.path.join(SITE, fn)
        sub.to_parquet(path, **_PQARGS)
        sz = os.path.getsize(path)
        qrange = f"{sub['quarter_end'].min()} - {sub['quarter_end'].max()}"
        print(f"  {fn}: {len(sub):,} rows, {sz/1e6:.1f} MB  ({qrange})")
        if sz > MAXBYTES:
            print(f"    --  EXCEEDS 95 MB - needs sub-splitting before GitHub push")
        if is_recent:
            parts.append(fn)
        else:
            old_active_parts.append(fn)

    # Remove stale era shards with old naming (1990_2009 - 1986_2009 rename)
    stale = [f for f in os.listdir(SITE)
             if f.startswith("fry9c_active_") and f.endswith(".parquet")
             and f not in parts + old_active_parts]
    for stale_fn in stale:
        os.remove(os.path.join(SITE, stale_fn))
        print(f"  removed stale shard: {stale_fn}")

    # -- Historical / inactive shard -------------------------------------------
    if not df_hist.empty:
        fn_h = "fry9c_hist.parquet"
        df_hist.to_parquet(os.path.join(SITE, fn_h), **_PQARGS)
        sz = os.path.getsize(os.path.join(SITE, fn_h))
        print(f"  {fn_h}: {len(df_hist):,} rows, {sz/1e6:.1f} MB  (lazy-loaded on Show merged)")

    # -- ALL pre-aggregated shard ----------------------------------------------
    # Aggregate over the FULL per-quarter filer set (all filers present that quarter, not just the
    # currently-active roster) so the "ALL" total is the TRUE sector total in every era. Nested
    # sub-holding filers are still excluded (de-nested) to avoid the HIGH-1 double-count.
    _write_agg(df, active_rssds)

    print(f"\nDone. Site parquets updated in {SITE}/")
    print("Next: python make_site_fry9c.py --html-only  (to regenerate index.html with new shard list)")


def _write_agg(df_all: pd.DataFrame, active_rssds: set) -> None:
    """Write the ALL pre-aggregated parquet: SUM per mdrm per quarter over EVERY filer present that
    quarter (the true sector total in all eras), with nested sub-holding filers excluded (de-nested)
    so consolidated assets aren't double-counted (audit HIGH-1). active_rssds is unused (kept for the
    call signature) — the aggregate is intentionally the full population, not the active roster."""
    excl = load_topholder_exclusions()
    df_agg_src = df_all
    if excl:
        # Vectorized anti-join (the panel is ~95M rows — a row-wise apply would be hours).
        ex_df = pd.DataFrame(excl, columns=["quarter_end", "id_rssd"]).drop_duplicates()
        ex_df["id_rssd"] = ex_df["id_rssd"].astype("int64")
        ex_df["_drop"] = True
        src = df_agg_src.copy()
        src["id_rssd"] = src["id_rssd"].astype("int64")
        src = src.merge(ex_df, on=["quarter_end", "id_rssd"], how="left")
        df_agg_src = src[src["_drop"].isna()].drop(columns=["_drop"])

    df_agg = (df_agg_src.groupby(["quarter_end", "mdrm"], as_index=False)["value"]
              .sum().sort_values(["mdrm", "quarter_end"]).reset_index(drop=True))
    fn_agg = "fry9c_agg.parquet"
    df_agg.to_parquet(os.path.join(SITE, fn_agg),
                      index=False, compression='zstd', row_group_size=10_000)
    sz = os.path.getsize(os.path.join(SITE, fn_agg))
    print(f"  {fn_agg}: {len(df_agg):,} rows, {sz/1e6:.1f} MB  (ALL pre-agg, loaded at startup)")


if __name__ == "__main__":
    main()

