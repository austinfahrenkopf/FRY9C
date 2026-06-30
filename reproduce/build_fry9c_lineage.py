#!/usr/bin/env python3
"""
build_fry9c_lineage.py
================================================================================
Stitches the MULTIPLE RSSDs one institution files under across time (restructurings,
IHC formations, renames, charter changes, mergers) into a single lineage, so the
dashboard can show a continuous history.

WHY: a bank's top-tier US FR Y-9C filer can change RSSD. Proven in our data:
  TD       : 1249196 (TD Bank US Holding Co, 2001->2015Q2) -> 3606542 (TD Group US Holdings, 2015Q3->)
  Barclays : 2938451 (Barclays Delaware Holdings, 2010->2016Q2) -> 5006575 (Barclays US LLC, 2016Q3->)
  UBS      : 4846998 (UBS Americas Holding) has NO prior US top-tier filer -> stands alone (correct).

WHY NOT stop/start alone: scanning every bank's total-assets first/last quarter gives ~15,000
"a bank stops as another of similar size starts" pairs -- almost all coincidental (e.g. FleetBoston
vs John Hancock). The NIC family graph + a name/transformation check is the filter that makes the
signal precise (~58 real lineages).

THE RULE -- link predecessor P -> successor S only when ALL hold:
  1. HANDOFF  : P's last filed quarter is within HANDOFF_Q quarters BEFORE S's first filed quarter
                (one filer stops right as the other starts -- a role handoff, not a parallel merge).
  2. FAMILY   : P and S are connected in the NIC graph within HOPS hops (parent/child control
                RELATIONSHIP or a merger/charter TRANSFORMATION).
  3. IDENTITY : P and S share a brand-name token (after dropping corporate stopwords) OR P->S is a
                direct TRANSFORMATION. Rejects "CIBC USA -> Barclays Group US" type coincidences.
  4. SIZE     : the seam ratio (S.first / P.last) is in [RATIO_LO, RATIO_HI] -- a GENEROUS band, not a
                tight gate. IHC consolidation makes 2-8x jumps normal (kept); but an absurd mismatch
                (Citigroup Holdings $971B -> Citigroup BUSA $2B = 0.002x; Charter National $0.3B ->
                Charter-Michigan $40B = 148x) means identity matched a coincidental same-name relative,
                so it's dropped. Among survivors the CLOSEST size match wins the spine. Kept links with
                a ratio outside [FLAG_LO, FLAG_HI] are flagged so the level step can be eyeballed.
  Chains build transitively (A->B->C), ordered by time.

INPUT  : fry9c_panel_long.parquet (filing spans via duckdb)  OR  fry9c_zips/*.ZIP (fallback)
         fry9c_nic/CSV_TRANSFORMATIONS.ZIP, CSV_RELATIONSHIPS.ZIP, CSV_ATTRIBUTES_{ACTIVE,CLOSED}.ZIP
OUTPUT : fry9c_lineage.json -> { "<rssd>": {lineage_id,label,members:[{rssd,name,first,last,assets}],
                                            splices:[{from,to,quarter}]}, ... }
         every member RSSD maps to the SAME lineage object, so clicking any one resolves the chain.

RUN    : python build_fry9c_lineage.py        # after download_fry9c_nic_playwright.py
================================================================================
"""
from __future__ import annotations
import argparse, glob, json, os, re, sys, zipfile
from collections import defaultdict

NIC = "fry9c_nic"; PANEL = "fry9c_panel_long.parquet"; ZIPS = "fry9c_zips"
OUT = "fry9c_lineage.json"; SPAN_CACHE = "_spans.json"

HANDOFF_Q = 2
HOPS = 2
# Size is used as a GENEROUS sanity band + a review flag, NOT a tight gate. Restructurings (esp.
# IHC formation) change consolidation scope, so a 2-8x seam jump is normal and kept (TD 1.0x,
# BBVA 3.9x, RBC 3.6x, Barclays IHC 7.5x). But an ABSURD mismatch means the identity/family check
# caught a coincidental same-name relative, not a real handoff -- e.g. Citigroup Holdings ($971B)
# -> Citigroup BUSA ($2B) (0.002x), Charter National ($0.3B) -> Charter-Michigan ($40B) (148x).
# So: require the seam ratio in [RATIO_LO, RATIO_HI], pick the closest size match, and FLAG kept
# links outside [0.5, 2.0] so they can be eyeballed.
RATIO_LO, RATIO_HI = 0.1, 8.0
FLAG_LO, FLAG_HI = 0.5, 2.0
STOP = set("FINANCIAL HOLDINGS HOLDING GROUP INC LLC CORP CORPORATION USA US CO COMPANY BANCORP "
           "BANCORPORATION BANCSHARES BANCGROUP NA THE AMERICAS AMERICA BANK NATIONAL OF AND "
           "SERVICES CAPITAL MHC SAVINGS MUTUAL FEDERAL".split())

