#!/usr/bin/env python3
"""
build_hierarchy_fry9c.py  —  SAFE HYBRID hierarchy builder
================================================================================
Builds fry9c_hierarchy.json: an ordered, drill-downable tree of every FR Y-9C
schedule, used by make_site_fry9c.py.

DESIGN (read this before editing):
  1. BACKBONE  — default-mode PDF text extraction gives reliable (code, item#,
     caption) rows. This is authoritative and NEVER dropped, so grand totals
     (BHCK2170 etc.) and every code/prefix are always correct.
  2. ENRICH    — layout-mode extraction (which preserves indentation + order +
     "Part/Memoranda" section markers) is used ONLY to ADD value, never to
     remove it:
        a. add data rows the backbone missed (codes present in layout, absent
           from the backbone — e.g. HI-C 1.a/3/6),
        b. recover captions for parent/sub-total headings,
        c. split Part II / Memoranda into their own tree sections.
     Because enrichment is additive, it can never drop a code or a total.
  3. OVERRIDES — fry9c_hierarchy_overrides.json (optional, hand-maintained) is a
     tiny curated layer for the rare cases heuristics can't get right. A future
     editor adds entries here instead of touching parser internals. See
     write_overrides_template() for the format.
  4. SELF-TEST — after building, the script compares the hierarchy's codes to the
     codes ACTUALLY REPORTED in fry9c_panel_long.parquet and writes
     fry9c_hierarchy_validation.txt listing any "reported-but-unmapped" codes.
     When a new quarter/PDF adds attributes, this report tells the next editor
     exactly what to add (to the PDF parse or to the overrides file).

Run:  python build_fry9c_dictionary.py     (optional, nicer captions)
      python build_hierarchy_fry9c.py
Setup: pip install pypdf pandas pyarrow
"""
from __future__ import annotations
import csv, json, re, os
import pypdf

PDF="ReturnFinancialReportPDF.pdf"; DICT="fry9c_dictionary.csv"
OVERRIDES="fry9c_hierarchy_overrides.json"; PANEL="fry9c_panel_long.parquet"
OUT=os.environ.get("FRY9C_HIER_OUT","fry9c_hierarchy.json")
VALID="fry9c_hierarchy_validation.txt"

PREFS=("BHCK","BHDM","BHFN","BHCA","BHCW","BHBC","BHOD")
# Match a real schedule HEADER, not a body reference. The header is "Schedule X—Title" with an
# EM/EN-dash; body references are "Schedule HC, item 12" or column labels "Totals From Schedule HC"
# (no dash). Requiring the dash stops HC-R Part II pages (whose column A reads "...Schedule HC") and
# HC-E pages from being misfiled as HC / HC-D. Continuation pages (no header) carry forward the last one.
SCHED=re.compile(r'Schedule\s+(H[ICR]?-?[A-Z0-9]*)\s*[—–]', re.I)
NOTES=re.compile(r'Notes to the (Balance Sheet|Income Statement)', re.I)  # optional free-text pages (14-16,72-73)
DCODE=re.compile(r'^(?=.*\d)[0-9A-Z]{4}$')                     # 4-char code w/ a digit
PREF=re.compile(r'^BH[A-Z]{2}$')
DITEM=re.compile(r'^\d+(?:\.[a-z0-9]+|\([0-9a-z]+\))*\.?$')    # trailing item-number token
MCODE=re.compile(r'^(?=.*[0-9])[0-9A-Z]{4}$')
TOK=re.compile(r'^(\(?(?:\d+|[a-z])\)?)\.?\s+(\S.*)?$')        # leading token: 1.  a.  (1)  (a)
LEAD=re.compile(r'^(?:\(\w+\)|\d+\.|[a-z]\.)\s*')
SECMARK=re.compile(r'^(Part\s+[IVX]+\.|Memoranda\b)', re.I)

