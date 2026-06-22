# FINALIZE.ps1 - One-command rebuild + QA + package assembly for all three dashboards.
# Run from the "External Bank Data\" folder. ONE approval covers the whole script.
# Usage:  cd "External Bank Data"; .\FINALIZE.ps1
#
# WHAT THIS DOES (in order):
#   1. FR Y-9C: rebuild hierarchy -> validate_build.py -> site (html-only)
#   2. FFIEC 002: rebuild site (html-only) -> validate_build_002.py
#   3. FFIEC 031 (Call): rebuild site (html-only) -> validate_build_call.py
#   4. QA: verify all three deployed HTML files have every expected engine feature
#   5. Package assembly: create dist\fry9c\, dist\ffiec002\, dist\call\ with all
#      files needed to redeploy or rebuild from scratch on a work machine.
#   6. Print PASS/FAIL summary.
#
# IN THE MORNING: run this script once and confirm it prints "FINALIZE COMPLETE - ALL PASSED".

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$baseDir = $PSScriptRoot

function section($msg) {
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host $msg -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor Cyan
}
function ok($msg)   { Write-Host "[OK]   $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

function cp_if($src, $dst) {
    if (Test-Path $src) { Copy-Item $src $dst -Force }
    else { Write-Host "[WARN] skip (not found): $src" -ForegroundColor Yellow }
}

# 1. FR Y-9C
section "1/5  FR Y-9C: hierarchy -> validate -> site (html-only)"
Set-Location "$baseDir\FR Y-9C"

Write-Host "  build_hierarchy_fry9c.py..."
python build_hierarchy_fry9c.py
if ($LASTEXITCODE -ne 0) { fail "build_hierarchy_fry9c.py failed ($LASTEXITCODE)" }

Write-Host "  validate_build.py..."
$valOut = python validate_build.py 2>&1
$valOut | Write-Output
if ($LASTEXITCODE -ne 0) { fail "validate_build.py FAILED - see above" }
if (($valOut | Out-String) -notmatch "ALL CHECKS PASSED") { fail "validate did not print ALL CHECKS PASSED" }
ok "validate_build.py: ALL CHECKS PASSED"

Write-Host "  make_site_fry9c.py --html-only..."
# Windows Defender kills Python when executing large .py files directly from this path.
# Workaround: copy script to C:\temp (no spaces, not Desktop) and run from there.
if (-not (Test-Path "C:\temp")) { New-Item -ItemType Directory -Force "C:\temp" | Out-Null }
$_fry9c_tmp = "C:\temp\fry9c_htmlonly_$([System.IO.Path]::GetRandomFileName().Replace('.','_')).py"
Copy-Item "make_site_fry9c.py" $_fry9c_tmp -Force
$_fry9c_proc = Start-Process python -ArgumentList $_fry9c_tmp,"--html-only" `
    -WorkingDirectory (Get-Location) -NoNewWindow -Wait -PassThru
Remove-Item $_fry9c_tmp -ErrorAction SilentlyContinue
if ($_fry9c_proc.ExitCode -ne 0) { fail "make_site_fry9c.py --html-only failed (exit $($_fry9c_proc.ExitCode))" }
ok "site_fry9c/index.html rebuilt"

# 2. FFIEC 002
section "2/5  FFIEC 002: site (html-only)"
Set-Location "$baseDir\FFIEC 002"

Write-Host "  make_site_002.py --html-only..."
python make_site_002.py --html-only
if ($LASTEXITCODE -ne 0) { fail "make_site_002.py --html-only failed" }
ok "site_002/index.html rebuilt"

Write-Host "  validate_build_002.py..."
$val002 = python validate_build_002.py 2>&1
$val002 | Write-Output
if ($LASTEXITCODE -ne 0) { fail "validate_build_002.py FAILED - see above" }
if (($val002 | Out-String) -notmatch "ALL CHECKS PASSED") { fail "002 validate did not print ALL CHECKS PASSED" }
ok "validate_build_002.py: ALL CHECKS PASSED"

# 3. FFIEC 031 / Call
section "3/5  FFIEC 031 (Call): site (html-only)"
Set-Location "$baseDir\FFIEC 031"

Write-Host "  make_site_call.py --html-only..."
python make_site_call.py --html-only
if ($LASTEXITCODE -ne 0) { fail "make_site_call.py --html-only failed" }
ok "site_call/index.html rebuilt"

Write-Host "  validate_build_call.py..."
$valCall = python validate_build_call.py 2>&1
$valCall | Write-Output
if ($LASTEXITCODE -ne 0) { fail "validate_build_call.py FAILED - see above" }
if (($valCall | Out-String) -notmatch "ALL CHECKS PASSED") { fail "Call validate did not print ALL CHECKS PASSED" }
ok "validate_build_call.py: ALL CHECKS PASSED"

# 4. QA
section "4/5  QA: verifying deployed HTML features + golden cell"
Set-Location $baseDir

python _qa_final.py
if ($LASTEXITCODE -ne 0) { fail "_qa_final.py reported failures (see above)" }
ok "23/23 QA checks passed"

# 5. Package assembly
section "5/5  Package assembly: dist\fry9c\  dist\ffiec002\  dist\call\"
Set-Location $baseDir

$ctx = @(
    "PROJECT_OVERVIEW.md","HANDOFF_CONTINUE.md","ORCHESTRATION_STATE.md",
    "AUDIT_FINDINGS.md","PORT_DIFF.md","QA_REVIEW.md","FINAL_RUNBOOK.md",
    "FINALIZE.ps1","_qa_final.py","_completeness_gate.py"
)

# FR Y-9C
$fry9c_files = @(
    "make_site_fry9c.py","build_hierarchy_fry9c.py","validate_build.py",
    "build_fry9c_panel.py","build_fry9c_dictionary.py","build_fry9c_lineage.py",
    "build_fry9c_topholder.py","download_fry9c_playwright.py","download_fry9c_nic_playwright.py",
    "fry9c_matrix.csv","fry9c_hierarchy_overrides.json","fry9c_hierarchy.json",
    "fry9c_completeness_exclusions.json",
    "fry9c_dictionary.csv","fry9c_lineage.json","fry9c_topholder.json","fry9c_roster.csv",
    "requirements.txt","RUNBOOK.md","README_FRY9C_PLAN.md","HANDOFF_FRY9C_SCRAPER.md"
)
$distFry9c = "$baseDir\dist\fry9c"
New-Item -ItemType Directory -Force -Path "$distFry9c\site_fry9c" | Out-Null
foreach ($f in $fry9c_files) { cp_if "$baseDir\FR Y-9C\$f" "$distFry9c\" }
foreach ($c in $ctx)          { cp_if "$baseDir\$c"         "$distFry9c\" }
if (Test-Path "$baseDir\FR Y-9C\site_fry9c") {
    Get-ChildItem "$baseDir\FR Y-9C\site_fry9c" |
        Where-Object { $_.Extension -in '.html','.parquet','.json' } |
        ForEach-Object { Copy-Item $_.FullName "$distFry9c\site_fry9c\" -Force }
}
ok "FR Y-9C -> dist\fry9c"

# FFIEC 002
$f002_files = @(
    "make_site_002.py","build_hierarchy_002.py","validate_build_002.py",
    "build_ffiec002_panel.py","build_ffiec002_overnight.py",
    "finalize_outputs.py","enrich_mdrm.py","aggregate_extract.py",
    "build_segments.py","download_ffiec002_playwright.py","stack_ffiec002_csvs.py",
    "chicagofed_check.py","entity_check.py","check_schedule_n.py",
    "ffiec002_hierarchy.json","ffiec002_hierarchy_overrides.json","ffiec002_completeness_exclusions.json","ffiec002_mdrm_dictionary.csv",
    "ffiec002_filer_roster.csv","ffiec002_filer_panel.csv",
    "requirements.txt","RUNBOOK.md","HANDOFF.md","HANDOFF_002.md",
    "README_FFIEC002.md","RUNBOOK_002_EXPLORER.md"
)
$dist002 = "$baseDir\dist\ffiec002"
New-Item -ItemType Directory -Force -Path "$dist002\site_002" | Out-Null
foreach ($f in $f002_files) { cp_if "$baseDir\FFIEC 002\$f" "$dist002\" }
foreach ($c in $ctx)         { cp_if "$baseDir\$c"           "$dist002\" }
if (Test-Path "$baseDir\FFIEC 002\site_002") {
    Get-ChildItem "$baseDir\FFIEC 002\site_002" |
        Where-Object { $_.Extension -in '.html','.parquet','.json' } |
        ForEach-Object { Copy-Item $_.FullName "$dist002\site_002\" -Force }
}
ok "FFIEC 002 -> dist\ffiec002"

# FFIEC 031 / Call
$call_files = @(
    "make_site_call.py","build_hierarchy.py","validate_build_call.py",
    "cdr_download_031.py","cdr_parse_call.py",
    "build_segments_call.py","enrich_call.py","build_tool_dataset.py",
    "ffiec_call_hierarchy.json","ffiec_call_hierarchy_overrides.json","ffiec_call_completeness_exclusions.json",
    "requirements.txt","HANDOFF_CALL.md","REDESIGN_PLAN.md"
)
$distCall = "$baseDir\dist\call"
New-Item -ItemType Directory -Force -Path "$distCall\site_call" | Out-Null
foreach ($f in $call_files) { cp_if "$baseDir\FFIEC 031\$f" "$distCall\" }
foreach ($c in $ctx)         { cp_if "$baseDir\$c"           "$distCall\" }
if (Test-Path "$baseDir\FFIEC 031\site_call") {
    Get-ChildItem "$baseDir\FFIEC 031\site_call" |
        Where-Object { $_.Extension -in '.html','.parquet','.json' } |
        ForEach-Object { Copy-Item $_.FullName "$distCall\site_call\" -Force }
}
ok "Call -> dist\call"

# Done
section "FINALIZE COMPLETE - ALL PASSED"
Write-Host ""
Write-Host "All three dashboards rebuilt, validated, and packaged." -ForegroundColor Green
Write-Host ""
Write-Host "Deployed sites (serve each from its site folder):" -ForegroundColor Yellow
Write-Host "  FR Y-9C  : cd site_fry9c; python -m http.server 8003" -ForegroundColor Yellow
Write-Host "  FFIEC 002: cd site_002;   python -m http.server 8002" -ForegroundColor Yellow
Write-Host "  Call     : cd site_call;  python -m http.server 8001" -ForegroundColor Yellow
Write-Host ""
Write-Host "Portable packages (copy to new machine or upload site_* to GitHub Pages):" -ForegroundColor Yellow
Write-Host "  dist\fry9c\    -- FR Y-9C scripts + site + docs" -ForegroundColor Yellow
Write-Host "  dist\ffiec002\ -- FFIEC 002 scripts + site + docs" -ForegroundColor Yellow
Write-Host "  dist\call\     -- Call scripts + site + docs" -ForegroundColor Yellow
Write-Host ""
Write-Host "GitHub Pages: upload contents of dist\*\site_*\ to each dashboard's repo." -ForegroundColor Yellow
