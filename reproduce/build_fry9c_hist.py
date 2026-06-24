#!/usr/bin/env python3
"""
build_fry9c_hist.py — FR Y-9C deep-history extension via the Chicago Fed BHC Database.
======================================================================================
The NIC bulk endpoint only serves FR Y-9C back to 2000-Q1. The Chicago Fed "Bank
Holding Company Database" hosts the SAME FR Y-9C micro-data, BHCK-coded, back to the
first FR Y-9C report (1986-Q3), as wide CSV files. This script downloads, parses, and
folds the pre-2000 history into our existing long panel.

SOURCE (free, public, NOT Akamai-walled — plain requests + a Chrome UA is sufficient):
  page:  https://www.chicagofed.org/banking/financial-institution-reports/bhc-data
  files: https://www.chicagofed.org/~/media/others/banking/financial-institution-reports/
         bhc-data/bhcf{yy}{mm}.csv          e.g. bhcf8609.csv = 1986-Q3 (Sept 30 1986)
  range (empirically verified 2026-06-24): bhcf8609 (1986-Q3) .. bhcf2103 (2021-Q1).
         8603/8606 -> 404 (don't exist); 2106+ -> 404 (migrated to NIC Aug-2021).

SCHEMA: wide CSV, one row per holding company. rssd9001=id, rssd9999=report date
  (YYYYMMDD), BHCK****/other BH** columns = values ($ thousands). RSSD9017 = legal name.
  Column casing shifts across eras (lowercase rssd9001 pre-~2005, uppercase 2005+); the
  BHCK value columns are uppercase in every era. Handled case-insensitively below.

CONVENTIONS — mirror build_fry9c_panel.py EXACTLY so the histories reconcile:
  * keep MDRM cols matching ^BH[A-Z]{2}[0-9A-Z]{4}$ whose prefix is a Y-9C consolidated
    prefix (drops Y-9SP/parent-only filers);
  * a Y-9C filer is one reporting consolidated total assets (BHCK2170) that quarter;
  * NULL-vs-ABSENT discipline: melt then drop NaN values. An empty CSV cell -> a GAP
    (no row), never a fabricated 0. A literal "0" is a real reported zero -> kept.

SUBCOMMANDS:
  python build_fry9c_hist.py download                 # download+parse 1986Q3..2009Q4 -> parts/
  python build_fry9c_hist.py download --end 2009      # (default end year = 2009; covers gap+overlap)
  python build_fry9c_hist.py validate                 # cross-check 2000-2009 parts vs NIC panel
  python build_fry9c_hist.py merge                     # append pre-2000 parts into the long panel

Resumable: per-quarter parquet parts in fry9c_hist_parts/; re-running skips finished quarters.
Setup: pip install pandas pyarrow requests duckdb
"""
from __future__ import annotations
import argparse, io, json, os, re, sys, time
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)

UA   = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
BASE = ("https://www.chicagofed.org/~/media/others/banking/"
        "financial-institution-reports/bhc-data/bhcf{}.csv")

CSV_DIR   = "fry9c_hist_csv"        # raw downloaded CSVs (cache)
PARTS_DIR = "fry9c_hist_parts"      # per-quarter long parquet parts
ROSTER    = "fry9c_hist_roster.csv"
PANEL     = "fry9c_panel_long.parquet"
HIST_LONG = "fry9c_hist_cf_long.parquet"

MDRM       = re.compile(r"^BH[A-Z]{2}[0-9A-Z]{4}$")
Y9C_PREFIX = {"BHCK", "BHDM", "BHFN", "BHCA", "BHCW", "BHBC", "BHOD"}
ID_COLS    = ["RSSD9001", "IDRSSD", "ID_RSSD"]
DATE_COLS  = ["RSSD9999"]
NAME_COLS  = ["RSSD9017", "RSSD9010", "TEXT9017"]

FIRST_TAG  = (1986, 9)   # bhcf8609 — earliest FR Y-9C report (1986-Q3)


def pick(cols, opts):
    up = {c.upper(): c for c in cols}
    for o in opts:
        if o.upper() in up:
            return up[o.upper()]
    return None


