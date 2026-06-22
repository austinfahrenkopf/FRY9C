#!/usr/bin/env python3
"""
build_fry9c_panel.py
Turn the FREE NIC FR Y-9C bulk files into the long panel the explorer needs.

WHERE TO GET THE DATA (free):
  https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload
  - Product: "Financial Data Download"
  - Report type: FR Y-9C
  - Download each quarter you want. Each is a .ZIP containing a caret (^) delimited .TXT,
    one row per holding company, columns = MDRM codes (BHCK2170, BHCK2122, ...).
  Put the downloaded .zip (or unzipped .txt) files into a folder named:  fry9c_zips/

THEN:  python build_fry9c_panel.py
OUTPUT: fry9c_panel_long.parquet  (quarter_end, id_rssd, institution_name, mdrm, value)
        fry9c_roster.csv

Setup: pip install pandas pyarrow
"""
from __future__ import annotations
import os, re, zipfile, io
import pandas as pd

ZIPDIR="fry9c_zips"; OUT="fry9c_panel_long.parquet"; ROSTER="fry9c_roster.csv"
MDRM=re.compile(r"^BH[A-Z]{2}[0-9A-Z]{4}$")          # BHCK/BHCT/BHDM/BHFN/BHCA/BHCW...
# Y-9C consolidated prefixes only (covers the form + hierarchy + derived ratios):
#   BHCK balance sheet/income · BHDM domestic · BHFN foreign · BHCA/BHCW RC-R capital
#   · BHBC (used in hierarchy) · BHOD other deposits.  Excludes BHSP (Y-9SP), BHCP, etc.
Y9C_PREFIXES={"BHCK","BHDM","BHFN","BHCA","BHCW","BHBC","BHOD"}
NAME_COLS=["RSSD9017","RSSD9010","TEXT9017"]          # try these for the institution name
DATE_COLS=["RSSD9999"]; ID_COLS=["RSSD9001","IDRSSD","ID_RSSD"]

def read_table(raw_bytes):
    txt=raw_bytes.decode("latin-1","replace")
    sep="^" if txt.count("^")>txt.count("\t") else "\t"
    # These files are caret-delimited precisely so values may contain commas/quotes; a stray
    # quote must NOT be treated as a CSV quote char (that caused an "EOF inside string" failure
    # on 2023Q4). quoting=QUOTE_NONE (3) reads every caret-separated field literally.
    return pd.read_csv(io.StringIO(txt), sep=sep, dtype=str, low_memory=False,
                       quoting=3, on_bad_lines="skip")

def iter_files():
    if not os.path.isdir(ZIPDIR):
        raise SystemExit(f"Put the NIC FR Y-9C bulk files in ./{ZIPDIR}/ (zip or txt). See header.")
    for f in sorted(os.listdir(ZIPDIR)):
        p=os.path.join(ZIPDIR,f)
        if f.lower().endswith(".zip"):
            try: zf=zipfile.ZipFile(p)
            except Exception as e: print("  bad zip",f,e); continue
            for n in zf.namelist():
                if n.lower().endswith((".txt",".csv")): yield f+"::"+n, zf.read(n)
        elif f.lower().endswith((".txt",".csv")):
            yield f, open(p,"rb").read()

def pick(cols, opts):
    up={c.upper():c for c in cols}
    for o in opts:
        if o.upper() in up: return up[o.upper()]
    return None

def qend_from(name, df, datecol):
    if datecol is not None and datecol in df.columns:
        v=str(df[datecol].dropna().iloc[0]) if df[datecol].notna().any() else ""
        m=re.search(r"(\d{4})(\d{2})(\d{2})", v)
        if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.search(r"(\d{6})", name)   # YYYYMM
    if m: y,mo=m.group(1)[:4],m.group(1)[4:]; return f"{y}-{mo}-01"
    return None

frames=[]; roster={}
for name, raw in iter_files():
    try: df=read_table(raw)
    except Exception as e: print("  skip",name,e); continue
    df.columns=[c.strip().strip('"') for c in df.columns]
    idc=pick(df.columns, ID_COLS); dtc=pick(df.columns, DATE_COLS); nmc=pick(df.columns, NAME_COLS)
    if not idc: print("  no RSSD9001 in",name); continue
    q=qend_from(name, df, dtc)
    if not q: print("  no date for",name); continue
    # Keep only Y-9C *consolidated* MDRM prefixes. The BHCF bulk file also carries
    # Y-9SP / parent-only filers (BHSP/BHCP/... ~3,300 rows/quarter) which have no
    # consolidated data; those would pollute the panel + entity list, so we drop them.
    mcols=[c for c in df.columns if MDRM.match(c) and c[:4] in Y9C_PREFIXES]
    if not mcols or "BHCK2170" not in df.columns:
        print("  no Y-9C consolidated columns in",name); continue
    df[idc]=pd.to_numeric(df[idc], errors="coerce").astype("Int64")
    # A Y-9C filer is one that reports consolidated total assets (BHCK2170) this quarter.
    ta=pd.to_numeric(df["BHCK2170"], errors="coerce")
    y9c_ids=set(int(x) for x in df[idc][ta.notna()].dropna().unique())
    if not y9c_ids: print("  0 Y-9C filers in",name); continue
    sub=df[df[idc].isin(y9c_ids)]
    if nmc:
        for r in sub[[idc,nmc]].dropna(subset=[idc]).itertuples(index=False):
            roster[int(r[0])]=str(r[1]).strip().strip('"').strip()   # QUOTE_NONE keeps quotes
    long=sub.melt(id_vars=[idc], value_vars=mcols, var_name="mdrm", value_name="value")
    long["value"]=pd.to_numeric(long["value"], errors="coerce")
    long=long[long["value"].notna()]
    long=long.rename(columns={idc:"id_rssd"}); long["quarter_end"]=q
    frames.append(long[["quarter_end","id_rssd","mdrm","value"]])
    print(f"  {q}: {len(y9c_ids)} Y-9C filers, {len(long):,} values  ({name})")

if not frames: raise SystemExit("No data parsed — check fry9c_zips/ contents.")
panel=pd.concat(frames, ignore_index=True)
panel["institution_name"]=panel["id_rssd"].map(roster).fillna("")
panel=panel[["quarter_end","id_rssd","institution_name","mdrm","value"]].sort_values(["quarter_end","id_rssd","mdrm"])
panel.to_parquet(OUT, index=False)
pd.DataFrame([(k,v) for k,v in sorted(roster.items())], columns=["id_rssd","institution_name"]).to_csv(ROSTER, index=False)
print(f"\nwrote {OUT}: {len(panel):,} rows, {panel['id_rssd'].nunique()} holding companies, "
      f"{panel['quarter_end'].nunique()} quarters")
print(f"wrote {ROSTER}. Next:  python make_site_fry9c.py")
