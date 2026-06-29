#!/usr/bin/env python3
"""
make_site_fry9c.py  (v3 engine for FR Y-9C — consolidated bank holding companies)
Clone of the Call/002 explorer, configured for Y-9C: MDRM prefix BHCK (BHDM/BHFN for
domestic/foreign), already fully consolidated -> NO COMB/coalesce-merge needed.

Inputs in this folder:
  fry9c_panel_long.parquet   long panel: quarter_end, id_rssd, mdrm, value
                             (+ institution_name if present; else RSSD is shown)
  fry9c_hierarchy.json       from build_hierarchy_fry9c.py
  fry9c_dictionary.csv       optional (mdrm, description) for nicer captions

If your panel file has a different name, set SRC below or rename it.

Run:  python build_hierarchy_fry9c.py  ->  python make_site_fry9c.py
"""
import os, sys, shutil, glob, json
from datetime import datetime
import pandas as pd
BUILD_TS = datetime.now().strftime('%Y-%m-%d %H:%M')
SITE="site_fry9c"; MAXBYTES=95*1024*1024
CREDIT_URL="https://github.com/austinfahrenkopf"   # <-- your GitHub profile (or set a specific repo URL)
# --html-only: regenerate just index.html from the EXISTING site parquet(s) — fast iteration on
# the dashboard UI without re-parsing the ~100M-row source panel. Use after editing the template.
HTML_ONLY = "--html-only" in sys.argv
SRC="fry9c_panel_long.parquet"
os.makedirs(SITE, exist_ok=True)

if HTML_ONLY:
    # Purge legacy (pre-split) parquets so they don't slow down the roster and NODATA reads
    _legacy_names=["fry9c.parquet","fry9c_1990_2009.parquet","fry9c_2010_2019.parquet","fry9c_2020_2031.parquet"]
    for _lg in _legacy_names:
        _lgp=os.path.join(SITE,_lg)
        if os.path.exists(_lgp): os.remove(_lgp); print(f"  [--html-only] removed legacy {_lg}")
    _all_p=sorted(f for f in os.listdir(SITE) if f.endswith(".parquet"))
    if not _all_p: raise SystemExit("--html-only: no site parquet in "+SITE+" yet; run a full build first.")
    AGG_PARTS=[p for p in _all_p if p=="fry9c_agg.parquet"]
    HIST_PARTS=[p for p in _all_p if p=="fry9c_hist.parquet"]
    OLD_ACTIVE_PARTS=[p for p in _all_p if "fry9c_active_1986" in p or "fry9c_active_2010" in p]
    PARTS=[p for p in _all_p if "fry9c_active_2020" in p]
    if not PARTS: PARTS=[p for p in _all_p if p not in AGG_PARTS+HIST_PARTS+OLD_ACTIVE_PARTS]
    if not PARTS: raise SystemExit("--html-only: no recent active parquet found; run a full build first.")
    print("[--html-only] PARTS:", PARTS, "| OLD:", OLD_ACTIVE_PARTS, "| HIST:", HIST_PARTS, "| AGG:", AGG_PARTS)
    # BANKS_JSON from all non-agg parquets so all 3,141 filers appear in the entity roster
    # De-dup per parquet first (hist has 150M+ rows; full concat would OOM on groupby)
    _roster_p=[p for p in _all_p if p not in AGG_PARTS]
    _roster_parts=[]
    for _rp in _roster_p:
        _pp=pd.read_parquet(os.path.join(SITE,_rp),columns=["id_rssd","institution_name"])
        _roster_parts.append(_pp.drop_duplicates(subset=["id_rssd"],keep="last"))
    _r=pd.concat(_roster_parts,ignore_index=True)
    ros=_r.groupby("id_rssd")["institution_name"].agg(lambda s:s.dropna().iloc[-1] if len(s.dropna()) else "").reset_index()
    banks=[[int(r.id_rssd), str(r.institution_name)] for r in ros.itertuples()]
    BANKS_JSON=json.dumps(banks, ensure_ascii=False)
    # active_rssds: filers present in the max quarter of the active parquets
    _ap=[p for p in _all_p if "fry9c_active_" in p and p not in AGG_PARTS]
    if _ap:
        _ra=pd.concat([pd.read_parquet(os.path.join(SITE,p), columns=["id_rssd","quarter_end"]) for p in _ap], ignore_index=True)
        _max_q=_ra["quarter_end"].max(); active_rssds=set(int(x) for x in _ra.loc[_ra["quarter_end"]==_max_q,"id_rssd"].unique())
    else: active_rssds=set()
    # no-data codes: in hierarchy but absent from all site parquets
    _hj2=json.load(open("fry9c_hierarchy.json",encoding="utf-8")) if os.path.exists("fry9c_hierarchy.json") else {}
    _dc2=set();[_dc2.add(_it.get("mdrm")) for _its in _hj2.values() for _it in _its];_dc2.discard(None)
    _spq=pd.concat([pd.read_parquet(os.path.join(SITE,p),columns=["mdrm"]) for p in _all_p],ignore_index=True) if _all_p else pd.DataFrame(columns=["mdrm"])
    NODATA_CODES=sorted(c for c in _dc2 if c and c not in set(_spq["mdrm"].unique()))
else:
  if not os.path.exists(SRC):
    cands=[f for f in glob.glob("*.parquet") if not f.startswith("site")]
    if not cands: raise SystemExit("No Y-9C panel parquet found. Put fry9c_panel_long.parquet here.")
    SRC=cands[0]; print("using panel:", SRC)
  for f in os.listdir(SITE):
    if f.endswith(".parquet"): os.remove(os.path.join(SITE,f))

  df=pd.read_parquet(SRC)
  cols={c.lower():c for c in df.columns}
  qc=cols.get("quarter_end") or cols.get("date") or list(df.columns)[0]
  ic=cols.get("id_rssd") or cols.get("rssd") or cols.get("entity")
  nc=cols.get("institution_name") or cols.get("name")
  # standardize column names so the browser SQL is predictable
  ren={qc:"quarter_end", ic:"id_rssd"}
  if nc: ren[nc]="institution_name"
  df=df.rename(columns=ren)
  if "institution_name" not in df.columns: df["institution_name"]=df["id_rssd"].astype(str)
  df["quarter_end"]=df["quarter_end"].astype(str)
  # roster from the panel
  ros=(df.groupby("id_rssd")["institution_name"].agg(lambda s:s.dropna().iloc[-1] if len(s.dropna()) else "")).reset_index()
  banks=[[int(r.id_rssd), str(r.institution_name)] for r in ros.itertuples()]
  BANKS_JSON=json.dumps(banks, ensure_ascii=False)

  # Write site parquets — split active (filers in latest quarter) vs historical/inactive.
  # Active: era-sharded; recent shard loads at startup, older eras lazy-loaded on demand.
  # Historical: single shard, lazy-loaded on "Show merged" or inactive-entity lookup.
  PARTS=[]; OLD_ACTIVE_PARTS=[]; HIST_PARTS=[]; AGG_PARTS=[]
  keep=[c for c in ["quarter_end","id_rssd","institution_name","mdrm","value"] if c in df.columns]
  df=df[keep]
  DISPLAY_CODES=set()
  if os.path.exists("fry9c_hierarchy.json"):
      _H=json.load(open("fry9c_hierarchy.json",encoding="utf-8"))
      for _items in _H.values():
          for _it in _items: DISPLAY_CODES.add(_it.get("mdrm"))
  DISPLAY_CODES|={"BHCK2122","BHCK2170","BHCK3210","BHCK4340","BHCK3123",
                  "BHCK1403","BHCK1406","BHCK1407","BHDM6631","BHDM6636","BHFN6631","BHFN6636",
                  "BHCK1606","BHCKB575","BHCKK213","BHCKK216","BHCK1594",
                  "BHCK5398","BHCKC236","BHCKC238","BHCKF172","BHCKF173","BHCK3499","BHCKF178","BHCKF179"}
  DISPLAY_CODES.discard(None)
  if DISPLAY_CODES:
      _before=len(df); df=df[df["mdrm"].isin(DISPLAY_CODES)].reset_index(drop=True)
      print(f"DISPLAY_CODES filter: {_before:,} -> {len(df):,} rows ({len(DISPLAY_CODES)} codes)")
  NODATA_CODES=sorted(c for c in DISPLAY_CODES if c and c not in set(df["mdrm"].unique()))
  print(f"NODATA_CODES: {len(NODATA_CODES)} codes in hierarchy but absent from panel")
  # Determine active filers: those reporting in the most recent quarter
  _max_q=df["quarter_end"].max()
  active_rssds=set(int(x) for x in df.loc[df["quarter_end"]==_max_q,"id_rssd"].unique())
  print(f"active filers ({_max_q}): {len(active_rssds):,} of {df['id_rssd'].nunique():,} total")
  # Sort by id_rssd (entity) FIRST so a single-entity query prunes to that entity's row groups:
  # DuckDB-WASM HTTP range requests then fetch ~0.1% of a shard instead of the whole multi-MB file.
  # (Also clusters like values -> ~34% better zstd compression.) Smaller row groups = finer pruning.
  df=df.sort_values(["id_rssd","mdrm","quarter_end"]).reset_index(drop=True)
  _PQARGS=dict(index=False, compression='zstd', row_group_size=50000)
  # Split: active filers by era shard, historical/inactive as one shard
  df_active=df[df["id_rssd"].isin(active_rssds)].reset_index(drop=True)
  df_hist=df[~df["id_rssd"].isin(active_rssds)].reset_index(drop=True)
  print(f"df_active: {len(df_active):,} rows  df_hist: {len(df_hist):,} rows")
  yr_a=df_active["quarter_end"].str[:4].astype(int)
  for lo,hi,is_recent in [(2020,2031,True),(2010,2019,False),(1986,2009,False)]:
      sub=df_active[(yr_a>=lo)&(yr_a<=hi)].reset_index(drop=True)
      if sub.empty: continue
      fn=f"fry9c_active_{lo}_{hi}.parquet"
      sub.to_parquet(os.path.join(SITE,fn),**_PQARGS)
      sz=os.path.getsize(os.path.join(SITE,fn))
      print(f"  {fn}: {len(sub):,} rows, {sz/1e6:.1f} MB")
      if is_recent: PARTS.append(fn)
      else: OLD_ACTIVE_PARTS.append(fn)
  if not df_hist.empty:
      fn_h="fry9c_hist.parquet"
      df_hist.to_parquet(os.path.join(SITE,fn_h),**_PQARGS)
      sz=os.path.getsize(os.path.join(SITE,fn_h))
      print(f"  {fn_h}: {len(df_hist):,} rows, {sz/1e6:.1f} MB  (lazy-loaded on Show merged)")
      HIST_PARTS=[fn_h]
  # Pre-aggregated ALL shard: SUM(value) per mdrm per quarter over EVERY filer present that
  # quarter (true sector total across all eras, not just the current active roster). Nested
  # sub-holding filers are still excluded (de-nested) to avoid double-count (audit HIGH-1).
  # Tiny file (~2 MB) loaded at startup so default ALL queries return instantly.
  df_agg_src=df.copy()
  if os.path.exists("fry9c_topholder.json"):
      _nm=json.load(open("fry9c_topholder.json")); _ne=_nm.get("nested",_nm)
      _ex=[(q,int(r2)) for q,rs in _ne.items() for r2 in rs]
      if _ex:
          _ex_df=pd.DataFrame(_ex,columns=["quarter_end","id_rssd"]); _ex_df["_d"]=True
          df_agg_src=df_agg_src.merge(_ex_df,on=["quarter_end","id_rssd"],how="left")
          df_agg_src=df_agg_src[df_agg_src["_d"].isna()].drop(columns=["_d"]).reset_index(drop=True)
  df_agg=df_agg_src.groupby(["quarter_end","mdrm"],as_index=False)["value"].sum()
  fn_agg="fry9c_agg.parquet"
  df_agg.to_parquet(os.path.join(SITE,fn_agg),**_PQARGS)
  sz=os.path.getsize(os.path.join(SITE,fn_agg))
  print(f"  {fn_agg}: {len(df_agg):,} rows, {sz/1e6:.1f} MB  (ALL pre-agg, loaded at startup)")
  AGG_PARTS=[fn_agg]
  # Remove legacy monolithic parquets (pre-split naming convention)
  for _old in ["fry9c.parquet","fry9c_1990_2009.parquet","fry9c_2010_2019.parquet","fry9c_2020_2031.parquet"]:
      _op=os.path.join(SITE,_old)
      if os.path.exists(_op): os.remove(_op); print(f"  removed legacy {_old}")
open(os.path.join(SITE,".nojekyll"),"w").close()
if os.path.exists("fry9c_hierarchy.json"):
    shutil.copy("fry9c_hierarchy.json", os.path.join(SITE,"fry9c_hierarchy.json")); print("copied hierarchy")
