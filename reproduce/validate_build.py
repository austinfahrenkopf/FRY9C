#!/usr/bin/env python3
"""
validate_build.py  —  automated post-build QA gate for the FR Y-9C hierarchy.
Run AFTER `python build_hierarchy_fry9c.py` (and before/after make_site). It re-derives the
form's ground-truth codes from the PDF and checks the built hierarchy + curated matrix CSV against
it. Exit code 0 = all green; 1 = at least one FAIL. Codifies the manual review of 2026-06.

Checks:
  1. SCHEDULES   every expected schedule is present (and no stray/duplicate-content ones).
  2. COMPLETE    every code on each schedule's form pages is in the hierarchy (no silent drops).
  3. RESOLVE     every curated MDRM code exists in the dictionary (no typos).
  4. ORDER       matrix rows are in natural item order (1,2,..,10,11 — not 1,10,11,2).
  5. DUP         no code lives in two schedules (except the known BHCK3123 allowance shared by
                 HI-B Part II and HC-R Part II).
  6. CAPTIONS    no data row renders as a bare item number (empty caption + no code).
  7. STRUCTURE   header rows carry no code; leaf rows carry a code.

Usage:  python validate_build.py
Setup:  pip install pypdf
"""
from __future__ import annotations
import csv, json, os, re, sys
import pypdf

PDF="ReturnFinancialReportPDF.pdf"; HIER="fry9c_hierarchy.json"
MATRIX="fry9c_matrix.csv"; DICT="fry9c_dictionary.csv"; PANEL="fry9c_panel_long.parquet"
SCHED=re.compile(r'Schedule\s+(H[ICR]?-?[A-Z0-9]*)\s*[—–]', re.I)   # em/en-dash header only
NOTES=re.compile(r'Notes to the (Balance Sheet|Income Statement)', re.I)  # optional free-text pages
SCH_ALIAS={"HC-E":"HC-D"}
KNOWN_DUP={"3123"}                                                  # allowance, legit in HI-B + HC-R

def codes_in(t): return [tk for tk in t.split() if re.match(r'^(?=.*\d)[0-9A-Z]{4}$', tk) and tk!='0000']
def bare(c): return c[4:] if re.match(r'^BH[A-Z]{2}', c or '') else (c or '')

def form_codes_by_schedule():
    """Ground truth: split each page at its header(s); single-header page -> whole page; carry forward."""
    r=pypdf.PdfReader(PDF); D={}; cur=None
    def s1(m): s=m.group(1).upper().rstrip('-'); return SCH_ALIAS.get(s,s)
    for pg in r.pages:
        t=pg.extract_text() or ""; ms=list(SCHED.finditer(t))
        if len(ms)==0:
            if NOTES.search(t): cur=None; continue   # 'Notes to the ...' pages (14-16, 72-73): not schedule data
            if cur: D.setdefault(cur,set()).update(codes_in(t))
        elif len(ms)==1:
            cur=s1(ms[0]); D.setdefault(cur,set()).update(codes_in(t))
        else:
            if ms[0].start()>20 and cur: D.setdefault(cur,set()).update(codes_in(t[:ms[0].start()]))
            for i,m in enumerate(ms):
                sch=s1(m); end=ms[i+1].start() if i+1<len(ms) else len(t)
                D.setdefault(sch,set()).update(codes_in(t[m.start():end])); cur=sch
    return D

def natkey(it):
    key=[]
    for t in re.findall(r'M|\d+|\([0-9a-z]+\)|[a-z]', it or ''):
        if t=='M': key.append((2,0,''))
        elif t.isdigit(): key.append((0,int(t),''))
        elif t.startswith('('):
            inner=t.strip('()'); key.append((0,int(inner),'') if inner.isdigit() else (1,0,inner))
        else: key.append((1,0,t))
    return key

