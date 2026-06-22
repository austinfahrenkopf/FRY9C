#!/usr/bin/env python3
"""
download_fry9c_playwright.py  (real-Chrome edition)
================================================================================
Downloads the FREE FR Y-9C bulk quarterly files from the NIC "Financial Data
Download" page, defeating its Akamai/WAF bot wall by driving your REAL installed
Google Chrome (headed, persistent profile, automation flags hidden) and doing the
download as an in-page fetch -- the same technique proven out by the FFIEC 002
scrape (download_ffiec002_playwright.py).

  source page : https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload
  endpoint    : /npw/FinancialReport/ReturnBHCFZipFiles?zipfilename=BHCF<YYYYMMDD>.ZIP
  writes      : ./fry9c_zips/BHCF<YYYYMMDD>.ZIP   (one zip per quarter)

Each BHCF zip holds a caret(^)-delimited .TXT, one row per holding company,
columns = MDRM codes (BHCK2170 total assets, BHCK2122 loans, ...). It carries
FR Y-9C + Y-9LP + Y-9SP items in one row; build_fry9c_panel.py keeps the BH****
(Y-9C) columns.

--------------------------------------------------------------------------------
SETUP (once):
  pip install playwright
  playwright install chrome      # or have Google Chrome installed (channel=chrome)

RUN:
  python download_fry9c_playwright.py --limit 2     # TEST: newest 2 quarters only
  python download_fry9c_playwright.py               # full pull 2001Q1 -> latest
  python download_fry9c_playwright.py --start 2015  # only 2015 onward

  then:  python build_fry9c_panel.py
         python make_site_fry9c.py

NOTES:
  * A visible Chrome window opens and stays open the whole run -- that is what
    keeps the WAF happy. Don't close it; you can keep working in other windows.
  * Resumable: stop anytime (Ctrl-C) and re-run; it skips zips already saved.
  * Newest quarter first, so useful data lands immediately. Quarters that aren't
    published yet simply log as "not available" and are skipped.
  * If you don't have Google Chrome, add --chromium to use bundled Chromium
    (less reliable against Akamai, but try it).
================================================================================
"""
from __future__ import annotations
import argparse, base64, random, sys, time
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path("./fry9c_zips")
PROFILE = "./.pw_profile"                       # reuse a persistent Chrome profile
HOME    = "https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload"
SLEEP   = 0.6

# In-page fetch: returns {status, b64} where b64 is the base64 of the zip bytes.
FETCH_JS = """
async (fname) => {
  const url = `/npw/FinancialReport/ReturnBHCFZipFiles?zipfilename=${fname}`;
  try {
    const r = await fetch(url, {headers:{'Accept':'application/zip,application/octet-stream,*/*'}});
    const buf = await r.arrayBuffer();
    const b = new Uint8Array(buf);
    // base64 encode in chunks (avoid call-stack limits on big files)
    let bin = ''; const C = 0x8000;
    for (let i=0; i<b.length; i+=C) bin += String.fromCharCode.apply(null, b.subarray(i, i+C));
    const ct = r.headers.get('content-type') || '';
    const isZip = b.length>3 && b[0]===0x50 && b[1]===0x4B;   // 'PK'
    return {status:r.status, ct, len:b.length, isZip, b64: isZip ? btoa(bin) : ''};
  } catch (e) { return {status:-1, ct:'', len:0, isZip:false, b64:'', err:String(e)}; }
}
"""

def quarter_dates(start_year: int):
    """All quarter-end YYYYMMDD strings from start_year-Q1 up to the last
    completed quarter, newest first."""
    today = date.today()
    qs = []
    for y in range(start_year, today.year + 1):
        for mm, dd in (("03", "31"), ("06", "30"), ("09", "30"), ("12", "31")):
            qe = date(y, int(mm), int(dd))
            if qe <= today:                      # only quarters that have ended
                qs.append(f"{y}{mm}{dd}")
    qs.sort(reverse=True)                         # newest first
    return qs

def warmup(pg):
    pg.goto(HOME, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(5000)
    pg.mouse.move(300, 300); pg.mouse.move(700, 500)
    pg.wait_for_timeout(1500)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2001, help="first year to fetch (default 2001)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N quarters (test)")
    ap.add_argument("--chromium", action="store_true", help="use bundled Chromium")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    dates = quarter_dates(args.start)
    if args.limit:
        dates = dates[:args.limit]
    print(f"{len(dates)} quarters to try -> {OUT_DIR}/  (newest first)"
          + (f"  [TEST limit={args.limit}]" if args.limit else ""))

    got = skipped = missed = 0
    with sync_playwright() as p:
        kw = dict(user_data_dir=PROFILE, headless=False,
                  accept_downloads=True,
                  args=["--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"],
                  viewport={"width": 1320, "height": 900})
        if not args.chromium:
            kw["channel"] = "chrome"
        try:
            ctx = p.chromium.launch_persistent_context(**kw)
        except Exception as e:
            sys.exit(f"Could not launch Chrome ({e}).\nTry: python download_fry9c_playwright.py --chromium")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("Warming up NIC session (clearing the bot check)...")
        warmup(pg)

        for i, dt in enumerate(dates, 1):
            fname = f"BHCF{dt}.ZIP"
            out = OUT_DIR / fname
            if out.exists() and out.stat().st_size > 1000:
                skipped += 1
                continue

            res = None
            for attempt in range(1, 4):
                res = pg.evaluate(FETCH_JS, fname)
                st = res.get("status")
                if st == 200 and res.get("isZip"):
                    break
                if st == 200:                      # 200 but not a zip = not published
                    break
                if st in (403, 429):
                    print(f"  HTTP {st} on {fname} -- re-warming (attempt {attempt})")
                    pg.wait_for_timeout(int(1500 * attempt + random.random() * 800))
                    warmup(pg); continue
                break                              # 404 / other

            if res and res.get("isZip") and res.get("b64"):
                out.write_bytes(base64.b64decode(res["b64"]))
                got += 1
                print(f"  saved {fname}  ({res['len']:,} bytes)")
            else:
                missed += 1
                print(f"  -- {fname}: not available (status={res.get('status') if res else '?'})")
            time.sleep(SLEEP)

        ctx.close()

    print(f"\nDone. downloaded={got}  already_had={skipped}  not_available={missed}")
    if got or skipped:
        print("Next: python build_fry9c_panel.py")

if __name__ == "__main__":
    main()
