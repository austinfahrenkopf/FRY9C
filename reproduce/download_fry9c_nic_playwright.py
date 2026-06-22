#!/usr/bin/env python3
"""
download_fry9c_nic_playwright.py  (real-Chrome edition)
================================================================================
Downloads the FREE NIC "institutional" bulk files (entity attributes, ownership
RELATIONSHIPS, and merger/acquisition TRANSFORMATIONS) from the same FFIEC NPW
site we already use for the FR Y-9C financials, defeating the Akamai/WAF bot wall
by driving your REAL installed Google Chrome and doing each download as an
in-page fetch -- identical technique to download_fry9c_playwright.py.

WHY: a single bank's history spans MULTIPLE RSSDs over time (restructurings, IHC
formations, mergers). Example proven in our data: TD's top-tier US filer is
RSSD 1249196 (TD Bank US Holding Company, 2001->2015Q2) then RSSD 3606542
(TD Group US Holdings LLC, 2015Q3->present). The TRANSFORMATIONS + RELATIONSHIPS
tables are what let us stitch those into one continuous lineage.

  source page : https://www.ffiec.gov/npw/FinancialReport/DataDownload
  endpoints   : /npw/FinancialReport/ReturnTransformationZipFile   (~1 MB)
                /npw/FinancialReport/ReturnRelationshipsZipFile
                /npw/FinancialReport/ReturnAttributesActiveZipFile
                /npw/FinancialReport/ReturnAttributesClosedZipFile
  writes      : ./fry9c_nic/<NAME>.ZIP   (one small zip each, compressed CSV)

Each zip holds one CSV. Key columns (see NPW Data Dictionary):
  TRANSFORMATIONS : ID_RSSD_PREDECESSOR, ID_RSSD_SUCCESSOR, D_DT_TRANS (date),
                    TRNSFM_CD (1=charter discontinued/merger, ...), ...
  RELATIONSHIPS   : ID_RSSD_PARENT, ID_RSSD_OFFSPRING, D_DT_START, D_DT_END,
                    PCT_EQUITY, ... (parent/child ownership over time)
  ATTRIBUTES_*    : ID_RSSD, NM_LGL (legal name), D_DT_START, D_DT_END, ENTITY_TYPE,...
--------------------------------------------------------------------------------
SETUP (once):
  pip install playwright
  playwright install chrome      # or have Google Chrome installed (channel=chrome)

RUN:
  python download_fry9c_nic_playwright.py            # grabs all four files
  python download_fry9c_nic_playwright.py --only transformations relationships

  then:  python build_fry9c_lineage.py

NOTES:
  * A visible Chrome window opens and stays open -- that's what keeps the WAF
    happy. Don't close it.
  * Resumable: re-run; it skips files already saved (use --force to refresh).
  * These files are SMALL and refresh in seconds, unlike the quarterly Y-9C zips.
================================================================================
"""
from __future__ import annotations
import argparse, base64, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path("./fry9c_nic")
PROFILE = "./.pw_profile"                       # reuse the SAME persistent profile as the Y-9C pull
HOME    = "https://www.ffiec.gov/npw/FinancialReport/DataDownload"
SLEEP   = 0.8

ENDPOINTS = {                                   # filename -> endpoint path (CSV zip, no query params)
    "CSV_TRANSFORMATIONS.ZIP":     "/npw/FinancialReport/ReturnTransformationZipFile",
    "CSV_RELATIONSHIPS.ZIP":       "/npw/FinancialReport/ReturnRelationshipsZipFile",
    "CSV_ATTRIBUTES_ACTIVE.ZIP":   "/npw/FinancialReport/ReturnAttributesActiveZipFile",
    "CSV_ATTRIBUTES_CLOSED.ZIP":   "/npw/FinancialReport/ReturnAttributesClosedZipFile",
}

# In-page fetch: returns {status, isZip, len, b64}.  Reads the whole (small) zip.
FETCH_JS = """
async (path) => {
  try {
    const r = await fetch(path, {headers:{'Accept':'application/zip,application/octet-stream,*/*'}});
    const buf = await r.arrayBuffer();
    const b = new Uint8Array(buf);
    let bin = ''; const C = 0x8000;
    for (let i=0; i<b.length; i+=C) bin += String.fromCharCode.apply(null, b.subarray(i, i+C));
    const isZip = b.length>3 && b[0]===0x50 && b[1]===0x4B;          // 'PK'
    return {status:r.status, len:b.length, isZip, b64: isZip ? btoa(bin) : ''};
  } catch (e) { return {status:-1, len:0, isZip:false, b64:'', err:String(e)}; }
}
"""

def warmup(pg):
    pg.goto(HOME, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(4000)
    pg.mouse.move(320, 320); pg.mouse.move(680, 520)
    pg.wait_for_timeout(1200)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    help="subset: any of transformations relationships attributes_active attributes_closed")
    ap.add_argument("--force", action="store_true", help="re-download even if the file exists")
    ap.add_argument("--chromium", action="store_true", help="use bundled Chromium")
    args = ap.parse_args()

    want = ENDPOINTS
    if args.only:
        keymap = {"transformations":"CSV_TRANSFORMATIONS.ZIP",
                  "relationships":"CSV_RELATIONSHIPS.ZIP",
                  "attributes_active":"CSV_ATTRIBUTES_ACTIVE.ZIP",
                  "attributes_closed":"CSV_ATTRIBUTES_CLOSED.ZIP"}
        want = {keymap[k]: ENDPOINTS[keymap[k]] for k in args.only if k in keymap}
        if not want:
            sys.exit("nothing selected; --only takes: transformations relationships attributes_active attributes_closed")

    OUT_DIR.mkdir(exist_ok=True)
    print(f"{len(want)} NIC file(s) -> {OUT_DIR}/")

    got = skipped = missed = 0
    with sync_playwright() as p:
        kw = dict(user_data_dir=PROFILE, headless=False, accept_downloads=True,
                  args=["--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"],
                  viewport={"width": 1320, "height": 900})
        if not args.chromium:
            kw["channel"] = "chrome"
        try:
            ctx = p.chromium.launch_persistent_context(**kw)
        except Exception as e:
            sys.exit(f"Could not launch Chrome ({e}).\nTry: python download_fry9c_nic_playwright.py --chromium")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("Warming up NIC session (clearing the bot check)...")
        warmup(pg)

        for fname, path in want.items():
            out = OUT_DIR / fname
            if out.exists() and out.stat().st_size > 1000 and not args.force:
                print(f"  have {fname}  (skip; --force to refresh)"); skipped += 1; continue
            res = None
            for attempt in range(1, 4):
                res = pg.evaluate(FETCH_JS, path)
                if res.get("status") == 200 and res.get("isZip"):
                    break
                print(f"  HTTP {res.get('status')} on {fname} -- re-warming (attempt {attempt})")
                pg.wait_for_timeout(1500 * attempt); warmup(pg)
            if res and res.get("isZip") and res.get("b64"):
                out.write_bytes(base64.b64decode(res["b64"]))
                print(f"  saved {fname}  ({res['len']:,} bytes)"); got += 1
            else:
                print(f"  -- {fname}: FAILED (status={res.get('status') if res else '?'})"); missed += 1
            time.sleep(SLEEP)
        ctx.close()

    print(f"\nDone. downloaded={got}  already_had={skipped}  failed={missed}")
    if got or skipped:
        print("Next: python build_fry9c_lineage.py")

if __name__ == "__main__":
    main()