QEND = ["0331", "0630", "0930", "1231"]
def qadd(q, n):
    t = int(q[:4]) * 4 + QEND.index(q[4:]) + n
    return f"{t//4}{QEND[t%4]}"
def fval(s):
    try: return float(s)
    except: return None

# ---- 1. filing spans: first/last quarter each RSSD reports BHCK2170, with first & last value ----
def spans_from_panel():
    import duckdb
    rows = duckdb.sql(f"""
        SELECT id_rssd::VARCHAR rssd, min(quarter_end) f, max(quarter_end) l,
               arg_min(value, quarter_end) fv, arg_max(value, quarter_end) lv
        FROM read_parquet('{PANEL}')
        WHERE mdrm='BHCK2170' AND value IS NOT NULL GROUP BY 1""").fetchall()
    q = lambda d: str(d).replace("-", "")[:8]
    return {r[0]: {"first": q(r[1]), "last": q(r[2]), "firstval": str(r[3]), "lastval": str(r[4])} for r in rows}

def spans_from_zips():
    spans = {}
    for z in sorted(glob.glob(f"{ZIPS}/*.ZIP")):
        q = re.search(r"(\d{8})", os.path.basename(z)).group(1)
        with zipfile.ZipFile(z) as zf, zf.open(zf.namelist()[0]) as f:
            hdr = [h.strip().strip(b'"').decode() for h in f.readline().rstrip(b"\r\n").split(b"^")]
            if "BHCK2170" not in hdr: continue
            i = hdr.index("BHCK2170")
            for line in f:
                p = line.rstrip(b"\r\n").split(b"^")
                if i >= len(p): continue
                rssd = p[0].strip().strip(b'"').decode(); v = p[i].strip().strip(b'"').decode()
                if not v: continue
                d = spans.setdefault(rssd, {"first": q, "last": q, "firstval": v, "lastval": v})
                if q < d["first"]: d["first"] = q; d["firstval"] = v
                if q > d["last"]:  d["last"] = q; d["lastval"] = v
    return spans

def get_spans():
    if os.path.exists(SPAN_CACHE):
        s = json.load(open(SPAN_CACHE))
        if s and "firstval" in next(iter(s.values())): return s     # cache must have firstval
    try:
        s = spans_from_panel(); src = "panel"
    except Exception as e:
        print(f"  (duckdb/panel unavailable: {e}; scanning zips)"); s = spans_from_zips(); src = "zips"
    json.dump(s, open(SPAN_CACHE, "w"))
    print(f"  filing spans for {len(s)} RSSDs (from {src})")
    return s

# ---- 2. NIC family graph, direct-transformation links, names ----
def _xml(name):
    with zipfile.ZipFile(f"{NIC}/{name}") as zf:
        return zf.read(zf.namelist()[0]).decode("latin-1")

def nic_graph():
    fam = defaultdict(set); tlink = set()
    for m in re.findall(r"<relationship[^>]*>", _xml("CSV_RELATIONSHIPS.ZIP")):
        p = re.search(r'parent="(\d+)"', m); o = re.search(r'offspring="(\d+)"', m)
        if p and o: fam[p.group(1)].add(o.group(1)); fam[o.group(1)].add(p.group(1))
    for m in re.findall(r"<transformation[^>]*>", _xml("CSV_TRANSFORMATIONS.ZIP")):
        a = re.search(r'predecessor="(\d+)"', m); b = re.search(r'successor="(\d+)"', m)
        if a and b:
            fam[a.group(1)].add(b.group(1)); fam[b.group(1)].add(a.group(1)); tlink.add((a.group(1), b.group(1)))
    names = {}
    for z in ("CSV_ATTRIBUTES_ACTIVE.ZIP", "CSV_ATTRIBUTES_CLOSED.ZIP"):
        if not os.path.exists(f"{NIC}/{z}"): continue
        for blk in _xml(z).split("<attributes ")[1:]:
            rid = re.search(r'id_rssd="(\d+)"', blk); nm = re.search(r"<nm_lgl>([^<]*)", blk)
            if rid and nm: names.setdefault(rid.group(1), nm.group(1).strip())
    return fam, tlink, names