# ---- MATRIX SCHEDULES (curated from the form) ----------------------------------
# Some schedules are a matrix: each ROW carries data in several fixed COLUMNS (e.g. HC-N
# past-due 30-89 / 90+ / nonaccrual). pypdf cannot extract these reliably, so they are
# transcribed in fry9c_matrix.csv and read here — authoritative, and easy for a future editor
# to extend (read the form page, add rows). MATRIX_COLS = column labels per schedule (A,B,C).
MATRIX_FILE="fry9c_matrix.csv"
MATRIX_COLS={
  "HC-N":["Past due 30 through 89 days and still accruing",
          "Past due 90 days or more and still accruing",
          "Nonaccrual"],
  "HI-B":["Charge-offs","Recoveries"],
  "HI-B — Part II (Allowance Changes)":["Loans and leases held for investment",
          "Held-to-maturity debt securities","Available-for-sale debt securities"],
  "HC-C":[["Consolidated","BHCK"],["In domestic offices","BHDM"]],
  "HC-V":["Securitization vehicles","Other VIEs"],
  "HI-C":["Amortized cost","Allowance balance"],
  "HC-B":["Held-to-maturity — Amortized cost","Held-to-maturity — Fair value",
          "Available-for-sale — Amortized cost","Available-for-sale — Fair value"],
  "HC-Q":["Total fair value (Schedule HC)","LESS: Amounts netted","Level 1 fair value",
          "Level 2 fair value","Level 3 fair value"],
  "HC-S":["1-4 family residential loans","Home equity lines","Credit card receivables",
          "Auto loans","Other consumer loans","Commercial and industrial loans",
          "All other loans, all leases, and all other assets"],
}
def load_matrix():
    rows={}
    if not os.path.exists(MATRIX_FILE): return rows
    lines=[c for c in open(MATRIX_FILE, encoding="utf-8") if not c.lstrip().startswith("#")]
    for r in csv.DictReader(lines):
        if (r.get("schedule") or "").strip(): rows.setdefault(r["schedule"].strip(), []).append(r)
    return rows
def matrix_nodes(sch, curated, caps):
    """Build a matrix schedule from curated rows: ROW (grouping) -> COLUMN leaves.
    MATRIX_COLS entries are either "Label" (prefix auto-detected, BHCK preferred) or
    ["Label","PREFIX"] to pin a column's prefix (e.g. HC-C col B = "BHDM" domestic), since the
    same 4-char code can exist under both BHCK and BHDM. A cell may also be a full 8-char code."""
    raw=MATRIX_COLS.get(sch, ["Column A","Column B","Column C"])
    cols=[(e[0],e[1]) if isinstance(e,(list,tuple)) else (e,None) for e in raw]
    def resolve(code, prefix=None):
        code=(code or "").strip()
        if not code: return ""
        if re.match(r'^BH[A-Z]{2}[0-9A-Z]{4}$', code): return code     # full code supplied
        if prefix and caps.get(prefix+code): return prefix+code        # column's pinned prefix wins
        for p in PREFS:
            if caps.get(p+code): return p+code
        return (prefix or "BHCK")+code
    # Natural item order (1,2,...,9,10,11 — not the lexicographic 1,10,11,2): CSV / transcript-recovery
    # order can scramble rows. Memoranda (M.x) sort after numbered items; empty-item SECTION headers
    # anchor to the row that follows them so they stay at the head of their group.
    def natkey(it):
        key=[]
        for t in re.findall(r'M|\d+|\([0-9a-z]+\)|[a-z]', it or ''):
            if t=='M': key.append((2,0,''))
            elif t.isdigit(): key.append((0,int(t),''))
            elif t.startswith('('):
                inner=t.strip('()'); key.append((0,int(inner),'') if inner.isdigit() else (1,0,inner))
            else: key.append((1,0,t))
        return key
    crows=list(curated); skeys=[]
    for i,rr in enumerate(crows):
        it=(rr.get("item") or "").strip()
        if it: skeys.append((natkey(it),1,i))
        else:
            nxt=next(((crows[j].get("item") or "").strip() for j in range(i+1,len(crows)) if (crows[j].get("item") or "").strip()), "")
            skeys.append((natkey(nxt),0,i))
    crows=[crows[i] for i in sorted(range(len(crows)), key=lambda i:skeys[i])]
    nodes=[]
    for r in crows:
        item=(r.get("item") or "").strip(); cap=(r.get("caption") or "").strip()
        if not item: continue
        is_header=(r.get("header") or "0").strip()=="1"
        # flexible N-column: a pipe-separated 'codes' field overrides colA/B/C (supports 4,5,... columns);
        # a pipe-separated 'labels' field overrides MATRIX_COLS labels for THIS row (heterogeneous schedules
        # like HC-L: 7.a=Sold/Purchased, 7.d=maturity buckets, 11=derivative type, 15=counterparty).
        if (r.get("codes") or "").strip():
            rawc=[c.strip() for c in r["codes"].split("|")]
            codes=[resolve(rawc[i], cols[i][1] if i<len(cols) else None) for i in range(len(rawc))]
        else:
            codes=[resolve(r.get(k), cols[i][1] if i<len(cols) else None) for i,k in enumerate(("colA","colB","colC"))]
        rl=[s.strip() for s in r["labels"].split("|")] if (r.get("labels") or "").strip() else None
        def collabel(i):
            if rl and i<len(rl): return rl[i]
            if i<len(cols): return cols[i][0]
            return "Column "+chr(65+i)
        ncodes=sum(1 for c in codes if c)
        if is_header or ncodes==0:               # grouping row
            nodes.append({"mdrm":"","caption":cap,"item":item,"depth":depth(item),"header":True})
        elif ncodes==1:                          # single-value row -> the row itself is the leaf
            nodes.append({"mdrm":next(c for c in codes if c),"caption":cap,"item":item,
                          "depth":depth(item),"header":False})
        else:                                    # matrix row -> grouping header + column leaves
            nodes.append({"mdrm":"","caption":cap,"item":item,"depth":depth(item),"header":True})
            for i,md in enumerate(codes):
                if md: nodes.append({"mdrm":md,"caption":collabel(i),"item":item+"."+chr(65+i),
                                     "depth":depth(item)+1,"header":False,"col":True})
    return nodes