def quarter_tags(start=(1986, 9), end_year=2009):
    """Yield (tag, quarter_end_iso) from start (YYYY, MM) through end_year-Q4, oldest first.
    tag is the bhcf file suffix yymm."""
    out = []
    for y in range(start[0], end_year + 1):
        for mm, dd in (("03", "31"), ("06", "30"), ("09", "30"), ("12", "31")):
            if (y, int(mm)) < (start[0], start[1]):
                continue
            out.append((f"{y % 100:02d}{mm}", f"{y}-{mm}-{dd}"))
    return out


def _clean_name(s):
    s = ("" if s is None else str(s)).strip().strip('"').strip()
    if s and set(s) <= set("-"):   # '--------' placeholder => unknown
        return ""
    return s


def parse_csv(raw: bytes, qend: str):
    """Wide Chicago bhcf CSV bytes -> (long_df[quarter_end,id_rssd,mdrm,value], roster{id:name}).
    Returns (None, {}) if the file isn't a usable Y-9C table."""
    df = pd.read_csv(io.BytesIO(raw), dtype=str, low_memory=False, encoding="latin-1",
                     on_bad_lines="skip")
    df.columns = [c.strip().strip('"') for c in df.columns]
    idc = pick(df.columns, ID_COLS); nmc = pick(df.columns, NAME_COLS)
    if not idc or "BHCK2170" not in {c.upper() for c in df.columns}:
        return None, {}
    # resolve the actual-cased BHCK2170 column
    ta_col = pick(df.columns, ["BHCK2170"])
    mcols = [c for c in df.columns if MDRM.match(c.upper()) and c.upper()[:4] in Y9C_PREFIX]
    if not mcols:
        return None, {}
    df[idc] = pd.to_numeric(df[idc], errors="coerce").astype("Int64")
    ta = pd.to_numeric(df[ta_col], errors="coerce")
    y9c_ids = set(int(x) for x in df[idc][ta.notna()].dropna().unique())
    if not y9c_ids:
        return None, {}
    sub = df[df[idc].isin(y9c_ids)].copy()
    roster = {}
    if nmc:
        for r in sub[[idc, nmc]].dropna(subset=[idc]).itertuples(index=False):
            nm = _clean_name(r[1])
            if nm:
                roster[int(r[0])] = nm
    long = sub.melt(id_vars=[idc], value_vars=mcols, var_name="mdrm", value_name="value")
    long["mdrm"] = long["mdrm"].str.upper()
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long[long["value"].notna()]                       # NULL-vs-ABSENT: drop gaps, keep real 0s
    long = long.rename(columns={idc: "id_rssd"})
    long["quarter_end"] = qend
    return long[["quarter_end", "id_rssd", "mdrm", "value"]], roster


def cmd_download(args):
    os.makedirs(CSV_DIR, exist_ok=True); os.makedirs(PARTS_DIR, exist_ok=True)
    tags = quarter_tags(FIRST_TAG, args.end)
    print(f"Chicago Fed BHC pull: {len(tags)} quarters {tags[0][1]} .. {tags[-1][1]}  (oldest first)")
    roster = {}
    if os.path.exists(ROSTER):
        for r in pd.read_csv(ROSTER, dtype=str).itertuples(index=False):
            roster[int(r[0])] = str(r[1])
    got = skip = miss = 0
    for tag, qend in tags:
        part = os.path.join(PARTS_DIR, f"bhcf{tag}.parquet")
        if os.path.exists(part):
            skip += 1
            # still fold its roster contribution if we have the csv cached and roster is empty
            continue
        csv_path = os.path.join(CSV_DIR, f"bhcf{tag}.csv")
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 100_000:
            raw = open(csv_path, "rb").read()
        else:
            url = BASE.format(tag)
            try:
                r = requests.get(url, headers=UA, timeout=300)
            except Exception as e:
                print(f"  bhcf{tag} ({qend}): ERROR {e}"); time.sleep(1.0); continue
            ct = r.headers.get("content-type", "").lower()
            if r.status_code != 200 or "csv" not in ct:
                print(f"  bhcf{tag} ({qend}): not available (HTTP {r.status_code}, ct={ct[:20]})")
                miss += 1; time.sleep(0.3); continue
            raw = r.content
            open(csv_path, "wb").write(raw)
        try:
            long, ros = parse_csv(raw, qend)
        except Exception as e:
            print(f"  bhcf{tag} ({qend}): parse error {e}"); continue
        if long is None or long.empty:
            print(f"  bhcf{tag} ({qend}): no Y-9C consolidated rows"); miss += 1; continue
        long.to_parquet(part, index=False, compression="zstd")
        roster.update(ros)
        got += 1
        print(f"  bhcf{tag} ({qend}): {long['id_rssd'].nunique():,} filers, {len(long):,} values"
              f"  ({long['mdrm'].nunique()} codes)")
        time.sleep(args.sleep)
    if roster:
        pd.DataFrame(sorted(roster.items()), columns=["id_rssd", "institution_name"]).to_csv(ROSTER, index=False)
    print(f"\ndownload done: parsed={got} skipped(existing)={skip} unavailable={miss}")
    print(f"parts in {PARTS_DIR}/  roster -> {ROSTER}")


