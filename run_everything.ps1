# run_everything.ps1 — verify coherence + run all new experiments
$ErrorActionPreference = "Stop"
$DB = "data\bugs4q\Bugs4Q-Database"
$SPLITS = "experiments\splits_70_15_15.json"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " PART 1: Verify coherence (legacy vs new)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n[1/3] Smoke tests..." -ForegroundColor Yellow
python tests\test_smoke.py
if ($LASTEXITCODE -ne 0) { throw "Smoke tests failed" }

Write-Host "`n[2/3] Behavioral equivalence (legacy vs new)..." -ForegroundColor Yellow
python tests\test_equivalence_with_legacy.py
if ($LASTEXITCODE -ne 0) { throw "Equivalence tests failed" }

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " PART 2: Run new experiments" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n[3/8] Statistical tests (Wilcoxon)..." -ForegroundColor Yellow
python scripts\run_statistical_tests.py --combined experiments\combined_results_val.csv --out experiments\statistical_tests_report.md
if ($LASTEXITCODE -ne 0) { throw "Stats failed" }

if (-not (Test-Path $DB)) {
    Write-Host "`n[INFO] Dataset not found at $DB. Downloading..." -ForegroundColor Yellow
    python scripts\download_bugs4q.py
    if ($LASTEXITCODE -ne 0) { throw "Download failed" }
}

Write-Host "`n[4/8] Rebuild 70/15/15 split..." -ForegroundColor Yellow
python scripts\resplit.py --db_root $DB --out $SPLITS --ratios 0.70 0.15 0.15
if ($LASTEXITCODE -ne 0) { throw "Resplit failed" }

Write-Host "`n[5/8] Rule-APR on TEST/VAL/ALL..." -ForegroundColor Yellow
python baselines\rule_based_apr.py --db_root $DB --splits $SPLITS --which test --out_csv experiments\rule_apr_test.csv
python baselines\rule_based_apr.py --db_root $DB --splits $SPLITS --which val --out_csv experiments\rule_apr_val.csv
python baselines\rule_based_apr.py --db_root $DB --splits $SPLITS --which all --out_csv experiments\rule_apr_all.csv

Write-Host "`n[6/8] QChecker static analysis..." -ForegroundColor Yellow
python baselines\qchecker.py --db_root $DB --filter_cases $SPLITS --out experiments\qchecker_findings_all.json

Write-Host "`n[7/8] Per-split baseline aggregates..." -ForegroundColor Yellow
python scripts\per_split_baseline_summary.py --db_root $DB --splits $SPLITS --out_md experiments\per_split_baselines_70_15_15.md

Write-Host "`n[8/8] Cross-method comparison table..." -ForegroundColor Yellow
python scripts\compare_baselines.py --grap_llm experiments\combined_results_val.csv --rule_apr experiments\rule_apr_val.csv --qchecker experiments\qchecker_findings_all.json --out experiments\baselines_comparison_val.md

Write-Host "`n========================================" -ForegroundColor Green
Write-Host " ALL DONE — headline results:" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Select-String -Path experiments\statistical_tests_report.md -Pattern "Mean paired|Wilcoxon|Cliff" | Select-Object -First 6 | ForEach-Object { Write-Host $_.Line }
Write-Host "`nFull artifacts saved in .\experiments\"