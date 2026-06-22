#!/usr/bin/env python3
"""
build_fry9c_dictionary.py
Build fry9c_dictionary.csv (mdrm, description) — clean captions for the hierarchy/tree.

SOURCE: the Fed **MDRM master data dictionary** — the SAME source the Call (enrich_call.py)
and FFIEC 002 explorers use, so captions are consistent across all three dashboards:
  https://www.federalreserve.gov/apps/mdrm/pdf/MDRM.zip   (browse: /apps/mdrm/data-dictionary)
This host is NOT Akamai/WAF-guarded, so a plain requests download works (repeatable, no browser).
We parse Mnemonic + Item Code -> Item Name, and keep the BH**** holding-company codes used by
the FR Y-9C (BHCK/BHDM/BHFN/BHCA/BHCW/BHBC/BHOD/BHCT...).

Run:  python build_fry9c_dictionary.py
Then: python build_hierarchy_fry9c.py     # picks up fry9c_dictionary.csv automatically
      python make_site_fry9c.py

Setup: pip install requests pandas
Note:  if a local MDRM.zip is already in this folder it is reused (offline / repeatable).
"""
from __future__ import annotations
import csv, io, os, sys, zipfile
import pandas as pd

URL  = "https://www.federalreserve.gov/apps/mdrm/pdf/MDRM.zip"
UA   = {"User-Agent": "Mozilla/5.0 (research; fry9c dictionary)"}
OUT  = "fry9c_dictionary.csv"
CACHE = "MDRM.zip"
# FR Y-9C consolidated holding-company prefixes (matches build_fry9c_panel.py + hierarchy).
KEEP_PREFIX = ("BHCK", "BHDM", "BHFN", "BHCA", "BHCW", "BHBC", "BHOD", "BHCT", "BHODA")

def get_zip_bytes() -> bytes:
    if os.path.exists(CACHE):
        print("using local", CACHE); return open(CACHE, "rb").read()
    try:
        import requests
        print("downloading Fed MDRM dictionary ...")
        r = requests.get(URL, headers=UA, timeout=180); r.raise_for_status()
        open(CACHE, "wb").write(r.content)           # cache for repeatable / offline reruns
        return r.content
    except Exception as e:
        sys.exit(f"could not download MDRM.zip ({e}).\n"
                 f"Download it manually from {URL} into this folder, then re-run.")

def main():
    content = get_zip_bytes()
    zf = zipfile.ZipFile(io.BytesIO(content))
    member = max((m for m in zf.namelist() if m.lower().endswith(".csv")),
                 key=lambda m: zf.getinfo(m).file_size)
    rows = list(csv.reader(io.StringIO(zf.read(member).decode("latin-1", errors="replace"))))
    hi = next(i for i, row in enumerate(rows) if any(c.strip().lower() == "mnemonic" for c in row))
    hdr = [c.strip() for c in rows[hi]]

    def col(*names):
        for n in names:
            for i, h in enumerate(hdr):
                if h.lower() == n.lower(): return i
        for n in names:
            for i, h in enumerate(hdr):
                if n.lower() in h.lower(): return i
        return None

    ci_mn = col("Mnemonic"); ci_ic = col("Item Code", "Item"); ci_nm = col("Item Name", "Name")
    ci_ed = col("End Date")
    if None in (ci_mn, ci_ic, ci_nm):
        sys.exit("Unexpected MDRM layout (no Mnemonic/Item/Name columns).")

    # keep the most-recent Item Name per code (largest End Date wins)
    best = {}   # code -> (end_date_str, name)
    for row in rows[hi + 1:]:
        if len(row) <= max(ci_mn, ci_ic, ci_nm): continue
        code = (row[ci_mn].strip() + row[ci_ic].strip()).upper()
        if len(code) != 8 or not code.startswith("BH"): continue
        if not code.startswith(KEEP_PREFIX): continue
        nm = row[ci_nm].strip()
        if not nm: continue
        ed = row[ci_ed].strip() if (ci_ed is not None and len(row) > ci_ed) else ""
        cur = best.get(code)
        if cur is None or ed > cur[0]:
            best[code] = (ed, nm)

    if not best:
        sys.exit("No BH**** codes found in MDRM — check the file.")
    out = pd.DataFrame(sorted((c, v[1]) for c, v in best.items()),
                       columns=["mdrm", "description"])
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out):,} BH codes "
          f"({(out['mdrm'].str[:4] == 'BHCK').sum()} BHCK). "
          f"Next: python build_hierarchy_fry9c.py")

if __name__ == "__main__":
    main()
