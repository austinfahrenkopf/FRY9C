#!/usr/bin/env python3
"""
_write_site_parquets.py
Write all site_fry9c/*.parquet shards using pure DuckDB — bypasses pandas OOM on
the 141M-row panel (1732/2878 display codes kept, ~85M rows after filter).

Run: python _write_site_parquets.py
Then: python make_site_fry9c.py --html-only
"""
import duckdb, json, os, sys, time

SRC  = 'fry9c_panel_long.parquet'
SITE = 'site_fry9c'

t0 = time.time()

# ---- DISPLAY_CODES ----
dc = set()
if os.path.exists('fry9c_hierarchy.json'):
    for items in json.load(open('fry9c_hierarchy.json')).values():
        for it in items: dc.add(it.get('mdrm'))
dc |= {'BHCK2122','BHCK2170','BHCK3210','BHCK4340','BHCK3123',
       'BHCK1403','BHCK1406','BHCK1407','BHDM6631','BHDM6636','BHFN6631','BHFN6636',
       'BHCK1606','BHCKB575','BHCKK213','BHCKK216','BHCK1594',
       'BHCK5398','BHCKC236','BHCKC238','BHCKF172','BHCKF173','BHCK3499','BHCKF178','BHCKF179'}
dc.discard(None); dc.discard('')
codes_csv = ','.join(f"'{c}'" for c in sorted(dc))
print(f'DISPLAY_CODES: {len(dc)}  elapsed={time.time()-t0:.1f}s')

conn = duckdb.connect()

# Create filtered view with standardized types
conn.execute(f"""
    CREATE VIEW filtered AS
    SELECT quarter_end::VARCHAR AS quarter_end,
           id_rssd::BIGINT      AS id_rssd,
           institution_name::VARCHAR AS institution_name,
           mdrm::VARCHAR        AS mdrm,
           value::DOUBLE        AS value
    FROM read_parquet('{SRC}')
    WHERE mdrm IN ({codes_csv})
""")
print(f'View created  elapsed={time.time()-t0:.1f}s')

# Latest quarter + active RSSDs
max_q = conn.execute("SELECT max(quarter_end) FROM filtered").fetchone()[0]
active_rssds = [r[0] for r in conn.execute(
    f"SELECT DISTINCT id_rssd FROM filtered WHERE quarter_end = '{max_q}'").fetchall()]
print(f'Active ({max_q}): {len(active_rssds)}  elapsed={time.time()-t0:.1f}s')
active_csv = ','.join(str(r) for r in sorted(active_rssds))
total_filers = conn.execute("SELECT count(distinct id_rssd) FROM filtered").fetchone()[0]
print(f'Total filers: {total_filers}  elapsed={time.time()-t0:.1f}s')

# Topholder exclusions for AGG (nested sub-holders must not be double-counted)
exclude_cte = ""
if os.path.exists('fry9c_topholder.json'):
    nm = json.load(open('fry9c_topholder.json'))
    ne = nm.get('nested', nm)
    pairs = [(q, int(r2)) for q, rs in ne.items() for r2 in rs]
    if pairs:
        vals = ','.join(f"('{q}',{r})" for q, r in pairs)
        conn.execute(f"CREATE TABLE _ex AS SELECT * FROM (VALUES {vals}) t(qe, rid)")
        exclude_cte = "LEFT JOIN _ex ON filtered.quarter_end=_ex.qe AND filtered.id_rssd=_ex.rid WHERE _ex.rid IS NULL"
        print(f'Topholder exclusions: {len(pairs)}  elapsed={time.time()-t0:.1f}s')

# Clean old parquets
os.makedirs(SITE, exist_ok=True)
for f in os.listdir(SITE):
    if f.endswith('.parquet'): os.remove(os.path.join(SITE, f))

pq_opts = "FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 50000"

# ---- Active era shards ----
recent_part = None
for lo, hi, is_recent in [(2020, 2031, True), (2010, 2019, False), (1986, 2009, False)]:
    fn = os.path.join(SITE, f'fry9c_active_{lo}_{hi}.parquet')
    fn_fwd = fn.replace('\\', '/')
    conn.execute(f"""
        COPY (
            SELECT quarter_end, id_rssd, institution_name, mdrm, value
            FROM filtered
            WHERE id_rssd IN ({active_csv})
            AND quarter_end[:4]::INTEGER BETWEEN {lo} AND {hi}
            ORDER BY id_rssd, mdrm, quarter_end
        ) TO '{fn_fwd}' ({pq_opts})
    """)
    sz = os.path.getsize(fn)
    print(f'  fry9c_active_{lo}_{hi}.parquet: {sz/1e6:.1f} MB  elapsed={time.time()-t0:.1f}s')
    if is_recent: recent_part = fn

# ---- Hist shard (inactive filers) ----
fn_h = os.path.join(SITE, 'fry9c_hist.parquet')
fn_h_fwd = fn_h.replace('\\', '/')
conn.execute(f"""
    COPY (
        SELECT quarter_end, id_rssd, institution_name, mdrm, value
        FROM filtered
        WHERE id_rssd NOT IN ({active_csv})
        ORDER BY id_rssd, mdrm, quarter_end
    ) TO '{fn_h_fwd}' ({pq_opts})
""")
sz = os.path.getsize(fn_h)
print(f'  fry9c_hist.parquet: {sz/1e6:.1f} MB (inactive)  elapsed={time.time()-t0:.1f}s')

# ---- AGG shard (ALL quarters, pre-aggregated, topholder-excluded) ----
fn_agg = os.path.join(SITE, 'fry9c_agg.parquet')
fn_agg_fwd = fn_agg.replace('\\', '/')
if exclude_cte:
    conn.execute(f"""
        COPY (
            SELECT filtered.quarter_end, filtered.mdrm, SUM(filtered.value) AS value
            FROM filtered {exclude_cte}
            GROUP BY filtered.quarter_end, filtered.mdrm
        ) TO '{fn_agg_fwd}' ({pq_opts})
    """)
else:
    conn.execute(f"""
        COPY (
            SELECT quarter_end, mdrm, SUM(value) AS value
            FROM filtered
            GROUP BY quarter_end, mdrm
        ) TO '{fn_agg_fwd}' ({pq_opts})
    """)
sz = os.path.getsize(fn_agg)
print(f'  fry9c_agg.parquet: {sz/1e6:.1f} MB (agg)  elapsed={time.time()-t0:.1f}s')

print(f'\nAll site parquets written in {time.time()-t0:.1f}s')
print('Next: python make_site_fry9c.py --html-only')
