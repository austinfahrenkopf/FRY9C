"""
add_missing_codes.py — append completeness-audit must-add codes to
fry9c_hierarchy_overrides.json force_rows.

Run once:  python add_missing_codes.py
Safe to re-run: de-duplicates on (key, mdrm) before writing.
"""

import json, os, sys
from pathlib import Path

OVERRIDES = Path(__file__).parent / "fry9c_hierarchy_overrides.json"

NEW_ROWS = [
    # ── HC (Balance Sheet) ────────────────────────────────────────────────
    # Foreign-office deposit sub-columns under item 13 (Deposits) -> 13.b in foreign offices.
    # (Domestic BHDM6631/6636 live at 13.a.(1)/(2); the parser/overrides place those. These were
    # ERRONEOUSLY at 9.b — item 9 is "real estate ventures", deposits belong under item 13. Fixed §52.)
    {"key": "HC", "mdrm": "BHFN6631", "item": "13.b.(1)",
     "caption": "Noninterest-bearing (in foreign offices)"},
    {"key": "HC", "mdrm": "BHFN6636", "item": "13.b.(2)",
     "caption": "Interest-bearing (in foreign offices)"},
    # Domestic-only federal funds purchased (column B of item 14.a)
    {"key": "HC", "mdrm": "BHDMB993", "item": "14.a.B",
     "caption": "Federal funds purchased in domestic offices (domestic offices only)"},

    # ── HC-B (Securities) ─────────────────────────────────────────────────
    # GSE-guaranteed structured financial products: sub-items included in 5.b
    {"key": "HC-B", "item": "5.b.a",
     "caption": "Of which: Structured financial products guaranteed by U.S. Government agencies or sponsored agencies (included in item 5.b):"},
    {"key": "HC-B", "mdrm": "BHCKPU98", "item": "5.b.a.A",
     "caption": "Held-to-maturity — Amortized cost"},
    {"key": "HC-B", "mdrm": "BHCKPU99", "item": "5.b.a.B",
     "caption": "Held-to-maturity — Fair value"},
    {"key": "HC-B", "mdrm": "BHCKPV00", "item": "5.b.a.C",
     "caption": "Available-for-sale — Amortized cost"},
    {"key": "HC-B", "mdrm": "BHCKPV01", "item": "5.b.a.D",
     "caption": "Available-for-sale — Fair value"},

    # ── HC-C (Loans and Leases) ───────────────────────────────────────────
    # Item 1 (RE loans): consolidated already at "1", add domestic column
    {"key": "HC-C", "mdrm": "BHDM1410", "item": "1.B",
     "caption": "Loans secured by real estate — domestic offices"},
    # Item 2 (depository inst.): consolidated at "2", add domestic column
    {"key": "HC-C", "mdrm": "BHDM1288", "item": "2.B",
     "caption": "Loans to depository institutions and acceptances of other banks — domestic offices"},
    # Item 4 (C&I): consolidated at "4", add domestic column
    {"key": "HC-C", "mdrm": "BHDM1766", "item": "4.B",
     "caption": "Commercial and industrial loans — domestic offices"},
    # Item 6 (individuals): consolidated at "6", add domestic column
    {"key": "HC-C", "mdrm": "BHDM1975", "item": "6.B",
     "caption": "Loans to individuals for household, family, and other personal expenditures — domestic offices"},
    # Item 7 (foreign govts): consolidated at "7", add domestic column
    {"key": "HC-C", "mdrm": "BHDM2081", "item": "7.B",
     "caption": "Loans to foreign governments and official institutions — domestic offices"},
    # Item 9.b.(3): consolidated at "9.b.(3)", add domestic column
    {"key": "HC-C", "mdrm": "BHDMKX57", "item": "9.b.(3).B",
     "caption": "Loans for purchasing or carrying securities and all other loans — domestic offices"},
    # Item 10: parser captured BHDM2165 (domestic) at "10"; add BHCK2165 (consolidated) at "10.A"
    {"key": "HC-C", "mdrm": "BHCK2165", "item": "10.A",
     "caption": "Lease financing receivables (net of unearned income) — consolidated"},
    # M.12.e column C: best-estimate cash flows (A and B already present)
    {"key": "HC-C", "mdrm": "BHCKKX62", "item": "M.12.e.C",
     "caption": "Best estimate at acquisition date of contractual cash flows not expected to be collected (purchased credit-deteriorated loans and leases)"},
    # M.16: loans to nondepository financial institution sub-types (HC-C Memorandum 16)
    {"key": "HC-C", "item": "M.16",
     "caption": "Loans to nondepository financial institutions by type (included in Schedule HC-C, item 9.a):"},
    {"key": "HC-C", "mdrm": "BHCKPV05", "item": "M.16.a",
     "caption": "Loans to mortgage credit intermediaries"},
    {"key": "HC-C", "mdrm": "BHCKPV06", "item": "M.16.b",
     "caption": "Loans to business credit intermediaries"},
    {"key": "HC-C", "mdrm": "BHCKPV07", "item": "M.16.c",
     "caption": "Loans to private equity funds"},
    {"key": "HC-C", "mdrm": "BHCKPV08", "item": "M.16.d",
     "caption": "Loans to consumer credit intermediaries"},
    {"key": "HC-C", "mdrm": "BHCKPV09", "item": "M.16.e",
     "caption": "Other loans to nondepository financial institutions"},
    # Domestic-office sub-columns for M.16
    {"key": "HC-C", "mdrm": "BHDMPV05", "item": "M.16.a.B",
     "caption": "Loans to mortgage credit intermediaries — domestic offices"},
    {"key": "HC-C", "mdrm": "BHDMPV06", "item": "M.16.b.B",
     "caption": "Loans to business credit intermediaries — domestic offices"},
    {"key": "HC-C", "mdrm": "BHDMPV07", "item": "M.16.c.B",
     "caption": "Loans to private equity funds — domestic offices"},
    {"key": "HC-C", "mdrm": "BHDMPV08", "item": "M.16.d.B",
     "caption": "Loans to consumer credit intermediaries — domestic offices"},
    {"key": "HC-C", "mdrm": "BHDMPV09", "item": "M.16.e.B",
     "caption": "Other loans to nondepository financial institutions — domestic offices"},

    # ── HC-K (Quarterly Averages — Balance Sheet) ─────────────────────────
    # Item 3.a: consolidated at "3.a"; add bank-consolidated and domestic columns
    {"key": "HC-K", "mdrm": "BHBC3516", "item": "3.a.B",
     "caption": "Quarterly averages of loans and leases — bank consolidated (bank subsidiary only)"},
    {"key": "HC-K", "mdrm": "BHDM3516", "item": "3.a.C",
     "caption": "Quarterly averages of loans and leases — domestic offices"},
    # Item 3.b: total loans in foreign offices; add foreign-offices breakdown
    {"key": "HC-K", "mdrm": "BHFN3360", "item": "3.b.B",
     "caption": "Quarterly average of total loans — foreign offices"},
    # Item 5: total assets; add bank-consolidated column
    {"key": "HC-K", "mdrm": "BHBC3368", "item": "5.B",
     "caption": "Quarterly average of total assets — bank consolidated (bank subsidiary only)"},
    # Item 11: equity capital; add bank-consolidated column
    {"key": "HC-K", "mdrm": "BHBC3519", "item": "11.B",
     "caption": "Quarterly average of equity capital — bank consolidated (bank subsidiary only)"},

    # ── HC-L (Off-Balance-Sheet Items) ────────────────────────────────────
    # NOTE: BHCKA251 "Credit losses on derivatives" is HI Memoranda item M.11 per the 2026
    # template (FR_Y-9C20260310_f.pdf p.5/44), NOT HC-L. It is force_rowed at HI — Memoranda
    # item "11" in fry9c_hierarchy_overrides.json. Do not re-add it to HC-L (was a misplacement; fixed §55).
    # Other unused commitments (1.e): sub-types of loans to financial institutions (1.e.(2))
    {"key": "HC-L", "item": "1.e.(2).a",
     "caption": "Other unused commitments — loans to depository financial institutions (included in item 1.e.(2)):"},
    {"key": "HC-L", "mdrm": "BHCKPV10", "item": "1.e.(2).a.i",
     "caption": "Other unused commitments: Loans to depository financial institutions"},
    {"key": "HC-L", "mdrm": "BHCKPV11", "item": "1.e.(2).b",
     "caption": "Other unused commitments: Loans to nondepository financial institutions"},
    {"key": "HC-L", "mdrm": "BHCKPV12", "item": "1.e.(2).c",
     "caption": "Other unused commitments: Loans to mortgage credit intermediaries"},
    {"key": "HC-L", "mdrm": "BHCKPV13", "item": "1.e.(2).d",
     "caption": "Other unused commitments: Loans to business credit intermediaries"},
    {"key": "HC-L", "mdrm": "BHCKPV14", "item": "1.e.(2).e",
     "caption": "Other unused commitments: Loans to private equity funds"},
    {"key": "HC-L", "mdrm": "BHCKPV15", "item": "1.e.(2).f",
     "caption": "Other unused commitments: Loans to consumer credit intermediaries"},
    {"key": "HC-L", "mdrm": "BHCKPV16", "item": "1.e.(2).g",
     "caption": "Other unused commitments: Other loans to nondepository financial institutions"},

    # ── HC-N (Past Due and Nonaccrual Loans) ──────────────────────────────
    # STANDING DECISION (2026-06-21, HOPPER #20): BHCKPV23/24/25 ("Loans to nondepository
    # financial institutions, included in Schedule HC-N item 7") are REMOVED — no "7.a", no M.10.
    #   * USER ADJUDICATION = DELETE. The HC-N matrix row was deleted at source; PV23/24/25 are
    #     listed in fry9c_completeness_exclusions.json -> excluded_codes so the gate's MISSING
    #     check does not re-flag or re-introduce them. Do NOT re-add a 7.a or an M.10 here.
    #   * EVIDENCE ON RECORD (so this is reversible/transparent): these ARE a real dictionary-
    #     defined FR Y-9C code (fry9c_dictionary.csv) and a genuinely NEW 2026-Q1 disclosure —
    #     384 filers reported them at 2026-03-31 (incl. Goldman Sachs RSSD 2380443; nonaccrual
    #     col C ≈ $1.10B), and the same line exists in the Call form (RCFD/RCON/COMB PV23/24/25).
    #     They are absent from the older HC-N PDF revision (page dated 12/2019) because the line
    #     was added in 2026. Removed by explicit product decision (avoid a single-quarter brand-
    #     new row), NOT because the codes are spurious. To restore: delete the three excluded_codes
    #     entries and re-add the matrix M.10 row above.

    # ── HC-R (Regulatory Capital) — Part I ───────────────────────────────
    # Standardized-approach equivalents of items 11, 12, 17, 18, 19 (BHCA = advanced approach)
    {"key": "HC-R", "mdrm": "BHCWP851", "item": "11.S",
     "caption": "LESS: Non-significant investments in the capital of unconsolidated financial institutions in the form of common stock that exceed the 10 percent threshold for non-significant investments (standardized approach)"},
    {"key": "HC-R", "mdrm": "BHCWP852", "item": "12.S",
     "caption": "Subtotal of common equity tier 1 capital: adjustments and deductions (standardized approach)"},
    {"key": "HC-R", "mdrm": "BHCWP857", "item": "17.S",
     "caption": "LESS: Deductions applied to common equity tier 1 capital due to insufficient amounts of additional tier 1 capital and tier 2 capital to cover deductions (standardized approach)"},
    {"key": "HC-R", "mdrm": "BHCWP858", "item": "18.S",
     "caption": "Total adjustments and deductions for common equity tier 1 capital (standardized approach)"},
    {"key": "HC-R", "mdrm": "BHCWP859", "item": "19.S",
     "caption": "Common equity tier 1 capital (standardized approach)"},
    # CDCI perpetual preferred stock (Memorandum / supplemental item)
    {"key": "HC-R", "mdrm": "BHCKK141", "item": "M.K141",
     "caption": "Outstanding issuances of perpetual preferred stock associated with the U.S. Department of Treasury CDCI program included in perpetual preferred stock and related surplus"},
    # GSIB TLAC advanced-approaches RWA ratio (standardized-approach variant is BHCWMK66 already at item 57)
    {"key": "HC-R", "mdrm": "BHCAMK66", "item": "57.A",
     "caption": "Top-tier BHCs of U.S. GSIBs only: LTD and TLAC total risk-weighted assets ratios using advanced approaches rule"},

    # ── HC-V (Variable Interest Entities) ────────────────────────────────
    # Quarterly average of earning assets — bank consolidated
    {"key": "HC-V", "mdrm": "BHBC3402", "item": "M.1",
     "caption": "Quarterly average of earning assets — bank consolidated (bank subsidiary only)"},

    # ── HI — Notes (Predecessor) ─────────────────────────────────────────
    # Y-9C form PDF page 14: "Notes to the Income Statement — Predecessor Financial Items"
    # ROOT CAUSE NOTE: build_hierarchy_fry9c.py correctly skips page 14 via the NOTES regex
    # (cur=None; continue). These codes have panel data and must be added via force_rows.
    # Prior versions WRONGLY used key="HI-C" — corrected 2026-06-19 to their true home.
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4107", "item": "1",
     "caption": "Total interest income — bank consolidated (predecessor)"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4094", "item": "1.a",
     "caption": "Interest income on loans and leases — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4218", "item": "1.b",
     "caption": "Interest income on investment securities — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4073", "item": "2",
     "caption": "Total interest expense — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4421", "item": "2.a",
     "caption": "Interest expense on deposits — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4074", "item": "3",
     "caption": "Net interest income — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCJJ33", "item": "4",
     "caption": "Provision for credit losses — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4079", "item": "5",
     "caption": "Total noninterest income — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4070", "item": "5.a",
     "caption": "Income from fiduciary activities — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCA220", "item": "5.b",
     "caption": "Trading revenue — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCB490", "item": "5.c",
     "caption": "Investment banking, advisory, brokerage, and underwriting fees and commissions — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCB491", "item": "5.d",
     "caption": "Venture capital revenue — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCB493", "item": "5.e",
     "caption": "Net securitization income — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCB494", "item": "5.f",
     "caption": "Insurance commissions and fees — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4091", "item": "6",
     "caption": "Realized gains (losses) on held-to-maturity and available-for-sale securities — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4093", "item": "7",
     "caption": "Total noninterest expense — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4135", "item": "7.a",
     "caption": "Salaries and employee benefits — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBCC216", "item": "7.b",
     "caption": "Goodwill impairment losses — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4301", "item": "8",
     "caption": "Income (loss) before applicable income taxes and discontinued operations — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4302", "item": "9",
     "caption": "Applicable income taxes — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4484", "item": "10",
     "caption": "Noncontrolling (minority) interest — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHCKFT41", "item": "11",
     "caption": "Discontinued operations, net of applicable income taxes and noncontrolling interest"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4340", "item": "12",
     "caption": "Net income (loss) — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4475", "item": "13",
     "caption": "Cash dividends declared — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC6061", "item": "14",
     "caption": "Net charge-offs — bank consolidated"},
    {"key": "HI — Notes (Predecessor)", "mdrm": "BHBC4519", "item": "15",
     "caption": "Net interest income on a fully taxable equivalent basis — bank consolidated"},
]

def main():
    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    existing = data.setdefault("force_rows", [])

    # Build a de-dup set by (key, mdrm) — skip header rows (no mdrm)
    seen = set()
    for row in existing:
        if row.get("mdrm"):
            seen.add((row["key"], row["mdrm"]))

    added = 0
    for row in NEW_ROWS:
        k = (row["key"], row.get("mdrm", ""))
        if row.get("mdrm") and k in seen:
            print(f"  SKIP (already present): {row['key']} {row['mdrm']}")
            continue
        existing.append(row)
        if row.get("mdrm"):
            seen.add(k)
        added += 1

    tmp = OVERRIDES.with_suffix(OVERRIDES.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OVERRIDES)
    json.loads(OVERRIDES.read_text(encoding="utf-8"))  # verify readable
    print(f"\nDone. Added {added} rows (total force_rows now: {len(existing)}); "
          f"verified, {OVERRIDES.stat().st_size} bytes.")

if __name__ == "__main__":
    main()