def _load_parts(lo=None, hi=None):
    """Concat per-quarter parts whose quarter_end is in [lo,hi) (iso strings; None=open)."""
    frames = []
    for f in sorted(os.listdir(PARTS_DIR)):
        if not f.endswith(".parquet"):
            continue
        d = pd.read_parquet(os.path.join(PARTS_DIR, f))
        q = d["quarter_end"].iloc[0]
        if (lo is None or q >= lo) and (hi is None or q < hi):
            frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["quarter_end", "id_rssd", "mdrm", "value"])


def cmd_validate(args):
    """Cross-validate the 2000-2009 overlap: Chicago parts vs the NIC-derived panel, cell by cell."""
    import duckdb
    if not os.path.exists(PANEL):
        sys.exit(f"missing {PANEL}")
    con = duckdb.connect(); con.execute(f"CREATE VIEW nic AS SELECT * FROM '{PANEL}'")
    overlap = [f for f in sorted(os.listdir(PARTS_DIR)) if f.endswith(".parquet")]
    tot_cells = tot_match = tot_only_chi = tot_only_nic = tot_mismatch = 0
    worst = []
    checked_q = 0
    for f in overlap:
        chi = pd.read_parquet(os.path.join(PARTS_DIR, f))
        q = chi["quarter_end"].iloc[0]
        if q < "2000-01-01" or q > "2009-12-31":
            continue
        checked_q += 1
        nic = con.execute("SELECT id_rssd, mdrm, value FROM nic WHERE quarter_end = ?", [q]).df()
        # restrict Chicago to the hierarchy-relevant comparison: same (id,mdrm) keys
        c = chi[["id_rssd", "mdrm", "value"]].rename(columns={"value": "v_chi"})
        n = nic.rename(columns={"value": "v_nic"})
        m = c.merge(n, on=["id_rssd", "mdrm"], how="outer", indicator=True)
        both = m[m["_merge"] == "both"]
        # numeric compare with tolerance for float repr
        diff = (both["v_chi"] - both["v_nic"]).abs()
        rel = diff / both["v_nic"].abs().clip(lower=1)
        match = ((diff <= 1) | (rel <= 1e-6)).sum()
        mism = len(both) - match
        only_chi = (m["_merge"] == "left_only").sum()
        only_nic = (m["_merge"] == "right_only").sum()
        tot_cells += len(both); tot_match += match; tot_mismatch += mism
        tot_only_chi += only_chi; tot_only_nic += only_nic
        mr = match / len(both) * 100 if len(both) else 0
        flag = "" if mr >= 99.5 and mism < 50 else "  <-- CHECK"
        print(f"  {q}: cells={len(both):,} match={mr:.3f}% mismatch={mism:,} "
              f"only_chi={only_chi:,} only_nic={only_nic:,}{flag}")
        if mism:
            ex = both[(diff > 1) & (rel > 1e-6)].head(3)
            for r in ex.itertuples(index=False):
                worst.append(f"    {q} rssd={r.id_rssd} {r.mdrm}: chi={r.v_chi:,.0f} nic={r.v_nic:,.0f}")
    con.close()
    print("\n" + "=" * 60)
    print(f"OVERLAP RECONCILIATION (2000-2009, {checked_q} quarters)")
    overall = tot_match / tot_cells * 100 if tot_cells else 0
    print(f"  common cells: {tot_cells:,}")
    print(f"  matching:     {tot_match:,}  ({overall:.4f}%)")
    print(f"  mismatched:   {tot_mismatch:,}")
    print(f"  only in Chicago: {tot_only_chi:,}   only in NIC: {tot_only_nic:,}")
    if worst:
        print("  sample mismatches:")
        for w in worst[:12]:
            print(w)
    verdict = "RECONCILES" if overall >= 99.5 and tot_mismatch < tot_cells * 0.005 else "DIVERGENCE — REVIEW"
    print(f"  VERDICT: {verdict}")