else: print("NOTE: run build_hierarchy_fry9c.py for the tree / call-report view")
def _pjson(lst): return "["+",".join(f"'{p}'" for p in lst)+"]"
parts_js=_pjson(PARTS); agg_parts_js=_pjson(AGG_PARTS)
old_active_parts_js=_pjson(OLD_ACTIVE_PARTS); hist_parts_js=_pjson(HIST_PARTS)
active_rssds_js=json.dumps(sorted(active_rssds))
nodata_codes_js=json.dumps(NODATA_CODES)
_all_site=[p for lst in [PARTS,OLD_ACTIVE_PARTS,HIST_PARTS,AGG_PARTS] for p in lst]
print("site parquets:", [(p, round(os.path.getsize(os.path.join(SITE,p))/1e6,1)) for p in _all_site if os.path.exists(os.path.join(SITE,p))], "| filers:", len(banks))

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FR Y-9C Dashboard</title>
<style>
 *{box-sizing:border-box}
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;color:#14213d;background:#fafbfc}
 header{background:#14213d;color:#fff;padding:12px 20px}header h1{margin:0;font-size:17px}header p{margin:3px 0 0;font-size:13px;color:#aeb7c9}
 .app{display:grid;grid-template-columns:var(--railw,460px) 7px 1fr;min-height:calc(100vh - 52px)}
 #railsplit{cursor:col-resize;background:#e3e8ef}#railsplit:hover{background:#b9c2cf}body.dark #railsplit{background:#2a3547}
 .app.popped #railsplit{display:none}
 .rail{border-right:1px solid #e3e8ef;background:#fff;display:flex;flex-direction:column;max-height:calc(100vh - 52px);position:sticky;top:0}
 .railtabs{display:flex;gap:4px;align-items:center;padding:8px 10px;border-bottom:1px solid #e3e8ef;background:#f7f9fb}
 .tab{background:#fff;color:#14213d;border:1px solid #cdd5e0;padding:4px 12px;border-radius:7px;font-size:13px;cursor:pointer}
 .tab.on{background:#14213d;color:#fff;border-color:#14213d}
 #panelItems,#panelEnts{flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0}
 .railhead{padding:8px 12px;border-bottom:1px solid #e3e8ef}
 .railhead input{width:100%;margin-top:6px;font-size:14px;padding:7px;border:1px solid #cdd5e0;border-radius:7px}
 #tree{flex:1;overflow:auto;padding:6px 10px}#entlistpanel{flex:1;overflow:auto;padding:4px 8px}
 .main{padding:14px 18px;overflow:auto}
 label{font-size:13px;color:#5a6478;display:block;margin-bottom:3px}
 select,input{font-size:15px;padding:7px;border:1px solid #cdd5e0;border-radius:7px;background:#fff}
 input{min-width:300px}#ent{min-width:380px}#pname{min-width:160px}
 button{font-size:14px;padding:7px 12px;border:1px solid #1b7f3b;background:#1b7f3b;color:#fff;border-radius:7px;cursor:pointer}
 button.sec{background:#fff;color:#14213d;border-color:#cdd5e0}
 .row{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:10px}
 #status{font-size:13px;color:#5a6478;margin:6px 0}.muted{color:#5a6478;font-size:13px}
 .chips{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 10px}
 .chip{display:inline-flex;align-items:center;gap:7px;font-size:13px;background:#eef3f8;border:1px solid #d8e0ea;border-radius:14px;padding:4px 10px}
 .chip b{font-weight:600}.chip .x{cursor:pointer;color:#8a93a3;font-weight:700}
 .sw{width:10px;height:10px;border-radius:50%;display:inline-block}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 12px}
 .card{flex:1;min-width:140px;background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:10px 13px}
 .card .k{font-size:13px;color:#5a6478}.card .v{font-size:28px;font-weight:700;margin-top:3px}
 .up{color:#fff;background:#1b7f3b;border-radius:4px;padding:1px 5px;font-size:13px;font-weight:600}.dn{color:#fff;background:#c0392b;border-radius:4px;padding:1px 5px;font-size:13px;font-weight:600}
 table{border-collapse:collapse;width:100%;font-size:14px;margin-top:10px}th,td{border:1px solid #e3e8ef;padding:6px 9px;text-align:right}
 th{background:#f2f5f9;position:sticky;top:0;z-index:1}td:first-child,th:first-child{text-align:left}tr:nth-child(even) td{background:#f7f9fc}
 svg{background:#fff;border:1px solid #e3e8ef;border-radius:8px;display:block;overflow:visible}
 .chartbox{position:relative;resize:both;overflow:hidden;width:100%;max-width:100%;min-width:300px;min-height:240px;box-sizing:border-box;border-radius:8px;margin-bottom:2px}
 .chartbox>svg{margin-bottom:0}
 .chartbox::after{content:"\\2921";position:absolute;right:4px;bottom:1px;font-size:12px;line-height:1;color:var(--muted,#9aa3b2);opacity:.5;pointer-events:none}
 svg circle.pt{cursor:pointer;r:1.5px;fill-opacity:0;stroke-opacity:0;pointer-events:none;transition:r .1s,fill-opacity .1s,stroke-opacity .1s}
 svg .qband .reveal{opacity:0;transition:opacity .05s;pointer-events:none}svg .qband:hover .reveal{opacity:1}svg .qband-pinned .reveal{opacity:1!important;pointer-events:none}svg .qband .hit{fill:#000;fill-opacity:0;pointer-events:all;cursor:crosshair}
 details{margin-top:14px;background:#fff;border:1px solid #e3e8ef;border-radius:8px;padding:12px}
 textarea{width:100%;height:70px;font-family:Consolas,monospace;font-size:14px}
 .box{background:#fff;border:1px solid #e3e8ef;border-radius:8px;padding:12px;margin-bottom:12px}
 .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin:6px 0 2px}
 .schhead{font-weight:700;color:#14213d;margin:8px 0 3px;cursor:pointer;font-size:13px}.schhead .cnt{color:#9aa3b2;font-weight:400}
 .trow{padding:3px 6px;border-radius:5px;cursor:pointer;font-size:13px;line-height:1.3;display:flex;align-items:baseline;gap:4px;white-space:nowrap}
 .trow:hover{background:#eef3f8}.trow .code{color:#9aa3b2;font-size:12px;flex:none}
 .trow .num{color:#5a6478;flex:none}.trow.on{background:#dcefe2}.trow.nodata{opacity:0.38;pointer-events:none;cursor:default}
 .trow .cap{overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
 .trow.hdr{font-weight:600;border-left:2px solid var(--accent,#1b7f3b);margin-top:2px}.trow.hdr .cap{color:#14213d}body.dark .trow.hdr .cap{color:#e6e9ef}
 .trow.placeholder{opacity:.55;cursor:default;pointer-events:none}
 .caret{cursor:pointer;color:#5a6478;display:inline-block;width:13px;text-align:center;font-size:12px}
 .railctl{margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:13px}.railctl button{padding:3px 8px}
 .erow{display:flex;justify-content:space-between;gap:8px;padding:4px 6px;border-radius:5px;cursor:pointer;font-size:13px;border-bottom:1px solid #f3f5f8}
 .erow:hover{background:#eef3f8}.erow .en{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .erow .ev{color:#5a6478;font-variant-numeric:tabular-nums}.erow .pp{color:#1b7f3b;font-weight:700;cursor:pointer}.erow.agg{font-weight:600}
 .erow .ewl{cursor:pointer;color:#c8992e;font-size:13px;flex:none;padding:0 2px;opacity:.2;transition:opacity .1s;user-select:none}.erow .ewl.on{opacity:1;color:#e8a800}.erow:hover .ewl{opacity:.6}.erow:hover .ewl.on{opacity:1}
 .erow .frag{color:#9aa3b2;font-size:12px;font-style:italic;margin-left:4px}.erow.frag-row .en{opacity:.7}
 .slider{display:flex;align-items:center;gap:10px;margin:8px 0}.slider input{min-width:120px;flex:1}
 .frow{display:flex;gap:10px;padding:2px 6px;font-size:14px;border-bottom:1px solid #f3f5f8}
 .frow .lab{flex:1;min-width:280px}.vcell{width:92px;flex:none;text-align:right;font-variant-numeric:tabular-nums;color:#14213d}
 :root{--border:#ccc;--head:#f7f8fc;--fg2:#64748b;--bg:#fff;--bg2:#f7f9fb;--fg:#14213d;--muted:#64748b}
 .modal{position:fixed;inset:0;background:rgba(10,20,40,.4);z-index:60;display:flex;align-items:flex-start;justify-content:center}
 .modalbox{background:#fff;margin-top:32px;width:min(960px,95vw);height:88vh;min-width:480px;min-height:320px;max-width:98vw;display:flex;flex-direction:column;border-radius:10px;overflow:hidden;resize:both}
 .modalbody{flex:1;overflow:auto}
 .modalhead{padding:12px 14px;border-bottom:1px solid #e3e8ef;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 .modal.float{background:transparent;pointer-events:none}
 .modal.float .modalbox{pointer-events:auto;position:fixed;top:60px;left:60px;width:min(900px,92vw);box-shadow:0 14px 44px rgba(10,20,40,.35);resize:both}
 .modal.float .modalhead{cursor:move}
 /* When popped, the rail is position:fixed (floating) and the splitter is display:none, so both
    leave the grid's auto-placement. A single 1fr column keeps #main (the only in-flow item) full-width;
    a "0 0 1fr" template would reflow #main into a 0px column (collapsing it to ~36px). */
 .app.popped{grid-template-columns:1fr}
 /* resize:both only works with a non-visible overflow; without it the handle does nothing. Use a
    fixed height (not max-height) + overflow:hidden so the panel is freely resizable, inner lists scroll. */
 .rail.floating{position:fixed;top:70px;left:24px;width:380px;height:82vh;min-width:300px;min-height:240px;z-index:80;border:1px solid #cdd5e0;border-radius:10px;box-shadow:0 14px 44px rgba(10,20,40,.32);resize:both;overflow:hidden}
 .rail.floating .railtabs{cursor:move}
 #panelEnts.entfloat{position:fixed;top:90px;right:26px;width:380px;height:70vh;min-width:300px;min-height:240px;z-index:84;background:#fff;border:1px solid #cdd5e0;border-radius:10px;box-shadow:0 14px 44px rgba(10,20,40,.32);resize:both;overflow:hidden}
 body.dark #panelEnts.entfloat{background:#161e2b;border-color:#2a3547}
 #panelEnts.entfloat .railhead{cursor:move}
 #entdetach{float:right;padding:2px 8px;margin-left:6px}
 body.dark{background:#0e1420;color:#e6e9ef;--border:#2a3547;--head:#1a2638;--fg2:#9aa3b2;--fg:#e6e9ef;--bg2:#1b2433;--bg:#161e2b;--muted:#9aa3b2}
 body.dark .rail,body.dark .card,body.dark .box,body.dark details,body.dark .modalbox{background:#161e2b;border-color:#2a3547}
 body.dark .railtabs{background:#121a26;border-color:#2a3547}body.dark .railhead,body.dark .modalhead{border-color:#2a3547}body.dark .rail{border-right-color:#2a3547}
 body.dark select,body.dark input,body.dark textarea,body.dark button.sec,body.dark .tab{background:#1b2433;color:#e6e9ef;border-color:#2a3547}
 body.dark .tab.on{background:#1b7f3b;color:#fff;border-color:#1b7f3b}
 body.dark .muted,body.dark label,body.dark .card .k,body.dark .schhead .cnt,body.dark .trow .code,body.dark .trow .num,body.dark .caret{color:#9aa3b2}
 body.dark .schhead,body.dark .card .v,body.dark .vcell,body.dark td:first-child{color:#e6e9ef}
 body.dark th{background:#1b2433;border-color:#2a3547}body.dark td{border-color:#2a3547}body.dark tr:nth-child(even) td{background:#19253a}body.dark .up{background:#1b5e2e}body.dark .dn{background:#8b1a1a}
 .erow.on{background:#dcefe2}
body.dark .erow.on{background:#16361f}
 body.dark .chip{background:#1b2433;border-color:#2a3547}body.dark .trow:hover,body.dark .erow:hover{background:#1f2a3a}body.dark .trow.on{background:#16361f}
 body.dark .erow,body.dark .frow{border-color:#222c3b}body.dark svg{background:#0f1825;border-color:#2a3547}
 body.dark .up{color:#3fb950}body.dark .dn{color:#f85149}body.dark a{color:#6cb6ff}
 #theme{float:right;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.25);padding:4px 10px;font-size:13px}
 .credit{margin:20px 2px 10px;font-size:13px;color:#9aa3b2}.credit a{color:inherit;text-decoration:underline}
.fav{cursor:pointer;color:#d69e2e;font-size:13px;flex:none;padding:0 3px;opacity:.4;transition:opacity .1s}.fav.on{opacity:1}.fav:hover{opacity:1}
.pane-toggle{font-size:13px;padding:3px 8px;margin-bottom:4px}
#charttip{position:fixed;pointer-events:none;z-index:50;background:var(--tip-bg,#1a2535);color:var(--tip-fg,#e6e9ef);border:1px solid #3a4a5e;border-radius:8px;padding:8px 12px;font-size:13px;line-height:1.55;white-space:normal;max-width:min(560px,90vw);min-width:160px;min-height:40px;display:none;box-shadow:0 4px 16px rgba(0,0,0,.4)}
body:not(.dark) #charttip{--tip-bg:#fff;--tip-fg:#14213d;border-color:#cdd5e0;box-shadow:0 4px 16px rgba(0,0,0,.12)}
#charttip .tip-q{font-weight:700;margin-bottom:4px;color:#9aa3b2;font-size:13px}
#charttip .tip-row{display:flex;align-items:center;gap:6px}
#charttip .tip-sw{width:8px;height:8px;border-radius:50%;flex:none}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(8px);background:#1a2638;color:#e6e9ef;padding:9px 18px;border-radius:8px;font-size:14px;z-index:9999;pointer-events:none;opacity:0;transition:opacity .2s,transform .2s;max-width:min(360px,90vw);text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.3)}
#formulatip{position:fixed;pointer-events:none;z-index:55;background:var(--tip-bg,#1a2535);color:var(--tip-fg,#e6e9ef);border:1px solid #3a4a5e;border-radius:6px;padding:7px 11px;font-size:13px;line-height:1.5;display:none;box-shadow:0 3px 12px rgba(0,0,0,.35);max-width:320px;white-space:normal}
#formulatip .ftip-lbl{font-weight:600;color:#9aa3b2;font-size:12px;letter-spacing:.3px;text-transform:uppercase;margin-bottom:3px}
body:not(.dark) #formulatip{--tip-bg:#fff;--tip-fg:#14213d;border-color:#cdd5e0;box-shadow:0 3px 12px rgba(0,0,0,.12)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
body:not(.dark) .lgon-row td{background:#e8f5e9!important}body.dark .lgon-row td{background:#0f2f1c!important}.lgon-row .lglink{font-weight:600}
#pbar{position:fixed;top:0;left:0;height:3px;width:0%;background:var(--accent,#1b7f3b);transition:width .3s ease,opacity .4s ease;z-index:10000;pointer-events:none}
@media print{body{background:#fff!important;color:#000!important}.rail,.railsplit,#pbar,button,.modal,#charttip,header .buttons{display:none!important}.main{margin:0!important;padding:0!important}svg{break-inside:avoid;max-width:100%!important}body.dark{background:#fff!important;color:#000!important}.cards{flex-wrap:wrap!important}h1,h2{color:#000!important}}
</style></head><body class="dark">
<div id="pbar"></div><div id="formulatip" style="display:none"></div>
<header><button id="theme">☀ Light</button><h1>FR Y-9C Dashboard</h1>
<p>Consolidated Financial Statements for Holding Companies · holding companies + ALL + peer groups · $ thousands<span id="datacur"></span></p>
<p class="muted" style="font-size:13px;margin-top:2px">“ALL” = top-tier holding companies (nested sub-holding filers excluded to avoid double-counting). These are <b>consolidated</b> totals that include nonbank and foreign subsidiaries, so the aggregate legitimately exceeds U.S. domestic commercial-bank assets.</p></header>
<div class="app">
 <div class="rail">
  <div class="railtabs"><button id="tabItems" class="tab on">Line items</button><button id="tabEnts" class="tab">Entities</button>
   <button id="popout" class="sec" style="margin-left:auto;padding:2px 8px">⧉ Pop out</button></div>
  <div id="panelItems">
   <div class="railhead"><span class="muted">click to add to chart</span>
    <input id="treesearch" placeholder="search code or caption…">
    <div class="railctl"><button id="drilldn" class="sec" title="expand one level in open branches [ ] keys">▼ Drill</button><button id="drillup" class="sec" title="collapse deepest open level [ ] keys">▲ Drill</button>
     <button id="expall" class="sec">⊕ all</button><button id="colall" class="sec">⊖ all</button>
     <button id="jumpto" class="sec" title="scroll to active measure in tree">⊙ active</button></div></div>
   <div id="tree"><p class="muted" style="padding:10px">Loading…</p></div></div>
  <div id="panelEnts" style="display:none">
   <div class="railhead"><button id="entdetach" class="sec" title="use Items + Entities at once">⧉ Detach</button><span class="muted">click to chart · ＋peer to bucket</span>
    <input id="entsearch" placeholder="search holding company / RSSD…">
    <div class="railctl">Show
     <select id="entfilter"><option value="all">All</option><option value="bank">Holding companies</option><option value="agg">ALL</option><option value="peer">Peer groups</option><option value="charted">Charted only</option><option value="watchlist">★ Watchlist</option></select>
     Sort <select id="entsort"><option value="assets">Total assets</option><option value="deposits">Total deposits</option><option value="loans">Total loans</option><option value="equity">Total equity</option><option value="current">Current measure</option><option value="name">Name A–Z</option><option value="rssd">RSSD</option></select>
     <label><input type="checkbox" id="entdesc" checked> high→low</label>
     <label title="show predecessor / merged-bank RSSDs in entity list"><input type="checkbox" id="showmerged"> Show merged</label></div></div>
   <div id="entlistpanel"><p class="muted" style="padding:10px">…</p></div></div>
 </div>
 <div id="railsplit" title="drag to resize the panel"></div>
 <div class="main">
  <div id="status">Loading data engine…</div><div id="downloads" class="muted" style="margin-bottom:8px"></div>
  <div class="row">
   <div><label>Entity (holding company name, RSSD, ALL, or ★ peer group)</label>
    <input id="ent" list="entlist" autocomplete="off"><datalist id="entlist"></datalist></div>
   <div><button id="add" class="sec">+ Add to chart</button> <button id="addpeer" class="sec">+ Add to peer</button>
    <button id="formbtn" class="sec">📄 Call-report view</button> <button id="leaguebtn" class="sec">🏆 League table</button> <button id="reportbtn" class="sec" disabled title="Select a single holding company to generate a tear-sheet report">📋 Report</button> <button id="exportbtn" class="sec">⬇ Export</button> <button id="copylink" class="sec" title="Copy link to current chart state">🔗 Link</button> <button id="kbdbtn" class="sec" title="Keyboard shortcuts (?)">⌨</button></div>
  </div>
  <div><label>Entities (overlay to compare)</label> <button id="clrents" class="sec" style="padding:1px 6px;font-size:12px;opacity:0.6" title="Remove all entities from chart">✕ Clear</button><div id="chips" class="chips"><span class="muted">none</span></div><div id="crosslinks" style="font-size:12px;color:var(--muted,#9aa3b2);margin-bottom:4px"></div>
   <label class="muted" style="font-size:13px;display:flex;align-items:flex-start;gap:4px;margin-top:4px" title="Stitch an institution's predecessor RSSDs into one continuous history (e.g. TD Bank US Holding Co + TD Group US Holdings)"><input type="checkbox" id="linkrssd" checked> Link predecessor RSSDs (<span id="linkn">0</span> lineages)</label>
   <label class="muted" style="font-size:13px;display:flex;align-items:flex-start;gap:4px;margin-top:4px" title="By default ALL counts only top-tier holding companies (a holding company that is itself controlled by another Y-9C filer is excluded so its assets aren't counted twice). Tick to sum every filer including nested sub-holding companies."><input type="checkbox" id="inclnested"> Include nested sub-holding filers in ALL (<span id="nestedn">0</span> excluded)</label></div>
  <div><label>Measures (click items in the left rail; ✕ to remove)</label> <button id="clrmeas" class="sec" style="padding:1px 6px;font-size:12px;opacity:0.6" title="Remove all measures">✕ Clear</button> <button id="calcbtn" class="sec" style="padding:1px 6px;font-size:12px" title="Define a custom calculated series combining existing line items">Σ Calc</button>
   <span style="font-size:13px;white-space:nowrap">Quick add: <select id="deriv-grpadd" style="font-size:13px;padding:1px 3px"><option value="">— category —</option><option value="Credit">Credit quality</option><option value="Loan quality">Loan-level NPL</option><option value="Capital">Capital</option><option value="Earnings">Earnings</option><option value="Funding">Funding</option><option value="Liquidity">Liquidity</option><option value="Subtotal">Subtotals $</option></select><button id="deriv-grpadd-btn" class="sec" style="padding:1px 6px;font-size:13px">Add</button></span>
   <div id="mchips" class="chips"><span class="muted">none</span></div>
   <div id="calcdiv" style="display:none;margin:4px 0 8px;padding:8px 10px;border:1px solid var(--border,#ccc);border-radius:6px;font-size:13px;background:var(--bg2,#f7f9fb)">
    <b style="display:block;margin-bottom:4px">Custom calculated series <span style="font-weight:400;color:var(--muted,#9aa3b2)">(session-only)</span></b>
    <div style="font-size:13px;color:var(--muted,#9aa3b2);margin-bottom:6px">Reference active measures by letter. Operators: <code>+ − * / ( )</code>. Division → % axis, Σnum/Σden aggregation.</div>
    <table style="border-collapse:collapse;font-size:13px;margin-bottom:8px;max-width:520px">
     <thead><tr><th style="text-align:left;padding:1px 8px 2px 0;color:var(--muted,#9aa3b2);font-weight:600">Letter</th><th style="text-align:left;padding:1px 8px 2px 0;color:var(--muted,#9aa3b2);font-weight:600">MDRM</th><th style="text-align:left;padding:1px 0 2px 0;color:var(--muted,#9aa3b2);font-weight:600">Line item</th></tr></thead>
     <tbody id="calc-picklist"></tbody>
    </table>
    <div style="border-top:1px solid var(--border,#ccc);margin:4px 0 6px;padding-top:6px">
     <div style="font-size:13px;color:var(--muted,#9aa3b2);margin-bottom:4px">Or search any code to insert at cursor:</div>
     <input id="calc-codesearch" autocomplete="off" placeholder="MDRM code or description…" style="width:260px;font:inherit;font-size:13px;padding:2px 5px;border:1px solid var(--border,#ccc);border-radius:3px;background:inherit;color:inherit">
     <div id="calc-coderes" style="display:none;max-height:110px;overflow-y:auto;border:1px solid var(--border,#ccc);border-radius:3px;margin-top:3px;font-size:13px;max-width:520px"></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
     <label style="display:flex;align-items:center;gap:4px">Name<input id="calcname" placeholder="My calc" style="width:110px;font:inherit;font-size:13px;padding:2px 5px;border:1px solid var(--border,#ccc);border-radius:3px;background:inherit;color:inherit"></label>
     <label style="display:flex;align-items:center;gap:4px">Formula<input id="calcformula" placeholder="e.g.  A/B  or  (A+B)/C  or  A*4" style="width:240px;font:inherit;font-size:13px;padding:2px 5px;border:1px solid var(--border,#ccc);border-radius:3px;background:inherit;color:inherit"></label>
     <button id="calcadd" class="sec" style="font-size:13px;padding:2px 8px">Add to chart</button>
    </div>
    <span id="calcstatus" style="color:#c0392b;font-size:13px;margin-top:4px;display:block"></span>
    <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;align-items:center">
     <button id="calcSave" class="sec" style="font-size:13px;padding:2px 8px" title="POST formulas to local server at /api/save-formulas">Save formulas</button>
     <button id="calcLoad" class="sec" style="font-size:13px;padding:2px 8px" title="GET formulas from local server at /api/formulas">Load formulas</button>
     <span style="color:var(--muted,#9aa3b2);font-size:12px;margin:0 2px">|</span>
     <button id="calcExport" class="sec" style="font-size:13px;padding:2px 8px" title="Download formulas as JSON file">Export</button>
     <button id="calcImport" class="sec" style="font-size:13px;padding:2px 8px" title="Upload formulas JSON file">Import</button>
     <input type="file" id="calcImportFile" accept=".json,application/json" style="display:none">
    </div>
   </div></div>
  <details class="box" id="peerbox"><summary><b>Peer-group builder</b> — custom bucket of holding companies</summary>
   <div class="row" style="margin-top:10px"><div><label>Peer group name</label><input id="pname" placeholder="e.g. Top 10 BHCs"></div>
    <div><button id="savepeer">Save peer group</button> <button id="clearpeer" class="sec">Clear members</button></div></div>
   <div><label>Members (use “+ Add to peer”)</label><div id="pmembers" class="chips"><span class="muted">none</span></div></div>
   <div><label>Saved peer groups</label><div id="psaved" class="chips"></div></div></details>
  <div id="kpiselrow" style="display:none;margin-bottom:4px"><span class="muted" style="font-size:13px">KPI series: </span><select id="kpisel" style="font-size:13px;padding:2px 4px;border:1px solid var(--border,#ccc);border-radius:4px"></select></div>
  <div class="cards" id="cards"></div><div class="legend" id="legend"></div>
  <div id="snapshot"></div>
  <div id="panes"><p class="muted">Pick an entity, then click a line item on the left.</p></div><button id="addchartbtn" class="sec" style="margin-top:8px;font-size:13px;display:none" onclick="addChart()">⊕ Add chart</button><div id="extracharts-area"></div>
  <div class="slider" id="sliderwrap" style="display:none"><span class="muted">From</span><input type="range" id="r0"><input type="range" id="r1">
   <input type="text" id="rfrom" list="qlist" size="10" style="font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:1px 4px;background:inherit;color:inherit"><span class="muted">to</span><input type="text" id="rto" list="qlist" size="10" style="font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:1px 4px;background:inherit;color:inherit"><datalist id="qlist"></datalist> <button id="preset1y" class="sec" style="padding:3px 8px;font-size:13px">1Y</button><button id="preset5y" class="sec" style="padding:3px 8px;font-size:13px">5Y</button><button id="preset10y" class="sec" style="padding:3px 8px;font-size:13px">10Y</button><button id="rreset" class="sec" style="padding:3px 8px;font-size:13px">All</button>
   <button id="loadhist" class="sec" style="display:none" title="Load pre-2020 historical series for active filers (~29 MB)">📅 Older data</button>
   <label class="muted" title="rebase each $ series to 100 at the start of the range"><input type="checkbox" id="idx"> index to 100</label>
   <label class="muted" title="show quarter-over-quarter absolute change instead of level"><input type="checkbox" id="qoqdelta"> QoQ Δ</label>
   <label class="muted" title="divide each $ series by total assets (BHCK2170), producing a % ratio"><input type="checkbox" id="normbyassets"> ÷ assets</label>
   <label class="muted" title="render $ series as stacked areas (additive measures only — disabled for % / ratio series)"><input type="checkbox" id="stackedmode"> ◫ Stacked</label>
   <label class="muted" title="show the series name at the right end of each line (turn off to rely on the hover/pinned tooltip; the chart gets more width)"><input type="checkbox" id="inlinelbls" checked> ⌯ Inline labels</label>
   <span class="muted" style="font-size:13px;white-space:nowrap">⟵<input id="reflineval" type="text" placeholder="ref line e.g. 8 or 5e6" style="width:100px;font-size:13px;padding:1px 4px;border:1px solid var(--border,#ccc);background:inherit;color:inherit;border-radius:3px"><input id="reflinelbl" type="text" placeholder="label" style="width:60px;font-size:13px;padding:1px 4px;border:1px solid var(--border,#ccc);background:inherit;color:inherit;border-radius:3px"><button id="reflineset" class="sec" style="padding:1px 6px;font-size:13px">Set</button><button id="reflineclr" class="sec" style="padding:1px 6px;font-size:13px">✕</button></span>
   <button id="csv" class="sec">Export</button><button id="svgexport" class="sec" style="padding:3px 8px;font-size:13px" title="Download chart as SVG file">📷 SVG</button><button id="cplink" class="sec" style="padding:3px 8px;font-size:13px" title="Copy shareable link to this view">🔗 Link</button></div>
  <div id="tbl"></div>
  <details class="box"><summary><b>SQL</b> — table <code>t</code> (quarter_end,id_rssd,institution_name,mdrm,value)</summary>
   <textarea id="sql">SELECT quarter_end, value FROM t WHERE mdrm='BHCK2170' AND id_rssd=1039502 ORDER BY quarter_end;</textarea>
   <div style="margin-top:8px"><button id="runsql" class="sec">Run</button> <button id="sqlcsv" class="sec">Export result</button></div>
   <div id="sqlout"></div></details>
  <div class="credit">Built by Austin Fahrenkopf &middot; data: public FFIEC/FRB filings &middot; Built __BUILD_TS__</div>
 </div>
</div>
<div id="formmodal" class="modal" style="display:none"><div class="modalbox">
 <div class="modalhead" style="flex-wrap:wrap;row-gap:4px"><b>Call-report view</b>
  <div id="fent-chips" style="display:inline-flex;flex-wrap:wrap;gap:3px;margin:0 4px"></div>
  <input id="fent-inp" list="entlist" autocomplete="off" placeholder="name or RSSD…" style="font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:2px 5px;background:inherit;color:inherit;width:140px">
  <button id="fent-add" class="sec" style="font-size:13px;padding:2px 6px">Add</button>
  <button id="fent-cur" class="sec" style="font-size:13px;padding:2px 6px" title="Add chart entities">+Chart</button>
  <label style="font-size:13px">From <select id="ffrom"></select></label><label style="font-size:13px">To <select id="fto"></select></label>
  <button id="ffull" class="sec" style="font-size:13px;padding:2px 6px" title="Full available range">Full</button>
  <span style="position:relative;display:inline-block"><input id="frow-filter" autocomplete="off" placeholder="filter items or search codes…" style="font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:2px 5px;background:inherit;color:inherit;width:170px"><div id="frow-coderes" style="display:none;position:absolute;top:100%;left:0;z-index:99;max-height:160px;overflow-y:auto;min-width:300px;border:1px solid var(--border,#ccc);border-radius:0 0 4px 4px;background:var(--bg,#fff);box-shadow:0 4px 8px rgba(0,0,0,.15);font-size:13px"></div></span>
  <button id="fdn" class="sec" title="expand one level">▾</button><button id="fup" class="sec" title="collapse one level">▴</button>
  <button id="fexp" class="sec">⊕</button><button id="fcol" class="sec">⊖</button><button id="fpop" class="sec" title="float / dock">⧉</button>
  <button id="formexport" class="sec">Export</button> <button id="formclose" class="sec">Close</button></div>
 <div id="formbody" style="flex:1;overflow:auto;padding:10px 14px"></div></div></div>
<div id="leaguemodal" class="modal" style="display:none"><div class="modalbox">
 <div class="modalhead"><b>🏆 League table</b>
  <label style="font-size:13px">Measure <select id="lgmeasure"></select></label>
  <label style="font-size:13px">Quarter <select id="lgquarter"></select></label>
  <label style="font-size:13px">Top <select id="lgtopn"><option>25</option><option>50</option><option>100</option><option value="0">All</option></select></label>
  <label style="font-size:13px" title="Filter by total-asset bucket">Size <select id="lgbucket"><option value="">All</option><option value="1">≥$1T</option><option value="0.1">$100B–$1T</option><option value="0.01">$10B–$100B</option><option value="0.001">$1B–$10B</option><option value="0.0001">$100M–$1B</option><option value="-">&lt;$100M</option></select></label>
  <button id="lgexport" class="sec">Export</button> <button id="lgclose" class="sec">Close</button></div>
 <div id="leaguebody" style="flex:1;overflow:auto;padding:10px 14px"><p class="muted">Loading…</p></div></div></div>
<div id="reportmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(1040px,96vw);height:92vh">
 <div class="modalhead"><b>📋 Entity Report</b> &nbsp;<span id="rpt-title"></span><span id="rpt-asof" class="muted" style="font-size:13px"></span>
  <button id="rpt-addchart" class="sec">📈 Add to chart</button> <button id="rpt-print" class="sec">🖨 Print / PDF</button> <button id="rpt-html" class="sec" title="Download report as HTML file">⬇ HTML</button> <button id="rpt-link" class="sec" style="padding:3px 8px;font-size:13px" title="Copy link to this entity view">📎 Link</button> <button id="rptclose" class="sec">Close</button></div>
 <div id="rptbody" class="modalbody" style="flex:1;overflow:auto;padding:14px 18px"></div></div></div>
<div id="exportmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(840px,96vw);max-height:92vh">
 <div class="modalhead"><b>⬇ Export Builder</b>
  <button id="expbld-setcur" class="sec" title="Copy current chart entity and date range">↺ From chart</button>
  <button id="expbld-preview" class="sec">👁 Preview</button>
  <button id="expbld-run" class="sec">⬇ Download CSV</button>
  <button id="expbld-close" class="sec">Close</button></div>
 <div id="expbldbody" class="modalbody" style="flex:1;overflow:auto;padding:14px 18px"><p class="muted">Loading…</p></div>
 <div id="eb-preview-area" style="overflow:auto;max-height:260px;padding:0 18px 10px;font-size:13px"></div></div></div>
<div id="toast"></div>
<div id="kbdmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(420px,92vw)">
 <div class="modalhead"><b>⌨ Keyboard shortcuts</b> <button id="kbdclose" class="sec">Close</button></div>
 <div style="padding:16px;font-size:14px"><table style="width:100%;border-collapse:collapse">
  <tr><td style="padding:3px 10px;font-family:monospace;width:120px">[  ,</td><td>Previous quarter</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">]  .</td><td>Next quarter</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">/</td><td>Focus tree search</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">Enter</td><td>Add first search result to chart</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">Esc</td><td>Clear search / close modal</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">I / E</td><td>Switch to Items / Entities tab</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">L</td><td>Open League table</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">R</td><td>Open entity report (single bank active)</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">?</td><td>This help</td></tr>
 </table></div></div></div>
<script type="module">
import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';
const PARTS=__PARTS__, AGG_PARTS=__AGG_PARTS__, OLD_ACTIVE_PARTS=__OLD_ACTIVE_PARTS__, HIST_PARTS=__HIST_PARTS__, ACTIVE_RSSDS=new Set(__ACTIVE_RSSDS__), BANKS=__BANKS__, LINEAGE=__LINEAGE__, NESTED=__NESTED__; let LINK=true;
const EMPTY_CODES=new Set(__NODATA__);
const st=m=>document.getElementById('status').textContent=m;
const _pb=document.getElementById('pbar');const pbar=pct=>{if(!_pb)return;_pb.style.width=pct+'%';if(pct>=100){setTimeout(()=>{_pb.style.opacity='0';setTimeout(()=>{_pb.style.display='none';},400);},300);}};
let _reflineVal=null,_reflineLbl='';
let _idxBase=null;
const COLORS=['#1b7f3b','#e07a1f','#2b6cb0','#b83280','#6b46c1','#d69e2e','#0f766e','#be123c',
  '#0891b2','#7c3aed','#15803d','#c2410c','#1d4ed8','#9d174d','#7e22ce','#b45309',
  '#0e7490','#5b21b6','#166534','#9a3412'];
const RECESSIONS=[['1990-09-30','1991-03-31','1990-91'],['2001-03-31','2001-09-30','2001'],['2007-12-31','2009-06-30','GFC'],['2020-03-31','2020-12-31','COVID'],['2023-03-31','2023-06-30','Reg. Banking']];
const DK=()=>document.body.classList.contains('dark');
let _toastTmr;function showToast(msg,type='warn'){const t=document.getElementById('toast');t.textContent=msg;t.style.background=type==='err'?'#7f1d1d':type==='ok'?'#14532d':'#1a2638';t.classList.add('show');clearTimeout(_toastTmr);_toastTmr=setTimeout(()=>t.classList.remove('show'),2800);}
const ROSTER=new Map();for(const [rssd,nm] of BANKS)ROSTER.set(rssd,{nm});
const SCHED_NAMES={'HI':'HI — Income Statement','HI-A':'HI-A — Changes in Equity','HI-B':'HI-B — Charge-offs & Allowance','HI-C':'HI-C — Disaggregated Allowances','HC':'HC — Balance Sheet','HC-B':'HC-B — Securities','HC-C':'HC-C — Loans & Leases','HC-D':'HC-D — Trading','HC-E':'HC-E — Deposits','HC-F':'HC-F — Other Assets','HC-G':'HC-G — Other Liabilities','HC-H':'HC-H — Interest Sensitivity','HC-I':'HC-I — Insurance','HC-K':'HC-K — Quarterly Averages','HC-L':'HC-L — Off-Balance-Sheet','HC-M':'HC-M — Memoranda','HC-N':'HC-N — Past Due & Nonaccrual','HC-P':'HC-P — Mortgage Banking','HC-Q':'HC-Q — Fair Value','HC-R':'HC-R — Regulatory Capital','HC-S':'HC-S — Servicing/Securitization','HC-V':'HC-V — Variable-Interest Entities'};
const FORM_ORDER=['HI','HI-A','HI-B','HI-C','HC','HC-B','HC-C','HC-D','HC-E','HC-F','HC-G','HC-H','HC-I','HC-K','HC-L','HC-M','HC-N','HC-P','HC-Q','HC-R','HC-S','HC-V'];
// Y-9C total deposits has NO single MDRM code (unlike Call's RCON2200): it is the
// sum of domestic (BHDM) + foreign (BHFN) non-interest + interest-bearing deposits.
const DEP=['BHDM6631','BHDM6636','BHFN6631','BHFN6636'];
// Derived terms may be a bare 4-char base (coalesced across BHCK/BHDM/BHFN) OR an
// explicit full MDRM code (used directly). Deposits MUST use explicit codes so the
// domestic+foreign components are summed, not coalesced to just one.
const DERIV={
 'D_LOANSDEP':{type:'ratio',lbl:'Liquidity ▸ Loans / Deposits (%)',plus:['BHCK2122'],den:DEP},
 'D_DEPASSETS':{type:'ratio',lbl:'Funding ▸ Deposits / Assets (%)',plus:DEP,den:['BHCK2170']},
 'D_NPL':{type:'ratio',lbl:'Credit ▸ NPL % (Past Due + Non Accrual / loans)',plus:['BHCK1403','BHCK1406','BHCK1407'],den:['BHCK2122']},
 'D_NONCUR':{type:'ratio',lbl:'Credit ▸ Noncurrent ratio % (90+PD+nonaccrual / loans)',plus:['BHCK1403','BHCK1407'],den:['BHCK2122']},
 'D_RESLOANS':{type:'ratio',lbl:'Credit ▸ Reserves / Loans (%)',plus:['BHCK3123'],den:['BHCK2122']},
 'D_RESCOV':{type:'ratio',lbl:'Credit ▸ Reserve coverage of noncurrent (%)',plus:['BHCK3123'],den:['BHCK1403','BHCK1407']},
 'D_EQASSETS':{type:'ratio',lbl:'Capital ▸ Equity / Assets (%)',plus:['BHCK3210'],den:['BHCK2170']},
 'D_ROA':{type:'ratio',lbl:'Earnings ▸ Return on assets % (annualized, NI/assets)',plus:['BHCK4340'],den:['BHCK2170'],annualize:true},
 'D_ROE':{type:'ratio',lbl:'Earnings ▸ Return on equity % (annualized, NI/equity)',plus:['BHCK4340'],den:['BHCK3210'],annualize:true},
 'S_DEP':{type:'sum',lbl:'Subtotal ▸ Total deposits $ (BHDM+BHFN 6631/6636)',plus:DEP},
 'S_NPL':{type:'sum',lbl:'Subtotal ▸ Past-due + nonaccrual loans $ (30-89+90++nonaccrual)',plus:['BHCK1403','BHCK1406','BHCK1407']},
 'S_NONCUR':{type:'sum',lbl:'Subtotal ▸ Noncurrent loans $ (1403+1407)',plus:['BHCK1403','BHCK1407']},
 'D_NPL_CI':{type:'ratio',lbl:'Loan quality ▸ C&I NPL % (Past Due + Non Accrual / C&I loans)',plus:['BHCK1606','BHCK1607','BHCK1608'],den:['BHCK1763','BHCK1764']},
 'D_NPL_CC':{type:'ratio',lbl:'Loan quality ▸ Credit card NPL % (Past Due + Non Accrual / CC loans)',plus:['BHCKB575','BHCKB576','BHCKB577'],den:['BHCKB538']},
 'D_NPL_AUTO':{type:'ratio',lbl:'Loan quality ▸ Auto NPL % (Past Due + Non Accrual / auto loans)',plus:['BHCKK213','BHCKK214','BHCKK215'],den:['BHCKK137']},
 'D_NPL_CONS':{type:'ratio',lbl:'Loan quality ▸ Other consumer NPL % (Past Due + Non Accrual / other consumer)',plus:['BHCKK216','BHCKK217','BHCKK218'],den:['BHCKK207']},
 'D_NPL_AG':{type:'ratio',lbl:'Loan quality ▸ Agricultural NPL % (Past Due + Non Accrual / ag loans)',plus:['BHCK1594','BHCK1597','BHCK1583'],den:['BHCK1590']},
 'D_NPL_RES':{type:'ratio',lbl:'Loan quality ▸ 1-4 family RE NPL % (Past Due + Non Accrual / residential loans)',plus:['BHCK5398','BHCK5399','BHCK5400','BHCKC236','BHCKC237','BHCKC229','BHCKC238','BHCKC239','BHCKC230'],den:['BHDM1797','BHDM5367','BHDM5368']},
 'D_NPL_CONSTR':{type:'ratio',lbl:'Loan quality ▸ Construction & land NPL % (Past Due + Non Accrual / construction loans)',plus:['BHCKF172','BHCKF173','BHCKF174','BHCKF176','BHCKF175','BHCKF177'],den:['BHCKF158','BHCKF159']},
 'D_NPL_MULTI':{type:'ratio',lbl:'Loan quality ▸ Multifamily RE NPL % (Past Due + Non Accrual / multifamily loans)',plus:['BHCK3499','BHCK3500','BHCK3501'],den:['BHDM1460']},
 'D_NPL_CRE':{type:'ratio',lbl:'Loan quality ▸ CRE nonfarm nonres NPL % (Past Due + Non Accrual / CRE loans)',plus:['BHCKF178','BHCKF179','BHCKF180','BHCKF182','BHCKF181','BHCKF183'],den:['BHCKF160','BHCKF161']},
 'D_NIM':{type:'ratio',lbl:'Earnings ▸ Net interest margin % approx. (NII/assets, annualized)',plus:['BHCK4074'],den:['BHCK2170'],annualize:true},
 'D_EFF':{type:'ratio',lbl:'Earnings ▸ Efficiency ratio % (nonint expense / (NII+nonint income))',plus:['BHCK4093'],den:['BHCK4074','BHCK4079']},
 'D_NCO_LOANS_Y9C':{type:'ratio',lbl:'Credit ▸ NCO rate % (annualized, (charge-offs−recoveries)/loans)',plus:['BHCK4635'],minus:['BHCK4605'],den:['BHCK2122'],annualize:true},
};
const DYN={};   // dynamic subtotal measures created by clicking a grouping/total row in the tree
const USERCALC={};  // user-defined custom calculated series (session-only)
const DKIND=m=>(DERIV[m]||DYN[m]||USERCALC[m])?.type||null;const isPct=m=>DKIND(m)==='ratio'||(USERCALC[m]?.type==='expr'&&!!USERCALC[m]?.pct);
// HC-R raw codes that are RATIOS / PERCENTAGES (not $ thousands) — so they chart on the % axis
const PCTC=new Set(['BHCA7204','BHCAP793','BHCWP793','BHCA7206','BHCW7206','BHCA7205','BHCW7205',
 'BHCAH311','BHCWH311','BHCAH036','BHCALF23','BHCWLF23','BHCALF24','BHCWLF24','BHCALF25','BHCWLF25',
 'BHCWMK66','BHCALE85','BHCWLE85','BHCALE86','BHCWLE86','BHCALE87','BHCWLE87','BHCAMK76','BHCALF27',
 'BHCALF28','BHCALE89','BHCALE90','BHCALE91','BHCAKX78','BHCAKX83']);
const short=lbl=>{const i=lbl.indexOf('▸');return (i>=0?lbl.slice(i+1):lbl).replace(/\s*\(.*\)\s*$/,'').trim();};
function _esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
// wrap an end-of-line series label to <=maxc chars per line, capped at 4 lines (4th gets an ellipsis)
function _wrapLbl(t,maxc){t=String(t==null?'':t).trim();if(!t)return[''];const ws=t.split(/\s+/);const out=[];let cur='';for(const w of ws){const cand=cur?cur+' '+w:w;if(cand.length<=maxc||!cur){cur=cand;}else{out.push(cur);cur=w;}}if(cur)out.push(cur);if(out.length>4){const extra=out.slice(3).join(' ');out.length=3;out.push(extra.length>maxc?extra.slice(0,maxc-1)+'…':extra);}return out;}
const sqlList=a=>a.map(x=>`'${String(x).replace(/'/g,"''")}'`).join(',');
// MEDIUM-2: date-based quarter helpers — quarter strings are "YYYY-MM-DD" (end-of-quarter).
function prevQtr(q){if(!q)return null;const m=q.slice(5,7);return m==='03'?`${+q.slice(0,4)-1}-12-31`:m==='06'?`${q.slice(0,4)}-03-31`:m==='09'?`${q.slice(0,4)}-06-30`:`${q.slice(0,4)}-09-30`;}
function yoyQtr(q){return q?`${+q.slice(0,4)-1}${q.slice(4)}`:null;}
const fmtUnit=(v,pct)=>v==null?'—':pct?(+v).toFixed(2)+'%':(Math.abs(v)>=1e9?(v/1e9).toLocaleString(undefined,{maximumFractionDigits:2})+' T':Math.abs(v)>=1e6?(v/1e6).toLocaleString(undefined,{maximumFractionDigits:2})+' B':Math.abs(v)>=1e3?(v/1e3).toLocaleString(undefined,{maximumFractionDigits:1})+' M':Number(v).toLocaleString()+' k');

let conn,db,HIER=null,treeBuilt=false,sqlC=[],sqlR=[],ALLQ=[],SPLICEQ=[];
const SUB_AGG_DESCS={
  // ONLY schedules whose row-subtotal (sum ACROSS columns) is a meaningful ADDITIVE total:
  // columns must be mutually-exclusive partitions in the SAME unit, with NO redundant
  // "Total"/"Memo" column. Verified against panel + hierarchy (see ORCHESTRATION_STATE §68 v2).
  'HC-N':'Total Past Due & Nonaccrual',   // cols = 30-89d / 90+d / nonaccrual — mutually-exclusive states
  'HC-S':'Total Securitized',             // cols = collateral types (residential/HELOC/CC/auto/C&I/…) — exclusive
  'HC-V':'Total VIE Exposure',            // cols = securitization vehicles / other VIEs — exclusive
  // NOT clean column-sum matrices (header-sum would double-count or mix units → plain roll-up, no descriptor):
  //   HC-Q : each row carries a "Total fair value" column PLUS Level 1/2/3 → sum ≈ 2× total (G478/G483 populated)
  //   HC-R : Part I rows are single-$ capital line items (a roll-up, not a matrix); Part II "approach" columns
  //          (non-advanced / advanced / standardized) are mutually-exclusive frameworks → summing double-counts
  //   HI-B : cols = charge-offs / recoveries; the real metric is NET (CO − Rec), not the sum of the two
  //   HC-B : cols = {HTM,AFS}×{amortized cost, fair value} crosstab → sum values the same securities twice
  //   HC-C (Consolidated⊇Domestic), HC-L (mixed col structures), HI-C (cost + allowance) — roll-up
};
const _fullCap=new Map();
function _walkFC(nodes,parts,sch){for(const nd of nodes){if(!nd.placeholder&&!nd.derived&&!nd.header&&nd.code&&!/^(H:|SEC:|SUB:|EMPTY:)/.test(nd.code)){const cap=nd.caption||'';const anc=parts.filter(Boolean);if(!nd.col||!_fullCap.has(nd.code))_fullCap.set(nd.code,anc.length?anc.join(' — ')+' — '+cap:cap);}if(nd.header&&nd.code){const _sn=sch&&SCHED_NAMES[sch]?SCHED_NAMES[sch]:(parts.length?parts[0]:'');const _si=_sn.indexOf(' — ');const _sk=_si>=0?_sn.slice(0,_si):_sn;const _agg=sch?SUB_AGG_DESCS[sch]||'':'';const _cnt=(function c(n){let k=0;for(const x of(n.children||[])){if(x.header)k+=c(x);else if(x.code&&!x.placeholder&&!/^(H:|SEC:|SUB:|EMPTY:)/.test(x.code))k++;}return k;})(nd);if(_cnt>0){const _rl=_agg?_sk+' '+_agg+': '+(nd.caption||''):_sk?_sk+' '+(nd.caption||''):(nd.caption||'');_fullCap.set('SUB:'+nd.code,_rl);if(!/^(H:|SEC:|EMPTY:)/.test(nd.code)&&!_fullCap.has(nd.code))_fullCap.set(nd.code,_rl);}}if(nd.children&&nd.children.length)_walkFC(nd.children,nd.header?[...parts,nd.caption||'']:parts,sch);}}
function fullCap(code){return _fullCap.get(code)||'';}
let active=[],measures=[],peerMembers=[],peers={},lastSeries=[],Qall=[],rangeSel={a:0,b:0};
// chart UI prefs: inline end-of-line labels on/off + persisted drag-resized chart size (px)
window._inlineLbls=true;window._chartW=0;window._chartH=0;
try{window._inlineLbls=localStorage.getItem('fry9c_inlinelbls')!=='0';const _cs=localStorage.getItem('fry9c_chartsize');if(_cs){const _m=_cs.split('x');window._chartW=+_m[0]||0;window._chartH=+_m[1]||0;}}catch(_){}
let aggLoaded=false,oldActiveLoaded=false,histLoaded=false,histLoading=null,oldActiveLoading=null,oldActiveError=false,histError=false;
let _loadedParts=[...PARTS];
function loadPeers(){try{peers=JSON.parse(localStorage.getItem('fry9c_peers')||'{}');}catch{peers={};}}
function savePeers(){localStorage.setItem('fry9c_peers',JSON.stringify(peers));}
async function _rebuildView(){
  await conn.query(`CREATE OR REPLACE VIEW t AS SELECT * FROM read_parquet([${_loadedParts.map(p=>`'${p}'`).join(',')}])`);
  _seriesCache.clear();_inflight.clear();}
function _showPanesLoading(msg){const ph=document.getElementById('panes');if(ph)ph.innerHTML=`<p class="muted" style="padding:30px;text-align:center;font-size:14px">⧖ ${msg}</p>`;}
async function ensureOldActive(){
  if(oldActiveLoaded||oldActiveError||!OLD_ACTIVE_PARTS.length)return;
  if(oldActiveLoading)return oldActiveLoading;
  oldActiveLoading=(async()=>{
    const prev=document.getElementById('status').textContent;st('Loading older series data…');_showPanesLoading('Loading older data series…');
    try{for(const p of OLD_ACTIVE_PARTS){await db.registerFileURL(p,new URL(p,location.href).href,duckdb.DuckDBDataProtocol.HTTP,false);_loadedParts.push(p);}
    await _rebuildView();oldActiveLoaded=true;
    // Quarter list comes from the buffered agg shard (has all quarters) so we DON'T full-scan the
    // just-loaded range-request lazy shards (a `DISTINCT quarter_end FROM t` would read every row group).
    ALLQ=(await conn.query(`SELECT DISTINCT quarter_end FROM ${aggLoaded?'t_agg':'t'} ORDER BY quarter_end`)).toArray().map(r=>String(r.quarter_end));
    const lhb=document.getElementById('loadhist');if(lhb)lhb.style.display='none';
    st(prev);recompute();}catch(e){oldActiveError=true;oldActiveLoading=null;st('Could not load older data');const ph=document.getElementById('panes');if(ph)ph.innerHTML=`<p class="muted" style="padding:30px;text-align:center;font-size:14px">⚠ Could not load older data — ${String(e).slice(0,200)}</p>`;}})();
  return oldActiveLoading;}
async function ensureHist(){
  if(histLoaded||histError||!HIST_PARTS.length)return;
  if(histLoading)return histLoading;
  histLoading=(async()=>{
    const prev=document.getElementById('status').textContent;st('Loading historical filer data…');_showPanesLoading('Loading historical data for inactive / predecessor filers…');
    try{for(const p of HIST_PARTS){await db.registerFileURL(p,new URL(p,location.href).href,duckdb.DuckDBDataProtocol.HTTP,false);_loadedParts.push(p);}
    await _rebuildView();histLoaded=true;st(prev);recompute();}
    catch(e){histError=true;histLoading=null;st('Could not load historical data');const ph=document.getElementById('panes');if(ph)ph.innerHTML=`<p class="muted" style="padding:30px;text-align:center;font-size:14px">⚠ Could not load historical data — ${String(e).slice(0,200)}</p>`;}})();
  return histLoading;}
function stateToHash(){
  const params=new URLSearchParams();
  if(active.length)params.set('e',active.map(a=>a.id).join(','));
  if(measures.length)params.set('m',measures.filter(m=>!m.code.startsWith('CALC_')).map(m=>m.code).join(','));
  if(Qall.length){params.set('q0',Qall[rangeSel.a]||'');params.set('q1',Qall[rangeSel.b]||'');}
  history.replaceState(null,'','#'+params.toString());}
function hashToState(){
  if(!location.hash||location.hash==='#')return false;
  try{const p=new URLSearchParams(location.hash.slice(1));
    const eStr=p.get('e');if(eStr){active=eStr.split(',').filter(Boolean).map(id=>({id,label:elabel(id)}));}
    const mStr=p.get('m');if(mStr){measures=[];for(const code of mStr.split(',').filter(Boolean)){
      const d=DERIV[code]||DYN[code]||USERCALC[code];const lbl=d?d.lbl:(fullCap(code)||code);const pct=isPct(code)||PCTC.has(code);
      if(measures.length<20)measures.push({code,label:lbl,pct:!!pct});}}
    const q0=p.get('q0'),q1=p.get('q1');
    if(q0&&q1&&Qall.length){const a=Qall.indexOf(q0),b=Qall.indexOf(q1);
      if(a>=0&&b>=0)rangeSel={a:Math.min(a,b),b:Math.max(a,b)};}
    return !!(eStr||mStr);}catch{return false;}}
function elabel(id){if(id==='ALL')return 'ALL';if(id.startsWith('PEER:'))return '★ '+id.slice(5);
 if(id.startsWith('BANK:')){const r=ROSTER.get(+id.slice(5));return r?`${r.nm} (${id.slice(5)})`:id;}return id;}
function resolveEnt(){const v=document.getElementById('ent').value.trim();
 if(v.replace(/^★\s*/,'') in peers){const n=v.replace(/^★\s*/,'');return {id:'PEER:'+n,label:'★ '+n};}
 if(/^all\b/i.test(v)||v.toUpperCase()==='ALL')return {id:'ALL',label:'ALL'};
 const m=v.match(/(\d{3,})/);if(m)return bankEnt(+m[1]);return null;}
// when linking, any predecessor RSSD resolves to the lineage's LATEST RSSD + latest name (dedup + mirror name)
function canonRssd(r){const L=LINK&&LINEAGE[r];return L?L.m[L.m.length-1]:r;}
function bankEnt(r){const c=canonRssd(r);return {id:'BANK:'+c,label:elabel('BANK:'+c)};}
function lineageMembers(r){const L=LINEAGE[r];return (LINK&&L)?L.m:[r];}   // r + predecessor RSSDs, non-overlapping in time
let TOPMODE='top';   // 'top' = ALL means top-tier holders only (no nested double-count); 'all' = every filer
const _seriesCache=new Map(),_inflight=new Map();
// ALL scope: optionally exclude holding companies that are themselves controlled by another Y-9C
// filer in the same quarter (nested-filer double-count). NESTED is a per-quarter exclusion map
// {quarter_end:[rssd,...]} built from the NIC relationships file; correlated against the outer
// table `t` so the filter is exact per quarter.
function allCond(){
 if(TOPMODE!=='top'||!NESTED||!Object.keys(NESTED).length)return '1=1';
 return 'NOT EXISTS (SELECT 1 FROM nested n WHERE n.quarter_end=t.quarter_end AND n.id_rssd=t.id_rssd)';}
function scopeCond(id){if(id==='ALL')return allCond();
 if(id.startsWith('BANK:'))return `id_rssd IN (${lineageMembers(+id.slice(5)).join(',')})`;
 if(id.startsWith('PEER:'))return `id_rssd IN (${(peers[id.slice(5)]||[-1]).join(',')})`;return null;}
// percentage/rate cells (PCTC) are NON-ADDITIVE: summing them across entities is meaningless.
// A raw HC-R ratio (not a curated DERIV/DYN) may only be charted for a SINGLE filing entity.
const peerSize=id=>id.startsWith('PEER:')?(new Set(peers[id.slice(5)]||[]).size):1;
const isAggScope=id=>id==='ALL'||(id.startsWith('PEER:')&&peerSize(id)>1);
const isRawPct=m=>PCTC.has(m)&&!DERIV[m]&&!DYN[m]&&!USERCALC[m];
function parseCalcExpr(str,aliases){
  const s=str.trim();if(!s)throw'Formula is empty.';
  const toks=[];let i=0;
  while(i<s.length){
    if(/\s/.test(s[i])){i++;continue;}
    const c=s[i];
    if(c==='('){toks.push({t:'lp'});i++;}
    else if(c===')'){toks.push({t:'rp'});i++;}
    else if(c==='+'){toks.push({t:'op',v:'+',p:1});i++;}
    else if(c==='-'){
      const prev=toks.length?toks[toks.length-1]:null;
      if(!prev||prev.t==='lp'||prev.t==='op')toks.push({t:'num',v:0});
      toks.push({t:'op',v:'-',p:1});i++;}
    else if(c==='*'||c==='×'){toks.push({t:'op',v:'*',p:2});i++;}
    else if(c==='/'||c==='÷'){toks.push({t:'op',v:'/',p:2});i++;}
    else if(/\d/.test(c)){let n='';while(i<s.length&&/[\d.]/.test(s[i]))n+=s[i++];toks.push({t:'num',v:parseFloat(n)});}
    else if(/[A-Za-z]/.test(c)){
      let n='';while(i<s.length&&/[A-Za-z0-9]/.test(s[i]))n+=s[i++];
      const up=n.toUpperCase();
      if(/^[A-Z]{4}\d{4,}$/.test(up))toks.push({t:'var',v:up});
      else if(/^[A-Z]$/.test(up)){
        if(!aliases[up])throw`Letter "${up}" not in pick-list — add that measure first.`;
        toks.push({t:'var',v:up});}
      else throw`Unknown token "${n}". Use A–Z from the pick-list or a MDRM code.`;}
    else throw`Unexpected character "${c}".`;}
  const out=[],ops=[];
  for(const tok of toks){
    if(tok.t==='num'||tok.t==='var')out.push(tok);
    else if(tok.t==='op'){
      while(ops.length&&ops[ops.length-1].t==='op'&&ops[ops.length-1].p>=tok.p)out.push(ops.pop());
      ops.push(tok);}
    else if(tok.t==='lp')ops.push(tok);
    else if(tok.t==='rp'){
      while(ops.length&&ops[ops.length-1].t!=='lp')out.push(ops.pop());
      if(!ops.length)throw'Mismatched parentheses.';
      ops.pop();}}
  while(ops.length){if(ops[ops.length-1].t==='lp')throw'Mismatched parentheses.';out.push(ops.pop());}
  const stk=[];
  for(const tok of out){
    if(tok.t==='num'||tok.t==='var')stk.push(tok);
    else{if(stk.length<2)throw'Invalid expression — each operator needs two operands.';
      const R=stk.pop(),L=stk.pop();stk.push({t:'op',v:tok.v,L,R});}}
  if(stk.length!==1)throw'Invalid expression.';
  const ast=stk[0];
  (function _z(n){if(n.t==='op'){if(n.v==='/'&&n.R.t==='num'&&n.R.v===0)throw'Division by zero.';_z(n.L);_z(n.R);}})(ast);
  function _hd(n){return n.t==='op'&&(n.v==='/'||_hd(n.L)||_hd(n.R));}
  const vars={};
  function _wk(n){
    if(n.t==='var'){const code=/^[A-Z]{4}\d/.test(n.v)?n.v:(aliases[n.v]||null);
      if(!code)throw`Variable "${n.v}" has no mapped code.`;vars[n.v]=code;}
    else if(n.t==='op'){_wk(n.L);_wk(n.R);}}
  _wk(ast);
  return {ast,pct:_hd(ast),vars};}
function evalCalcAST(node,env){
  if(node.t==='num')return node.v;
  if(node.t==='var'){const v=env[node.v];return v==null?null:Number(v);}
  if(node.t==='op'){
    const L=evalCalcAST(node.L,env),R=evalCalcAST(node.R,env);
    if(L==null||R==null)return null;
    if(node.v==='+')return L+R;if(node.v==='-')return L-R;
    if(node.v==='*')return L*R;if(node.v==='/')return R===0?null:L/R;}
  return null;}
function refreshCalcPicklist(){
  const tbody=document.getElementById('calc-picklist');if(!tbody)return;
  const AL='ABCDEFGHIJKLMNOPQRSTUVWXYZ';let h='';
  for(let i=0;i<Math.min(measures.length,26);i++){
    const m=measures[i];const lbl=m.label||fullCap(m.code)||m.code;
    h+=`<tr><td style="font-weight:700;padding:1px 8px 1px 0;color:var(--accent,#2b6cb0)">${AL[i]}</td><td style="color:var(--muted,#9aa3b2);padding:1px 8px 1px 0;font-family:monospace;font-size:12px">${m.code}</td><td style="color:var(--fg,#14213d)">${lbl}</td></tr>`;}
  tbody.innerHTML=h||'<tr><td colspan="3" style="color:var(--muted,#9aa3b2);font-style:italic">Add measures to the chart first, then open Σ Calc.</td></tr>';}
function searchHier(q){const q2=q.toLowerCase();const seen=new Set();const res=[];
 if(HIER)for(const sch of Object.keys(HIER))for(const r of (HIER[sch]||[])){
  if(!r.mdrm||seen.has(r.mdrm))continue;seen.add(r.mdrm);
  if((r.mdrm||'').toLowerCase().includes(q2)||(r.caption||'').toLowerCase().includes(q2))res.push({m:r.mdrm,c:r.caption||''});}
 for(const k of Object.keys(DERIV)){if(seen.has(k))continue;seen.add(k);
  const d=DERIV[k];if((k||'').toLowerCase().includes(q2)||(d.lbl||'').toLowerCase().includes(q2))res.push({m:k,c:d.lbl||''});}
 return res.slice(0,40);}
function coalesce(map,base){return map['BHCK'+base]??map['BHDM'+base]??map['BHFN'+base];}
// A derived "term" is either a full 8-char MDRM code (BHCK2122 -> used directly) or a
// bare 4-char base (2122 -> coalesced across BHCK/BHDM/BHFN, as Call/002 do).
const isFullCode=t=>/^BH[A-Z]{2}/.test(t);
const term2codes=t=>isFullCode(t)?[t]:['BHCK'+t,'BHDM'+t,'BHFN'+t];
const termVal=(mp,t)=>isFullCode(t)?(mp[t]??null):coalesce(mp,t);

async function seriesFor(id,m){const cond=scopeCond(id);if(cond==null)return [];
 // Lazy-load the right shard based on entity type before cache/query
 if(id.startsWith('BANK:')){
   const rssd=+id.slice(5);const members=lineageMembers(rssd);
   const isActive=members.some(r=>ACTIVE_RSSDS.has(r));
   if(isActive&&!oldActiveLoaded)await ensureOldActive();
   else if(!isActive&&!histLoaded)await ensureHist();
   if(isActive&&LINK&&!histLoaded){const L=LINEAGE[rssd];if(L&&L.m.some(r=>!ACTIVE_RSSDS.has(r)))await ensureHist();}
 }else if(id.startsWith('PEER:')){
   const pr=peers[id.slice(5)]||[];
   if(pr.some(r=>!ACTIVE_RSSDS.has(r))&&!histLoaded)await ensureHist();
   if(pr.some(r=>ACTIVE_RSSDS.has(r))&&!oldActiveLoaded)await ensureOldActive();}
 const _sk=`${id}::${m}::${TOPMODE}`;if(_seriesCache.has(_sk))return _seriesCache.get(_sk);
 if(_inflight.has(_sk))return _inflight.get(_sk);
 const _p=(async()=>{
 let d=DERIV[m]||DYN[m]||USERCALC[m];
 if(d?.type==='expr'){
   const vSer={};
   for(const[vn,vc]of Object.entries(d.vars))vSer[vn]=Object.fromEntries(await seriesFor(id,vc));
   const qSet=new Set();for(const rows of Object.values(vSer))Object.keys(rows).forEach(q=>qSet.add(q));
   const out=[];
   for(const q of[...qSet].sort()){
     const env={};for(const[vn,qmap]of Object.entries(vSer))env[vn]=qmap[q]??null;
     try{let v=evalCalcAST(d.ast,env);if(v!=null){if(d.pct)v=v*100;out.push([q,v]);}}catch(e){}}
   _seriesCache.set(_sk,out);return out;}
 // For ALL with pre-agg loaded (TOPMODE=top): route through t_agg for instant results
 if(id==='ALL'&&aggLoaded&&TOPMODE==='top'){
   if(d&&!DYN[m]&&!USERCALC[m]){
     const terms=[...d.plus,...(d.minus||[]),...(d.den||[])];
     const codes=[...new Set(terms.flatMap(term2codes))];
     const r=(await conn.query(`SELECT quarter_end,mdrm,value v FROM t_agg WHERE mdrm IN (${sqlList(codes)}) ORDER BY quarter_end`)).toArray();
     const byq={};for(const x of r){(byq[x.quarter_end]=byq[x.quarter_end]||{})[x.mdrm]=Number(x.v);}
     const acc2=(mp,arr)=>{let s=0,seen=false;for(const t of arr){const v=termVal(mp,t);if(v!=null){s+=v;seen=true;}}return [s,seen];};
     const out=[];for(const q of Object.keys(byq).sort()){const mp=byq[q];
       const [np,ns]=acc2(mp,d.plus);const [nm,ms]=acc2(mp,d.minus||[]);const num=np-nm;
       const [dp,ds]=acc2(mp,d.den||[]);const den=dp;
       if(d.type==='sum'){if(ns||ms)out.push([q,num]);}
       else if((ns||ms)&&ds&&den>0){let val=100*num/den;
         if(d.annualize){const qn={'03':1,'06':2,'09':3,'12':4}[String(q).slice(5,7)];if(qn)val*=4/qn;}
         out.push([q,val]);}}
     _seriesCache.set(_sk,out);return out;}
   if(!d){
     if(isRawPct(m))return [];
     const r=(await conn.query(`SELECT quarter_end,value v FROM t_agg WHERE mdrm='${m}' ORDER BY quarter_end`)).toArray();
     const res=r.map(x=>[String(x.quarter_end),Number(x.v)]);_seriesCache.set(_sk,res);return res;}}
 if(d){const terms=[...d.plus,...(d.minus||[]),...(d.den||[])];
   const codes=[];for(const t of terms)for(const c of term2codes(t))codes.push(c);
   const r=(await conn.query(`SELECT id_rssd,quarter_end,mdrm,value FROM t WHERE ${cond} AND mdrm IN (${sqlList(codes)})`)).toArray();
   const byqe={};for(const x of r){((byqe[x.quarter_end]=byqe[x.quarter_end]||{})[x.id_rssd]=byqe[x.quarter_end][x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const acc=(mp,arr)=>{let s=0,seen=false;for(const t of arr){const v=termVal(mp,t);if(v!=null){s+=v;seen=true;}}return [s,seen];};
   const out=[];for(const q of Object.keys(byqe).sort()){let num=0,den=0,anyN=false,anyD=false;
     for(const id2 of Object.keys(byqe[q])){const mp=byqe[q][id2];
       const [np,ns]=acc(mp,d.plus);const [nm,ms]=acc(mp,d.minus||[]);num+=np-nm;if(ns||ms)anyN=true;
       const [dp,ds]=acc(mp,d.den||[]);den+=dp;if(ds)anyD=true;}
     if(d.type==='sum'){if(anyN)out.push([q,num]);}
     else if(anyN&&anyD&&den>0){let val=100*num/den;
       if(d.annualize){const qn={'03':1,'06':2,'09':3,'12':4}[String(q).slice(5,7)];if(qn)val*=4/qn;}
       out.push([q,val]);}}
   _seriesCache.set(_sk,out);return out;}
 // HIGH-2: a raw percentage/rate cell is non-additive — never SUM it across a multi-entity aggregate.
 if(isRawPct(m)&&isAggScope(id))return [];
 const r=(await conn.query(`SELECT quarter_end, SUM(value) v FROM t WHERE ${cond} AND mdrm='${m}' GROUP BY quarter_end ORDER BY quarter_end`)).toArray();
 const res=r.map(x=>[String(x.quarter_end),Number(x.v)]);_seriesCache.set(_sk,res);return res;})();
 _inflight.set(_sk,_p);_p.then(()=>_inflight.delete(_sk),()=>_inflight.delete(_sk));return _p;}

async function init(){try{
 pbar(5);
 const B=duckdb.getJsDelivrBundles(),b=await duckdb.selectBundle(B);
 const w=await duckdb.createWorker(b.mainWorker);db=new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(),w);
 await db.instantiate(b.mainModule,b.pthreadWorker);conn=await db.connect();pbar(20);
 // Load recent active shard (primary: filers who reported in the latest quarter, ~20 MB)
 const _totParts=PARTS.length+AGG_PARTS.length;let _doneP=0;
 for(const p of PARTS){const r=await fetch(new URL(p,location.href).href);if(!r.ok)throw new Error(p+' HTTP '+r.status);
   await db.registerFileBuffer(p,new Uint8Array(await r.arrayBuffer()));_doneP++;pbar(20+60*_doneP/_totParts);}
 await conn.query(`CREATE VIEW t AS SELECT * FROM read_parquet([${_loadedParts.map(p=>`'${p}'`).join(',')}])`);
 // Load ALL pre-agg shard (~2 MB): enables instant aggregate queries without raw data
 if(AGG_PARTS.length){
   for(const p of AGG_PARTS){const r=await fetch(new URL(p,location.href).href);if(!r.ok)throw new Error(p+' HTTP '+r.status);
     await db.registerFileBuffer(p,new Uint8Array(await r.arrayBuffer()));_doneP++;pbar(20+60*_doneP/_totParts);}
   await conn.query(`CREATE VIEW t_agg AS SELECT * FROM read_parquet([${AGG_PARTS.map(p=>`'${p}'`).join(',')}])`);
   aggLoaded=true;}
 // nested-filer exclusion table for the ALL aggregate (HIGH-1): holding companies that are themselves
 // controlled by another Y-9C filer in the same quarter, so they must not be double-counted in ALL.
 await conn.query('CREATE TABLE nested(quarter_end VARCHAR, id_rssd BIGINT)');
 {const vals=[];for(const q in NESTED)for(const r of NESTED[q])vals.push(`('${q}',${+r})`);
  if(vals.length){for(let i=0;i<vals.length;i+=1000)await conn.query('INSERT INTO nested VALUES '+vals.slice(i,i+1000).join(','));}
  window._nestedN=vals.length;}
 // ALLQ from pre-agg (full history for active filers) so slider shows all quarters from start
 ALLQ=(await conn.query(`SELECT DISTINCT quarter_end FROM ${aggLoaded?'t_agg':'t'} ORDER BY quarter_end`)).toArray().map(r=>String(r.quarter_end));
 {const maxQ=ALLQ[ALLQ.length-1];if(maxQ){const dc=document.getElementById('datacur');if(dc)dc.textContent=` · data through ${maxQ}`;}}
 pbar(85);loadPeers();rebuildEntList();
 try{const hr=await fetch(new URL('fry9c_hierarchy.json',location.href).href);if(hr.ok)HIER=await hr.json();}catch(e){}
 document.getElementById('ent').value='ALL';
 {const ln=document.getElementById('linkrssd'),cnt=document.getElementById('linkn');
  if(cnt)cnt.textContent=new Set(Object.values(LINEAGE).map(l=>l.l)).size;
  if(ln)ln.onchange=()=>{LINK=ln.checked;scheduleRecompute();};}
 {const nb=document.getElementById('inclnested'),nc=document.getElementById('nestedn');
  if(nc)nc.textContent=new Set(Object.values(NESTED||{}).flat()).size;
  if(nb)nb.onchange=()=>{TOPMODE=nb.checked?'all':'top';_seriesCache.clear();scheduleRecompute();};}
 document.getElementById('add').onclick=()=>{const e=resolveEnt();if(!e)return;if(!active.find(a=>a.id===e.id))active.push(e);renderChips();scheduleRecompute();};
 document.getElementById('addpeer').onclick=()=>{const e=resolveEnt();if(!e)return;if(!e.id.startsWith('BANK:')){showToast('Peer members must be holding companies.');return;}const rssd=+e.id.slice(5);if(!peerMembers.find(a=>a.rssd===rssd))peerMembers.push({rssd,label:e.label});renderPeerBuilder();document.getElementById('peerbox').open=true;};
 document.getElementById('savepeer').onclick=savePeer;document.getElementById('clearpeer').onclick=()=>{peerMembers=[];renderPeerBuilder();};
 document.getElementById('treesearch').addEventListener('input',e=>filterTree(e.target.value));
 document.getElementById('treesearch').addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';filterTree('');e.target.blur();}else if(e.key==='Enter'){const vis=[...document.querySelectorAll('#tree .trow')].filter(r=>r.style.display!=='none');if(vis.length)vis[0].click();}});
 document.getElementById('entsearch').addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';renderEntList();e.target.blur();}else if(e.key==='Enter'){const r=document.querySelector('#entlistpanel .erow');if(r)r.querySelector('.en').click();}});
 document.getElementById('expall').onclick=()=>expandAll(true);document.getElementById('colall').onclick=()=>expandAll(false);
 document.getElementById('jumpto').onclick=()=>{
   const on=document.querySelector('#tree .trow.on');if(!on)return;
   on.scrollIntoView({block:'nearest',behavior:'smooth'});
   on.style.outline='2px solid #1b7f3b';setTimeout(()=>on.style.outline='',800);};
 document.getElementById('drilldn').onclick=()=>drillSmart(1);document.getElementById('drillup').onclick=()=>drillSmart(-1);
 document.getElementById('tabItems').onclick=()=>switchTab(true);document.getElementById('tabEnts').onclick=()=>switchTab(false);
 document.getElementById('entsearch').addEventListener('input',renderEntList);
 document.getElementById('entfilter').onchange=renderEntList;document.getElementById('entsort').onchange=renderEntList;document.getElementById('entdesc').onchange=renderEntList;
 document.getElementById('showmerged').onchange=async()=>{if(document.getElementById('showmerged').checked&&HIST_PARTS.length&&!histLoaded)await ensureHist();renderEntList();};
 document.addEventListener('keydown',e=>{if(e.target.closest('input,textarea,select'))return;if(e.key===']'||e.key==='.')  {e.preventDefault();drillSmart(1);}if(e.key==='['||e.key===','){e.preventDefault();drillSmart(-1);}if(e.key==='/'){e.preventDefault();const ts=document.getElementById('treesearch');ts.focus();ts.select();}if(e.key==='l'||e.key==='L'){e.preventDefault();openLeague();}if((e.key==='r'||e.key==='R')&&active.length===1&&active[0].id.startsWith('BANK:')){e.preventDefault();openReport(active[0].id);}if(e.key==='?'){e.preventDefault();document.getElementById('kbdmodal').style.display='flex';}if(e.key==='i'||e.key==='I'){e.preventDefault();switchTab(true);}if(e.key==='e'||e.key==='E'){e.preventDefault();switchTab(false);}if(e.key==='Escape'){document.querySelectorAll('.modal').forEach(m=>{if(m.style.display&&m.style.display!=='none')m.style.display='none';});}});
 if(localStorage.getItem('fry9c_theme')==='light')document.body.classList.remove('dark');
 const setLbl=()=>document.getElementById('theme').textContent=DK()?'☀ Light':'🌙 Dark';setLbl();
 document.getElementById('theme').onclick=()=>{const d=document.body.classList.toggle('dark');localStorage.setItem('fry9c_theme',d?'dark':'light');setLbl();draw();};
 (function(){const app=document.querySelector('.app'),rail=document.querySelector('.rail'),head=rail.querySelector('.railtabs');
  document.getElementById('popout').onclick=ev=>{ev.stopPropagation();const f=rail.classList.toggle('floating');app.classList.toggle('popped',f);document.getElementById('popout').textContent=f?'⧈ Dock':'⧉ Pop out';};
  let dx=0,dy=0,drag=false;head.addEventListener('mousedown',e=>{if(!rail.classList.contains('floating'))return;if(e.target.closest('input,button,label'))return;drag=true;dx=e.clientX-rail.offsetLeft;dy=e.clientY-rail.offsetTop;e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;rail.style.left=(e.clientX-dx)+'px';rail.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('entdetach').onclick=()=>{entFloating?dockEnts():detachEnts();};
 (function(){const p=document.getElementById('panelEnts'),h=p.querySelector('.railhead');let dx=0,dy=0,drag=false;
  h.addEventListener('mousedown',e=>{if(!entFloating)return;if(e.target.closest('input,button,select,label'))return;drag=true;dx=e.clientX-p.offsetLeft;dy=e.clientY-p.offsetTop;p.style.right='auto';e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;p.style.left=(e.clientX-dx)+'px';p.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('ffrom').onchange=renderForm;document.getElementById('fto').onchange=renderForm;
 document.getElementById('fexp').onclick=()=>expandAll(true,'#formbody');document.getElementById('fcol').onclick=()=>expandAll(false,'#formbody');
 document.getElementById('fdn').onclick=()=>drillSmart(1,'#formbody');document.getElementById('fup').onclick=()=>drillSmart(-1,'#formbody');
 document.getElementById('frow-filter').oninput=function(){const q=this.value;const el=document.getElementById('frow-coderes');if(q.length>=2){const res=searchHier(q);if(res.length){el.innerHTML=res.map(r=>`<div class="frow-cr" data-m="${r.m}" style="padding:3px 8px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:inherit" title="${r.c}"><b>${r.m}</b> — ${r.c}</div>`).join('');el.style.display='block';el.querySelectorAll('.frow-cr').forEach(d=>d.onclick=()=>{document.getElementById('frow-filter').value=d.dataset.m;el.style.display='none';const qm=d.dataset.m.toLowerCase();document.querySelectorAll('#formbody .frow').forEach(r=>{const lab=r.querySelector('.lab');if(!lab)return;r.style.display=lab.textContent.toLowerCase().includes(qm)?'':'none';});});}else el.style.display='none';}else el.style.display='none';const qlo=q.toLowerCase();document.querySelectorAll('#formbody .frow').forEach(r=>{const lab=r.querySelector('.lab');if(!lab)return;const txt=lab.textContent.toLowerCase();const show=!qlo||txt.includes(qlo);r.style.display=show?'':'none';});};
 document.getElementById('ffull').onclick=()=>{const qs=window._fq||[];if(qs.length){document.getElementById('ffrom').value=qs[0];document.getElementById('fto').value=qs[qs.length-1];}renderForm();};
 document.getElementById('fent-add').onclick=()=>{const v=document.getElementById('fent-inp').value.trim();if(!v)return;const m=v.match(/(\d{3,})/);if(m){const be=bankEnt(+m[1]);if(be){window._feEnts=window._feEnts||[];if(!window._feEnts.find(e=>e.id===be.id)){window._feEnts.push({id:be.id,label:be.label});renderFentChips();renderForm();}}document.getElementById('fent-inp').value='';}};
 document.getElementById('fent-cur').onclick=()=>{window._feEnts=window._feEnts||[];for(const e of active){if(e.id.startsWith('BANK:')&&!window._feEnts.find(x=>x.id===e.id))window._feEnts.push({id:e.id,label:e.label});}renderFentChips();renderForm();};
 (function(){const md=document.getElementById('formmodal'),box=md.querySelector('.modalbox'),head=md.querySelector('.modalhead');
  document.getElementById('fpop').onclick=()=>md.classList.toggle('float');
  let dx=0,dy=0,drag=false;head.addEventListener('mousedown',e=>{if(!md.classList.contains('float'))return;if(e.target.closest('input,button,select,label'))return;drag=true;dx=e.clientX-box.offsetLeft;dy=e.clientY-box.offsetTop;e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;box.style.left=(e.clientX-dx)+'px';box.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('formbtn').onclick=openForm;document.getElementById('formclose').onclick=()=>{document.getElementById('formmodal').style.display='none';window._feEnts=[];};
 document.getElementById('leaguebtn').onclick=openLeague;document.getElementById('lgclose').onclick=()=>document.getElementById('leaguemodal').style.display='none';
 document.getElementById('lgmeasure').onchange=renderLeague;document.getElementById('lgquarter').onchange=renderLeague;document.getElementById('lgtopn').onchange=renderLeague;document.getElementById('lgbucket').onchange=renderLeague;
 document.getElementById('lgexport').onclick=()=>{if(!window._lg)return;const pm=window._lg.pctileMap||new Map();dl2(['rank','rssd','holding_company',window._lg.meas.label,'QoQ','YoY','percentile'],window._lg.rows.map((r,i)=>[i+1,r.rssd,r.name,r.v,r.qoq,r.yoy,pm.get(r.rssd)??'']),'league');};
 document.getElementById('reportbtn').onclick=()=>{if(active.length===1&&active[0].id.startsWith('BANK:'))openReport(active[0].id);};
 document.getElementById('rptclose').onclick=()=>{document.getElementById('reportmodal').style.display='none';const p=new URLSearchParams(location.hash.slice(1));p.delete('report');history.replaceState(null,'','#'+p.toString());};
 document.getElementById('rpt-print').onclick=rptPrint;
 document.getElementById('rpt-html').onclick=()=>{const b=document.getElementById('rptbody');if(!b)return;const title=document.getElementById('rpt-title')?.textContent||'entity_report';const css=`<style>body{font-family:system-ui,sans-serif;margin:20px;background:#fff;color:#111}h3{margin:14px 0 6px}table{border-collapse:collapse}td,th{padding:3px 6px;border-bottom:1px solid #ddd}.muted{color:#666}</style>`;const html=`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>${css}</head><body>${b.innerHTML}</body></html>`;const bl=new Blob([html],{type:'text/html'});const a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download=(title.replace(/\s+/g,'_').replace(/[^\w_-]/g,'')||'report')+'.html';a.click();};
 document.getElementById('rpt-link').onclick=()=>{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(location.href).then(()=>showToast('Link copied!','ok')).catch(()=>prompt('Copy this link:',location.href));}else{prompt('Copy this link:',location.href);}};
 document.getElementById('exportbtn').onclick=openExportBuilder;
 document.getElementById('copylink').onclick=()=>{const b=document.getElementById('copylink');navigator.clipboard.writeText(location.href).then(()=>{const t=b.textContent;b.textContent='✓ Copied!';setTimeout(()=>b.textContent=t,2000);}).catch(()=>showToast('Copy the URL from the address bar.'));};
 document.getElementById('kbdbtn').onclick=()=>document.getElementById('kbdmodal').style.display='flex';
 document.getElementById('clrents').onclick=()=>{active=[];renderChips();scheduleRecompute();};
 document.getElementById('clrmeas').onclick=()=>{measures=[];entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();};
 document.getElementById('calcbtn').onclick=()=>{const d=document.getElementById('calcdiv');const show=d.style.display==='none';d.style.display=show?'block':'none';if(show)refreshCalcPicklist();};
 document.getElementById('calc-codesearch').oninput=function(){const q=this.value.trim();const el=document.getElementById('calc-coderes');if(!q){el.style.display='none';el.innerHTML='';return;}const res=searchHier(q);if(!res.length){el.innerHTML='<div style="padding:4px 6px;color:var(--muted,#9aa3b2)">No matches</div>';el.style.display='block';return;}el.innerHTML=res.map(r=>`<div class="calc-cr" data-m="${r.m}" style="padding:2px 6px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.c}"><b>${r.m}</b> — ${r.c}</div>`).join('');el.style.display='block';el.querySelectorAll('.calc-cr').forEach(d=>d.onclick=()=>{const inp=document.getElementById('calcformula');const p=inp.selectionStart,txt=inp.value;inp.value=txt.slice(0,p)+d.dataset.m+txt.slice(inp.selectionEnd);inp.focus();inp.setSelectionRange(p+d.dataset.m.length,p+d.dataset.m.length);el.style.display='none';this.value='';});};
 document.getElementById('calcadd').onclick=()=>{
   const name=(document.getElementById('calcname').value.trim()||'Custom calc');
   const fstr=document.getElementById('calcformula').value.trim();
   const st=document.getElementById('calcstatus');st.textContent='';
   if(!fstr){st.textContent='Enter a formula.';return;}
   const AL='ABCDEFGHIJKLMNOPQRSTUVWXYZ';
   const aliases={};for(let i=0;i<Math.min(measures.length,26);i++)aliases[AL[i]]=measures[i].code;
   let parsed;try{parsed=parseCalcExpr(fstr,aliases);}catch(e){st.textContent=String(e);return;}
   const code='CALC_'+(Date.now()%1e9);
   USERCALC[code]={type:'expr',ast:parsed.ast,pct:parsed.pct,vars:parsed.vars,lbl:name};
   _seriesCache.clear();
   toggleMeasure(code,name,parsed.pct);
   document.getElementById('calcformula').value='';document.getElementById('calcname').value='';
   document.getElementById('calcdiv').style.display='none';};
function getFormulasJson(){const out={};for(const[k,v]of Object.entries(USERCALC))out[k]=v;return JSON.stringify(out);}
function applyFormulas(obj){let n=0;for(const[code,entry]of Object.entries(obj)){if(!code.startsWith('CALC_'))continue;if(!entry?.type||!entry?.lbl)continue;if(!USERCALC[code]){USERCALC[code]=entry;toggleMeasure(code,entry.lbl,!!entry.pct);n++;}}return n;}
async function saveFormulas(){try{const r=await fetch('/api/save-formulas',{method:'POST',headers:{'Content-Type':'application/json'},body:getFormulasJson()});if(!r.ok)throw new Error('HTTP '+r.status);showToast('Formulas saved.','ok');}catch(e){try{localStorage.setItem('fry9c_formulas',getFormulasJson());showToast('Formulas saved to this browser.','ok');}catch(le){const el=document.getElementById('calcstatus');if(el)el.textContent='Save failed: '+le.message;}}}
async function loadFormulas(){try{const r=await fetch('/api/formulas');if(!r.ok)throw new Error('HTTP '+r.status);const obj=await r.json();const n=applyFormulas(obj);showToast('Loaded '+n+' formula'+(n===1?'':'s')+'.','ok');}catch(e){const _el=document.getElementById('calcstatus');try{const s=localStorage.getItem('fry9c_formulas');if(!s){if(_el)_el.textContent='No saved formulas to load.';return;}const _obj=JSON.parse(s);const _tot=Object.keys(_obj).filter(k=>k.startsWith('CALC_')).length;if(!_tot){if(_el)_el.textContent='No saved formulas to load.';return;}const n=applyFormulas(_obj);showToast(n>0?'Restored '+n+' formula'+(n===1?'':'s')+' from this browser.':'Formulas already active.','ok');}catch(le){if(_el)_el.textContent='Load failed: '+le.message;}}}
async function autoLoadFormulas(){try{const r=await fetch('/api/formulas');if(!r.ok)throw new Error();const obj=await r.json();applyFormulas(obj);}catch(e){try{const s=localStorage.getItem('fry9c_formulas');if(s)applyFormulas(JSON.parse(s));}catch{}}}
function exportFormulas(){const s=getFormulasJson();const b=new Blob([s],{type:'application/json'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='formulas.json';a.click();URL.revokeObjectURL(u);}
 document.getElementById('calcSave').onclick=saveFormulas;
 document.getElementById('calcLoad').onclick=loadFormulas;
 document.getElementById('calcExport').onclick=exportFormulas;
 document.getElementById('calcImport').onclick=()=>document.getElementById('calcImportFile').click();
 document.getElementById('calcImportFile').onchange=e=>{const f=e.target.files?.[0];if(!f)return;const rd=new FileReader();rd.onload=ev=>{try{const obj=JSON.parse(ev.target.result);const n=applyFormulas(obj);showToast('Imported '+n+' formula'+(n===1?'':'s')+'.','ok');}catch(ex){const el=document.getElementById('calcstatus');if(el)el.textContent='Import failed: invalid JSON.';}};rd.readAsText(f);e.target.value='';};
 {const stackEl=document.getElementById('stackedmode');if(stackEl)stackEl.onchange=()=>draw();}
 {const il=document.getElementById('inlinelbls');if(il){il.checked=(window._inlineLbls!==false);il.onchange=()=>{window._inlineLbls=il.checked;try{localStorage.setItem('fry9c_inlinelbls',il.checked?'1':'0');}catch(_){}draw();};}}
 document.getElementById('deriv-grpadd-btn').onclick=()=>{const cat=document.getElementById('deriv-grpadd').value;if(!cat)return;let added=0;for(const [code,d] of Object.entries(DERIV)){const lbl=d.lbl||'';const parts=lbl.split(' ▸ ');if(parts[0]!==cat)continue;if(measures.length>=20){showToast('Measure limit is 20 — remove some first.','warn');break;}if(!measures.find(m=>m.code===code)){const shortLbl=parts.slice(1).join(' ▸ ')||lbl;measures.push({code,label:shortLbl,pct:true});added++;}}if(!added){showToast('No new measures found for that category.','warn');return;}entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();};
 document.getElementById('kbdclose').onclick=()=>document.getElementById('kbdmodal').style.display='none';
 (function(){const ft=document.getElementById('formulatip');document.querySelector('.rail').addEventListener('mouseover',e=>{const row=e.target.closest('.trow[data-formula]');if(!row||!ft)return;ft.innerHTML=`<div class="ftip-lbl">Formula</div>${row.dataset.formula}`;ft.style.display='block';});document.querySelector('.rail').addEventListener('mouseout',e=>{if(e.target.closest('.trow[data-formula]')&&!e.relatedTarget?.closest('.trow[data-formula]'))ft.style.display='none';});document.addEventListener('mousemove',e=>{if(ft&&ft.style.display!=='none'){const x=e.clientX+14,y=e.clientY+14,w=ft.offsetWidth,h=ft.offsetHeight;ft.style.left=Math.min(x,window.innerWidth-w-10)+'px';ft.style.top=Math.min(y,window.innerHeight-h-10)+'px';}});})();
 document.getElementById('expbld-close').onclick=()=>document.getElementById('exportmodal').style.display='none';
 document.getElementById('expbld-run').onclick=async()=>{const btn=document.getElementById('expbld-run');btn.textContent='⏳…';btn.disabled=true;try{const res=await runExport(false);if(!res||!res.body?.length){showToast('No data for the selected scope.');return;}dl2(res.headers,res.body,'fry9c_export');}catch(e){showToast('Export error: '+e,'err');}finally{btn.textContent='⬇ Download CSV';btn.disabled=false;}};
 document.getElementById('expbld-preview').onclick=async()=>{const btn=document.getElementById('expbld-preview');btn.textContent='⏳…';btn.disabled=true;try{const res=await runExport(true);if(!res)return;const sqlBlock=res.sql?`<details style="margin-bottom:8px"><summary style="cursor:pointer;font-size:13px;color:var(--muted,#9aa3b2)">Generated SQL (click to expand)</summary><pre style="font-size:12px;white-space:pre-wrap;word-break:break-all;background:var(--head,#eef2f7);padding:6px 8px;border-radius:4px;margin:4px 0">${res.sql.replace(/</g,'&lt;')}</pre></details>`:'';let h=`<table><tr>${res.headers.map(c=>`<th>${c}</th>`).join('')}</tr>`;for(const r of res.body)h+=`<tr>${r.map(v=>`<td>${v??''}</td>`).join('')}</tr>`;document.getElementById('eb-preview-area').innerHTML=sqlBlock+h+`</table><p class="muted">${res.body.length} rows shown (first 50).</p>`;}catch(e){showToast('Preview error: '+e,'err');}finally{btn.textContent='👁 Preview';btn.disabled=false;}};
 document.getElementById('expbld-setcur').onclick=()=>{for(const e of active){if(!_eb.entities.find(x=>x.id===e.id))_eb.entities.push({id:e.id,label:e.label});}if(Qall.length){_eb.fromQ=Qall[rangeSel.a];_eb.toQ=Qall[rangeSel.b];}renderExportUI();};
 document.getElementById('formexport').onclick=exportForm;document.getElementById('csv').onclick=exportSeries;document.getElementById('svgexport').onclick=exportChartSVG;document.getElementById('kpisel').onchange=draw;document.getElementById('cplink').onclick=()=>{const url=location.href;if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(url).then(()=>showToast('Link copied!','ok')).catch(()=>prompt('Copy this link:',url));}else{prompt('Copy this link:',url);}};
 document.getElementById('runsql').onclick=runsql;document.getElementById('sqlcsv').onclick=()=>dl2(sqlC,sqlR,'query');
 document.getElementById('r0').oninput=onSlide;document.getElementById('r1').oninput=onSlide;
 document.getElementById('rreset').onclick=()=>{rangeSel={a:0,b:Qall.length-1};syncSlider();draw();};
 ['1y','5y','10y'].forEach((id,k)=>{const btn=document.getElementById(`preset${id}`);if(btn)btn.onclick=()=>{if(!Qall.length)return;const n=[4,20,40][k];rangeSel={a:Math.max(0,Qall.length-n),b:Qall.length-1};syncSlider();draw();};});
 document.getElementById('rfrom').onchange=()=>{const q=document.getElementById('rfrom').value.trim();const i=Qall.indexOf(q);if(i>=0){rangeSel.a=Math.min(i,rangeSel.b);syncSlider();draw();}};
 document.getElementById('rto').onchange=()=>{const q=document.getElementById('rto').value.trim();const i=Qall.indexOf(q);if(i>=0){rangeSel.b=Math.max(i,rangeSel.a);syncSlider();draw();}};
 {const lhb=document.getElementById('loadhist');if(lhb){if(OLD_ACTIVE_PARTS.length)lhb.style.display='';lhb.onclick=async()=>{lhb.disabled=true;lhb.textContent='Loading…';await ensureOldActive();};}}
 document.getElementById('idx').onchange=draw;document.getElementById('qoqdelta').onchange=draw;document.getElementById('normbyassets').onchange=draw;document.getElementById('reflineset').onclick=()=>{const v=parseFloat(document.getElementById('reflineval').value);if(!isNaN(v)){_reflineVal=v;_reflineLbl=document.getElementById('reflinelbl').value.trim()||String(v);}draw();};document.getElementById('reflineclr').onclick=()=>{_reflineVal=null;document.getElementById('reflineval').value='';document.getElementById('reflinelbl').value='';draw();};
 (function(){const sp=document.getElementById('railsplit');let drag=false;
  sp.addEventListener('mousedown',e=>{drag=true;e.preventDefault();document.body.style.userSelect='none';});
  window.addEventListener('mousemove',e=>{if(!drag)return;const w=Math.min(820,Math.max(300,e.clientX));document.documentElement.style.setProperty('--railw',w+'px');});
  window.addEventListener('mouseup',()=>{drag=false;document.body.style.userSelect='';});})();
 document.getElementById('downloads').innerHTML='&#11015; Data: '+PARTS.map(p=>`<a href="${p}" download>${p}</a>`).join(' &middot; ')+' (Python / Power BI / DuckDB)';
 if(HIER)buildTree();else document.getElementById('tree').innerHTML='<p class="muted" style="padding:10px">hierarchy not found</p>';
 const restored=hashToState();
 if(!restored){active=[{id:'ALL',label:'ALL'}];}
 if(!measures.length){try{const s=localStorage.getItem('fry9c_measures');if(s){const ms=JSON.parse(s);if(Array.isArray(ms)&&ms.length)measures=ms.slice(0,20);}}catch{}if(!measures.length)measures=[{code:'BHCK2170',label:'Total assets',pct:false}];}
 renderChips();renderMeasures();renderPeerSaved();
 st(`Ready — ${ROSTER.size} holding companies. Click items on the left.`);pbar(100);recompute();autoLoadFormulas();
 {const _rp=new URLSearchParams(location.hash.slice(1));if(_rp.get('report')==='1'&&active.length===1&&active[0].id.startsWith('BANK:'))openReport(active[0].id);}
}catch(e){st('Load failed: '+e);console.error(e);}}

function rebuildEntList(){const dl=document.getElementById('entlist');dl.innerHTML='';
 const add=v=>{const o=document.createElement('option');o.value=v;dl.appendChild(o);};
 add('ALL');for(const n in peers)add('★ '+n);for(const [rssd,r] of ROSTER)add(`${r.nm} (${rssd})`);}
function renderChips(){const c=document.getElementById('chips');if(!active.length){c.innerHTML='<span class="muted">none</span>';const cl=document.getElementById('crosslinks');if(cl)cl.innerHTML='';return;}
 c.innerHTML=active.map((a,i)=>`<span class="chip"><span class="sw" style="background:${COLORS[i%COLORS.length]}"></span><b>${a.label}</b><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{active.splice(+x.dataset.i,1);renderChips();scheduleRecompute();});
 // cross-dashboard links for BANK: entities
 const cl=document.getElementById('crosslinks');if(cl){const banks=active.filter(a=>a.id.startsWith('BANK:'));if(banks.length){const base=location.href.replace(/\/[^/]*$/,'/');const eHash=banks.map(a=>a.id).join(',');const mk=(dir,lbl)=>`<a href="${base.replace(/site_fry9c\//,''+dir+'/')}index.html#e=${encodeURIComponent(eHash)}" target="_blank" style="color:var(--muted,#9aa3b2);text-decoration:underline dotted">${lbl}</a>`;cl.innerHTML='Also view in: '+mk('site_002','002')+' · '+mk('site_call','Call');}else cl.innerHTML='';}
 // keep entity-list highlights in sync
 const ep=document.getElementById('panelEnts');
 if(ep&&ep.style.display!=='none')renderEntList();
 const rb=document.getElementById('reportbtn');if(rb)rb.disabled=!(active.length===1&&active[0].id.startsWith('BANK:'));}
const saveMeasures=()=>{try{localStorage.setItem('fry9c_measures',JSON.stringify(measures.filter(m=>!m.code.startsWith('CALC_')).map(m=>({code:m.code,label:m.label,pct:m.pct}))));}catch{}};
function renderMeasures(){const c=document.getElementById('mchips');if(!measures.length){c.innerHTML='<span class="muted">none</span>';return;}
 c.innerHTML=measures.map((m,i)=>`<span class="chip"><b>${m.label}</b> <span class="muted">${m.pct?'%':'$'}</span><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{measures.splice(+x.dataset.i,1);entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();});}
function renderPeerBuilder(){const c=document.getElementById('pmembers');if(!peerMembers.length){c.innerHTML='<span class="muted">none</span>';return;}
 c.innerHTML=peerMembers.map((a,i)=>`<span class="chip"><b>${a.label}</b><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{peerMembers.splice(+x.dataset.i,1);renderPeerBuilder();});}
function renderPeerSaved(){const c=document.getElementById('psaved');const names=Object.keys(peers);
 if(!names.length){c.innerHTML='<span class="muted">none saved</span>';return;}
 c.innerHTML=names.map(n=>`<span class="chip"><b>★ ${n}</b> <span class="muted">(${peers[n].length})</span> <span class="use" data-n="${n}" style="cursor:pointer;color:#1b7f3b;font-weight:700">＋chart</span> <span class="x" data-n="${n}">✕</span></span>`).join('');
 c.querySelectorAll('.use').forEach(u=>u.onclick=()=>{const id='PEER:'+u.dataset.n;if(!active.find(a=>a.id===id))active.push({id,label:'★ '+u.dataset.n});renderChips();scheduleRecompute();});
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{delete peers[x.dataset.n];savePeers();rebuildEntList();renderPeerSaved();});}
function savePeer(){const n=document.getElementById('pname').value.trim();if(!n){showToast('Name the peer group.');return;}
 if(!peerMembers.length){showToast('Add at least one member.');return;}
 const prefix=`PEER:${n}::`;for(const k of _seriesCache.keys())if(k.startsWith(prefix))_seriesCache.delete(k);
 peers[n]=peerMembers.map(m=>m.rssd);savePeers();rebuildEntList();renderPeerSaved();
 document.getElementById('pname').value='';peerMembers=[];renderPeerBuilder();st(`Saved peer group "${n}".`);}

function loadFavs(){try{return new Set(JSON.parse(localStorage.getItem('fry9c_favs')||'[]'));}catch{return new Set();}}
function saveFavs(s){localStorage.setItem('fry9c_favs',JSON.stringify([...s]));}
function loadWL(){try{return new Set(JSON.parse(localStorage.getItem('fry9c_wl')||'[]'));}catch{return new Set();}}
function saveWL(s){localStorage.setItem('fry9c_wl',JSON.stringify([...s]));}
function buildFavShelf(){
  const favs=loadFavs();if(!favs.size)return null;
  const nodes=[...favs].map(code=>{
    const row=document.querySelector(`#tree .trow[data-code="${CSS.escape(code)}"]`);
    const cap=row?row.querySelector('.cap')?.textContent||code:code;
    return {code,caption:cap,num:'',depth:1,derived:false,header:false,pct:PCTC.has(code),children:[]};});
  return nodes;}
function renderFavShelf(){
  const old=document.getElementById('favshelf');if(old)old.remove();
  const nodes=buildFavShelf();if(!nodes||!nodes.length)return;
  const t=document.getElementById('tree');
  const {sec,rows}=mkSec('★ Favorites',nodes.length);sec.id='favshelf';
  renderNodes(rows,nodes);rows.style.display='block';
  sec.querySelector('.schhead').innerHTML=sec.querySelector('.schhead').innerHTML.replace('▸','▾');
  t.insertBefore(sec,t.firstChild);}
// ---- tree ----
const REPORT=/^BH[A-Z]{2}[0-9A-Z]{4}$/;
function mkSec(title,cnt){const sec=document.createElement('div');sec.className='schsec';
 const h=document.createElement('div');h.className='schhead';h.innerHTML=`▸ ${title} ${cnt?`<span class=cnt>(${cnt})</span>`:''}`;
 const rows=document.createElement('div');rows.className='schrows';rows.style.display='none';
 h.onclick=()=>{const open=rows.style.display!=='none';rows.style.display=open?'none':'block';h.innerHTML=h.innerHTML.replace(open?'▾':'▸',open?'▸':'▾');};
 sec.appendChild(h);sec.appendChild(rows);return {sec,rows};}
function rowEl(nd,has,dispCap){
 if(nd.placeholder){
   const p=document.createElement('div');p.className='trow placeholder';
   p.style.cssText=`padding-left:${6+(nd.depth-1)*14}px`;
   p.innerHTML=`<span class="caret" style="visibility:hidden">▸</span>`+
     (nd.num?`<span class="num">${nd.num}</span>`:'') +
     `<span class="cap" style="color:#9aa3b2;font-style:italic">(empty)</span>`;
   return p;}
 const d=document.createElement('div');d.className='trow'+(nd.header?' hdr':'');
 d.dataset.code=nd.code;d.dataset.txt=(nd.code+' '+nd.caption).toLowerCase();d.dataset.depth=nd.depth;d.style.paddingLeft=(6+(nd.depth-1)*14)+'px';
 const car=`<span class="caret"${has?'':' style="visibility:hidden"'}>▸</span>`;
 const cap=`<span class="cap" title="${String(nd.caption||'').replace(/"/g,'&quot;')}">${dispCap||nd.caption||''}</span>`;
 if(nd.header){   // grouping / subtotal / total row — clicking sums its descendant codes
   d.innerHTML=`${car}${nd.num?`<span class=num>${nd.num}</span>`:''}${cap}`;
   d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};
   const codes=descCodes(nd);const pctSkip=hasPctDesc(nd);
   if(codes.length){d.title='Click to chart sum of '+codes.length+' leaf $ code(s)'+(pctSkip?' · non-additive % cells excluded':'');
     d.onclick=()=>{const code='SUB:'+nd.code;const rl=fullCap(code)||nd.caption;DYN[code]={type:'sum',lbl:rl,plus:codes};toggleMeasure(code,rl,false);};}
   else if(pctSkip){d.title='Contains only non-additive % cells — cannot sum';d.onclick=()=>{if(has)toggleNode(d);};}
   else d.onclick=()=>{if(has)toggleNode(d);};
   return d;}
 d.innerHTML=nd.derived?`${car}${cap}`:`${car}${(nd.num&&!nd.col)?`<span class=num>${nd.num}</span>`:''}${cap}<span class=code>${nd.code}</span>`;
 const lab=nd.derived?short(nd.caption):(nd.caption||nd.code);
 d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};
 d.onclick=()=>toggleMeasure(nd.code,fullCap(nd.code)||lab,nd.pct||PCTC.has(nd.code));
 if(nd.derived&&DERIV[nd.code]){const dr=DERIV[nd.code];const ab=a=>{if(!a||!a.length)return '?';return a.length<=3?a.join(' + '):a.slice(0,2).join(' + ')+` + …(${a.length})`};let fml;if(dr.type==='ratio'){const nStr=dr.minus&&dr.minus.length?`(${ab(dr.plus)} − ${ab(dr.minus)})`:ab(dr.plus);fml=`${nStr} ÷ ${ab(dr.den)} × 100${dr.annualize?' × (4/N)':''}`;}else{fml=`${ab(dr.plus)}`;}d.dataset.formula=fml;d.title='Click to chart · hover for formula';}
 if(!nd.derived){const fstar=document.createElement('span');fstar.className='fav'+(loadFavs().has(nd.code)?' on':'');fstar.textContent='★';fstar.title='Add to favorites';
   fstar.onclick=ev=>{ev.stopPropagation();const f=loadFavs();if(f.has(nd.code)){f.delete(nd.code);fstar.classList.remove('on');}else{f.add(nd.code);fstar.classList.add('on');}saveFavs(f);renderFavShelf();};
   const caret=d.querySelector('.caret');if(caret)caret.after(fstar);else d.prepend(fstar);}
 if(!nd.header&&!nd.derived&&EMPTY_CODES.has(nd.code)){d.classList.add('nodata');d.title='No panel data for this item';}
 return d;}
function nest(flat){const ns=flat.map(it=>({...it,children:[]}));
 const byItem=new Map();for(const n of ns){if(n.num){if(!byItem.has(n.num))byItem.set(n.num,[]);byItem.get(n.num).push(n);}}
 const first=it=>{const a=byItem.get(it);return a&&a[0];};
 const ancestor=it=>{const p=String(it).split('.');p.pop();while(p.length){const k=p.join('.');if(byItem.has(k))return k;p.pop();}return null;};
 const roots=[];
 for(const n of ns){if(!n.num){roots.push(n);continue;}const a=ancestor(n.num);const par=a&&first(a);(par?par.children:roots).push(n);}
 return roots;}
function emitSchedule(sch){const out=[],done=new Set();
 for(const r of HIER[sch]){const isH=!!r.header;
   if(!isH && !REPORT.test(r.mdrm)){
     if(r.item){  // reserved/N/A item — emit a labelled placeholder
       out.push({code:'EMPTY:'+r.item,caption:'(empty)',num:r.item||'',depth:r.depth||1,
                 derived:false,header:false,col:false,pct:false,placeholder:true});
     }
     continue;}
   const key=r.mdrm||('H:'+sch+':'+r.item); if(done.has(key))continue; done.add(key);
   out.push({code:key,caption:r.caption||r.mdrm,num:r.item||'',depth:r.depth||1,derived:false,header:isH,col:!!r.col,pct:false,sch:sch});}
 return out;}
function secPrefix(nodes){
 const caps=[];function walk(ns){for(const n of ns){if(!n.header&&!n.derived&&!n.placeholder){if(!n.children.length)caps.push(n.caption||'');else walk(n.children);}}}
 walk(nodes);if(caps.length<3)return '';
 let pre=caps[0];for(const s of caps.slice(1)){while(pre&&!s.startsWith(pre))pre=pre.slice(0,-1);}
 const mm=pre.match(/^(.*\w)\s*/);pre=mm?mm[1]+' ':pre;if(pre.length<12)return '';
 return caps.filter(c=>c.startsWith(pre)).length/caps.length>=0.7?pre:'';}
function nodeChildPfx(children){
 const caps=children.filter(c=>!c.placeholder&&!c.col&&!c.header).map(c=>c.caption||'');
 if(caps.length<2)return '';
 let pre=caps[0];for(const s of caps.slice(1)){while(pre&&!s.startsWith(pre))pre=pre.slice(0,-1);}
 const mm=pre.match(/^(.*\w)\s*/);pre=mm?mm[1]+' ':pre;
 if(pre.length<12)return '';
 const tails=caps.filter(c=>c.startsWith(pre)).map(c=>c.slice(pre.length).replace(/^[\s:\-–]+/,''));
 if(tails.some(t=>t.length<10))return '';
 return pre;}
function renderNodes(container,nodes,pfx,pfx2){if(!pfx)pfx='';if(!pfx2)pfx2='';
 // Matrix rows: items sharing item# with long common prefix get "… stripped" display
 const disp=new Map(),grp={};
 for(const n of nodes) if(!n.header&&n.num){(grp[n.num]=grp[n.num]||[]).push(n);}
 for(const num in grp){const g=grp[num];if(g.length<2)continue;
   let pre=g[0].caption||'';
   for(const n of g){const c=n.caption||'';while(pre&&!c.startsWith(pre))pre=pre.slice(0,-1);}
   const mm=pre.match(/^.*[ :\-–]/);const bp=mm?mm[0]:'';
   if(bp.length>=18)for(const n of g){const c=n.caption||'';if(c.startsWith(bp))disp.set(n,'… '+c.slice(bp.length).replace(/^[\s:\-–]+/,''));}}
 for(const nd of nodes){const has=nd.children.length>0;
   let dc=disp.get(nd);
   if(!dc){const cap=nd.caption||'';
     if(pfx2&&!nd.header&&cap.toUpperCase().startsWith(pfx2.toUpperCase())){const tail=cap.slice(pfx2.length).replace(/^[\s:\-–]+/,'');dc='… '+(tail||'(total)');}
     else if(pfx&&cap.toUpperCase().startsWith(pfx.toUpperCase()))dc=cap.slice(pfx.length).replace(/^[\s:\-–]+/,'');}
   const row=rowEl(nd,has,dc);container.appendChild(row);
 if(has){const kids=document.createElement('div');kids.className='kids';kids.style.display='none';
   const kp=nodeChildPfx(nd.children);renderNodes(kids,nd.children,pfx,kp);container.appendChild(kids);row._kids=kids;}}}
function addSchedule(t,title,nodes){const pfx=secPrefix(nodes);const {sec,rows}=mkSec(title,nodes.length);renderNodes(rows,nodes,pfx);t.appendChild(sec);}
function toggleNode(row){if(!row._kids)return;const open=row._kids.style.display!=='none';row._kids.style.display=open?'none':'block';const c=row.querySelector('.caret');if(c)c.textContent=open?'▸':'▾';}
function bumpDepth(nodes,by){for(const n of nodes){n.depth=(n.depth||1)+by;if(n.children)bumpDepth(n.children,by);}}
function buildTree(){const t=document.getElementById('tree');t.innerHTML='';
 addSchedule(t,'★ Ratios & Subtotals',Object.keys(DERIV).map(k=>({code:k,caption:DERIV[k].lbl,num:'',depth:1,derived:true,pct:isPct(k),children:[]})));
 const allk=Object.keys(HIER);
 const bases=[...new Set(allk.map(k=>k.split(' — ')[0]))];
 const ordered=[...FORM_ORDER.filter(b=>bases.includes(b)),...bases.filter(b=>!FORM_ORDER.includes(b))];
 for(const base of ordered){
   let roots=HIER[base]?nest(emitSchedule(base)):[];
   // nest each Memoranda / Part-II sub-section INSIDE its parent schedule as a collapsible group
   for(const sub of allk.filter(k=>k!==base&&k.split(' — ')[0]===base)){
     const subRoots=nest(emitSchedule(sub));if(!subRoots.length)continue;bumpDepth(subRoots,1);
     roots.push({code:'SEC:'+sub,caption:sub.slice(base.length+3),num:'',depth:1,derived:false,header:true,sch:sub,children:subRoots});
   }
   if(roots.length){addSchedule(t,SCHED_NAMES[base]||base,roots);_walkFC(roots,[SCHED_NAMES[base]||base],base);}
 }
 treeBuilt=true;markTree();renderFavShelf();}
let lvl={'#tree':0,'#formbody':0};
function applyLevel(L,root='#tree'){L=Math.max(0,L);lvl[root]=L;
 document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display=L>=1?'block':'none');
 document.querySelectorAll(`${root} .schhead`).forEach(h=>{const w=L>=1;h.innerHTML=h.innerHTML.replace(w?'▸':'▾',w?'▾':'▸');});
 document.querySelectorAll(`${root} .trow, ${root} .frow`).forEach(row=>{if(!row._kids)return;const d=+(row.dataset.depth||1),open=d<L;
   row._kids.style.display=open?'block':'none';const c=row.querySelector('.caret');if(c&&c.style.visibility!=='hidden')c.textContent=open?'▾':'▸';});}
function maxDepth(root){let m=1;document.querySelectorAll(`${root} .trow, ${root} .frow`).forEach(r=>{const d=+(r.dataset.depth||1);if(d>m)m=d;});return m;}
function expandAll(open,root='#tree'){applyLevel(open?maxDepth(root)+1:0,root);}
function drill(step,root='#tree'){applyLevel((lvl[root]||0)+step,root);}
function drillSmart(step,root='#tree'){
  if(step>0){
    const openRows=[];
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(r._kids&&r._kids.style.display==='block')openRows.push(r);});
    if(!openRows.length){
      document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display='block');
      document.querySelectorAll(`${root} .schhead`).forEach(h=>{h.innerHTML=h.innerHTML.replace('▸','▾');});
      return;}
    openRows.forEach(row=>{
      Array.from(row._kids.children).forEach(el=>{
        if((el.classList.contains('trow')||el.classList.contains('frow'))&&el._kids){
          el._kids.style.display='block';
          const c=el.querySelector('.caret');
          if(c&&c.style.visibility!=='hidden')c.textContent='▾';}});});
  } else {
    let maxD=0;
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(r._kids&&r._kids.style.display==='block'){const d=+(r.dataset.depth||1);if(d>maxD)maxD=d;}});
    if(!maxD){
      document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display='none');
      document.querySelectorAll(`${root} .schhead`).forEach(h=>{h.innerHTML=h.innerHTML.replace('▾','▸');});
      return;}
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(!r._kids||r._kids.style.display==='none')return;
      if(+(r.dataset.depth||1)===maxD){r._kids.style.display='none';
        const c=r.querySelector('.caret');if(c&&c.style.visibility!=='hidden')c.textContent='▸';}});}}
function filterTree(q){q=q.trim().toLowerCase();
 if(!q){document.querySelectorAll('#tree .trow').forEach(r=>r.style.display='');document.querySelectorAll('#tree .schsec').forEach(s=>s.style.display='');applyLevel(0);return;}
 document.querySelectorAll('#tree .kids').forEach(k=>k.style.display='block');
 document.querySelectorAll('#tree .schsec').forEach(sec=>{const rows=sec.querySelector('.schrows');let any=false;
   sec.querySelectorAll('.trow').forEach(r=>{const m=(r.dataset.txt||'').includes(q);r.style.display=m?'':'none';if(m)any=true;});
   rows.style.display=any?'block':'none';sec.style.display=any?'':'none';});}
function markTree(){const on=new Set(measures.map(m=>m.code));document.querySelectorAll('#tree .trow').forEach(r=>r.classList.toggle('on',on.has(r.dataset.code)||on.has('SUB:'+r.dataset.code)));}
// MEDIUM-1 + PART-B roll-up double-count fix — schedule-aware, per VALIDATION_FRY9C.md 13-rule spec.
// A header click Σ-sums descendant leaf codes; a naive Σ double-/triple-counts in several patterns:
//   • PCTC ratio cells are non-additive (filtered out everywhere).
//   • DC-2/DC-2a: BHCK (consolidated) + BHDM (domestic subset) col pair share a 4-char suffix —
//     domestic is a SUBSET of consolidated; the BHCK col also contains the non-col breakdown beneath.
//   • DC-8: BHCA (standardized) + BHCW (advanced) are alternative regulatory calcs, not additive.
//   • DC-3 (HC-B): 4 cols = HTM-amort + HTM-FV + AFS-amort + AFS-FV → carrying value = ColA + ColD.
//   • DC-4 (HC-Q) / DC-5 (HC-R Part II): Col A is the balance-sheet total; later cols re-slice it.
//   • DC-1: a header carries an explicit "Total" leaf alongside its components (2× the total).
// ROLLUP_RULES keys explicit (sch -> item -> action) for DC-1 totals and non-additive headers
// (avoids the fragile "caption contains Total" heuristic, which has documented false positives:
// HC item 27, HC-M item 7, HC-L 7.a). Generalized col logic handles DC-2/2a/3/4/5/8 structurally.
const ROLLUP_RULES={
 'HI':{'1':{codes:['BHCK4107']},'2':{codes:['BHCK4073']},'5':{codes:['BHCK4079']},'7':{codes:['BHCK4093']}},
 'HC':{'4':{codes:['BHCK5369','BHCKB529']}},
 'HC-C':{'M.1':{codes:['BHCKHK25']}},
 'HC-N':{'M.1':{use:'M.1.g'}},
 'HC-L':{'7':{use:'7.a'},'7.b':{suppress:1},'7.c':{suppress:1},'7.d':{suppress:1},
         '14':{suppress:1},'14.a':{suppress:1},'14.b':{suppress:1},'15.b':{use:'15.b.(8)'}},
 'HC-R':{'33':{codes:['BHCAKX77']},'34':{codes:['BHCAKX82']},'34.d':{codes:['BHCAKX82']},
         '45':{codes:['BHCA3792']},'46':{codes:['BHCAA223']}}
};
function descCodes(nd){
 const sch=nd.sch||'';
 const ok=c=>c&&/^BH/.test(c)&&!PCTC.has(c);
 const rules=ROLLUP_RULES[sch]||{};
 const colStrat=sch==='HC-B'?'AD':(sch==='HC-Q'||sch==='HC-R — Part II (Risk-Weighted Assets)')?'A':'pair';
 const pickCols=cl=>{const codes=cl.map(c=>c.code).filter(ok);if(!codes.length)return [];
   if(colStrat==='A')return [codes[0]];                                  // DC-4/DC-5: Col A only
   if(colStrat==='AD')return codes.length>=4?[codes[0],codes[codes.length-1]]:[codes[0]];  // DC-3: ColA+ColD
   const bhck=new Set(codes.filter(c=>c.startsWith('BHCK')).map(c=>c.slice(4)));
   const bhca=new Set(codes.filter(c=>c.startsWith('BHCA')).map(c=>c.slice(4)));
   return codes.filter(c=>{const s=c.slice(4);
     if(c.startsWith('BHDM')&&bhck.has(s))return false;   // DC-2: drop domestic subset of a BHCK col
     if(c.startsWith('BHCW')&&bhca.has(s))return false;   // DC-8: drop advanced alt of a BHCA col
     return true;});};
 const out=[];
 const findItem=(n,it)=>{if(n&&n.num===it)return n;for(const c of((n&&n.children)||[])){const r=findItem(c,it);if(r)return r;}return null;};
 (function rec(n){
   const r=rules[n.num];
   if(r){
     if(r.suppress)return;
     if(r.codes){for(const c of r.codes)if(ok(c))out.push(c);return;}
     if(r.use){const t=findItem(nd,r.use);if(t&&t!==n)rec(t);return;}   // not found -> suppress (safe)
   }
   const kids=n.children||[];
   const colLeaves=kids.filter(c=>!c.header&&c.col&&c.code&&/^BH/.test(c.code)&&!PCTC.has(c.code));
   if(colLeaves.length){for(const c of pickCols(colLeaves))out.push(c);return;}
   for(const c of kids){if(c.header)rec(c);else if(ok(c.code))out.push(c.code);}
 })(nd);
 return out;}
function hasPctDesc(nd){return(function chk(n){for(const c of n.children||[]){if(c.header){if(chk(c))return true;}else if(PCTC.has(c.code))return true;}return false;})(nd);}
function toggleMeasure(code,label,pct){
 if(window._addToChartId!=null){const ch=_extraCharts.find(c=>c.id===window._addToChartId);if(ch){const i=ch.measures.findIndex(m=>m.code===code);if(i>=0)ch.measures.splice(i,1);else{if(ch.measures.length>=20){showToast('Up to 20 measures.');return;}ch.measures.push({code,label,pct:!!pct});}renderExtraChartChips(ch);recomputeExtraCharts().then(()=>drawExtraCharts());return;}}
 const i=measures.findIndex(m=>m.code===code);
 if(i>=0)measures.splice(i,1);else{if(measures.length>=20){showToast('Up to 20 measures.');return;}measures.push({code,label,pct:!!pct});}
 entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();}

// ---- entity panel ----
let entSortVals=new Map(),entSortField='__none__';
async function computeSortVals(field){if(field===entSortField)return;entSortVals=new Map();
 if(field==='name'||field==='rssd'){entSortField=field;return;}
 // Each sort field maps to a list of MDRM codes summed per filer (deposits = BHDM+BHFN).
 const codeMap={assets:['BHCK2170'],deposits:DEP,loans:['BHCK2122'],equity:['BHCK3210']};
 let codes;
 if(field==='current'){if(!measures.length){entSortField=field;return;}const c=measures[0].code;
   if(!/^BH/.test(c)){
     // LOW-1: derived/DYN code — use perFilerValues to compute per-filer values for sorting
     try{const latR=(await conn.query('SELECT max(quarter_end) q FROM t')).toArray();
       const latQ=latR.length?String(latR[0].q):null;
       if(latQ){const vals=await perFilerValues(c,[latQ]);const cur=vals[latQ]||new Map();
         let all=0;for(const[rssd,v]of cur){entSortVals.set('BANK:'+rssd,v);all+=v;}
         entSortVals.set('ALL',all);
         for(const n in peers){let s=0,any=false;for(const r2 of peers[n])if(cur.has(r2)){s+=cur.get(r2);any=true;}if(any)entSortVals.set('PEER:'+n,s);}}}
     catch(e){}entSortField=field;return;}
   codes=[c];}
 else codes=codeMap[field];
 if(!codes||!codes.length){entSortField=field;return;}
 try{const r=(await conn.query(`SELECT id_rssd,mdrm,value FROM t WHERE mdrm IN (${sqlList(codes)}) AND quarter_end=(SELECT max(quarter_end) FROM t)`)).toArray();
   const per={};for(const x of r){(per[x.id_rssd]=per[x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const filer=new Map();for(const id in per){const mp=per[id];let s=0,any=false;for(const c of codes){if(mp[c]!=null){s+=mp[c];any=true;}}if(any)filer.set(+id,s);}
   let all=0;for(const v of filer.values())all+=v;entSortVals.set('ALL',all);
   for(const [r2,v] of filer)entSortVals.set('BANK:'+r2,v);
   for(const n in peers){let s=0,any=false;for(const r2 of peers[n])if(filer.has(r2)){s+=filer.get(r2);any=true;}if(any)entSortVals.set('PEER:'+n,s);}
 }catch(e){}entSortField=field;}
async function renderEntList(){const field=document.getElementById('entsort').value;await computeSortVals(field);
 const desc=document.getElementById('entdesc').checked,filt=document.getElementById('entfilter').value,q=document.getElementById('entsearch').value.trim().toLowerCase();
 const showMerged=document.getElementById('showmerged').checked;
 const wlSet=loadWL();
 const pool=[{id:'ALL',label:'ALL',cat:'agg'}];
 for(const [rssd,r] of ROSTER){const rr=+rssd,L=LINEAGE[rr];const isPred=L&&rr!==L.m[L.m.length-1];
   if(isPred&&!showMerged)continue;  // hide predecessors unless Show merged is checked
   pool.push({id:'BANK:'+rssd,label:`${r.nm} (${rssd})`,cat:'bank',isPred:!!isPred,lineage:L||null});}
 for(const n in peers)pool.push({id:'PEER:'+n,label:'★ '+n,cat:'peer',isPred:false,lineage:null});
 const rows=[];for(const p of pool){if(filt==='charted'){if(!active.some(a=>a.id===p.id))continue;}else if(filt==='watchlist'){if(!wlSet.has(p.id))continue;}else if(filt!=='all'&&p.cat!==filt)continue;
   if(q&&!(p.label.toLowerCase().includes(q)||p.id.toLowerCase().includes(q)))continue;
   let sv;if(field==='name')sv=p.label.toLowerCase();else if(field==='rssd'){const m=p.id.match(/(\d+)/);sv=m?+m[1]:(desc?-Infinity:Infinity);}
   else sv=entSortVals.has(p.id)?entSortVals.get(p.id):(desc?-Infinity:Infinity);rows.push({...p,sv});}
 // secondary sort: successors sort above predecessors when all else equal
 rows.sort((a,b)=>{const fragA=a.isPred?1:0,fragB=b.isPred?1:0;
   if(typeof a.sv==='string'){const c=desc?b.sv.localeCompare(a.sv):a.sv.localeCompare(b.sv);return c||fragA-fragB;}
   const c=desc?b.sv-a.sv:a.sv-b.sv;return c||fragA-fragB;});
 {const et=document.getElementById('tabEnts');if(et)et.textContent=`Entities (${rows.length.toLocaleString()})`;}
 const cont=document.getElementById('entlistpanel');
 cont.innerHTML=rows.slice(0,800).map(r=>{const val=(field==='name')?'':(field==='rssd'?(r.id.match(/(\d+)/)?r.id.match(/(\d+)/)[1]:''):(entSortVals.has(r.id)?fmtUnit(entSortVals.get(r.id),false):''));
   const rr=r.id.startsWith('BANK:')?+r.id.slice(5):0,L=r.lineage;
   const ownNm=(ROSTER.get(rr)?.nm||String(rr)).replace(/"/g,'&quot;');
   const frag=r.isPred?` <span class="frag" title="${ownNm} (predecessor → ${L.l.replace(/"/g,'&quot;')}) — merged into current entity; link is on to combine them">${ownNm} (predecessor → ${L.l.replace(/"/g,'&quot;')})</span>`:'';
   const isOn=active.some(a=>a.id===r.id);const isWL=wlSet.has(r.id);
   return `<div class="erow${r.cat==='agg'?' agg':''}${r.isPred?' frag-row':''}${isOn?' on':''}" data-id="${r.id}" data-label="${r.label.replace(/"/g,'&quot;')}"><span class="en">${r.label}${frag}</span><span class="ev">${val}</span> <span class="pp">＋peer</span><span class="rpt" title="Open entity report">📋</span><span class="ewl${isWL?' on':''}" title="Toggle watchlist">★</span></div>`;}).join('')||'<p class="muted" style="padding:8px">none match</p>';
 cont.querySelectorAll('.erow').forEach(el=>{const id=el.dataset.id,label=el.dataset.label;
   const addChart=()=>{let aid=id,alab=label;if(id.startsWith('BANK:')){const e=bankEnt(+id.slice(5));aid=e.id;alab=e.label;}if(!active.find(a=>a.id===aid))active.push({id:aid,label:alab});renderChips();scheduleRecompute();};
   el.querySelector('.en').onclick=addChart;el.querySelector('.ev').onclick=addChart;
   el.querySelector('.pp').onclick=ev=>{ev.stopPropagation();if(!id.startsWith('BANK:')){showToast('Peer members must be holding companies.');return;}const rssd=+id.slice(5);if(!peerMembers.find(a=>a.rssd===rssd))peerMembers.push({rssd,label});renderPeerBuilder();document.getElementById('peerbox').open=true;};
   el.querySelector('.rpt').onclick=ev=>{ev.stopPropagation();if(id.startsWith('BANK:'))openReport(id);};
   el.querySelector('.ewl').onclick=ev=>{ev.stopPropagation();const wl2=loadWL();if(wl2.has(id)){wl2.delete(id);ev.currentTarget.classList.remove('on');}else{wl2.add(id);ev.currentTarget.classList.add('on');}saveWL(wl2);if(document.getElementById('entfilter').value==='watchlist')renderEntList();};});}
let entFloating=false;
function switchTab(items){
 if(entFloating&&!items){dockEnts();return;}          // clicking Entities while floating re-docks it
 document.getElementById('panelItems').style.display=items?'flex':'none';
 if(!entFloating)document.getElementById('panelEnts').style.display=items?'none':'flex';
 document.getElementById('tabItems').classList.toggle('on',items);document.getElementById('tabEnts').classList.toggle('on',!items);
 if(!items)renderEntList();}
function detachEnts(){const p=document.getElementById('panelEnts');entFloating=true;p.classList.add('entfloat');p.style.display='flex';
 document.getElementById('panelItems').style.display='flex';
 document.getElementById('tabItems').classList.add('on');document.getElementById('tabEnts').classList.remove('on');
 document.getElementById('entdetach').textContent='⧈ Dock';renderEntList();}
function dockEnts(){const p=document.getElementById('panelEnts');entFloating=false;p.classList.remove('entfloat');p.style.cssText='';
 document.getElementById('entdetach').textContent='⧉ Detach';
 document.getElementById('panelItems').style.display='none';document.getElementById('panelEnts').style.display='flex';
 document.getElementById('tabItems').classList.remove('on');document.getElementById('tabEnts').classList.add('on');renderEntList();}

// ---- compute + draw ----
const _assetRows=new Map();
let _rcSeq=0,_rcTimer=null;
// Debounce user-triggered recomputes: rapid multi-select coalesces into one run.
// Direct recompute() is still used for data-load recovery (ensureOldActive/ensureHist).
function scheduleRecompute(){clearTimeout(_rcTimer);_rcTimer=setTimeout(recompute,60);}
async function recompute(){if(!measures.length||!active.length){lastSeries=[];Qall=[];draw();return;}
 const mySeq=++_rcSeq;
 const skW=n=>`<div style="height:14px;border-radius:3px;background:linear-gradient(90deg,var(--head,#eef2f7) 25%,var(--bg2,#f7f9fb) 50%,var(--head,#eef2f7) 75%);background-size:200% 100%;animation:skshimmer 1.2s infinite;width:${n}%;margin-bottom:6px"></div>`;
 if(!document.getElementById('skstyle')){const ss=document.createElement('style');ss.id='skstyle';ss.textContent='@keyframes skshimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}';document.head.appendChild(ss);}
 const pEl=document.getElementById('panes'),cEl=document.getElementById('cards');
 if(pEl)pEl.innerHTML=`<div style="padding:24px 16px">${skW(90)}${skW(75)}${skW(85)}${skW(60)}</div>`;
 if(cEl)cEl.innerHTML=`<div style="padding:10px 0">${skW(55)}${skW(40)}${skW(48)}</div>`;
 const out=[];let ci=0;
 for(const m of measures)for(const e of active){if(mySeq!==_rcSeq)return;const blocked=isRawPct(m.code)&&isAggScope(e.id);
   const rows=blocked?[]:await seriesFor(e.id,m.code);if(mySeq!==_rcSeq)return;
   const mlbl=fullCap(m.code)||m.label;
   const label=`${e.label} · ${mlbl}`+(blocked?' (n/a — % cell, not summable across entities)':'');
   out.push({label,pct:m.pct,rows,color:COLORS[ci++%COLORS.length],eid:e.id});}
 lastSeries=out;const qs=new Set();for(const s of out)for(const r of s.rows)qs.add(r[0]);
 _assetRows.clear();for(const e of active){if(mySeq!==_rcSeq)return;const ar=await seriesFor(e.id,'BHCK2170');_assetRows.set(e.id,Object.fromEntries(ar.map(r=>[r[0],r[1]])));}

 // splice markers: seam quarters where a charted entity's RSSD lineage hands off (only when linking)
 SPLICEQ=[];if(LINK){const seen=new Set();for(const e of active){if(!e.id.startsWith('BANK:'))continue;const L=LINEAGE[+e.id.slice(5)];if(!L)continue;
   for(const sp of (L.s||[])){if(!seen.has(sp)){seen.add(sp);SPLICEQ.push(sp);}}}}
 Qall=[...qs].sort();rangeSel={a:0,b:Math.max(0,Qall.length-1)};syncSlider();await recomputeExtraCharts();draw();stateToHash();}
function syncSlider(){const n=Qall.length,w=document.getElementById('sliderwrap');if(n<2){w.style.display='none';return;}w.style.display='flex';
 for(const id of['r0','r1']){const el=document.getElementById(id);el.min=0;el.max=n-1;}
 document.getElementById('r0').value=rangeSel.a;document.getElementById('r1').value=rangeSel.b;
 document.getElementById('rfrom').value=Qall[rangeSel.a];document.getElementById('rto').value=Qall[rangeSel.b];
 const dl=document.getElementById('qlist');dl.innerHTML=Qall.map(q=>`<option value="${q}">`).join('');}
function onSlide(){let a=+document.getElementById('r0').value,b=+document.getElementById('r1').value;rangeSel={a:Math.min(a,b),b:Math.max(a,b)};
 document.getElementById('rfrom').value=Qall[rangeSel.a];document.getElementById('rto').value=Qall[rangeSel.b];draw();}
// Drag-to-resize: mirror the pinnable-tooltip ResizeObserver pattern. Each pane SVG sits in a
// .chartbox (CSS resize:both). On a user drag we capture the new px size into _chartW/_chartH,
// persist it, and redraw — pane()/paneDual() re-lay the geometry at that aspect (no distortion).
let _chartRO=null,_chartRT=null;
function applyChartSize(){
 const boxes=[...document.querySelectorAll('.chartbox')];
 if(!boxes.length){if(_chartRO){_chartRO.disconnect();_chartRO=null;}return;}
 if(window._chartW>40&&window._chartH>40){for(const b of boxes){const maxw=(b.parentElement&&b.parentElement.clientWidth)||window._chartW;b.style.width=Math.min(window._chartW,maxw)+'px';b.style.height=window._chartH+'px';}}
 // baseline = each box's current rendered size, so the observer's initial (non-user) callback is ignored
 window._chartBase=boxes.map(b=>Math.round(b.clientWidth)+'x'+Math.round(b.clientHeight));
 if(_chartRO)_chartRO.disconnect();
 _chartRO=new ResizeObserver(es=>{for(const e of es){const cw=Math.round(e.contentRect.width),ch=Math.round(e.contentRect.height);if(cw<80||ch<80)continue;if((window._chartBase||[]).includes(cw+'x'+ch))continue;if(cw===window._chartW&&ch===window._chartH)continue;window._chartW=cw;window._chartH=ch;try{localStorage.setItem('fry9c_chartsize',cw+'x'+ch);}catch(_){}clearTimeout(_chartRT);_chartRT=setTimeout(()=>{draw();if(typeof _extraCharts!=='undefined'&&_extraCharts.length)drawExtraCharts();},150);return;}});
 for(const b of boxes)_chartRO.observe(b);
}
function draw(){const host=document.getElementById('panes');
 if(!lastSeries.length){host.innerHTML='<p class="muted">Pick an entity, then click a line item on the left.</p>';document.getElementById('cards').innerHTML='';document.getElementById('tbl').innerHTML='';return;}
 const win=Qall.slice(rangeSel.a,rangeSel.b+1),ws=new Set(win);
 const normOn=document.getElementById('normbyassets')&&document.getElementById('normbyassets').checked;
 const workSeries=normOn?lastSeries.map(s=>{if(s.pct)return s;const am=_assetRows.get(s.eid)||{};const norm=s.rows.map(([q,v])=>{const a=am[q];return [q,v!=null&&a&&a!==0?100*v/a:null];});return {...s,rows:norm,pct:true,_normLabel:s.label+' / assets %'};}).map(s=>s._normLabel?{...s,label:s._normLabel}:s):lastSeries;
 const groups=[['$ thousands',workSeries.filter(s=>!s.pct)],['percent',workSeries.filter(s=>s.pct)]];let html='';
 let dualAxis=window._dualAxis||false;
 if(!window._axisRight)window._axisRight=new Set();
 const hasDol=workSeries.some(s=>!s.pct),hasPct=workSeries.some(s=>s.pct);
 const stackedOn=!!(document.getElementById('stackedmode')?.checked);
 if(hasDol&&hasPct){
   html+=`<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px"><label style="font-size:13px;cursor:pointer;user-select:none"><input type="checkbox" id="combinepct"${dualAxis?' checked':''}> Combine % onto right axis</label></div>`;
   if(dualAxis){const lFilt=workSeries.filter(s=>!s.pct);const rFilt=workSeries.filter(s=>s.pct);html+=paneDual(lFilt.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),rFilt.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),win);}
   else{for(const [unit,arr] of groups){if(!arr.length)continue;const w=arr.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))}));html+=pane(w,unit==='percent',unit,win,stackedOn&&unit==='$ thousands');}}}
 else{for(const [unit,arr] of groups){if(!arr.length)continue;const w=arr.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))}));html+=pane(w,unit==='percent',unit,win,stackedOn&&unit==='$ thousands');}}
 if(document.getElementById('idx')&&document.getElementById('idx').checked){const dol=lastSeries.filter(s=>!s.pct);
   if(dol.length){const w=dol.map(s=>{const rw=s.rows.filter(r=>ws.has(r[0]));let bb;if(_idxBase){bb=rw.find(r=>r[0]===_idxBase&&r[1]!=null&&r[1]!==0)||rw.find(r=>r[1]!=null&&r[1]!==0);}else{bb=rw.find(r=>r[1]!=null&&r[1]!==0);}const b=bb&&bb[1];return {...s,rows:b?rw.map(([q,v])=>[q,v==null?null:100*v/b]):[]};});const baseLbl=_idxBase?` (base: ${_idxBase})`:'';html+=`<div class="idx-pane"><div style="font-size:12px;color:var(--muted,#9aa3b2);padding:2px 14px">Index to 100${baseLbl} — click chart to rebase${_idxBase?` · <a href="#" id="idxbasereset" style="color:var(--muted,#9aa3b2)">reset</a>`:''}`;html+=pane(w,false,'index',win);html+=`</div>`;}}
 if(document.getElementById('qoqdelta')&&document.getElementById('qoqdelta').checked){const dol=lastSeries.filter(s=>!s.pct);
   if(dol.length){const w=dol.map(s=>{const rw=s.rows.filter(r=>ws.has(r[0]));const qm=Object.fromEntries(s.rows.map(r=>[r[0],r[1]]));const dd=rw.map((r,i)=>{const pQ=prevQtr(r[0]);const pv=pQ in qm?qm[pQ]:null;return [r[0],r[1]!=null&&pv!=null?r[1]-pv:null];}).filter(r=>r[1]!=null);return {...s,rows:dd,pct:false};});html+=pane(w,false,'$ thousands',win);}}
 host.innerHTML=html;
 applyChartSize();
 if(window._pinnedQ){document.querySelectorAll(`#panes .qband[data-q="${window._pinnedQ}"]`).forEach(g=>g.classList.add('qband-pinned'));}
 if(lastSeries.length>0&&!lastSeries.some(s=>s.rows.some(r=>ws.has(r[0])))){host.innerHTML+=`<div style="text-align:center;padding:16px 8px 4px;font-size:14px;color:var(--muted,#9aa3b2)">No data available in the selected date range — try expanding the range or selecting <b>All</b>.</div>`;}
 const cpEl=document.getElementById('combinepct');if(cpEl)cpEl.onchange=()=>{window._dualAxis=cpEl.checked;draw();};
 const kpiSelEl=document.getElementById('kpisel'),kpiSelRow=document.getElementById('kpiselrow');
 if(lastSeries.length>1){kpiSelRow.style.display='';const pv=kpiSelEl.value;kpiSelEl.innerHTML=lastSeries.map((s,i)=>`<option value="${i}">${s.label||s.id||('Series '+(i+1))}</option>`).join('');if(pv&&+pv<lastSeries.length)kpiSelEl.value=pv;}else{kpiSelRow.style.display='none';kpiSelEl.innerHTML='';}
 const kpiIdx=lastSeries.length>1?(+kpiSelEl.value||0):0;
 const prim={...lastSeries[kpiIdx],rows:lastSeries[kpiIdx].rows.filter(r=>ws.has(r[0]))};
 // MEDIUM-2: date-based QoQ/YoY — positional v[n-2]/v[n-5] gives wrong results when a filer
 // has reporting gaps or lineage hand-offs. Use the quarter exactly 1/4 quarters prior by date.
 const primR=prim.rows,last=primR.length?primR[primR.length-1][1]:null,lastQ=primR.length?primR[primR.length-1][0]:null;
 const qmapObj=Object.fromEntries(primR.map(r=>[r[0],r[1]]));
 const pQ=lastQ?prevQtr(lastQ):null,yQ=lastQ?yoyQtr(lastQ):null;
 const prev=(pQ&&pQ in qmapObj)?qmapObj[pQ]:null,yr=(yQ&&yQ in qmapObj)?qmapObj[yQ]:null;
 const f0=primR.length?primR[0][1]:null,f0q=primR.length?primR[0][0]:null;
 // LOW-2: guard sign-flip % changes (e.g. loss → profit or vice versa) — show null so the "▲/▼"
 // arrow isn't misleading (100*(50/-100-1) = -150% looks like a decline but it's an improvement).
 const sameSign=(a,b)=>(a>=0)===(b>=0);
 const pctChg=(a,b)=>(a!=null&&b!=null&&b!==0&&sameSign(a,b))?100*(a/b-1):null;
 const qoq=pctChg(last,prev),yoy=pctChg(last,yr),tot=pctChg(last,f0);
 const cls=x=>x==null?'':(x>=0?'up':'dn'),ar=x=>x==null?'—':((x>=0?'▲ ':'▼ ')+Math.abs(x).toFixed(1)+'%');
 const qoqRaw=last!=null&&prev!=null?last-prev:null,yoyRaw=last!=null&&yr!=null?last-yr:null,totRaw=last!=null&&f0!=null?last-f0:null;
 const absChg=(d)=>{if(d==null)return '';const s=d>=0?'+':'−';const a=Math.abs(d);if(prim.pct)return `${s}${a.toFixed(2)} pp`;if(a>=1e9)return `${s}${(a/1e9).toLocaleString(undefined,{maximumFractionDigits:2})} T`;if(a>=1e6)return `${s}${(a/1e6).toLocaleString(undefined,{maximumFractionDigits:2})} B`;if(a>=1e3)return `${s}${(a/1e3).toLocaleString(undefined,{maximumFractionDigits:1})} M`;return `${s}${a.toLocaleString()} k`;};
 const hasAgg=active.some(a=>a.id==='ALL'||a.id.startsWith('PEER:')||a.id.startsWith('ET:'));
 const aggNote=hasAgg?`<div style="font-size:13px;color:#d97706;padding:4px 0 2px" title="Dollar figures for ALL/peer/type-group entities are Σ of individual filer values — ratios (%) are Σnumerator/Σdenominator, not averages">⚠ Aggregate view — $ values are sums across filers; ratios are population-weighted</div>`:'';
 document.getElementById('cards').innerHTML=
  aggNote+
  `<div class=card><div class=k>${prim.label} — latest${lastQ?` (${lastQ})`:''}</div><div class=v>${fmtUnit(last,prim.pct)}</div></div>`+
  `<div class=card><div class=k>QoQ${pQ&&prev!=null?' vs '+pQ:''}</div><div class="v ${cls(qoq)}">${ar(qoq)}</div>${qoq!=null?`<div class="muted" style="font-size:13px;margin-top:2px">${absChg(qoqRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>YoY${yQ&&yr!=null?' vs '+yQ:''}</div><div class="v ${cls(yoy)}">${ar(yoy)}</div>${yoy!=null?`<div class="muted" style="font-size:13px;margin-top:2px">${absChg(yoyRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>Total Δ (range${f0q?' from '+f0q:''})</div><div class="v ${cls(tot)}">${ar(tot)}</div>${tot!=null?`<div class="muted" style="font-size:13px;margin-top:2px">${absChg(totRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>Series</div><div class=v>${lastSeries.length}</div></div>`;
 const maps=lastSeries.map(s=>Object.fromEntries(s.rows));
 const head=['quarter_end',...lastSeries.map(s=>s.label+(s.pct?' (%)':' ($k)'))];
 const body=win.map(q=>[q,...maps.map((mp,i)=>mp[q]==null?'':(lastSeries[i].pct?(+mp[q]).toFixed(2)+'%':fmtUnit(mp[q],false)))]);
 const expBody=win.map(q=>[q,...maps.map((mp,i)=>mp[q]==null?'':(lastSeries[i].pct?(+mp[q]).toFixed(3):mp[q]))]);
 let h='<table><tr>'+head.map(x=>`<th>${x}</th>`).join('')+'</tr>';
 for(const r of body)h+='<tr>'+r.map(x=>`<td>${x}</td>`).join('')+'</tr>';
 document.getElementById('tbl').innerHTML=h+'</table>';window._exp={head,body:expBody};
 const snapEl=document.getElementById('snapshot');
 if(lastSeries.length>1&&snapEl){
  const fmtDelta=(d,isPct)=>{if(d==null)return '';const sg=d>=0?'+':'−';const a=Math.abs(d);if(isPct)return `${sg}${a.toFixed(2)} pp`;if(a>=1e9)return `${sg}${(a/1e9).toLocaleString(undefined,{maximumFractionDigits:2})} T`;if(a>=1e6)return `${sg}${(a/1e6).toLocaleString(undefined,{maximumFractionDigits:2})} B`;if(a>=1e3)return `${sg}${(a/1e3).toLocaleString(undefined,{maximumFractionDigits:1})} M`;return `${sg}${a.toLocaleString()} k`;};
  const snapRows=lastSeries.map(s=>{const sR=s.rows.filter(r=>ws.has(r[0]));const sLast=sR.length?sR[sR.length-1][1]:null,sLastQ=sR.length?sR[sR.length-1][0]:null;const sMap=Object.fromEntries(sR.map(r=>[r[0],r[1]]));const sPQ=sLastQ?prevQtr(sLastQ):null,sYQ=sLastQ?yoyQtr(sLastQ):null;const sPrev=(sPQ&&sPQ in sMap)?sMap[sPQ]:null,sYr=(sYQ&&sYQ in sMap)?sMap[sYQ]:null;const sF0=sR.length?sR[0][1]:null;const sQoq=pctChg(sLast,sPrev),sYoy=pctChg(sLast,sYr),sTot=pctChg(sLast,sF0);const sQR=sLast!=null&&sPrev!=null?sLast-sPrev:null,sYR=sLast!=null&&sYr!=null?sLast-sYr:null,sTR=sLast!=null&&sF0!=null?sLast-sF0:null;return {s,sLast,sQoq,sYoy,sTot,sQR,sYR,sTR};});
  let sh=`<table style="width:100%;margin-top:8px;border-collapse:collapse;font-size:13px"><thead><tr><th style="text-align:left;padding:3px 6px">Entity</th><th style="padding:3px 6px">Latest</th><th style="padding:3px 6px">QoQ</th><th style="padding:3px 6px">YoY</th><th style="padding:3px 6px">Total Δ</th></tr></thead><tbody>`;
  for(const {s,sLast,sQoq,sYoy,sTot,sQR,sYR,sTR} of snapRows){const dot=`<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color};margin-right:5px"></span>`;sh+=`<tr><td style="text-align:left;padding:3px 6px">${dot}${s.label}</td><td style="padding:3px 6px;text-align:right">${fmtUnit(sLast,s.pct)}</td><td class="${cls(sQoq)}" style="padding:3px 6px;text-align:right">${ar(sQoq)}${sQR!=null?` <span class="muted" style="font-size:12px">${fmtDelta(sQR,s.pct)}</span>`:''}</td><td class="${cls(sYoy)}" style="padding:3px 6px;text-align:right">${ar(sYoy)}${sYR!=null?` <span class="muted" style="font-size:12px">${fmtDelta(sYR,s.pct)}</span>`:''}</td><td class="${cls(sTot)}" style="padding:3px 6px;text-align:right">${ar(sTot)}${sTR!=null?` <span class="muted" style="font-size:12px">${fmtDelta(sTR,s.pct)}</span>`:''}</td></tr>`;}
  snapEl.innerHTML=sh+'</tbody></table>';
 }else if(snapEl){snapEl.innerHTML='';} const _aBtn=document.getElementById('addchartbtn');if(_aBtn)_aBtn.style.display='';drawExtraCharts();}
// ---- extra charts ----
let _extraCharts=[],_nextChartId=1;window._addToChartId=null;
function addChart(){const id=_nextChartId++;_extraCharts.push({id,measures:[],lastSeries:[]});renderExtraChartsArea();}
function removeChart(id){_extraCharts=_extraCharts.filter(c=>c.id!==id);if(window._addToChartId===id)window._addToChartId=null;renderExtraChartsArea();}
function setChartTarget(id){window._addToChartId=(window._addToChartId===id)?null:id;document.querySelectorAll('.ec-target-btn').forEach(b=>{b.style.background='';b.style.color='';});if(window._addToChartId!=null){const b=document.getElementById('ec-tgt-'+window._addToChartId);if(b){b.style.background='var(--acc,#1d4ed8)';b.style.color='#fff';}}if(window._addToChartId!=null)showToast('Click tree items to add to Chart '+(window._addToChartId+1),'warn');}
window.addChart=addChart;window.removeChart=removeChart;window.setChartTarget=setChartTarget;
function renderExtraChartsArea(){const area=document.getElementById('extracharts-area');if(!area)return;area.innerHTML=_extraCharts.map(chart=>`<div class="extra-chart" id="ec-${chart.id}" style="margin-top:14px;border-top:1px solid var(--head,#eef2f7);padding-top:8px"><div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px"><b style="font-size:13px;color:var(--muted,#9aa3b2)">Chart ${chart.id+1}</b><button class="sec" style="font-size:12px;padding:1px 6px" onclick="removeChart(${chart.id})">✕</button><button class="sec ec-target-btn" id="ec-tgt-${chart.id}" style="font-size:12px;padding:1px 6px" onclick="setChartTarget(${chart.id})">▶ Add items</button><span id="ec-mchips-${chart.id}"></span></div><div id="ec-panes-${chart.id}"><p class="muted" style="font-size:13px">Click ▶ Add items, then a line item on the left.</p></div></div>`).join('');_extraCharts.forEach(c=>renderExtraChartChips(c));drawExtraCharts();}
function renderExtraChartChips(chart){const c=document.getElementById('ec-mchips-'+chart.id);if(!c)return;c.innerHTML=chart.measures.map((m,i)=>`<span class="chip" style="font-size:12px"><b>${m.label}</b> <span class="muted">${m.pct?'%':'$'}</span><span class="x" data-ci="${chart.id}" data-i="${i}">✕</span></span>`).join('');c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{const ch=_extraCharts.find(c=>c.id===+x.dataset.ci);if(ch){ch.measures.splice(+x.dataset.i,1);renderExtraChartChips(ch);recomputeExtraCharts().then(()=>drawExtraCharts());}});}
async function recomputeExtraCharts(){for(const chart of _extraCharts){if(!chart.measures.length||!active.length){chart.lastSeries=[];continue;}const out=[];let ci=0;for(const m of chart.measures)for(const e of active){const rows=await seriesFor(e.id,m.code);const mlbl=fullCap(m.code)||m.label;const label=`${e.label} · ${mlbl}`;out.push({label,pct:m.pct,rows,color:COLORS[ci++%COLORS.length],eid:e.id});}chart.lastSeries=out;}}
function drawExtraCharts(){if(!_extraCharts.length)return;const win=Qall.slice(rangeSel.a,rangeSel.b+1),ws=new Set(win);for(const chart of _extraCharts)drawExtraChart(chart,win,ws);applyChartSize();}
function drawExtraChart(chart,win,ws){const host=document.getElementById('ec-panes-'+chart.id);if(!host)return;if(!chart.lastSeries.length){host.innerHTML='<p class="muted" style="font-size:13px">Click ▶ Add items, then a line item on the left.</p>';return;}const _m=measures;measures=chart.measures;let html='';try{const hasDol=chart.lastSeries.some(s=>!s.pct),hasPct=chart.lastSeries.some(s=>s.pct);if(hasDol&&hasPct){const lF=chart.lastSeries.filter(s=>!s.pct),rF=chart.lastSeries.filter(s=>s.pct);html+=paneDual(lF.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),rF.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),win);}else{const groups=[['$ thousands',chart.lastSeries.filter(s=>!s.pct)],['percent',chart.lastSeries.filter(s=>s.pct)]];for(const[unit,arr]of groups){if(!arr.length)continue;html+=pane(arr.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),unit==='percent',unit,win,false);}}}finally{measures=_m;}host.innerHTML=html;}
function pane(series,pct,unit,win,stacked){const W=1080,pad=64,n=win.length;const _showL=window._inlineLbls!==false;const _gut=_showL?170:16;const _vbw=W+_gut;const _pinned=window._chartW>40&&window._chartH>40;let H=_pinned?Math.round(_vbw*window._chartH/window._chartW):420;H=Math.max(260,Math.min(2800,H));const _svgsty=(_pinned?'width:100%;height:100%':'width:100%;height:auto')+';display:block';const xi=Object.fromEntries(win.map((q,i)=>[q,i]));
 let mn=Infinity,mx=-Infinity;for(const s of series)for(const r of s.rows){mn=Math.min(mn,r[1]);mx=Math.max(mx,r[1]);}
 if(!isFinite(mn)){const aC=DK()?'#9aa3b2':'#5a6478';return `<div class="chartbox"><svg viewBox="0 0 ${_vbw} ${H}" preserveAspectRatio="none" style="${_svgsty}" xmlns="http://www.w3.org/2000/svg"><text x="${(_vbw/2).toFixed(0)}" y="${(H/2).toFixed(0)}" font-size="16" fill="${aC}" text-anchor="middle" dominant-baseline="middle">No data available for this entity / date range</text></svg></div>`;}
 // In stacked mode scale to total; otherwise anchor at zero baseline
 if(stacked){mn=0;const tots={};for(const q of win)tots[q]=0;for(const s of series){const m=Object.fromEntries(s.rows.map(r=>[r[0],r[1]]));for(const q of win)tots[q]+=(m[q]??0);}mx=Math.max(...Object.values(tots),0);}
 else{if(unit==='$ thousands'&&mn>0)mn=0;if(unit==='percent'){if(mn>0)mn=0;if(mx<0)mx=0;}}
 if(mn===mx){mx=mn+1;}
 const rg=(mx-mn)||1;
 const X=i=>pad+i*(W-2*pad)/Math.max(1,n-1),Y=v=>H-pad-(v-mn)/rg*(H-2*pad);
 const f=v=>unit==='percent'?v.toFixed(2)+'%':unit==='index'?v.toFixed(0):fmtUnit(v,false);
 const gC=DK()?'#243044':'#eef2f7',aC=DK()?'#9aa3b2':'#5a6478',tC=DK()?'#e6e9ef':'#14213d';
 // gridlines at min / mid / max, with a distinct zero line whenever 0 falls inside the range
 const ticks=[...new Set([mn,(mn+mx)/2,mx])];
 let tk=ticks.map(v=>`<line x1="${pad}" y1="${Y(v)}" x2="${W-pad}" y2="${Y(v)}" stroke="${gC}"></line><text x="8" y="${Y(v)+4}" font-size="11" fill="${aC}">${f(v)}</text>`).join('');
 if(mn<0&&mx>0){const zC=DK()?'#6b7689':'#9aa3b2';tk+=`<line x1="${pad}" y1="${Y(0)}" x2="${W-pad}" y2="${Y(0)}" stroke="${zC}" stroke-width="1.5"></line><text x="8" y="${Y(0)+4}" font-size="11" fill="${zC}">${unit==='percent'?'0%':'0'}</text>`;}
 // RSSD-lineage splice markers: faint dashed vertical where the predecessor hands off to the successor
 for(const sq of SPLICEQ){if(xi[sq]==null)continue;const sx=X(xi[sq]).toFixed(1);const sC=DK()?'#5a6478':'#b0b8c4';
   tk+=`<line x1="${sx}" y1="${pad}" x2="${sx}" y2="${H-pad}" stroke="${sC}" stroke-width="1" stroke-dasharray="3 3"></line><text x="${sx}" y="${pad-3}" font-size="9" fill="${sC}" text-anchor="middle">RSSD change</text>`;}
 const recC=DK()?'rgba(217,119,6,0.09)':'rgba(217,119,6,0.07)';
 for(const [rs,re,rl] of RECESSIONS){const i0=win.findIndex(q=>q>=rs);const i1=win.reduceRight((a,q,i)=>a<0&&q<=re?i:a,-1);if(i0<0||i1<0||i0>i1)continue;const rx=X(i0),rx2=X(i1);tk+=`<rect x="${rx.toFixed(1)}" y="${pad}" width="${Math.max(2,rx2-rx).toFixed(1)}" height="${H-2*pad}" fill="${recC}"></rect><text x="${((rx+rx2)/2).toFixed(1)}" y="${pad-3}" font-size="8" fill="#d97706" text-anchor="middle" opacity=".7">${rl}</text>`;}
 if(_reflineVal!=null&&_reflineVal>=mn&&_reflineVal<=mx){const ry=Y(_reflineVal).toFixed(1);tk+=`<line x1="${pad}" y1="${ry}" x2="${W-pad}" y2="${ry}" stroke="#e07a1f" stroke-width="1.5" stroke-dasharray="5 3"></line><text x="${pad+4}" y="${+ry-4}" font-size="9" fill="#e07a1f">${_reflineLbl||_reflineVal}</text>`;}
 const dotC=DK()?'#0f1825':'#fff';
 const byQ={};   // win-index -> {x, q, items:[{cy,color,label,val}]} for nearest-X hover snapping
 let areas='',paths='',pts='',slbls='',_el=[];
 if(stacked){
   // Stacked area rendering: cumulative polygon bands per series
   const sMaps=series.map(s=>Object.fromEntries(s.rows.map(r=>[r[0],r[1]])));
   const botY={};for(const q of win)botY[q]=0;
   for(let si=0;si<series.length;si++){const s=series[si];const sm=sMaps[si];
     const topPts=[],botPts=[];let lastTopCx=null,lastTopCy=null;
     for(const q of win){if(xi[q]==null)continue;const v=sm[q]??0;const bot=botY[q];const top=bot+(v>0?v:0);
       const cx=X(xi[q]),cy_top=Y(top),cy_bot=Y(bot),cy_mid=Y(bot+(v>0?v/2:0));
       topPts.push({cx,cy:cy_top});botPts.push({cx,cy:cy_bot});lastTopCx=cx;lastTopCy=cy_top;
       (byQ[xi[q]]=byQ[xi[q]]||{x:cx,q,items:[]}).items.push({cy:cy_mid,color:s.color,label:s.label,val:f(v)});
       botY[q]=top;}
     if(topPts.length>1){
       const fwd=topPts.map((p,i)=>(i?'L':'M')+p.cx.toFixed(1)+' '+p.cy.toFixed(1)).join(' ');
       const rev=[...botPts].reverse().map(p=>'L'+p.cx.toFixed(1)+' '+p.cy.toFixed(1)).join(' ');
       areas+=`<path d="${fwd} ${rev} Z" fill="${s.color}" fill-opacity="0.72" stroke="${s.color}" stroke-width="0.5"></path>`;}
     if(lastTopCx!=null){const pts2=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const sl=(nE>1&&nM===1?pts2[0]:(nE===1?short(pts2.slice(1).join(' \xb7 '))||short(s.label):short(s.label))).slice(0,90);_el.push({x:lastTopCx+5,y:lastTopCy+4,sl,color:s.color});}}
 }else{
   for(const s of series){let p='',firstCx,lastCx,lastCy;s.rows.forEach((r,k)=>{const cx=X(xi[r[0]]).toFixed(1),cy=Y(r[1]).toFixed(1);if(k===0)firstCx=cx;lastCx=cx;lastCy=cy;p+=(k?'L':'M')+cx+' '+cy+' ';
     const qi=xi[r[0]];(byQ[qi]=byQ[qi]||{x:+cx,q:r[0],items:[]}).items.push({cy:+cy,color:s.color,label:s.label,val:f(r[1])});
     pts+=`<circle class="pt" cx="${cx}" cy="${cy}" r="1.5" fill="${s.color}" stroke="${dotC}" stroke-width="1"></circle>`;});
     if(s.rows.length>1){const by=Y(Math.max(mn,0)).toFixed(1);areas+=`<path d="${p}L${lastCx} ${by} L${firstCx} ${by} Z" fill="${s.color}" fill-opacity="0.12" stroke="none"></path>`;}
     paths+=`<path d="${p}" fill="none" stroke="${s.color}" stroke-width="2"></path>`;
     if(lastCx!=null){const pts2=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const sl=(nE>1&&nM===1?pts2[0]:(nE===1?short(pts2.slice(1).join(' \xb7 '))||short(s.label):short(s.label))).slice(0,90);_el.push({x:+lastCx+5,y:+lastCy+4,sl:sl,color:s.color});}}}
 // Nearest-X hover bands: each quarter owns a full-height transparent rect spanning the midpoints
 // to its neighbors, so hovering ANYWHERE in that vertical band (any distance, any height) snaps
 // the marker(s) + tooltip to that quarter. Pure SVG+CSS so it is instant. Multi-series: every
 // series with a point at the quarter gets its own marker and a line in the shared tooltip.
 const _bi=Object.keys(byQ).map(Number).sort((a,b)=>a-b); let bands='';
 _bi.forEach((qi,k)=>{const Q=byQ[qi],xc=Q.x;
   const left=k===0?0:(byQ[_bi[k-1]].x+xc)/2, right=k===_bi.length-1?W:(xc+byQ[_bi[k+1]].x)/2;
   let mk=`<line class="reveal" x1="${xc.toFixed(1)}" y1="${pad}" x2="${xc.toFixed(1)}" y2="${H-pad}" stroke="${aC}" stroke-width="1" stroke-dasharray="2 2"></line>`;
   for(const it of Q.items)mk+=`<circle class="reveal" cx="${xc.toFixed(1)}" cy="${it.cy.toFixed(1)}" r="4" fill="${it.color}" stroke="${dotC}" stroke-width="1.5"></circle>`;
   bands+=`<g class="qband" data-q="${Q.q}"><rect class="hit" x="${left.toFixed(1)}" y="0" width="${(right-left).toFixed(1)}" height="${H}"></rect>${mk}</g>`;});
 const want=Math.min(8,n),ix=[...new Set(Array.from({length:want},(_,k)=>Math.round(k*(n-1)/Math.max(1,want-1))))];
 const lb=ix.map(i=>{const a=i===0?'start':(i===n-1?'end':'middle');return `<text x="${X(i)}" y="${H-pad+18}" font-size="10" fill="${aC}" text-anchor="${a}">${win[i]}</text>`;}).join('');
 if(_showL){const _LH=12,_MAXC=22;_el.forEach(e=>{e.lines=_wrapLbl(e.sl,_MAXC);});_el.sort((a,b)=>a.y-b.y);for(let _i=1;_i<_el.length;_i++){const _need=_el[_i-1].y+_el[_i-1].lines.length*_LH+2;if(_el[_i].y<_need)_el[_i].y=_need;}const _bot=_el.length?_el[_el.length-1].y+_el[_el.length-1].lines.length*_LH:0;const _ov=Math.max(0,_bot-(H-2));slbls=_el.map(e=>{const _x=Math.min(e.x,_vbw-_MAXC*6.4).toFixed(1);const _y=(e.y-_ov).toFixed(1);return `<text x="${_x}" y="${_y}" font-size="11" fill="${e.color}" font-weight="600">`+e.lines.map((ln,li)=>`<tspan x="${_x}" dy="${li?_LH:0}">${_esc(ln)}</tspan>`).join('')+`</text>`;}).join('');}else{slbls='';}
 return `<div class="chartbox"><svg viewBox="0 0 ${_vbw} ${H}" preserveAspectRatio="none" style="${_svgsty}" data-pl="${pad}" data-pw="${W-2*pad}" xmlns="http://www.w3.org/2000/svg">${tk}${areas}${paths}${pts}${slbls}${lb}<text x="14" y="18" font-size="13" fill="${tC}">${unit==='$ thousands'?'$':unit}</text>${bands}</svg></div>`;}
function exportSeries(){if(!window._exp){showToast('Nothing to export.');return;}dl2(window._exp.head,window._exp.body,'series');}
function exportChartSVG(){const svgs=[...document.querySelectorAll('#panes svg')];if(!svgs.length){showToast('No chart to export.');return;}let y=0;const bg=DK()?'#0f1825':'#fff';const gs=svgs.map(s=>{const vb=(s.getAttribute('viewBox')||'0 0 1080 300').split(' ').map(Number);const H=vb[3]||300;const g=`<g transform="translate(0,${y})">${s.innerHTML}</g>`;y+=H+8;return g;});const total=Math.max(y-8,1);const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 ${total}" width="1080" height="${total}"><rect width="1080" height="${total}" fill="${bg}"/>${gs.join('')}</svg>`;const a=document.createElement('a');a.href='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);a.download='chart.svg';a.click();}
function paneDual(dol,pct,win){const W=1080,pad=64,padR=80,n=win.length;const _showL=window._inlineLbls!==false;const _gut=_showL?170:16;const _vbw=W+_gut;const _pinned=window._chartW>40&&window._chartH>40;let H=_pinned?Math.round(_vbw*window._chartH/window._chartW):420;H=Math.max(260,Math.min(2800,H));const _svgsty=(_pinned?'width:100%;height:100%':'width:100%;height:auto')+';display:block';const xi=Object.fromEntries(win.map((q,i)=>[q,i]));
 let mn0=Infinity,mx0=-Infinity;for(const s of dol)for(const r of s.rows){mn0=Math.min(mn0,r[1]);mx0=Math.max(mx0,r[1]);}
 let mn1=Infinity,mx1=-Infinity;for(const s of pct)for(const r of s.rows){mn1=Math.min(mn1,r[1]);mx1=Math.max(mx1,r[1]);}
 if(!isFinite(mn0)&&!isFinite(mn1))return '';
 if(mn0>0)mn0=0;if(mn1>0)mn1=0;if(mn0===mx0)mx0=mn0+1;if(mn1===mx1)mx1=mn1+1;
 const rg0=(mx0-mn0)||1,rg1=(mx1-mn1)||1;
 const X=i=>pad+i*(W-pad-padR)/Math.max(1,n-1);
 const Y0=v=>H-pad-(v-mn0)/rg0*(H-2*pad);const Y1=v=>H-pad-(v-mn1)/rg1*(H-2*pad);
 const f0=v=>fmtUnit(v,false),f1=v=>(+v).toFixed(2)+'%';
 const gC=DK()?'#243044':'#eef2f7',aC=DK()?'#9aa3b2':'#5a6478',tC=DK()?'#e6e9ef':'#14213d';
 const ticks0=[mn0,(mn0+mx0)/2,mx0],ticks1=[mn1,(mn1+mx1)/2,mx1];
 let tk=ticks0.map(v=>`<line x1="${pad}" y1="${Y0(v)}" x2="${W-padR}" y2="${Y0(v)}" stroke="${gC}"></line><text x="8" y="${Y0(v)+4}" font-size="11" fill="${aC}">${f0(v)}</text>`).join('');
 tk+=ticks1.map(v=>`<text x="${W-padR+4}" y="${Y1(v)+4}" font-size="11" fill="${aC}">${f1(v)}</text>`).join('');
 const dotC=DK()?'#0f1825':'#fff';
 const byQ={};   // win-index -> {x,q,items:[{cy,color}]} for the hover crosshair bands (both axes)
 let areas='',paths='',pts='',slbls='',_el=[];
 const render=(arr,Yf,fmt)=>{for(const s of arr){let p='',firstCx,lastCx,lastCy;s.rows.forEach((r,k)=>{const cx=X(xi[r[0]]).toFixed(1),cy=Yf(r[1]).toFixed(1);if(k===0)firstCx=cx;lastCx=cx;lastCy=cy;p+=(k?'L':'M')+cx+' '+cy+' ';
   const qi=xi[r[0]];(byQ[qi]=byQ[qi]||{x:+cx,q:r[0],items:[]}).items.push({cy:+cy,color:s.color});
   pts+=`<circle class="pt" cx="${cx}" cy="${cy}" r="1.5" fill="${s.color}" stroke="${dotC}" stroke-width="1"></circle>`;});
   if(s.rows.length>1){const by=Yf(Math.max(mn0,mn1,0)).toFixed(1);areas+=`<path d="${p}L${lastCx} ${by} L${firstCx} ${by} Z" fill="${s.color}" fill-opacity="0.12" stroke="none"></path>`;}
   paths+=`<path d="${p}" fill="none" stroke="${s.color}" stroke-width="2"></path>`;
   if(lastCx!=null){const pts2=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const sl=(nE>1&&nM===1?pts2[0]:(nE===1?short(pts2.slice(1).join(' \xb7 '))||short(s.label):short(s.label))).slice(0,90);_el.push({x:+lastCx+5,y:+lastCy+4,sl:sl,color:s.color});}}};
 render(dol,Y0,f0);render(pct,Y1,f1);
 const want=Math.min(8,n),ix=[...new Set(Array.from({length:want},(_,k)=>Math.round(k*(n-1)/Math.max(1,want-1))))];
 const lb=ix.map(i=>`<text x="${X(i)}" y="${H-pad+18}" font-size="10" fill="${aC}" text-anchor="${i===0?'start':(i===n-1?'end':'middle')}">${win[i]}</text>`).join('');
 if(_showL){const _LH=12,_MAXC=22;_el.forEach(e=>{e.lines=_wrapLbl(e.sl,_MAXC);});_el.sort((a,b)=>a.y-b.y);for(let _i=1;_i<_el.length;_i++){const _need=_el[_i-1].y+_el[_i-1].lines.length*_LH+2;if(_el[_i].y<_need)_el[_i].y=_need;}const _bot=_el.length?_el[_el.length-1].y+_el[_el.length-1].lines.length*_LH:0;const _ov=Math.max(0,_bot-(H-2));slbls=_el.map(e=>{const _x=Math.min(e.x,_vbw-_MAXC*6.4).toFixed(1);const _y=(e.y-_ov).toFixed(1);return `<text x="${_x}" y="${_y}" font-size="11" fill="${e.color}" font-weight="600">`+e.lines.map((ln,li)=>`<tspan x="${_x}" dy="${li?_LH:0}">${_esc(ln)}</tspan>`).join('')+`</text>`;}).join('');}else{slbls='';}
 // Hover crosshair bands — parity with pane() so dual-axis gets the identical tracking line + markers.
 const _bi=Object.keys(byQ).map(Number).sort((a,b)=>a-b);let bands='';
 _bi.forEach((qi,k)=>{const Q=byQ[qi],xc=Q.x;
   const left=k===0?0:(byQ[_bi[k-1]].x+xc)/2,right=k===_bi.length-1?W:(xc+byQ[_bi[k+1]].x)/2;
   let mk=`<line class="reveal" x1="${xc.toFixed(1)}" y1="${pad}" x2="${xc.toFixed(1)}" y2="${H-pad}" stroke="${aC}" stroke-width="1" stroke-dasharray="2 2"></line>`;
   for(const it of Q.items)mk+=`<circle class="reveal" cx="${xc.toFixed(1)}" cy="${it.cy.toFixed(1)}" r="4" fill="${it.color}" stroke="${dotC}" stroke-width="1.5"></circle>`;
   bands+=`<g class="qband" data-q="${Q.q}"><rect class="hit" x="${left.toFixed(1)}" y="0" width="${(right-left).toFixed(1)}" height="${H}"></rect>${mk}</g>`;});
 return `<div class="chartbox"><svg viewBox="0 0 ${_vbw} ${H}" preserveAspectRatio="none" style="${_svgsty}" data-pl="${pad}" data-pw="${W-pad-padR}" xmlns="http://www.w3.org/2000/svg"><text x="14" y="18" font-size="13" fill="${tC}">$ (left) \xb7 % (right)</text>${tk}${areas}${paths}${pts}${slbls}${lb}${bands}</svg></div>`;}

// ---- league / rank table ----
let LGMEAS=[];
function buildLGMEAS(){
 const seed=[
  {code:'BHCK2170',label:'Total assets',pct:false},
  {code:'S_DEP',label:'Total deposits',pct:false},
  {code:'BHCK2122',label:'Total loans',pct:false},
  {code:'BHCK3210',label:'Total equity',pct:false},
  {code:'BHCK4340',label:'Net income (YTD)',pct:false},
 ];
 const seen=new Set(seed.map(m=>m.code));const out=[...seed];
 for(const[k,d] of Object.entries(DERIV)){if(seen.has(k))continue;seen.add(k);
  const lbl=d.lbl||k;const parts=lbl.split(' ▸ ');const shortLbl=parts.length>1?parts.slice(1).join(' ▸ '):lbl;
  out.push({code:k,label:shortLbl,pct:d.type!=='sum'});}
 return out;}
let lgSortField='v',lgSortDir=-1;   // league sort: field v/qoq/yoy, dir 1=asc -1=desc
async function perFilerValues(measCode, quarters){
 // map: quarter -> Map(rssd -> per-filer value) for a raw code OR a DERIV ratio/sum
 const out={}; for(const q of quarters) out[q]=new Map();
 const d=DERIV[measCode]||DYN[measCode];   // LOW-1: also handle dynamic SUB: subtotals
 if(d){const terms=[...d.plus,...(d.minus||[]),...(d.den||[])];
   const codes=[...new Set(terms.flatMap(term2codes))];
   const r=(await conn.query(`SELECT id_rssd,quarter_end,mdrm,value FROM t WHERE mdrm IN (${sqlList(codes)}) AND quarter_end IN (${sqlList(quarters)})`)).toArray();
   const byqf={}; for(const x of r){const q=String(x.quarter_end);(byqf[q]=byqf[q]||{});(byqf[q][x.id_rssd]=byqf[q][x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const acc=(mp,arr)=>{let s=0,seen=false;for(const t of arr){const v=termVal(mp,t);if(v!=null){s+=v;seen=true;}}return [s,seen];};
   for(const q of quarters){const per=byqf[q]||{};
     for(const id in per){const mp=per[id];const [np,ns]=acc(mp,d.plus);const [nm,ms]=acc(mp,d.minus||[]);const num=np-nm;const [dp,ds]=acc(mp,d.den||[]);
       if(d.type==='sum'){if(ns||ms)out[q].set(+id,num);}else{if((ns||ms)&&ds&&dp>0)out[q].set(+id,100*num/dp);}}}
 } else {
   const r=(await conn.query(`SELECT id_rssd,quarter_end,SUM(value) v FROM t WHERE mdrm='${measCode}' AND quarter_end IN (${sqlList(quarters)}) GROUP BY id_rssd,quarter_end`)).toArray();
   for(const x of r) out[String(x.quarter_end)].set(Number(x.id_rssd), Number(x.v));
 }
 return out;}
async function renderLeague(){
 const meas=LGMEAS[+document.getElementById('lgmeasure').value];
 const q=document.getElementById('lgquarter').value, topn=+document.getElementById('lgtopn').value;
 const prevQ=prevQtr(q), yoyQ=yoyQtr(q);
 const quarters=[q,prevQ,yoyQ].filter(Boolean);
 document.getElementById('leaguebody').innerHTML='<p class="muted">Computing…</p>';
 const bkt=document.getElementById('lgbucket').value;
 const qi=ALLQ.indexOf(q);const spkQs=qi>=0?ALLQ.slice(Math.max(0,qi-7),qi+1):[];
 const allFetchQs=[...new Set([...quarters,...spkQs])];
 const [vals,avals]=await Promise.all([perFilerValues(meas.code,allFetchQs),bkt?perFilerValues('BHCK2170',[q]):Promise.resolve(null)]);
 const assetMap=avals?avals[q]||new Map():null;
 const cur=vals[q]||new Map();
 const spkFn=rssd=>{const pts=spkQs.map(sq=>vals[sq]?vals[sq].get(rssd):undefined).filter(v=>v!=null&&!isNaN(v));if(pts.length<2)return '';const mn2=Math.min(...pts),mx2=Math.max(...pts),rng=mx2-mn2||1;const W2=56,H2=20,pad2=2;const xs=pts.map((_,i)=>(pad2+i*(W2-2*pad2)/(pts.length-1)).toFixed(1));const ys=pts.map(v=>(H2-pad2-(v-mn2)/rng*(H2-2*pad2)).toFixed(1));const poly=xs.map((x,i)=>`${x},${ys[i]}`).join(' ');const lc=DK()?'#4ade80':'#1b7f3b';return `<svg width="${W2}" height="${H2}" style="vertical-align:middle"><polyline points="${poly}" fill="none" stroke="${lc}" stroke-width="1.5"></polyline></svg>`;};
 let rows=[...cur.entries()].map(([rssd,v])=>{const pv=prevQ?vals[prevQ].get(rssd):null, yv=yoyQ?vals[yoyQ].get(rssd):null;
   const qoq=meas.pct?(pv!=null?v-pv:null):(pv?100*(v/pv-1):null);
   const yoy=meas.pct?(yv!=null?v-yv:null):(yv?100*(v/yv-1):null);
   return {rssd,name:(ROSTER.get(rssd)&&ROSTER.get(rssd).nm)||String(rssd),v,qoq,yoy};});
 if(assetMap&&bkt){const lo=bkt==='-'?0:(+bkt)*1e9,hi=bkt==='-'?1e8:(+bkt)*1e10;rows=rows.filter(r=>{const a=assetMap.get(r.rssd);return a!=null&&a>=lo&&(bkt==='-'?a<1e8:a<hi);});}
 rows.sort((a,b)=>{const av=a[lgSortField],bv=b[lgSortField];   // nulls always last
   if(av==null&&bv==null)return 0;if(av==null)return 1;if(bv==null)return -1;return lgSortDir*(av-bv);});
 const valSorted=rows.filter(r=>r.v!=null).sort((a,b)=>b.v-a.v);const nm=valSorted.length;
 const pctileMap=new Map(valSorted.map((r,i)=>[r.rssd,nm>1?Math.round(100*(nm-1-i)/(nm-1)):50]));
 const show=topn?rows.slice(0,topn):rows;
 const fmtV=v=>v==null?'—':(meas.pct?(+v).toFixed(2)+'%':fmtUnit(v,false));
 const fmtD=x=>x==null?'—':(meas.pct?((x>=0?'+':'')+x.toFixed(2)+' pp'):((x>=0?'▲ ':'▼ ')+Math.abs(x).toFixed(1)+'%'));
 const cls=x=>x==null?'':(x>=0?'up':'dn');
 const arr=f=>lgSortField===f?(lgSortDir<0?' ▼':' ▲'):'';
 const pcClr=pc=>pc>=75?'color:#1b7f3b':pc<25?'color:#c0392b':'';
 let h=`<table><tr><th>#</th><th style="text-align:left">Holding company</th>`+
   `<th class="lgs" data-f="v" style="cursor:pointer" title="click to sort">${meas.label}${arr('v')}</th>`+
   `<th class="lgs" data-f="qoq" style="cursor:pointer" title="click to sort">QoQ${arr('qoq')}</th>`+
   `<th class="lgs" data-f="yoy" style="cursor:pointer" title="click to sort">YoY${arr('yoy')}</th>`+
   `<th title="Percentile rank by value this quarter — 99th = top 1%">Pctile</th>`+
   `<th title="8-quarter trend">Trend</th></tr>`;
 show.forEach((r,i)=>{const pc=pctileMap.get(r.rssd);const on=active.some(a=>a.id===`BANK:${r.rssd}`);h+=`<tr${on?' class="lgon-row"':''}><td>${i+1}</td><td class="lglink${on?' lgon':''}" data-id="BANK:${r.rssd}" data-nm="${r.name.replace(/"/g,'&quot;')}" style="text-align:left;cursor:pointer;text-decoration:underline dotted" title="${on?'In chart':'Click to add to chart'}">${r.name} <span style="color:#9aa3b2">(${r.rssd})</span>${on?' <span style="font-size:12px;color:#1b7f3b">✓</span>':''}</td><td>${fmtV(r.v)}</td><td class="${cls(r.qoq)}">${fmtD(r.qoq)}</td><td class="${cls(r.yoy)}">${fmtD(r.yoy)}</td><td style="${pcClr(pc)}">${pc!=null?pc+'th':'—'}</td><td>${spkFn(r.rssd)}</td></tr>`;});
 h+=`</table><p class="muted">${show.length} of ${rows.length} holding companies · ${q}${meas.pct?' · QoQ/YoY in percentage points':''} · click a name to add to chart · click a header to sort</p>`;
 const body=document.getElementById('leaguebody'); body.innerHTML=h; window._lg={meas,q,rows:show,pctileMap};
 body.querySelectorAll('.lgs').forEach(th=>th.onclick=()=>{const f=th.dataset.f;if(lgSortField===f)lgSortDir*=-1;else{lgSortField=f;lgSortDir=-1;}renderLeague();});
 body.querySelectorAll('.lglink').forEach(td=>{td.onclick=()=>{const id=td.dataset.id,nm=td.dataset.nm;if(!active.find(a=>a.id===id))active.push({id,label:nm});renderChips();scheduleRecompute();};});}
async function openLeague(){
 LGMEAS=buildLGMEAS();
 const msel=document.getElementById('lgmeasure');
 msel.innerHTML=LGMEAS.map((m,i)=>`<option value="${i}">${m.label}</option>`).join('');
 const qsel=document.getElementById('lgquarter');
 if(!qsel.options.length){qsel.innerHTML=ALLQ.map(q=>`<option>${q}</option>`).join(''); if(ALLQ.length)qsel.value=ALLQ[ALLQ.length-1];}
 document.getElementById('leaguemodal').style.display='flex'; await renderLeague();}

// ---- call-report view ----
function renderFentChips(){const c=document.getElementById('fent-chips');if(!c)return;const ents=window._feEnts||[];c.innerHTML=ents.map((ent,i)=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:13px">${ent.label}<span class="fent-del" data-i="${i}" style="cursor:pointer;color:#c0392b;margin-left:3px">×</span></span>`).join('');for(const d of document.querySelectorAll('.fent-del'))d.onclick=()=>{(window._feEnts||[]).splice(+d.dataset.i,1);renderFentChips();renderForm();};}
function fentCond(){const ents=window._feEnts||[];if(!ents.length)return null;const rs=new Set();for(const ent of ents){if(ent.id.startsWith('BANK:'))for(const r of lineageMembers(+ent.id.slice(5)))rs.add(r);else if(ent.id.startsWith('PEER:'))for(const r of(peers[ent.id.slice(5)]||[]))rs.add(r);}return rs.size?`id_rssd IN (${[...rs].join(',')})`:null;}
async function openForm(){if(!HIER){showToast('Hierarchy not loaded.');return;}
 const initE=active[0]||resolveEnt();if(!initE){showToast('Add an entity first.');return;}
 if(!window._feEnts||!window._feEnts.length){window._feEnts=active.length?active.filter(e=>e.id.startsWith('BANK:')||e.id.startsWith('PEER:')):[initE];}
 renderFentChips();
 const cond=fentCond()||scopeCond(initE.id);
 const qs=(await conn.query(`SELECT DISTINCT quarter_end FROM t WHERE ${cond} ORDER BY quarter_end`)).toArray().map(r=>String(r.quarter_end));
 window._fq=qs;const opt=qs.map(q=>`<option>${q}</option>`).join('');
 document.getElementById('ffrom').innerHTML=opt;document.getElementById('fto').innerHTML=opt;
 if(qs.length){document.getElementById('fto').value=qs[qs.length-1];document.getElementById('ffrom').value=qs[Math.max(0,qs.length-4)];}
 document.getElementById('formmodal').style.display='flex';renderForm();}
async function renderForm(){const fq=window._fq||[];const cond=fentCond();if(!cond)return;
 let lo=fq.indexOf(document.getElementById('ffrom').value),hi=fq.indexOf(document.getElementById('fto').value);
 if(lo<0)lo=0;if(hi<0)hi=fq.length-1;if(lo>hi){const t=lo;lo=hi;hi=t;}
 let cols=fq.slice(lo,hi+1);if(cols.length>16)cols=cols.slice(cols.length-16);const colsDesc=[...cols].reverse();
 const r=(await conn.query(`SELECT quarter_end,mdrm,SUM(value) v FROM t WHERE ${cond} AND quarter_end IN (${sqlList(cols)}) GROUP BY quarter_end,mdrm`)).toArray();
 const val={};for(const x of r){(val[x.mdrm]=val[x.mdrm]||{})[String(x.quarter_end)]=Number(x.v);}
 const body=document.getElementById('formbody');body.innerHTML='';window._fr=[];window._fcols=colsDesc;
 const hd=document.createElement('div');hd.className='frow';hd.style.cssText=`font-weight:700;position:sticky;top:0;z-index:2;background:${DK()?'#161e2b':'#fff'}`;
 hd.innerHTML=`<span class="lab">Item</span>`+colsDesc.map(q=>`<span class="vcell">${q.slice(0,7)}</span>`).join('');body.appendChild(hd);
 const keys=(()=>{const base=[...FORM_ORDER.filter(k=>HIER[k]),...Object.keys(HIER).filter(k=>!FORM_ORDER.includes(k)&&!k.includes(' — '))];const ks=[];for(const b of base){if(HIER[b])ks.push(b);for(const k of Object.keys(HIER))if(k.startsWith(b+' — ')&&!ks.includes(k))ks.push(k);}for(const k of Object.keys(HIER))if(!ks.includes(k))ks.push(k);return ks;})();
 for(const sch of keys){const items=HIER[sch].filter(rr=>REPORT.test(rr.mdrm)&&val[rr.mdrm]);if(!items.length)continue;
   const flat=items.map(rr=>({code:rr.mdrm,caption:rr.caption||rr.mdrm,num:rr.item||'',depth:rr.depth||1}));
   const {sec,rows}=mkSec(SCHED_NAMES[sch]||sch,items.length);body.appendChild(sec);renderFormNodes(rows,nest(flat),colsDesc,val);
   for(const rr of items)window._fr.push([sch,rr.item||'',rr.mdrm,rr.caption||rr.mdrm,...colsDesc.map(q=>(val[rr.mdrm]&&val[rr.mdrm][q])??'')]);}
 if(!window._fr.length)body.innerHTML='<p class=muted>No data for this entity/range.</p>';}
function renderFormNodes(container,nodes,colsDesc,val){for(const nd of nodes){const has=nd.children.length>0;
 const d=document.createElement('div');d.className='frow';d.dataset.depth=nd.depth;d.style.paddingLeft=(6+(nd.depth-1)*14)+'px';
 const car=has?`<span class="caret">▸</span>`:`<span class="caret" style="visibility:hidden">▸</span>`;
 const cells=colsDesc.map(q=>{const v=val[nd.code]&&val[nd.code][q];return `<span class="vcell">${v==null?'':Number(v).toLocaleString()}</span>`;}).join('');
 d.innerHTML=`<span class="lab">${car}${nd.num?`<b>${nd.num}</b> `:''}${nd.caption} <span style="color:#9aa3b2;font-size:13px">${nd.code}</span></span>${cells}`;
 d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};container.appendChild(d);
 if(has){const kids=document.createElement('div');kids.className='kids';kids.style.display='none';renderFormNodes(kids,nd.children,colsDesc,val);container.appendChild(kids);d._kids=kids;}}}
function exportForm(){if(!window._fr||!window._fr.length){showToast('Nothing to export.');return;}dl2(['schedule','item','mdrm','caption',...(window._fcols||[])],window._fr,'callreport');}

function dl2(c,rows,nm){if(!rows.length){showToast('Nothing to export.');return;}const e=v=>{v=v==null?'':String(v);return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
 const lines=[c.join(',')].concat(rows.map(r=>r.map(e).join(',')));const bl=new Blob([lines.join('\n')],{type:'text/csv'});
 const a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download='fry9c_'+nm+'.csv';a.click();}
// ---- entity report (V2) ----
async function openReport(entityId){
 if(!entityId||!entityId.startsWith('BANK:'))return;
 const rssd=+entityId.slice(5);
 {const p=new URLSearchParams(location.hash.slice(1));p.set('report','1');history.replaceState(null,'','#'+p.toString());}
 document.getElementById('reportmodal').style.display='';
 document.getElementById('rpt-title').innerHTML=`${ROSTER.get(rssd)?.nm||String(rssd)} · RSSD ${rssd} <a href="https://www.ffiec.gov/nicpubweb/nicweb/InstitutionProfile.aspx?parID_RSSD=${rssd}&parDT_END=99991231" target="_blank" rel="noopener" style="font-size:13px;font-weight:400;color:inherit;opacity:0.55;text-decoration:none;margin-left:4px" title="FFIEC NIC institution profile">NIC ↗</a>`;
 {const ac=document.getElementById('rpt-addchart');const ae=bankEnt(rssd);const on=active.some(a=>a.id===ae.id);ac.textContent=on?'✓ In chart':'📈 Add to chart';ac.style.opacity=on?'0.5':'';ac.onclick=()=>{const e=bankEnt(rssd);if(!active.find(a=>a.id===e.id)){active.push({id:e.id,label:e.label});renderChips();scheduleRecompute();}ac.textContent='✓ In chart';ac.style.opacity='0.5';};}
 document.getElementById('rpt-asof').textContent='';
 document.getElementById('rptbody').innerHTML='<p class="muted" style="padding:20px">Loading…</p>';
 try{
  const qtrsRes=(await conn.query(`SELECT DISTINCT quarter_end FROM t WHERE id_rssd=${rssd} ORDER BY quarter_end DESC LIMIT 16`)).toArray();
  if(!qtrsRes.length){document.getElementById('rptbody').innerHTML='<p class="muted" style="padding:20px">No data for this entity.</p>';return;}
  const latestQ=qtrsRes[0].quarter_end;
  document.getElementById('rpt-asof').textContent=' · as of '+latestQ;
  document.getElementById('rptbody').innerHTML=await buildReport(rssd,latestQ,qtrsRes.map(r=>r.quarter_end).reverse());
 }catch(e){document.getElementById('rptbody').innerHTML='<p style="color:#c0392b;padding:20px">Report error: '+e+'</p>';}}
async function buildReport(rssd,latestQ,qtrs){
 const kpiCodes=['BHCK2170','BHCK2122','BHDM6631','BHDM6636','BHFN6631','BHFN6636','BHCK3210','BHCK4340',
  'BHCK4074','BHCK4079','BHCK4093','BHCK4635','BHCK4605',
  'BHCAP793','BHCWP793','BHCA7205','BHCW7205',
  'BHCK1403','BHCK1406','BHCK1407','BHCK3123'];
 const qList=qtrs.map(q=>`'${q}'`).join(',');
 const cList=kpiCodes.map(c=>`'${c}'`).join(',');
 const data=(await conn.query(`SELECT mdrm,quarter_end,value FROM t WHERE id_rssd=${rssd} AND quarter_end IN (${qList}) AND mdrm IN (${cList})`)).toArray();
 const V={};for(const r of data)(V[r.mdrm]=V[r.mdrm]||{})[r.quarter_end]=Number(r.value);
 const get=(c,q)=>V[c]?.[q??latestQ]??null;
 const DEP_CODES_RPT=['BHDM6631','BHDM6636','BHFN6631','BHFN6636'];
 const depSum=(q)=>{const vs=DEP_CODES_RPT.map(c=>get(c,q));return vs.every(v=>v==null)?null:vs.reduce((s,v)=>s+(v||0),0);};
 const qnlFor=q=>({'03':1,'06':2,'09':3,'12':4}[String(q).slice(5,7)]||4);
 const qnl=qnlFor(latestQ);
 const assets=get('BHCK2170'),loans=get('BHCK2122'),dep=depSum(),eq=get('BHCK3210'),ni=get('BHCK4340');
 const nii=get('BHCK4074'),niexp=get('BHCK4093'),niinc=get('BHCK4079');
 const coff=get('BHCK4635'),rec=get('BHCK4605'),alll=get('BHCK3123');
 const npl30=get('BHCK1403'),npl90=get('BHCK1406'),nona=get('BHCK1407');
 const npl=(npl30!=null||npl90!=null||nona!=null)?((npl30||0)+(npl90||0)+(nona||0)):null;
 const noncur=(npl90!=null||nona!=null)?((npl90||0)+(nona||0)):null;
 const cet1=get('BHCAP793')??get('BHCWP793'),tier1=get('BHCA7205')??get('BHCW7205');
 const ann=(n,d)=>n!=null&&d!=null&&d>0?100*n/d*(4/qnl):null;
 const roa=ann(ni,assets),roe=ann(ni,eq),nim=ann(nii,assets);
 const eff=(nii!=null&&niinc!=null&&niexp!=null&&(nii+niinc)>0)?100*niexp/(nii+niinc):null;
 const nplRat=loans&&npl!=null?100*npl/loans:null;
 const nco=(loans&&coff!=null&&rec!=null)?ann(coff-rec,loans):null;
 const rescov=noncur&&alll!=null&&noncur>0?100*alll/noncur:null;
 const alllPct=loans&&alll!=null&&loans>0?100*alll/loans:null;
 let assetRank=null,assetCount=null;
 try{
  const rk=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='BHCK2170' AND quarter_end='${latestQ}' AND value>=${assets??0}`)).toArray();
  const ct=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='BHCK2170' AND quarter_end='${latestQ}'`)).toArray();
  assetRank=Number(rk[0]?.n??0);assetCount=Number(ct[0]?.n??0);
 }catch{}
 // Peer percentile bars — compute entity's rank in universe for each metric
 const peerPctile={};
 try{
  const peerBase=await conn.query(`SELECT mdrm,value FROM t WHERE mdrm IN (${kpiCodes.map(c=>`'${c}'`).join(',')}) AND quarter_end='${latestQ}' AND id_rssd=${rssd}`);
  const entVals=Object.fromEntries(peerBase.toArray().map(r=>[r.mdrm,Number(r.value)]));
  for(const code of kpiCodes){const ev=entVals[code];if(ev==null)continue;
   const res=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='${code}' AND quarter_end='${latestQ}'`)).toArray();
   const tot=Number(res[0]?.n||0);if(!tot)continue;
   const lwr=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='${code}' AND quarter_end='${latestQ}' AND value<=${ev}`)).toArray();
   peerPctile[code]=Math.round(100*Number(lwr[0]?.n||0)/tot);}
 }catch{}
 const prevQ=qtrs.length>=2?qtrs[qtrs.length-2]:null,yoyQ=qtrs.length>=5?qtrs[qtrs.length-5]:null;
 const pctD=(a,b)=>(a!=null&&b!=null&&b!==0)?100*(a-b)/b:null;
 const aQoQ=pctD(assets,prevQ?get('BHCK2170',prevQ):null),aYoY=pctD(assets,yoyQ?get('BHCK2170',yoyQ):null);
 const lPrev=prevQ?get('BHCK2122',prevQ):null;
 const nplPrev=prevQ?((get('BHCK1403',prevQ)||0)+(get('BHCK1406',prevQ)||0)+(get('BHCK1407',prevQ)||0)):null;
 const nplRatPrev=lPrev&&nplPrev!=null&&lPrev>0?100*nplPrev/lPrev:null;
 const nplQoQ=pctD(nplRat,nplRatPrev);
 const fA=v=>v==null?'—':v>=1e9?'$'+(v/1e9).toFixed(1)+'T':v>=1e6?'$'+(v/1e6).toFixed(1)+'B':'$'+Math.round(v/1e3)+'M';
 const fP=v=>v==null?'—':v.toFixed(2)+'%';
 const fD=v=>v==null?'':v>=0?`<span style="color:#1b7f3b;font-size:12px"> ▲${v.toFixed(1)}%</span>`:`<span style="color:#c0392b;font-size:12px"> ▼${Math.abs(v).toFixed(1)}%</span>`;
 const pct=assetRank&&assetCount?Math.round((1-assetRank/assetCount)*100):null;
 const rnk=assetRank?`Rank #${assetRank} of ${assetCount}${pct!=null?' ('+pct+'th %ile)':''}`:null;
 const nm=ROSTER.get(rssd)?.nm||String(rssd);
 const hdr=`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:14px 18px;margin-bottom:14px;background:var(--head,#f7f8fc);color:var(--fg,#111)"><div style="font-size:20px;font-weight:700;color:var(--fg,#111)">${nm}</div><div class="muted" style="font-size:13px;margin-top:3px">RSSD ${rssd} · Bank Holding Company · FR Y-9C</div><div style="font-size:14px;margin-top:7px;color:var(--fg,#111)">As of ${latestQ}${assets!=null?' &nbsp;·&nbsp; Total assets: '+fA(assets):''}${rnk?' &nbsp;·&nbsp; '+rnk:''}</div></div>`;
 // per-quarter helpers for sparklines and trend charts
 const qnlQ=q=>({'03':1,'06':2,'09':3,'12':4}[String(q).slice(5,7)]||4);
 const annQ=(n,d,q)=>{const nv=get(n,q),dv=get(d,q);return nv!=null&&dv!=null&&dv>0?100*nv/dv*(4/qnlQ(q)):null;};
 const ncoQ=q=>{const c=get('BHCK4635',q),r=get('BHCK4605',q),l=get('BHCK2122',q);return c!=null&&r!=null&&l!=null&&l>0?100*(c-r)/l*(4/qnlQ(q)):null;};
 const effQ=q=>{const n=get('BHCK4074',q),nc=get('BHCK4079',q),x=get('BHCK4093',q);return n!=null&&nc!=null&&x!=null&&(n+nc)>0?100*x/(n+nc):null;};
 const nplQ=q=>{const l=get('BHCK2122',q);const np=(get('BHCK1403',q)||0)+(get('BHCK1406',q)||0)+(get('BHCK1407',q)||0);return l&&l>0?100*np/l:null;};
 const pctileBar=(p)=>{if(p==null)return '';const c=p>=75?'#1b7f3b':p>=50?'#2980b9':p>=25?'#e67e22':'#c0392b';return `<div style="margin-top:4px"><div style="height:5px;background:var(--border,#e0e4ea);border-radius:3px;overflow:hidden"><div style="height:100%;width:${p}%;background:${c};border-radius:3px"></div></div><div style="font-size:11px;color:var(--fg2,#888);margin-top:1px">${p}th %ile among reporters</div></div>`;};
 const kpis=[
  {lbl:'Total Assets',val:fA(assets),spk:sparkline(qtrs.map(q=>[q,get('BHCK2170',q)]),false,COLORS[0]),qoq:aQoQ,yoy:aYoY,pc:peerPctile['BHCK2170']},
  {lbl:'Total Loans',val:fA(loans),spk:sparkline(qtrs.map(q=>[q,get('BHCK2122',q)]),false,COLORS[1]),qoq:null,yoy:null,pc:peerPctile['BHCK2122']},
  {lbl:'Total Deposits',val:fA(dep),spk:sparkline(qtrs.map(q=>[q,depSum(q)]),false,COLORS[2]),qoq:null,yoy:null,pc:null},
  {lbl:'Total Equity',val:fA(eq),spk:sparkline(qtrs.map(q=>[q,get('BHCK3210',q)]),false,COLORS[3]),qoq:null,yoy:null,pc:peerPctile['BHCK3210']},
  {lbl:'ROA (ann.)',val:fP(roa),spk:sparkline(qtrs.map(q=>[q,annQ('BHCK4340','BHCK2170',q)]),true,COLORS[0]),qoq:null,yoy:null,pc:peerPctile['BHCK4340']},
  {lbl:'ROE (ann.)',val:fP(roe),spk:sparkline(qtrs.map(q=>[q,annQ('BHCK4340','BHCK3210',q)]),true,COLORS[1]),qoq:null,yoy:null,pc:null},
  {lbl:'NIM % (approx.)',val:fP(nim),spk:sparkline(qtrs.map(q=>[q,annQ('BHCK4074','BHCK2170',q)]),true,COLORS[2]),qoq:null,yoy:null,pc:peerPctile['BHCK4074']},
  {lbl:'Efficiency Ratio',val:fP(eff),spk:sparkline(qtrs.map(q=>[q,effQ(q)]),true,COLORS[3]),qoq:null,yoy:null,pc:null},
  {lbl:'CET1 Ratio',val:fP(cet1),spk:sparkline(qtrs.map(q=>[q,get('BHCAP793',q)??get('BHCWP793',q)]),true,COLORS[4]),qoq:null,yoy:null,pc:peerPctile['BHCAP793']??peerPctile['BHCWP793']},
  {lbl:'Tier 1 RBC',val:fP(tier1),spk:sparkline(qtrs.map(q=>[q,get('BHCA7205',q)??get('BHCW7205',q)]),true,COLORS[5]),qoq:null,yoy:null,pc:peerPctile['BHCA7205']??peerPctile['BHCW7205']},
  {lbl:'NPL Ratio',val:fP(nplRat),spk:sparkline(qtrs.map(q=>[q,nplQ(q)]),true,COLORS[6]),qoq:nplQoQ,yoy:null,pc:peerPctile['BHCK1403']},
  {lbl:'NCO Rate (ann.)',val:fP(nco),spk:sparkline(qtrs.map(q=>[q,ncoQ(q)]),true,COLORS[7]),qoq:null,yoy:null,pc:peerPctile['BHCK4635']},
 ];
 const cards=kpis.map(k=>`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;min-width:148px;display:inline-block;vertical-align:top;margin:4px"><div style="font-size:12px;color:var(--fg2,#666);font-weight:600;letter-spacing:.3px;text-transform:uppercase">${k.lbl}</div><div style="font-size:26px;font-weight:700;line-height:1.1;margin-top:4px">${k.val}</div><div style="min-height:14px;margin-top:2px">${fD(k.qoq)}${k.yoy!=null?' &nbsp;YoY:'+fD(k.yoy):''}</div>${k.spk||''}${pctileBar(k.pc)}</div>`).join('');
 const kpiSec=`<h3 style="font-size:14px;font-weight:600;margin:0 0 6px">Key Metrics — as of ${latestQ}</h3><div style="margin-bottom:14px">${cards}</div>`;
 // reserve coverage panel
 const resSec=alll!=null?`<div style="display:inline-block;vertical-align:top;border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;min-width:240px;margin-bottom:14px"><div style="font-size:13px;font-weight:600;margin-bottom:6px">Allowance / Reserve Coverage</div><table style="font-size:13px;border-collapse:collapse;width:100%"><tr><td style="padding:3px 0">ALLL / Total Loans</td><td style="text-align:right;font-weight:700">${fP(alllPct)}</td></tr><tr><td style="padding:3px 0">ALLL / Noncurrent Loans</td><td style="text-align:right;font-weight:700">${fP(rescov)}</td></tr><tr><td style="padding:3px 0">Noncurrent Loans</td><td style="text-align:right;font-weight:700">${noncur!=null?fA(noncur):'—'}</td></tr></table></div>`:'';
 // trend small-multiples — 2×3 grid using full pane() at reduced container width
 const mkS=(rows,color,lbl)=>({rows:rows.filter(r=>r[1]!=null),color,label:lbl,pct:false});
 const trends=[
  {t:'Total Assets',s:[mkS(qtrs.map(q=>[q,get('BHCK2170',q)]),COLORS[0],'Assets')],u:'$ thousands'},
  {t:'Loans & Deposits',s:[mkS(qtrs.map(q=>[q,get('BHCK2122',q)]),COLORS[1],'Loans'),mkS(qtrs.map(q=>[q,depSum(q)]),COLORS[2],'Deposits')],u:'$ thousands'},
  {t:'ROA & ROE (ann. %)',s:[mkS(qtrs.map(q=>[q,annQ('BHCK4340','BHCK2170',q)]),COLORS[0],'ROA'),mkS(qtrs.map(q=>[q,annQ('BHCK4340','BHCK3210',q)]),COLORS[1],'ROE')],u:'percent'},
  {t:'NIM & Efficiency (%)',s:[mkS(qtrs.map(q=>[q,annQ('BHCK4074','BHCK2170',q)]),COLORS[2],'NIM'),mkS(qtrs.map(q=>[q,effQ(q)]),COLORS[3],'Efficiency')],u:'percent'},
  {t:'Capital Ratios (%)',s:[mkS(qtrs.map(q=>[q,get('BHCAP793',q)??get('BHCWP793',q)]),COLORS[4],'CET1'),mkS(qtrs.map(q=>[q,get('BHCA7205',q)??get('BHCW7205',q)]),COLORS[5],'Tier 1')],u:'percent'},
  {t:'Credit Quality (%)',s:[mkS(qtrs.map(q=>[q,nplQ(q)]),COLORS[6],'NPL %'),mkS(qtrs.map(q=>[q,ncoQ(q)]),COLORS[7],'NCO %')],u:'percent'},
 ];
 const trendCells=trends.map(t=>{if(!t.s.some(s=>s.rows.length>0))return '';const svg=pane(t.s,false,t.u,qtrs);return svg?`<div style="min-width:0"><div style="font-size:13px;font-weight:600;color:var(--fg2,#666);margin-bottom:3px">${t.t}</div>${svg}</div>`:''}).filter(Boolean);
 const trendSec=trendCells.length?`<h3 style="font-size:14px;font-weight:600;margin:14px 0 6px">Trends — last ${qtrs.length} quarters</h3><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">${trendCells.join('')}</div>`:'';
 const nar=buildNarrative({nm,latestQ,assets,assetRank,assetCount,aQoQ,aYoY,roa,roe,cet1,eff,nplRat,nplQoQ,rescov,nco});
 return hdr+kpiSec+resSec+trendSec+`<h3 style="font-size:14px;font-weight:600;margin:14px 0 6px">Summary</h3>`+nar;}
function sparkline(rows,pct,color){
 const W=120,H=40;if(!rows||rows.every(r=>r[1]==null))return '';
 const vals=rows.map(r=>r[1]).filter(v=>v!=null);if(!vals.length)return '';
 let mn=Math.min(...vals),mx=Math.max(...vals);if(mn===mx){mn-=1;mx+=1;}
 if(!pct&&mn>0)mn=0;const rg=mx-mn,n=rows.length;
 const X=i=>4+i*(W-8)/Math.max(1,n-1),Y=v=>H-4-(v-mn)/rg*(H-8);
 const filtered=rows.filter(r=>r[1]!=null);
 const pts=filtered.map((r,i)=>`${X(rows.indexOf(r)).toFixed(1)},${Y(r[1]).toFixed(1)}`).join(' ');
 if(!pts)return '';
 const lp=filtered[filtered.length-1],li=rows.indexOf(lp);
 const fill=`4,${H-4} ${pts} ${X(li).toFixed(1)},${H-4}`;
 return `<svg width="120" height="40" style="display:block;margin-top:4px"><polygon points="${fill}" fill="${color||COLORS[0]}" fill-opacity=".12"/><polyline points="${pts}" fill="none" stroke="${color||COLORS[0]}" stroke-width="1.5"/></svg>`;}
function buildNarrative(d){
 const {nm,latestQ,assets,assetRank,assetCount,aQoQ,aYoY,roa,roe,cet1,eff,nplRat,nplQoQ,rescov,nco}=d;
 const fA=v=>v==null?null:v>=1e9?'$'+(v/1e9).toFixed(1)+'T':v>=1e6?'$'+(v/1e6).toFixed(1)+'B':'$'+Math.round(v/1e3)+'M';
 const fP=v=>v==null?null:v.toFixed(2)+'%';
 const pct=assetRank&&assetCount?Math.round((1-assetRank/assetCount)*100):null;
 const grTxt=aYoY!=null?(aYoY>5?` Assets grew ${aYoY.toFixed(1)}% year-over-year.`:aYoY<-5?` Assets contracted ${Math.abs(aYoY).toFixed(1)}% year-over-year.`:' Asset levels were stable year-over-year.'):'';
 const p1=`${nm} is a bank holding company with ${fA(assets)||'undisclosed assets'} as of ${latestQ}${assetRank?`, ranking #${assetRank} of ${assetCount} FR Y-9C reporters${pct!=null?' ('+pct+'th percentile)':''}`:''}.${grTxt}`;
 const roaD=roa==null?null:roa<0?'reporting a net loss':roa<0.5?'modestly profitable':roa<1.0?'adequately profitable':roa<1.5?'solidly profitable':'strongly profitable';
 const cetD=cet1==null?null:cet1<8?'approaching minimum capital thresholds':cet1<10?'meeting minimum requirements':cet1<12?'well-capitalized':'strongly capitalized';
 const effD=eff==null?null:eff<55?'highly efficient':eff<65?'within the industry norm':eff<75?'moderately inefficient':'carrying an above-average cost structure';
 const p2p=[];
 if(roaD&&roa!=null&&roe!=null)p2p.push(`For the period ending ${latestQ}, ${nm} was ${roaD} with an annualized ROA of ${fP(roa)} and ROE of ${fP(roe)}.`);
 if(cetD)p2p.push(`The CET1 ratio stood at ${fP(cet1)}, indicating the institution is ${cetD}.`);
 if(effD&&eff!=null)p2p.push(`The efficiency ratio of ${fP(eff)} suggests the institution is ${effD}.`);
 const p2=p2p.join(' ')||null;
 const nplD=nplRat==null?null:nplRat<1?'clean credit quality':nplRat<2?'manageable credit stress':nplRat<3?'elevated NPL levels':'significant credit deterioration';
 const ncoD=nco==null?null:nco<0.25?'minimal charge-off activity':nco<0.5?'modest charge-offs':nco<1.0?'moderate charge-offs':'elevated charge-off rates';
 const resD=rescov==null?null:rescov<50?'thin reserve coverage':rescov<100?'adequate reserve coverage':'strong reserve coverage';
 const nplTr=nplQoQ!=null?(nplQoQ>10?' and trending higher.':nplQoQ<-10?' and improving.':'.'):'.'
 const p3p=[];
 if(nplD&&nplRat!=null)p3p.push(`${nm} reported a total NPL ratio of ${fP(nplRat)}, indicating ${nplD}${nplTr}`);
 if(resD&&rescov!=null)p3p.push(`The allowance for loan losses covered ${fP(rescov)} of noncurrent loans, reflecting ${resD}.`);
 if(ncoD&&nco!=null)p3p.push(`Net charge-offs ran at an annualized rate of ${fP(nco)}, indicating ${ncoD}.`);
 const p3=p3p.join(' ')||null;
 return [p1,p2,p3].filter(Boolean).map(p=>`<p style="line-height:1.6;margin:6px 0">${p}</p>`).join('');}
function rptPrint(){
 const content=document.getElementById('rptbody').innerHTML;
 const title=document.getElementById('rpt-title').textContent;
 const w=window.open('','_blank','width=900,height=700');if(!w)return;
 w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>'+title+' Tear Sheet<\/title><style>*{box-sizing:border-box}:root{--border:#ccc;--head:#f7f8fc;--fg2:#555}.muted{color:#555}body{font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;color:#1a202c;margin:24px 32px}svg{display:block}h3{font-size:14px;margin:12px 0 4px}p{margin:6px 0}@media print{body{margin:0}}<\/style><\/head><body>'+content+'<p style="margin-top:32px;font-size:12px;color:#888">Data: public FFIEC\/FRB filings · Generated '+new Date().toISOString().slice(0,10)+'<\/p><script>window.onload=()=>window.print();<\/script><\/body><\/html>');
 w.document.close();}
// ---- export builder (V2) ----
const _eb={entities:[],scope:'all',scheds:new Set(),codes:new Set(),fromQ:null,toQ:null,fmt:'long'};
function ebScheduleCodes(){
 if(!HIER)return [];
 const out=new Set();
 for(const sch of _eb.scheds)for(const r of (HIER[sch]||[]))if(REPORT.test(r.mdrm))out.add(r.mdrm);
 return [...out];}
function ebRawCodes(){
 const out=new Set();
 for(const c of _eb.codes){const d=DERIV[c];
   if(d){for(const t of [...(d.plus||[]),...(d.minus||[]),...(d.den||[])])for(const fc of term2codes(t))out.add(fc);}
   else out.add(c);}
 return [...out];}
function ebEntityCond(){
 if(!_eb.entities.length)return null;
 if(_eb.entities.some(e=>e.id==='ALL'))return allCond();
 const rssds=new Set();
 for(const ent of _eb.entities){
   if(ent.id.startsWith('BANK:'))for(const r of lineageMembers(+ent.id.slice(5)))rssds.add(r);
   else if(ent.id.startsWith('PEER:')){for(const r of peers[ent.id.slice(5)]||[])rssds.add(r);}
 }
 return rssds.size?`id_rssd IN (${[...rssds].join(',')})`:null;}
function pivotWide(rows){
 const captionMap={};
 if(HIER)for(const sch of Object.keys(HIER))for(const r of HIER[sch])if(r.mdrm&&r.caption)captionMap[r.mdrm]=r.caption;
 const qtrs=[...new Set(rows.map(r=>String(r.quarter_end)))].sort().reverse();
 const ents=[...new Set(rows.map(r=>r.id_rssd))];
 const byE={};for(const r of rows){const k=r.id_rssd;if(!byE[k])byE[k]={nm:r.institution_name,m:{}};(byE[k].m[r.mdrm]=byE[k].m[r.mdrm]||{})[String(r.quarter_end)]=r.value;}
 const body=[];for(const eid of ents){if(!byE[eid])continue;for(const m of Object.keys(byE[eid].m).sort())body.push([eid,byE[eid].nm||'',m,fullCap(m)||captionMap[m]||'',...qtrs.map(q=>byE[eid].m[m][q]??'')]);}
 return {headers:['id_rssd','institution_name','mdrm','caption',...qtrs],body};}
async function ebEstimate(){
 let nC=0;
 if(_eb.scope==='schedules')nC=ebScheduleCodes().length;
 else if(_eb.scope==='codes')nC=ebRawCodes().length;
 else try{const r=(await conn.query('SELECT COUNT(DISTINCT mdrm) n FROM t')).toArray();nC=Number(r[0]?.n||0);}catch{nC=0;}
 let nQ=0;
 if(_eb.fromQ&&_eb.toQ)try{const r=(await conn.query(`SELECT COUNT(DISTINCT quarter_end) n FROM t WHERE quarter_end>='${_eb.fromQ}' AND quarter_end<='${_eb.toQ}'`)).toArray();nQ=Number(r[0]?.n||0);}catch{}
 let nE=_eb.entities.length||0;
 if(_eb.entities.some(e=>e.id==='ALL'))try{const r=(await conn.query('SELECT COUNT(DISTINCT id_rssd) n FROM t')).toArray();nE=Number(r[0]?.n||0);}catch{}
 else if(nE>0){const rs=new Set();for(const ent of _eb.entities){if(ent.id.startsWith('BANK:'))rs.add(+ent.id.slice(5));else if(ent.id.startsWith('PEER:')){for(const r of peers[ent.id.slice(5)]||[])rs.add(r);}}if(rs.size)nE=rs.size;}
 const nR=nC*nQ*nE;const warn=nR>500000,block=nR>10000000;
 const el=document.getElementById('eb-estimate');
 if(el){el.innerHTML=`Estimated rows: <b>~${nR.toLocaleString()}</b> (${nC.toLocaleString()} codes × ${nQ} qtrs × ${nE} entities)`+(warn&&!block?' <span style="color:#e07a1f">⚠ large export</span>':'')+(block?' <span style="color:#c0392b">⛔ too large — narrow scope or date range first</span>':'');
   const btn=document.getElementById('expbld-run');if(btn)btn.disabled=block;}
 return nR;}
function openExportBuilder(){document.getElementById('exportmodal').style.display='flex';renderExportUI();}
async function renderExportUI(){
 const body=document.getElementById('expbldbody');
 const hierKeys=HIER?[...FORM_ORDER.filter(k=>HIER[k]),...Object.keys(HIER).filter(k=>SCHED_NAMES[k]&&!FORM_ORDER.includes(k))]:[];
 const schedHtml=hierKeys.map(sch=>{const cnt=(HIER[sch]||[]).filter(r=>REPORT.test(r.mdrm)).length;const chk=_eb.scheds.has(sch)?'checked':'';return `<label style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border:1px solid var(--border,#ccc);border-radius:4px;font-size:13px;cursor:pointer"><input type="checkbox" class="eb-sch" value="${sch}" ${chk}>${SCHED_NAMES[sch]||sch} <span class="muted" style="font-size:12px">(${cnt})</span></label>`;}).join(' ');
 const selCodes=[..._eb.codes].map(c=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:13px;margin:2px">${c}<span class="eb-del" data-c="${c}" style="cursor:pointer;color:#c0392b;margin-left:2px">×</span></span>`).join('');
 body.innerHTML=`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Entities</b> <span class="muted" style="font-size:13px">Add one or more banks, ALL filers, or peer groups</span>
  <div id="eb-ent-chips" style="display:flex;flex-wrap:wrap;gap:3px;min-height:26px;padding:4px;border:1px solid var(--border,#ccc);border-radius:3px;margin:6px 0 6px"></div>
  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
   <input id="eb-ent" list="entlist" autocomplete="off" placeholder="bank name, RSSD, or ★ peer-group…" style="flex:1;min-width:200px;font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:3px 6px;background:inherit;color:inherit">
   <button id="eb-ent-add" class="sec">Add</button>
   <button id="eb-ent-cur" class="sec" title="Add entities currently in the chart">+ From chart</button>
   <button id="eb-ent-all" class="sec" title="Export all filing institutions">All filers</button>
   <span id="eb-ent-status" style="font-size:13px"></span>
  </div></div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Scope</b>
  <div style="margin-top:6px;display:flex;gap:16px;flex-wrap:wrap">
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="all" ${_eb.scope==='all'?'checked':''}><span><b>All codes</b><br><span class="muted" style="font-size:13px">Every MDRM in site parquet</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="schedules" ${_eb.scope==='schedules'?'checked':''}><span><b>Selected schedules</b><br><span class="muted" style="font-size:13px">Choose by form schedule</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="codes" ${_eb.scope==='codes'?'checked':''}><span><b>Selected codes</b><br><span class="muted" style="font-size:13px">Custom MDRM / DERIV list</span></span></label>
  </div>
  <div id="eb-sched-panel" style="display:${_eb.scope==='schedules'?'block':'none'};margin-top:8px">
   <div style="display:flex;flex-wrap:wrap;gap:4px">${schedHtml}</div>
   <div style="margin-top:6px;display:flex;align-items:center;gap:8px"><button id="eb-sall" class="sec" style="font-size:13px;padding:2px 7px">All</button><button id="eb-snone" class="sec" style="font-size:13px;padding:2px 7px">None</button><span class="muted" style="font-size:13px" id="eb-sched-cnt">${_eb.scheds.size} schedule${_eb.scheds.size!==1?'s':''} / ${ebScheduleCodes().length} codes</span></div>
  </div>
  <div id="eb-code-panel" style="display:${_eb.scope==='codes'?'block':'none'};margin-top:8px">
   <div style="display:flex;gap:6px;align-items:center"><input id="eb-csearch" autocomplete="off" placeholder="Search MDRM or description…" style="flex:1;min-width:200px;font:inherit;font-size:13px;border:1px solid var(--border,#ccc);border-radius:3px;padding:3px 6px;background:inherit;color:inherit"><button id="eb-cadd" class="sec" style="font-size:13px;padding:2px 7px">Add</button><button id="eb-caddfil" class="sec" style="font-size:13px;padding:2px 7px">Add all matching</button></div>
   <div id="eb-cres" style="max-height:90px;overflow-y:auto;border:1px solid var(--border,#ccc);border-radius:3px;margin-top:4px;font-size:13px"></div>
   <div id="eb-selcodes" style="margin-top:6px;display:flex;flex-wrap:wrap">${selCodes}</div>
   <div style="margin-top:4px;display:flex;align-items:center;gap:8px"><span class="muted" style="font-size:13px" id="eb-code-cnt">${_eb.codes.size} code${_eb.codes.size!==1?'s':''} selected</span><button id="eb-clrall" class="sec" style="font-size:13px;padding:1px 7px">Clear all</button></div>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Date range</b>
  <div style="display:flex;align-items:center;gap:8px;margin-top:6px;flex-wrap:wrap">
   <span class="muted">From</span><select id="eb-from" style="font:inherit;font-size:13px"></select>
   <span class="muted">to</span><select id="eb-to" style="font:inherit;font-size:13px"></select>
   <button id="eb-full" class="sec">Full range</button>
   <span class="muted" style="font-size:13px" id="eb-qcount">—</span>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Format</b>
  <div style="margin-top:6px;display:flex;gap:16px;flex-wrap:wrap">
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-fmt" value="long" ${_eb.fmt==='long'?'checked':''}><span><b>Long</b><br><span class="muted" style="font-size:13px">One row per entity-quarter-code</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-fmt" value="wide" ${_eb.fmt==='wide'?'checked':''}><span><b>Wide</b><br><span class="muted" style="font-size:13px">Codes as rows, quarters as columns (one column per quarter)</span></span></label>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:8px 14px;font-size:13px" id="eb-estimate"><span class="muted">Set entity and scope to estimate row count.</span></div>`;
 function updSchedCnt(){const n=_eb.scheds.size,c=ebScheduleCodes().length;const el=document.getElementById('eb-sched-cnt');if(el)el.textContent=n+' schedule'+(n!==1?'s':'')+' / '+c+' codes';ebEstimate();}
 function updCodeCnt(){const n=_eb.codes.size;const el=document.getElementById('eb-code-cnt');if(el)el.textContent=n+' code'+(n!==1?'s':'')+' selected';ebEstimate();}
 function renderCodeTags(){document.getElementById('eb-selcodes').innerHTML=[..._eb.codes].map(c=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:13px;margin:2px">${c}<span class="eb-del" data-c="${c}" style="cursor:pointer;color:#c0392b;margin-left:2px">×</span></span>`).join('');for(const d of document.querySelectorAll('.eb-del'))d.onclick=()=>{_eb.codes.delete(d.dataset.c);renderCodeTags();updCodeCnt();};}
 function buildCandidates(q){const q2=q.toLowerCase();const seen=new Set();const res=[];
  if(HIER)for(const sch of Object.keys(HIER))for(const r of (HIER[sch]||[])){if(!r.mdrm||seen.has(r.mdrm))continue;seen.add(r.mdrm);if((r.mdrm||'').toLowerCase().includes(q2)||(r.caption||'').toLowerCase().includes(q2))res.push({m:r.mdrm,c:r.caption||''});}
  for(const k of Object.keys(DERIV)){if(seen.has(k))continue;seen.add(k);const d=DERIV[k];if((k||'').toLowerCase().includes(q2)||(d.lbl||'').toLowerCase().includes(q2))res.push({m:k,c:d.lbl||''});}
  return res.slice(0,40);}
 function renderEbChips(){const c=document.getElementById('eb-ent-chips');if(!c)return;c.innerHTML=_eb.entities.map((ent,i)=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 6px;background:var(--head,#eef2f7);border-radius:3px;font-size:13px">${ent.id==='ALL'?'All filers':ent.label}<span class="eb-edel" data-i="${i}" style="cursor:pointer;color:#c0392b;margin-left:3px">×</span></span>`).join('');for(const d of document.querySelectorAll('.eb-edel'))d.onclick=()=>{_eb.entities.splice(+d.dataset.i,1);renderEbChips();ebEstimate();};}
 function addEbEnt(v){v=v.trim();if(!v)return;const cv=v.replace(/^★\s*/,'');
  if(/^all$/i.test(v)){_eb.entities=[{id:'ALL',label:'All filers'}];renderEbChips();ebEstimate();return;}
  if(cv in peers){const id='PEER:'+cv;if(!_eb.entities.find(e=>e.id===id))_eb.entities.push({id,label:'★ '+cv});renderEbChips();ebEstimate();return;}
  const m=v.match(/(\d{3,})/);if(m){const be=bankEnt(+m[1]);if(be){if(!_eb.entities.find(e=>e.id===be.id))_eb.entities.push({id:be.id,label:be.label});renderEbChips();ebEstimate();return;}}
  document.getElementById('eb-ent-status').innerHTML='<span style="color:#c0392b">Not recognised</span>';return;}
 document.getElementById('eb-ent-add').onclick=()=>{addEbEnt(document.getElementById('eb-ent').value);document.getElementById('eb-ent').value='';};
 document.getElementById('eb-ent').onkeydown=e=>{if(e.key==='Enter'){addEbEnt(e.target.value);e.target.value='';}};
 document.getElementById('eb-ent-cur').onclick=()=>{for(const e of active){if(!_eb.entities.find(x=>x.id===e.id))_eb.entities.push({id:e.id,label:e.label});}renderEbChips();ebEstimate();};
 document.getElementById('eb-ent-all').onclick=()=>{_eb.entities=[{id:'ALL',label:'All filers'}];renderEbChips();ebEstimate();};
 for(const el of document.querySelectorAll('[name=eb-scope]'))el.addEventListener('change',e=>{_eb.scope=e.target.value;document.getElementById('eb-sched-panel').style.display=_eb.scope==='schedules'?'block':'none';document.getElementById('eb-code-panel').style.display=_eb.scope==='codes'?'block':'none';ebEstimate();});
 for(const el of document.querySelectorAll('.eb-sch'))el.addEventListener('change',e=>{if(e.target.checked)_eb.scheds.add(e.target.value);else _eb.scheds.delete(e.target.value);updSchedCnt();});
 document.getElementById('eb-sall').onclick=()=>{for(const el of document.querySelectorAll('.eb-sch')){el.checked=true;_eb.scheds.add(el.value);}updSchedCnt();};
 document.getElementById('eb-snone').onclick=()=>{for(const el of document.querySelectorAll('.eb-sch')){el.checked=false;_eb.scheds.delete(el.value);}updSchedCnt();};
 document.getElementById('eb-csearch').oninput=function(){const q=this.value.trim();const el=document.getElementById('eb-cres');if(!q){el.innerHTML='';return;}const res=buildCandidates(q);el.innerHTML=res.length?res.map(r=>`<div class="eb-cand" data-m="${r.m}" style="padding:2px 6px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.m}: ${r.c}"><b>${r.m}</b> ${r.c}</div>`).join(''):'<div class="muted" style="padding:4px 6px">No matches</div>';for(const d of el.querySelectorAll('.eb-cand'))d.onclick=()=>{_eb.codes.add(d.dataset.m);renderCodeTags();updCodeCnt();};};
 document.getElementById('eb-cadd').onclick=()=>{const v=document.getElementById('eb-csearch').value.trim().toUpperCase();if(!v)return;_eb.codes.add(v);renderCodeTags();updCodeCnt();};
 document.getElementById('eb-caddfil').onclick=()=>{const q=document.getElementById('eb-csearch').value.trim();if(!q)return;buildCandidates(q).forEach(r=>_eb.codes.add(r.m));renderCodeTags();updCodeCnt();};
 document.getElementById('eb-clrall').onclick=()=>{_eb.codes.clear();renderCodeTags();updCodeCnt();};
 for(const d of document.querySelectorAll('.eb-del'))d.onclick=()=>{_eb.codes.delete(d.dataset.c);renderCodeTags();updCodeCnt();};
 for(const el of document.querySelectorAll('[name=eb-fmt]'))el.addEventListener('change',e=>{_eb.fmt=e.target.value;});
 renderEbChips();
 // Async: load available date range (entity section already visible above)
 let allQtrs=[];
 try{
  const ec0=_eb.entities.length?ebEntityCond():null;
  const cond=ec0?`WHERE ${ec0}`:'';
  const res=(await conn.query(`SELECT DISTINCT quarter_end FROM t ${cond} ORDER BY quarter_end`)).toArray();
  allQtrs=res.map(r=>String(r.quarter_end));
 }catch{}
 if(allQtrs.length&&!_eb.fromQ)_eb.fromQ=allQtrs[0];
 if(allQtrs.length&&!_eb.toQ)_eb.toQ=allQtrs[allQtrs.length-1];
 const selF=allQtrs.map(q=>`<option value="${q}"${q===_eb.fromQ?' selected':''}>${q}</option>`).join('');
 const selT=allQtrs.map(q=>`<option value="${q}"${q===_eb.toQ?' selected':''}>${q}</option>`).join('');
 const fromEl=document.getElementById('eb-from');if(fromEl)fromEl.innerHTML=selF;
 const toEl=document.getElementById('eb-to');if(toEl)toEl.innerHTML=selT;
 const inRange=allQtrs.filter(q=>(!_eb.fromQ||q>=_eb.fromQ)&&(!_eb.toQ||q<=_eb.toQ));
 const qcEl=document.getElementById('eb-qcount');if(qcEl)qcEl.textContent=inRange.length+' quarter'+(inRange.length!==1?'s':'');
 document.getElementById('eb-from').onchange=()=>{_eb.fromQ=document.getElementById('eb-from').value;const n=allQtrs.filter(q=>q>=_eb.fromQ&&q<=_eb.toQ).length;document.getElementById('eb-qcount').textContent=n+' quarter'+(n!==1?'s':'');ebEstimate();};
 document.getElementById('eb-to').onchange=()=>{_eb.toQ=document.getElementById('eb-to').value;const n=allQtrs.filter(q=>q>=_eb.fromQ&&q<=_eb.toQ).length;document.getElementById('eb-qcount').textContent=n+' quarter'+(n!==1?'s':'');ebEstimate();};
 document.getElementById('eb-full').onclick=()=>{if(allQtrs.length){_eb.fromQ=allQtrs[0];_eb.toQ=allQtrs[allQtrs.length-1];}renderExportUI();};
 ebEstimate();}
async function runExport(preview=false){
 if(!_eb.entities.length){showToast('Add at least one entity first.');return null;}
 const ec=ebEntityCond();if(!ec){showToast('Could not resolve entities.');return null;}
 const df=_eb.fromQ?`AND quarter_end>='${_eb.fromQ}'`:'',dt=_eb.toQ?`AND quarter_end<='${_eb.toQ}'`:'';
 let mdrmF='';
 if(_eb.scope==='schedules'){const cs=ebScheduleCodes();if(!cs.length){showToast('No codes selected for the chosen schedules.');return null;}mdrmF=`AND mdrm IN (${cs.map(m=>`'${m}'`).join(',')}) `;}
 else if(_eb.scope==='codes'){const cs=ebRawCodes();if(!cs.length){showToast('No codes in selection.');return null;}mdrmF=`AND mdrm IN (${cs.map(m=>`'${m}'`).join(',')}) `;}
 const sql=`SELECT quarter_end,id_rssd,institution_name,mdrm,value FROM t WHERE ${ec} ${df} ${dt} ${mdrmF}ORDER BY mdrm,id_rssd,quarter_end${preview?' LIMIT 50':''}`;
 const rows=(await conn.query(sql)).toArray();
 if(_eb.fmt==='wide'&&!preview)return pivotWide(rows);
 return {headers:['quarter_end','id_rssd','institution_name','mdrm','caption','value'],body:rows.map(r=>[r.quarter_end,r.id_rssd,r.institution_name,r.mdrm,fullCap(r.mdrm)||'',r.value]),sql};}
async function runsql(){try{const r=(await conn.query(document.getElementById('sql').value)).toArray();
 sqlC=r.length?Object.keys(r[0]):[];sqlR=r.map(x=>sqlC.map(c=>x[c]));
 let h='<table><tr>'+sqlC.map(c=>`<th>${c}</th>`).join('')+'</tr>';for(const x of r.slice(0,500))h+='<tr>'+sqlC.map(c=>`<td>${x[c]}</td>`).join('')+'</tr>';
 document.getElementById('sqlout').innerHTML=h+`</table><p class=muted>${r.length} rows (first 500)</p>`;}catch(e){document.getElementById('sqlout').textContent='SQL error: '+e;}}
(function(){
  const tip=document.createElement('div');tip.id='charttip';document.body.appendChild(tip);
  // ResizeObserver persists chosen size across pins
  const _ro=new ResizeObserver(()=>{if(window._pinnedQ){window._tipW=tip.offsetWidth+'px';window._tipH=tip.offsetHeight+'px';}});
  _ro.observe(tip);
  let _hovQ=null,_hovTx=null,_hovTy=null;window._pinnedQ=null;
  function showTip(e,svg){
    if(!lastSeries.length){if(!window._pinnedQ)tip.style.display='none';return;}
    const win=Qall.slice(rangeSel.a,rangeSel.b+1);
    if(!win.length){if(!window._pinnedQ)tip.style.display='none';return;}
    if(window._pinnedQ)return;
    const br=svg.getBoundingClientRect();
    // Map cursor->quarter using the PLOT coord width (1080), not the viewBox width (which now
    // includes the +96 right label gutter). padR matches paneDual's extra right pad on dual-axis.
    // Map cursor→quarter from the SVG's TRUE plot geometry (data-pl/data-pw stamped by pane/paneDual),
    // not the viewBox width — exact for single & dual axis and immune to the dynamic right-label margin.
    const vb=svg.viewBox.baseVal;const svgW=br.width;const sc=svgW/vb.width;
    const pl=+svg.dataset.pl||64,pw=+svg.dataset.pw||(vb.width-128);
    const mx=e.clientX-br.left;
    const frac=(mx-pl*sc)/(pw*sc);
    const qi=Math.max(0,Math.min(win.length-1,Math.round(frac*(win.length-1))));
    const q=win[qi];_hovQ=q;
    const qSvgX=pl+qi*pw/Math.max(1,win.length-1);
    const qScreenX=br.left+qSvgX*sc;
    const maps=lastSeries.map(s=>Object.fromEntries(s.rows));
    let html=`<div class="tip-q">${q}</div>`;
    for(let i=0;i<lastSeries.length;i++){const s=lastSeries[i];const v=maps[i][q];if(v==null)continue;
      const fv=s.pct?(+v).toFixed(2)+'%':fmtUnit(v,false);
      const tpts=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const tl=(nE>1&&nM===1?tpts[0]:(nE===1?tpts.slice(1).join(' · ')||s.label:s.label));
      html+=`<div class="tip-row"><span class="tip-sw" style="background:${s.color}"></span>${tl}: <b>${fv}</b></div>`;}
    html+=`<div style="font-size:12px;color:#9aa3b2;margin-top:3px;opacity:.6">click to pin</div>`;
    tip.innerHTML=html;tip.style.display='block';
    let tx=qScreenX+14;if(tx+tip.offsetWidth>window.innerWidth-8)tx=qScreenX-14-tip.offsetWidth;if(tx<8)tx=8;
    const ty=Math.max(8,Math.min(br.top+14,window.innerHeight-tip.offsetHeight-8));
    tip.style.left=tx+'px';tip.style.top=ty+'px';_hovTx=tx+'px';_hovTy=ty+'px';}
  document.getElementById('panes').addEventListener('pointermove',e=>{const svg=e.target.closest('svg');if(!svg){if(!window._pinnedQ)tip.style.display='none';return;}showTip(e,svg);});
  document.getElementById('panes').addEventListener('pointerleave',()=>{if(!window._pinnedQ)tip.style.display='none';});
  document.getElementById('panes').addEventListener('click',e=>{
    if(e.target.closest('#idxbasereset')){e.preventDefault();window._idxBase=null;draw();return;}
    const svg=e.target.closest('svg');if(!svg)return;
    const idxEl=document.getElementById('idx');
    if(idxEl&&idxEl.checked&&_hovQ&&svg.closest('.idx-pane')){window._idxBase=_hovQ;draw();return;}
    if(window._pinnedQ){
      window._pinnedQ=null;
      document.querySelectorAll('#panes .qband').forEach(g=>g.classList.remove('qband-pinned'));
      tip.style.pointerEvents='none';tip.style.resize='none';tip.style.overflow='';
      tip.style.display='none';
    }else if(_hovQ){
      window._pinnedQ=_hovQ;
      if(_hovTx){tip.style.left=_hovTx;tip.style.top=_hovTy;}
      const cur=tip.innerHTML;tip.innerHTML=cur.replace(/<div style="font-size:12px[^"]*"[^>]*>click to pin<\/div>/,'');
      tip.innerHTML+=`<div style="font-size:12px;color:#9aa3b2;margin-top:3px">📌 click to unpin · drag corner to resize</div>`;
      // enable resize on pin
      tip.style.pointerEvents='auto';tip.style.resize='both';tip.style.overflow='auto';tip.style.boxSizing='border-box';
      if(window._tipW)tip.style.width=window._tipW;
      if(window._tipH)tip.style.height=window._tipH;
      tip.style.display='block';
      document.querySelectorAll(`#panes .qband[data-q="${window._pinnedQ}"]`).forEach(g=>g.classList.add('qband-pinned'));
    }});
})();
init();
</script></body></html>"""
# RSSD lineage map (predecessor stitching) — compact: {rssd:{m:[member rssds],l:label,s:[splice quarters]}}
LINEAGE_MAP={}
if os.path.exists("fry9c_lineage.json"):
    _lin=json.load(open("fry9c_lineage.json"))
    for _r,_o in _lin.items():
        if len(_o.get("members",[]))>1:
            _iso=lambda q: f"{q[:4]}-{q[4:6]}-{q[6:8]}" if q and len(q)==8 and q.isdigit() else q
            LINEAGE_MAP[int(_r)]={"m":[int(x["rssd"]) for x in _o["members"]],
                                  "l":_o["label"],"s":[_iso(x["quarter"]) for x in _o["splices"]]}
    print(f"embedded {len(set(v['l'] for v in LINEAGE_MAP.values()))} RSSD lineages ({len(LINEAGE_MAP)} member RSSDs)")
LINEAGE_JSON=json.dumps(LINEAGE_MAP, ensure_ascii=False)
# Nested-filer exclusion map for the ALL aggregate (HIGH-1) — {quarter_end:[rssd,...]} of holding
# companies controlled by another Y-9C filer that quarter. Built by build_fry9c_topholder.py from the
# NIC relationships file. Absent => '{}' (ALL falls back to every filer, with the header caveat).
NESTED_JSON="{}"
if os.path.exists("fry9c_topholder.json"):
    _nest=json.load(open("fry9c_topholder.json"))
    NESTED_JSON=json.dumps(_nest.get("nested", _nest), ensure_ascii=False)
    _nn=len(set(r for v in (_nest.get("nested", _nest)).values() for r in v))
    print(f"embedded nested-filer exclusion map: {_nn} RSSD(s) across {len(_nest.get('nested', _nest))} quarter(s)")
HTML=(HTML.replace("__PARTS__",parts_js).replace("__AGG_PARTS__",agg_parts_js)
    .replace("__OLD_ACTIVE_PARTS__",old_active_parts_js).replace("__HIST_PARTS__",hist_parts_js)
    .replace("__ACTIVE_RSSDS__",active_rssds_js)
    .replace("__BANKS__",BANKS_JSON).replace("__CREDIT_URL__",CREDIT_URL)
    .replace("__LINEAGE__",LINEAGE_JSON).replace("__NESTED__",NESTED_JSON).replace("__BUILD_TS__",BUILD_TS)
    .replace("__NODATA__",nodata_codes_js))
open(os.path.join(SITE,"index.html"),"w",encoding="utf-8").write(HTML)
_startup_mb=sum(os.path.getsize(os.path.join(SITE,p))/1e6 for p in PARTS+AGG_PARTS if os.path.exists(os.path.join(SITE,p)))
print(f"wrote {SITE}/index.html | startup download: {_startup_mb:.1f} MB ({len(PARTS)} active shard(s) + {len(AGG_PARTS)} agg)")
print("Upload site_fry9c/'s index.html + fry9c*.parquet + fry9c_hierarchy.json")