# ---- 3. clean-handoff predecessor for filer S ----
def make_tokenizer(names):
    cache = {}
    def toks(r):
        if r not in cache:
            cache[r] = {t for t in re.sub(r"[^A-Z0-9 ]", " ", names.get(r, "").upper()).split()
                        if len(t) > 1 and t not in STOP}
        return cache[r]
    return toks

def seam_ratio(P, S, spans):
    pv, sv = fval(spans[P]["lastval"]), fval(spans[S]["firstval"])
    return (sv / pv) if (pv and sv and pv > 0) else None

def find_pred(S, spans, fam, tlink, toks):
    s = spans[S]; cands = []; seen = {S}; frontier = [S]
    for hop in range(1, HOPS + 1):
        nxt = []
        for a in frontier:
            for y in fam.get(a, ()):
                if y in seen: continue
                seen.add(y); nxt.append(y); sy = spans.get(y)
                if not sy: continue
                if not (qadd(s["first"], -HANDOFF_Q) <= sy["last"] < s["first"]): continue   # handoff timing
                is_tlink = (y, S) in tlink
                name_match = bool(toks(y) & toks(S))
                if not (name_match or is_tlink): continue                                      # identity
                # NAME-ONLY at hop>1: 2-hop paths through large unrelated intermediaries
                # (e.g. IberiaBank, Synovus) generate false positives — require direct family.
                if name_match and not is_tlink and hop > 1: continue
                r = seam_ratio(y, S, spans)
                if r is None or not (RATIO_LO <= r <= RATIO_HI): continue                     # generous size sanity
                cands.append(y)
        frontier = nxt
    if not cands: return None
    import math
    # closest size match at the seam, ties broken toward a direct transformation
    return min(cands, key=lambda y: (abs(math.log(seam_ratio(y, S, spans))), (y, S) not in tlink))

# ---- 4. assemble lineages ----
def build(spans, fam, tlink, names):
    toks = make_tokenizer(names)
    pred = {}
    for S in spans:
        p = find_pred(S, spans, fam, tlink, toks)
        if p: pred[S] = p
    par = {}
    def find(a):
        par.setdefault(a, a)
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for s, p in pred.items(): par[find(s)] = find(p)
    groups = defaultdict(list)
    for r in set(list(pred) + list(pred.values())): groups[find(r)].append(r)
    by_rssd = {}; lineages = []
    for root, members in groups.items():
        members = sorted(members, key=lambda r: spans[r]["first"])
        chain = [{"rssd": r, "name": names.get(r, "?"), "first": spans[r]["first"],
                  "last": spans[r]["last"], "assets": spans[r]["lastval"]} for r in members]
        def splice(s, p):
            r = seam_ratio(p, s, spans)
            return {"from": p, "to": s, "quarter": spans[s]["first"], "ratio": round(r, 2) if r else None,
                    "flag": bool(r and not (FLAG_LO <= r <= FLAG_HI))}    # flag = noticeable level step at the seam
        splices = sorted((splice(s, p) for s, p in pred.items() if find(s) == root), key=lambda x: x["quarter"])
        obj = {"lineage_id": members[-1], "label": names.get(members[-1], members[-1]),
               "members": chain, "splices": splices}
        lineages.append(obj)
        for r in members: by_rssd[r] = obj
    return by_rssd, lineages

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true", help="Force fresh span calculation from panel")
    args = ap.parse_args()
    if args.no_cache and os.path.exists(SPAN_CACHE):
        os.remove(SPAN_CACHE)
        print(f"  (removed {SPAN_CACHE} for fresh rebuild)")
    for z in ("CSV_TRANSFORMATIONS.ZIP", "CSV_RELATIONSHIPS.ZIP"):
        if not os.path.exists(f"{NIC}/{z}"):
            sys.exit(f"missing {NIC}/{z} -- run download_fry9c_nic_playwright.py first")
    print("Loading filing spans...");     spans = get_spans()
    print("Parsing NIC graph...");        fam, tlink, names = nic_graph()
    print("Building lineages...");        by_rssd, lineages = build(spans, fam, tlink, names)
    tmp = OUT + ".tmp"
    json.dump(by_rssd, open(tmp, "w"))
    os.replace(tmp, OUT)
    # Verify the write landed intact
    check = json.load(open(OUT))
    assert len(check) == len(by_rssd), f"atomic-write verify failed: expected {len(by_rssd)} keys, got {len(check)}"
    multi = [l for l in lineages if len(l["members"]) > 1]
    print(f"\nWrote {OUT}: {len(multi)} multi-RSSD lineages covering {len(by_rssd)} RSSDs.")

if __name__ == "__main__":
    main()