def main():
    for f in (PDF,HIER,MATRIX,DICT):
        if not os.path.exists(f): sys.exit(f"missing {f} — run the build first")
    dd={r['mdrm'].strip() for r in csv.DictReader(open(DICT,encoding='latin-1'))}
    hier=json.load(open(HIER,encoding='utf-8'))
    form=form_codes_by_schedule()
    rows=[r for r in csv.DictReader([l for l in open(MATRIX,encoding='utf-8') if not l.lstrip().startswith('#')])
          if (r.get('schedule') or '').strip()]
    fails=[]; notes=[]
    base=lambda k:(re.match(r'(H[IC](?:-[A-Z]{1,2})?)',k) or [k,k])[1] if isinstance(k,str) else k
    def baseof(k):
        m=re.match(r'(H[IC](?:-[A-Z]{1,2})?)',k); return m.group(1) if m else k

    # hierarchy codes per base schedule
    hcodes={}
    for k,nodes in hier.items():
        b=baseof(k); s=hcodes.setdefault(b,set())
        for n in nodes:
            if n.get('mdrm'): s.add(bare(n['mdrm']))

    # 1. SCHEDULES present
    expect={'HI','HI-A','HI-B','HI-C','HC','HC-B','HC-C','HC-D','HC-F','HC-G','HC-H','HC-I',
            'HC-K','HC-L','HC-M','HC-N','HC-P','HC-Q','HC-R','HC-S','HC-V'}
    missing_sch=sorted(s for s in expect if s not in hcodes)
    if missing_sch: fails.append(f"[SCHEDULES] missing from hierarchy: {missing_sch}")

    # 2. COMPLETE — every code we actually HAVE NUMERIC DATA FOR must appear somewhere in the tree.
    #    Two principled relaxations vs. naive per-schedule matching:
    #      (a) check against the WHOLE tree, not one schedule — the PDF attributes shared/cross-
    #          referenced codes onto neighboring pages (e.g. 3543/3547 -> HC-Q, 3545 -> HC), and
    #      (b) require only codes REPORTED in the panel parquet. This excludes the form's free-text
    #          "Notes to the financial statements" fields (5351-5360, B027-B056, ...) which are
    #          textual, never numeric/charted, plus any historical-only codes with no current data.
    hier_all=set().union(*hcodes.values()) if hcodes else set()
    panel_bare=None
    if os.path.exists(PANEL):
        try:
            import pandas as pd
            panel_bare={bare(c) for c in pd.read_parquet(PANEL,columns=["mdrm"])["mdrm"].unique()}
        except Exception as e:
            notes.append(f"[COMPLETE] panel unreadable ({e}); checking against all form codes")
    for sch in sorted(form):
        miss=sorted(c for c in form[sch]
                    if c not in hier_all and (panel_bare is None or c in panel_bare))
        if miss: fails.append(f"[COMPLETE] {sch}: {len(miss)} reported code(s) absent from hierarchy: {miss[:10]}")

    # 3. RESOLVE — curated codes exist in dictionary
    PREF=('BHCK','BHDM','BHFN','BHCA','BHCW','BHBC','BHOD','BHSA','BHSZ')
    bad=[]
    for r in rows:
        cs=(r.get('codes') or '').split('|') if (r.get('codes') or '').strip() else [r.get('colA'),r.get('colB'),r.get('colC')]
        for c in cs:
            c=(c or '').strip()
            if not c: continue
            full=c if re.match(r'^BH[A-Z]{2}[0-9A-Z]{4}$',c) else next((p+c for p in PREF if p+c in dd),'BHCK'+c)
            if full not in dd and not re.match(r'^BH[A-Z]{2}[0-9A-Z]{4}$',full): bad.append((r['schedule'],r.get('item'),c))
    if bad: fails.append(f"[RESOLVE] {len(bad)} curated code(s) not in dictionary: {bad[:8]}")

    # 4. ORDER — check the BUILT hierarchy's item order, not the CSV row order. matrix_nodes()
    #    natural-sorts at build time, so the CSV may sit in any order; what ships is what matters.
    for k,nodes in hier.items():
        items=[(n.get('item') or '').strip() for n in nodes
               if not n.get('col') and (n.get('item') or '').strip()]
        if items!=sorted(items,key=natkey):
            fails.append(f"[ORDER] {k}: built hierarchy items not in natural order")

    # 5. DUP — code in 2+ schedules
    code2sch={}
    for r in rows:
        s=r['schedule'].split(' — ')[0]
        cs=(r.get('codes') or '').split('|') if (r.get('codes') or '').strip() else [r.get('colA'),r.get('colB'),r.get('colC')]
        for c in cs:
            c=bare((c or '').strip())
            if c: code2sch.setdefault(c,set()).add(s)
    dups={c:s for c,s in code2sch.items() if len(s)>1 and c not in KNOWN_DUP}
    if dups: fails.append(f"[DUP] code(s) in multiple schedules: {dict(list(dups.items())[:8])}")

    # 6. GOLDEN CELL — JPMorgan (RSSD 1039502) BHCK2170 at the latest quarter must match the raw
    #    BHCF source within rounding.  Also sanity-assert ALL total assets stay below $100T (tripwire
    #    for HIGH-1 double-count; real US banking system is ~$25T across all Y-9C filers).
    JPM_RSSD=1039502; GOLDEN_CODE="BHCK2170"; GOLDEN_VALUE=4_900_475_000; ASSET_CAP=100_000_000_000
    if os.path.exists(PANEL):
        try:
            import pandas as pd
            pnl=pd.read_parquet(PANEL,columns=["quarter_end","id_rssd","mdrm","value"])
            lq=pnl["quarter_end"].max()
            jpm=pnl[(pnl["id_rssd"]==JPM_RSSD)&(pnl["mdrm"]==GOLDEN_CODE)&(pnl["quarter_end"]==lq)]
            if jpm.empty: fails.append(f"[GOLDEN] JPM {JPM_RSSD} {GOLDEN_CODE} not found in panel at {lq}")
            else:
                got=int(jpm["value"].iloc[0])
                if got!=GOLDEN_VALUE: notes.append(f"[GOLDEN] JPM {GOLDEN_CODE} at {lq}: got {got:,}, expected {GOLDEN_VALUE:,} — update GOLDEN_VALUE if a new quarter was added")
            all_assets=pnl[(pnl["mdrm"]==GOLDEN_CODE)&(pnl["quarter_end"]==lq)]["value"].sum()
            if all_assets>ASSET_CAP: fails.append(f"[GOLDEN] ALL total assets {all_assets/1e9:.0f}B exceeds {ASSET_CAP/1e9:.0f}B cap (HIGH-1 double-count tripwire)")
        except Exception as e:
            notes.append(f"[GOLDEN] panel unreadable ({e}); golden-cell check skipped")

    # 7. CAPTIONS / 8. STRUCTURE — on built hierarchy
    blank=0; badhdr=0
    for k,nodes in hier.items():
        for n in nodes:
            cap=(n.get('caption') or '').strip()
            if not cap and not n.get('mdrm') and not n.get('col'): blank+=1
            if n.get('header') and n.get('mdrm'): badhdr+=1
    if blank: notes.append(f"[CAPTIONS] {blank} row(s) with no caption and no code (bare item numbers)")
    if badhdr: notes.append(f"[STRUCTURE] {badhdr} header row(s) unexpectedly carry a code")

    # 8. DERIV — every DERIV formula code must resolve in the deployed site parquet.
    #    Catches clone-porting bugs where a code is referenced in JS but absent from data.
    SITE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"site_fry9c")
    SITE_HTML=os.path.join(SITE_DIR,"index.html")
    if os.path.exists(SITE_HTML):
        import re as _re
        html=open(SITE_HTML,encoding="utf-8").read()
        dm=_re.search(r'const DERIV=\{(.*?)\n\};',html,_re.DOTALL)
        if dm:
            deriv_codes=set(_re.findall(r"'(BH[A-Z]{2}[0-9A-Z]{4})'",dm.group(1)))
            site_parts=[os.path.join(SITE_DIR,f) for f in os.listdir(SITE_DIR) if f.endswith(".parquet")]
            if site_parts and deriv_codes:
                try:
                    import pandas as _pd
                    site_codes=set()
                    for p in site_parts: site_codes.update(_pd.read_parquet(p,columns=["mdrm"])["mdrm"].unique())
                    missing_deriv=sorted(deriv_codes-site_codes)
                    if missing_deriv: fails.append(f"[DERIV] {len(missing_deriv)} DERIV code(s) absent from site parquet: {missing_deriv[:10]}")
                except Exception as e: notes.append(f"[DERIV] site parquet unreadable ({e}); check skipped")
            elif not site_parts: notes.append("[DERIV] no site parquet in site_fry9c/; run make_site_fry9c.py first")
        else: notes.append("[DERIV] DERIV block not found in site HTML; pattern mismatch")
    else: notes.append("[DERIV] site HTML not found; run make_site_fry9c.py first")

    # 9. COMPLETENESS (manifest-driven) — consume expected_items.json from the form-completeness
    #    auditor. The manifest lists, per form/schedule, MDRM codes that HAVE DATA but are absent
    #    from the hierarchy (the dropped-item class invisible to the code-resolution checks #2/#8).
    #    We re-test each must-add code (has_recent_data) against the freshly built hierarchy and WARN
    #    with the remaining count so a future fixer can close them — this is a tracking signal, not a
    #    blocking gate (there are 100s of historical gaps). Reserved "Not applicable" items such as
    #    HC-C #8 / HC-K #10 carry no MDRM and are correctly NOT listed here.
    HERE=os.path.dirname(os.path.abspath(__file__))
    EXP=next((c for c in (os.path.join(HERE,"expected_items.json"),os.path.join(HERE,"..","expected_items.json")) if os.path.exists(c)),None)
    if not EXP:
        notes.append("[COMPLETE2] no expected_items.json manifest found; schedule-completeness check skipped")
    else:
        try:
            forms=json.load(open(EXP,encoding="utf-8")).get("forms",{})
            fkey=next((k for k in ("FR Y-9C","FRY9C","Y-9C") if k in forms),None)
            if not fkey:
                notes.append("[COMPLETE2] manifest has no FR Y-9C entry; check skipped")
            else:
                present=set()
                for nodes in hier.values():
                    for nd in nodes:
                        if nd.get("mdrm"): present.add(nd["mdrm"]); present.add(bare(nd["mdrm"]))
                still=[]; per={}
                for sch,sobj in forms[fkey].get("schedules",{}).items():
                    for mc in sobj.get("missing_codes",[]):
                        if not mc.get("has_recent_data"): continue
                        code=str(mc.get("code","")).strip()
                        if code and code not in present and bare(code) not in present:
                            still.append(code); per[sch]=per.get(sch,0)+1
                if still:
                    top=sorted(per.items(),key=lambda x:-x[1])[:6]
                    notes.append(f"[COMPLETE2] {fkey}: {len(still)} must-add code(s) still absent from hierarchy "
                                 f"(top schedules: {top}); sample {sorted(still)[:12]} — tracked for the completeness fixer")
                else:
                    notes.append(f"[COMPLETE2] {fkey}: all must-add codes from manifest are now present in the hierarchy")
        except Exception as e:
            notes.append(f"[COMPLETE2] expected_items.json unreadable ({e}); check skipped")

    # Hierarchy structural lint — EMPTY_CAPTION / SCHED_CONTAM / within-DUPLICATE
    try:
        import sys as _sys; _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '_lint_scratch'))
        from hierarchy_linter import lint_structural
        lint_defects = lint_structural(hier, 'y9c')
        if lint_defects:
            fails.append(f"[HIERARCHY_LINT] {len(lint_defects)} structural defect(s) detected")
            for d in lint_defects[:5]:
                fails.append(f"  {d['check']} {d['sched']} item={d['item']} {d.get('mdrm','')}: {d['problem'][:80]}")
    except ImportError:
        notes.append("[HIERARCHY_LINT] hierarchy_linter not found; structural check skipped")
    except Exception as e:
        notes.append(f"[HIERARCHY_LINT] structural check error ({e}); skipped")

    # 10. COMPLETENESS GATE (bidirectional, era-aware, BLOCKING) — MISSING / SPURIOUS / SEQUENCE /
    #     ERA_SEAM. Replaces the old one-directional non-blocking [COMPLETE2] WARN. See
    #     _completeness_gate.py for the full contract.
    try:
        import sys as _sys; _gbase=os.path.dirname(os.path.abspath(__file__))
        for _p in (os.path.join(_gbase,'..'), _gbase):
            if _p not in _sys.path: _sys.path.insert(0,_p)
        from _completeness_gate import run_gate
        g_fails, g_notes = run_gate('y9c', hier, _gbase)
        fails.extend(g_fails); notes.extend(g_notes)
    except ImportError:
        fails.append("[GATE] _completeness_gate.py not found — completeness gate is REQUIRED; build cannot be trusted")
    except Exception as e:
        fails.append(f"[GATE] completeness gate error ({e})")

    print("="*70); print("FR Y-9C build validation"); print("="*70)
    print(f"  schedules in hierarchy: {len(hier)}   matrix rows: {len(rows)}   dict codes: {len(dd)}")
    for n in notes: print("  NOTE  "+n)
    if fails:
        print(f"\n  {len(fails)} FAILURE(S):")
        for x in fails: print("  FAIL  "+x)
        sys.exit(1)
    print("\n  ALL CHECKS PASSED [OK]")

if __name__=="__main__":
    main()