def cmd_merge(args):
    """Append pre-2000 (1986-Q3 .. 1999-Q4) parts to the long panel. Backs up the panel first."""
    if not os.path.exists(PANEL):
        sys.exit(f"missing {PANEL}")
    pre = _load_parts(lo=None, hi="2000-01-01")
    if pre.empty:
        sys.exit("no pre-2000 parts found — run `download` first")
    # institution_name from hist roster, then fall back to existing panel roster
    roster = {}
    if os.path.exists(ROSTER):
        for r in pd.read_csv(ROSTER, dtype=str).itertuples(index=False):
            roster[int(r[0])] = str(r[1])
    panel = pd.read_parquet(PANEL)
    nic_names = (panel.dropna(subset=["institution_name"])
                 .query("institution_name != ''")
                 .drop_duplicates("id_rssd", keep="last")
                 .set_index("id_rssd")["institution_name"].to_dict())
    pre["institution_name"] = pre["id_rssd"].map(roster)
    pre["institution_name"] = pre["institution_name"].fillna(pre["id_rssd"].map(nic_names)).fillna("")
    pre = pre[["quarter_end", "id_rssd", "institution_name", "mdrm", "value"]]

    before_q = panel["quarter_end"].nunique(); before_rows = len(panel)
    # dedupe safety: drop any pre-2000 rows already present (idempotent re-merge)
    panel = panel[panel["quarter_end"] >= "2000-01-01"]
    merged = pd.concat([pre, panel], ignore_index=True)
    merged = merged.drop_duplicates(subset=["quarter_end", "id_rssd", "mdrm"], keep="last")
    merged = merged.sort_values(["quarter_end", "id_rssd", "mdrm"]).reset_index(drop=True)

    bak = os.path.join("..", "_archive", f"fry9c_panel_long_pre1986merge_{time.strftime('%Y%m%d_%H%M%S')}.parquet")
    os.makedirs(os.path.dirname(bak), exist_ok=True)
    os.replace(PANEL, bak) if args.move_backup else __import__("shutil").copy2(PANEL, bak)
    merged.to_parquet(PANEL, index=False)
    print(f"backup -> {bak}")
    print(f"panel: {before_rows:,} rows / {before_q} quarters  ->  "
          f"{len(merged):,} rows / {merged['quarter_end'].nunique()} quarters "
          f"({merged['quarter_end'].min()} .. {merged['quarter_end'].max()})")
    print(f"pre-2000 rows added: {len(pre):,}  ({pre['id_rssd'].nunique():,} holding companies)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download"); d.add_argument("--end", type=int, default=2009)
    d.add_argument("--sleep", type=float, default=0.3)
    sub.add_parser("validate")
    m = sub.add_parser("merge"); m.add_argument("--move-backup", action="store_true")
    args = ap.parse_args()
    {"download": cmd_download, "validate": cmd_validate, "merge": cmd_merge}[args.cmd](args)


if __name__ == "__main__":
    main()