def natkey(it):
    """Natural item-number sort key: 1<2<...<9<10<11; M.x sorts after numbers; (a)<a."""
    key=[]
    for t in re.findall(r'M|\d+|\([0-9a-z]+\)|[a-z]', it or ''):
        if t=='M': key.append((2,0,''))
        elif t.isdigit(): key.append((0,int(t),''))
        elif t.startswith('('):
            inner=t.strip('()'); key.append((0,int(inner),'') if inner.isdigit() else (1,0,inner))
        else: key.append((1,0,t))
    return key

def comp(t): return t.strip('.').strip()
def depth(it): return max(1, len(re.findall(r'\(\w+\)|\d+|[a-z]', it)))
def lvlcomp(tok):
    t=comp(tok)
    if re.match(r'^\d+$',t): return 0,t
    if re.match(r'^[a-z]$',t): return 1,t
    if re.match(r'^\(\d+\)$',t): return 2,t
    if re.match(r'^\([a-z]\)$',t): return 3,t
    return 0,t
def itemkey(it):
    out=[]
    for p in re.findall(r'\d+|\([0-9a-z]+\)|[a-z]', it):
        if p.isdigit(): out.append((0,int(p),''))
        elif p.startswith('('): inner=p[1:-1]; out.append((1,int(inner) if inner.isdigit() else 0,inner))
        else: out.append((2,0,p))
    return out
def cap_clean(s):
    s=re.sub(r'\s*\.{2,}.*$','',s); s=re.sub(r'(\s+[0-9A-Z]{4}){1,2}\s*$','',s)
    return s.strip().rstrip(':').strip()

def load_caps():
    caps={}
    if os.path.exists(DICT):
        for row in csv.DictReader(open(DICT, encoding="latin-1")):
            m=(row.get("mdrm") or "").strip()
            if m: caps[m]=(row.get("description") or "").strip()
    return caps

def resolve(code, caps, bycode):
    if code in bycode: return bycode[code]            # reliable prefix from backbone
    for p in PREFS:
        if caps.get(p+code): return p+code
    return "BHCK"+code

# ---- 1. BACKBONE: default-mode data nodes (authoritative codes incl. totals) ----
def backbone_nodes(pages, caps):
    nodes=[]; seen=set(); bycode={}
    for t in pages:
        for ln in t.splitlines():
            tk=ln.split()
            if len(tk)<2 or not DITEM.match(tk[-1]): continue
            j=len(tk)-2
            if j<0 or not DCODE.match(tk[j]): continue
            code=tk[j]; pre="BHCK"
            if j-1>=0 and PREF.match(tk[j-1]): pre=tk[j-1]; j-=1
            md=pre+code; bycode.setdefault(code, md)
            if md in seen: continue
            it=tk[-1].rstrip('.')
            cap=caps.get(md)
            if not cap:
                frag=LEAD.sub("", " ".join(tk[:j])); frag=re.sub(r'[.\s]+$',"",frag).strip()
                cap=frag or md
            if it.isdigit() and int(it)>=100: continue   # 3-4 digit "item" = misread code (1913, 750)
            seen.add(md); nodes.append({"item":it,"mdrm":md,"caption":cap,"header":False})
    return nodes, bycode

