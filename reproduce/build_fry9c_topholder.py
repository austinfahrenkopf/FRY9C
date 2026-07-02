#!/usr/bin/env python3
"""
build_fry9c_topholder.py
Produce fry9c_topholder.json — a per-quarter map of NESTED Y-9C filers that must be EXCLUDED
from the "ALL" aggregate so their consolidated assets aren't double-counted (audit HIGH-1).

A Y-9C filer is "nested" in a quarter if it is itself controlled (directly or transitively,
ctrl_ind=1, relationship active on the quarter-end date) by ANOTHER holding company that ALSO
files a Y-9C that same quarter. Such a sub-holding company's balance sheet is already consolidated
into its parent's Y-9C, so summing both double-counts.

INPUTS (already in this folder, all free public Fed/FFIEC data):
  fry9c_zips/BHCF*.ZIP             the per-quarter NIC BHCF bulk files (filer set via BHCK2170)
  fry9c_nic/CSV_RELATIONSHIPS.ZIP  NIC relationships (XML inside, despite the .ZIP name)

OUTPUT:
  fry9c_topholder.json   {"nested": {"YYYY-MM-DD": [rssd, ...]}, "_meta": {...}}
                         consumed by make_site_fry9c.py (inlined as __NESTED__).

NOTE: empirically the nested set is tiny (≈2 filers / ~$0.05T at 2026Q1) — the ALL total is
~$30.6T of CONSOLIDATED holding-company assets (incl. nonbank + foreign + IHCs of foreign banks),
which legitimately exceeds U.S. domestic commercial-bank assets (~$24-25T). This filter removes the
genuine (small) nesting double-count and future-proofs ALL; it is NOT expected to move ALL to ~$25T.

Run:  python build_fry9c_topholder.py
Setup: pip install pandas
"""
from __future__ import annotations
import os, re, io, json, zipfile

ZIPDIR="fry9c_zips"; NIC="fry9c_nic/CSV_RELATIONSHIPS.ZIP"; OUT="fry9c_topholder.json"
import pandas as pd

def iso(q8):  # 20260331 -> 2026-03-31
    return f"{q8[:4]}-{q8[4:6]}-{q8[6:8]}"

def filers_for_zip(path):
    """Return (quarter_yyyymmdd, set(rssd)) of Y-9C filers (BHCK2170 reported) in one BHCF zip."""
    zf=zipfile.ZipFile(path)
    name=next((n for n in zf.namelist() if n.lower().endswith((".txt",".csv"))), None)
    if not name: return None, set()
    txt=zf.read(name).decode("latin-1","replace")
    sep="^" if txt.count("^")>txt.count("\t") else "\t"
    df=pd.read_csv(io.StringIO(txt), sep=sep, dtype=str, low_memory=False, quoting=3, on_bad_lines="skip")
    df.columns=[c.strip().strip('"') for c in df.columns]
    idc=next((c for c in df.columns if c.upper() in ("RSSD9001","IDRSSD","ID_RSSD")), None)
    if not idc or "BHCK2170" not in df.columns: return None, set()
    rssd=pd.to_numeric(df[idc], errors="coerce")
    ta=pd.to_numeric(df["BHCK2170"], errors="coerce")
    ids=set(int(x) for x in rssd[ta.notna()].dropna().unique())
    # quarter from the file name (BHCF20260331.ZIP) or the date column
    m=re.search(r"(\d{8})", os.path.basename(path))
    q=m.group(1) if m else None
    if q is None:
        dc=next((c for c in df.columns if c.upper()=="RSSD9999"), None)
        if dc is not None and df[dc].notna().any():
            mm=re.search(r"(\d{8})", str(df[dc].dropna().iloc[0]))
            q=mm.group(1) if mm else None
    return q, ids

