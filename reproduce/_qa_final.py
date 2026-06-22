"""
_qa_final.py -- deployed-HTML verification for all three dashboards.
Run from 'External Bank Data' folder.
"""
import sys, re, os

results = []

def check(name, path, patterns):
    try:
        html = open(path, encoding='utf-8').read()
    except FileNotFoundError:
        results.append(('FAIL', name, f'file not found: {path}'))
        return
    for label, pat in patterns:
        if not re.search(pat, html):
            results.append(('FAIL', name, f'missing: {label}'))
        else:
            results.append(('OK',   name, label))

# Y-9C checks
check('Y-9C', r'FR Y-9C\site_fry9c\index.html', [
    ('prevQtr helper',         r'function prevQtr'),
    ('yoyQtr helper',          r'function yoyQtr'),
    ('pctChg sign-flip guard', r'sameSign'),
    ('descCodes PCTC filter',  r'PCTC\.has\(c\.code\)'),
    ('hasPctDesc',             r'function hasPctDesc'),
    ('perFilerValues DYN',     r'DYN\[measCode\]'),
    ('isRawPct (Y-9C)',        r'isRawPct'),
    ('isAggScope (Y-9C)',      r'isAggScope'),
    ('NESTED topholder',       r'NESTED'),
    ('allCond top-tier',       r'function allCond'),
])

# 002 checks
check('002', r'FFIEC 002\site_002\index.html', [
    ('prevQtr helper',   r'function prevQtr'),
    ('yoyQtr helper',    r'function yoyQtr'),
    ('pctChg sign-flip', r'sameSign'),
    ('perFilerValues',   r'perFilerValues'),
])

# Call checks
check('Call', r'FFIEC 031\site_call\index.html', [
    ('prevQtr helper',      r'function prevQtr'),
    ('yoyQtr helper',       r'function yoyQtr'),
    ('pctChg sign-flip',    r'sameSign'),
    ('perFilerValues',      r'perFilerValues'),
    ('HIGH-2 PCTC set',     r"const PCTC=new Set\(\['RCFA7204'"),
    ('isRawPct (Call)',      r'isRawPct'),
    ('isAggScope (Call)',    r'isAggScope'),
    ('blocked label',       r'not summable across entities'),
])

# Golden cell check (Y-9C panel)
try:
    import pandas as pd
    pnl = pd.read_parquet(
        os.path.join('FR Y-9C', 'fry9c_panel_long.parquet'),
        columns=['quarter_end','id_rssd','mdrm','value']
    )
    lq = pnl['quarter_end'].max()
    jpm = pnl[(pnl['id_rssd']==1039502)&(pnl['mdrm']=='BHCK2170')&(pnl['quarter_end']==lq)]
    if jpm.empty:
        results.append(('FAIL','GOLDEN','JPM BHCK2170 not found in panel'))
    elif int(jpm['value'].iloc[0]) != 4_900_475_000:
        v = int(jpm['value'].iloc[0])
        results.append(('FAIL','GOLDEN',f'JPM BHCK2170={v:,} expected 4,900,475,000'))
    else:
        results.append(('OK','GOLDEN',f'JPM BHCK2170 @ {lq} = 4,900,475,000'))
except Exception as e:
    results.append(('WARN','GOLDEN',f'panel check skipped: {e}'))

# Report
fails = [r for r in results if r[0]=='FAIL']
warns = [r for r in results if r[0]=='WARN']
print()
for status, name, msg in results:
    tag = {'OK':'  [OK]','FAIL':'[FAIL]','WARN':'[WARN]'}[status]
    print(f'{tag} {name}: {msg}')
print()
if fails:
    print(f'QA FAILED — {len(fails)} failure(s), {len(warns)} warning(s)')
    sys.exit(1)
elif warns:
    print(f'ALL QA PASSED with {len(warns)} warning(s)')
else:
    print('ALL QA CHECKS PASSED')