# ---- 2. LAYOUT info: code->section, code->item (for missing rows), header captions ----
def layout_info(pages, caps, bycode):
    code2sec={}; code2item={}; headers={}; secorder=["main"]
    sec="main"; stack=[]; seenmax=0; rstn=0
    for raw in pages:
        for ln in raw.splitlines():
            if not ln.strip(): continue
            ind=len(ln)-len(ln.lstrip()); s=ln.strip()
            if ind>60: continue
            sm=SECMARK.match(s)
            if sm and 'Continued' not in s and 'item' not in s.lower() and len(s)<72:
                sec=cap_clean(s)
                if sec not in secorder: secorder.append(sec)
                stack=[]; seenmax=0; continue
            if ind<2: continue
            mt=TOK.match(s)
            if not mt: continue
            lvl,c=lvlcomp(mt.group(1))
            # restart: a fresh top-level "1" deep into the schedule signals an UNMARKED
            # sub-section (e.g. HC Memoranda / quarterly averages). Split it so its numbers
            # don't collide with the main section. Additive only — never drops a code.
            if lvl==0 and c=='1' and seenmax>=5:
                rstn+=1; sec="Memoranda" if rstn==1 else f"Supplemental {rstn}"
                if sec not in secorder: secorder.append(sec)
                stack=[]; seenmax=0
            if lvl==0 and c.isdigit(): seenmax=max(seenmax,int(c))
            while stack and stack[-1][0]>=lvl: stack.pop()
            parent='.'.join(x[1] for x in stack)
            it=(parent+'.'+c) if parent else c
            stack.append((lvl,c))
            codes=[x for x in re.findall(r'\b[0-9A-Z]{4}\b', re.sub(r'[.–\-]',' ',s))
                   if MCODE.match(x) and x!='0000']
            if codes:
                for x in codes:
                    md=resolve(x, caps, bycode)
                    code2sec.setdefault(md, sec); code2item.setdefault(md, it)
            else:
                headers.setdefault((sec,it), cap_clean(mt.group(2) or ''))
    return code2sec, code2item, headers, secorder

def build_schedule(sch, dpages, lpages, caps):
    nodes, bycode = backbone_nodes(dpages, caps)
    code2sec, code2item, headers, secorder = layout_info(lpages, caps, bycode)
    have={n["mdrm"] for n in nodes}
    # 2a. ADD rows the backbone missed (present in layout, absent from backbone)
    for md, it in code2item.items():
        if md not in have:
            nodes.append({"item":it,"mdrm":md,"caption":caps.get(md) or md,"header":False})
            have.add(md)
    # assign sections (marker sections only; everything else stays 'main' -> safe, no collisions invented)
    for n in nodes:
        n["section"]=code2sec.get(n["mdrm"],"main")
    groups={}
    for n in nodes: groups.setdefault(n["section"],[]).append(n)
    result={}
    for sec in secorder+[s for s in groups if s not in secorder]:
        g=groups.get(sec)
        if not g: continue
        di={n["item"] for n in g}
        needed=set()
        for it in di:
            p=it.split('.')
            while len(p)>1:
                p=p[:-1]; a='.'.join(p)
                if a not in di: needed.add(a)
        for it in needed:
            cap=headers.get((sec,it)) or headers.get(("main",it)) or ""
            g.append({"item":it,"mdrm":"","caption":cap,"header":True,"section":sec})
        for n in g: n["depth"]=depth(n["item"])
        g.sort(key=lambda n: itemkey(n["item"]))
        key=sch if sec=="main" else f"{sch} — {sec}"
        result[key]=[{"mdrm":n["mdrm"],"caption":n["caption"],"item":n["item"],
                      "depth":n["depth"],"header":n["header"]} for n in g]
    return result

# ---- 3. OVERRIDES (curated, hand-maintained) ----
def write_overrides_template():
    if os.path.exists(OVERRIDES): return
    tmpl={"_README":"Curated fixes applied on top of the parsed hierarchy. Safe for a future "
                    "editor. 'captions' overrides a code's caption. 'force_rows' guarantees a "
                    "row exists under a schedule key. 'drop_codes' removes a misparsed code.",
          "captions":{}, "force_rows":[], "drop_codes":[]}
    json.dump(tmpl, open(OVERRIDES,"w",encoding="utf-8"), indent=2)