def load_relationships(path):
    """Parse NIC relationships once: list of (offspring, parent, dt_start, dt_end, ctrl_ind)."""
    raw=zipfile.ZipFile(path).read(zipfile.ZipFile(path).namelist()[0]).decode("latin-1","replace")
    out=[]
    for a,b in re.findall(r'<relationship ([^>]*?)>(.*?)</relationship>', raw, re.S):
        mo=re.search(r'id_rssd_offspring="(\d+)"', a); mp=re.search(r'id_rssd_parent="(\d+)"', a)
        if not mo or not mp: continue
        def tag(k):
            m=re.search('<'+k+r'>(.*?)</'+k+'>', b); return m.group(1).strip() if m else None
        ds=tag("dt_start"); de=tag("dt_end"); ctrl=tag("ctrl_ind")
        ds=int(ds) if ds and ds.isdigit() else 0
        de=int(de) if de and de.isdigit() else 99991231
        out.append((int(mo.group(1)), int(mp.group(1)), ds, de, ctrl=="1"))
    return out

def nested_for_quarter(filers, rels, qd):
    """RSSDs in `filers` that have a transitive controlling ancestor which is also in `filers`."""
    par_of={}
    for off,par,ds,de,ctrl in rels:
        if not ctrl: continue
        if not (ds<=qd<=de): continue
        par_of.setdefault(off,set()).add(par)
    def filer_ancestor(r):
        seen=set(); stk=list(par_of.get(r,()))
        while stk:
            p=stk.pop()
            if p in seen: continue
            seen.add(p)
            if p in filers and p!=r: return True
            stk.extend(par_of.get(p,()))
        return False
    return sorted(r for r in filers if filer_ancestor(r))

def filers_from_panel(panel="fry9c_panel_long.parquet"):
    """Per-quarter Y-9C filer sets straight from the long panel (covers the FULL history,
    1986-Q3 onward — the deep-history extension). A filer is one reporting BHCK2170 that quarter.
    Yields (quarter_yyyymmdd, set(rssd)) oldest-first. Used by --from-panel so the nested map
    covers every quarter the ALL aggregate spans, not just the 2000+ NIC zips."""
    import pandas as _pd
    df=_pd.read_parquet(panel, columns=["quarter_end","id_rssd","mdrm","value"])
    df=df[(df["mdrm"]=="BHCK2170") & df["value"].notna()]
    for q, sub in df.groupby("quarter_end"):
        yield q.replace("-",""), set(int(x) for x in sub["id_rssd"].dropna().unique())


def main():
    import sys
    from_panel = "--from-panel" in sys.argv
    if not os.path.exists(NIC): raise SystemExit(f"missing {NIC}")
    if not from_panel and not os.path.isdir(ZIPDIR): raise SystemExit(f"missing {ZIPDIR}/")
    print("parsing NIC relationships …")
    rels=load_relationships(NIC)
    print(f"  {len(rels):,} relationship rows")
    nested={}; total_excluded=0
    if from_panel:
        print("filer sets from fry9c_panel_long.parquet (full history) …")
        for q, ids in filers_from_panel():
            if not q or not ids: continue
            nl=nested_for_quarter(ids, rels, int(q))
            if nl:
                nested[iso(q)]=nl; total_excluded+=len(nl)
            print(f"  {iso(q)}: {len(ids)} filers, {len(nl)} nested -> excluded")
    else:
      for f in sorted(os.listdir(ZIPDIR)):
        if not f.lower().endswith(".zip"): continue
        q,ids=filers_for_zip(os.path.join(ZIPDIR,f))
        if not q or not ids: print("  skip",f); continue
        nl=nested_for_quarter(ids, rels, int(q))
        if nl:
            nested[iso(q)]=nl; total_excluded+=len(nl)
        print(f"  {iso(q)}: {len(ids)} filers, {len(nl)} nested -> excluded")
    payload={"nested":nested,
             "_meta":{"source":"NIC CSV_RELATIONSHIPS.ZIP (ctrl_ind=1, active on quarter-end) + BHCF filer set",
                      "rule":"exclude a filer controlled (transitively) by another Y-9C filer in the same quarter",
                      "quarters_with_nesting":len(nested),"total_excluded_rows":total_excluded}}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=0)
    os.replace(tmp, OUT)
    json.load(open(OUT, encoding="utf-8"))  # verify readable
    print(f"\nwrote {OUT}: nesting in {len(nested)} quarter(s), {total_excluded} excluded filer-quarters "
          f"(verified, {os.path.getsize(OUT)} bytes)")
    print("Next: python make_site_fry9c.py")

if __name__=="__main__":
    main()