def apply_overrides(hier, matrix_keys=frozenset()):
    if not os.path.exists(OVERRIDES): return hier
    try: ov=json.load(open(OVERRIDES,encoding="utf-8"))
    except Exception as e:
        print(f"  WARNING: {OVERRIDES} present but NOT applied (parse error: {e})"); return hier
    caps_ov=ov.get("captions",{}); drop=set(ov.get("drop_codes",[]))
    # drop_items: remove nodes by (schedule key, EXACT item) — the only way to delete a no-mdrm
    # HEADER node (drop_codes only matches by mdrm). Used to re-home a mis-parsed sub-tree: drop the
    # orphan header here, then force_rows re-add the real codes under the correct parent. Format:
    # "drop_items": [{"key":"HC","item":"9.a"}, ...]. Runs BEFORE force_rows so re-adds aren't clobbered.
    drop_items=set((d.get("key"),str(d.get("item"))) for d in ov.get("drop_items",[]) if d.get("key") and d.get("item") is not None)
    for key,rows in hier.items():
        rows[:]=[r for r in rows if r["mdrm"] not in drop and (key,str(r.get("item"))) not in drop_items]
        for r in rows:
            if r["mdrm"] in caps_ov: r["caption"]=caps_ov[r["mdrm"]]
    touched=set()
    for fr in ov.get("force_rows",[]):
        key=fr.get("key");
        if not key: continue
        rows=hier.setdefault(key,[])
        mdrm=fr.get("mdrm","")
        if mdrm:
            # Authoritative: remove existing entry for this mdrm so force_row takes precedence
            rows[:]=[r for r in rows if r.get("mdrm")!=mdrm]
        else:
            # Header-only row: update caption if already present, then skip re-add
            item_=fr.get("item","")
            if item_:
                for r in rows:
                    if r.get("item")==item_ and not r.get("mdrm"):
                        if fr.get("caption"): r["caption"]=fr["caption"]
                        touched.add(key)
                        break
                else:
                    pass  # not found, fall through to append below
                if any(r.get("item")==item_ and not r.get("mdrm") for r in rows):
                    continue
        rows.append({"mdrm":mdrm,"caption":fr.get("caption",""),
                     "item":fr.get("item",""),"depth":fr["depth"] if "depth" in fr else depth(fr.get("item","1")),
                     "header":not bool(mdrm)})
        touched.add(key)
    # Re-sort ALL touched schedule keys using natkey (handles M.x memoranda items correctly and
    # is identical to the validator's sort key). This applies to both PDF-parsed schedules and
    # matrix schedules — matrix_nodes already natkey-sorts CSV rows; re-sorting here just inserts
    # newly-appended force_rows at their correct positions without changing any existing order.
    for key in touched:
        hier[key].sort(key=lambda r: natkey(r.get("item") or ""))
    return hier

# ---- 4. SELF-TEST: hierarchy vs codes actually reported in the panel ----
def completeness_report(hier):
    mapped={r["mdrm"] for rows in hier.values() for r in rows if r["mdrm"]}
    lines=[f"FR Y-9C hierarchy validation",
           f"schedules/sections: {len(hier)}",
           f"mapped codes: {len(mapped)}"]
    if os.path.exists(PANEL):
        try:
            import pandas as pd
            rep=set(pd.read_parquet(PANEL, columns=["mdrm"])["mdrm"].unique())
            display_rep={c for c in rep if c[:4] in PREFS}
            unmapped=sorted(display_rep - mapped)
            lines.append(f"codes reported in panel (display prefixes): {len(display_rep)}")
            lines.append(f"REPORTED BUT NOT IN HIERARCHY: {len(unmapped)}")
            if unmapped:
                lines.append("  -> a future editor should add these to the PDF parse or to "
                             + OVERRIDES + ":")
                lines += ["    "+c for c in unmapped[:200]]
        except Exception as e:
            lines.append(f"(panel check skipped: {e})")
    else:
        lines.append(f"(panel not found: run build_fry9c_panel.py to enable completeness check)")
    open(VALID,"w",encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines[:6])); print(f"...full report -> {VALID}")

def main():
    caps=load_caps(); write_overrides_template()
    r=pypdf.PdfReader(PDF)
    D={}; L={}
    # Some pages hold the END of one schedule and the START of the next (page 30 = HC-D+HC-E;
    # page 31 = HC-F+HC-G+HC-H). Assigning a whole page to one schedule leaks the other's items, so
    # SPLIT each page at every "Schedule X—" header and attribute each segment to its own schedule.
    # Continuation pages (no header) carry forward the last schedule. HC-E is folded into HC-D.
    cur=None
    SCH_ALIAS={"HC-E":"HC-D"}
    for pg in r.pages:
        t=pg.extract_text() or ""
        lay=pg.extract_text(extraction_mode="layout") or ""
        ms=list(SCHED.finditer(t))
        sch1=lambda m:(lambda s: SCH_ALIAS.get(s,s))(m.group(1).upper().rstrip('-'))
        if len(ms)==0:                                # pure continuation page -> carry forward
            if NOTES.search(t): cur=None; continue    # 'Notes to the ...' free-text pages: not schedule data
            if cur: D.setdefault(cur,[]).append(t); L.setdefault(cur,[]).append(lay)
        elif len(ms)==1:                              # one schedule on the page -> the WHOLE page is it.
            cur=sch1(ms[0])                           # (pypdf can emit the header AFTER its own codes, so
            D.setdefault(cur,[]).append(t)            #  splitting on header position would lose them — HC-P)
            L.setdefault(cur,[]).append(lay)
        else:                                         # 2+ headers: a page that ends one schedule and starts
            on_page=[]                                # the next (page 30 HC-D/HC-E, page 31 HC-F/G/H) -> split
            if ms[0].start()>20 and cur:
                D.setdefault(cur,[]).append(t[:ms[0].start()]); on_page.append(cur)
            for i,mm in enumerate(ms):
                sch=sch1(mm); end=ms[i+1].start() if i+1<len(ms) else len(t)
                D.setdefault(sch,[]).append(t[mm.start():end]); on_page.append(sch); cur=sch
            for sch in dict.fromkeys(on_page):
                L.setdefault(sch,[]).append(lay)
    curated=load_matrix()
    hier={}
    for key in curated:                          # curated matrix schedules (incl. sub-sections, e.g. HI-B Part II)
        hier[key]=matrix_nodes(key, curated[key], caps)
    for sch in D:
        if sch in curated: continue              # matrix schedules already built from the curated CSV
        hier.update(build_schedule(sch, D[sch], L.get(sch,[]), caps))
    hier=apply_overrides(hier, set(curated))
    # fill captions on grouping rows the parser created for nesting but left blank (e.g. HC item 14 owns
    # 14.a/14.b). Without this they render as a bare item number. Keyed by (schedule key, item).
    CAPTION_FILL={
      ("HC","14"):"Federal funds purchased and securities sold under agreements to repurchase",
      ("HC","19"):"Subordinated notes and debentures",
      ("HC","26"):"Retained earnings, accumulated other comprehensive income, and other equity components",
      ("HC","27"):"Total bank equity capital and noncontrolling (minority) interests",
      ("HC — Memoranda","23"):"Secured liabilities",
      ("HC — Memoranda","24"):"Issuances associated with the U.S. Treasury Capital Purchase Program",
      ("HC-K","3"):"Loans secured by real estate and other loans",
      ("HC-K","4"):"Trading assets and other earning assets",
      ("HC-M","12"):"Intangible assets",
      ("HC-M","14"):"Other borrowed money",
      ("HC-M","19"):"Asset-backed commercial paper conduits",
      ("HC-M","20"):"Broker-dealer subsidiary and intercompany items",
      ("HC-M","23"):"Secured liabilities",
      ("HC-M","24"):"Issuances associated with the U.S. Department of the Treasury Capital Purchase Program",
    }
    for (sch,item),cap in CAPTION_FILL.items():
        for nd in hier.get(sch,[]):
            if str(nd.get("item",""))==item and nd.get("header") and not (nd.get("caption") or "").strip():
                nd["caption"]=cap
    # Prune header nodes that have no children after overrides (avoids orphaned blank rows in the UI).
    for sch in hier:
        nodes = hier[sch]
        item_set = {str(r.get("item","")) for r in nodes}
        def _has_children(item_str, _iset=item_set):
            pfx = item_str + "."
            return any(it.startswith(pfx) for it in _iset)
        hier[sch] = [
            r for r in nodes
            if not (r.get("header") and not r.get("mdrm") and not _has_children(str(r.get("item",""))))
        ]
    json.dump(hier, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=0)
    n=sum(len(v) for v in hier.values()); nh=sum(1 for v in hier.values() for x in v if x.get("header"))
    print(f"wrote {OUT}: {len(hier)} schedule sections, {n} items ({nh} header/parent nodes)")
    completeness_report(hier)

if __name__=="__main__": main()
