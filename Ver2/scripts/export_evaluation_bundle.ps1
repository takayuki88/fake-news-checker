param(
    [string]$DatasetPath = "..\Ver3\testdata\real_article_dataset_v2.json",
    [switch]$UseGemini = $true,
    [string]$OutputStem = "real_v2_use_gemini",
    [string]$CsvBaseName = "",
    [string]$Timestamp = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

if (-not $Timestamp) {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmm"
}

$resolvedDatasetPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $DatasetPath))
$datasetName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedDatasetPath)

if (-not $CsvBaseName) {
    $CsvBaseName = "${datasetName}_with_predicted_verdict_attention_score"
}

$outDir = Join-Path $projectRoot "evaluation_outputs\$Timestamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$predictionsPath = Join-Path $outDir ("predictions_{0}.json" -f $OutputStem)
$evalPath = Join-Path $outDir ("eval_{0}.json" -f $OutputStem)
$plotsDir = Join-Path $outDir "plots"
$csvPath = Join-Path $outDir ("{0}.csv" -f $CsvBaseName)
$xlsxPath = Join-Path $outDir ("{0}.xlsx" -f $CsvBaseName)

$runnerArgs = @(
    "-m", "app.dataset_runner",
    $resolvedDatasetPath,
    "--output-json", $predictionsPath,
    "--print-evaluation",
    "--evaluation-output", $evalPath
)
if ($UseGemini) {
    $runnerArgs += "--use-gemini"
}

python @runnerArgs
python .\scripts\plot_evaluation.py $evalPath --output-dir $plotsDir

$pythonCode = @'
import csv
import json
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
except ModuleNotFoundError as exc:
    raise SystemExit("openpyxl is required to export xlsx. Install it with: python -m pip install openpyxl") from exc

predictions_path = Path(sys.argv[1])
dataset_path = Path(sys.argv[2])
csv_path = Path(sys.argv[3])
xlsx_path = Path(sys.argv[4])

predictions = json.loads(predictions_path.read_text(encoding="utf-8"))["records"]
pred_by_id = {}
for record in predictions:
    predicted = record.get("predicted", {})
    attention_score = predicted.get("attention_score")
    pred_by_id[record["id"]] = {
        "predicted_verdict": predicted.get("verdict", ""),
        "attention_score": "" if attention_score is None else str(int(round(attention_score))),
    }

dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
cases = dataset_payload.get("cases", [])

fieldnames = [
    "id",
    "expected_verdict",
    "analysis_text",
    "expected_domain",
    "predicted_verdict",
    "attention_score",
]

rows = []
for case in cases:
    expected = case.get("expected", {})
    row = {
        "id": case.get("id", ""),
        "expected_verdict": case.get("expected_verdict") or expected.get("verdict", ""),
        "analysis_text": case.get("analysis_text", ""),
        "expected_domain": case.get("expected_domain") or expected.get("domain", ""),
    }
    row.update(pred_by_id.get(case.get("id", ""), {"predicted_verdict": "", "attention_score": ""}))
    rows.append(row)

with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

workbook = Workbook()
sheet = workbook.active
sheet.title = "real_article_dataset"
sheet.append(fieldnames)
for row in rows:
    sheet.append([row[name] for name in fieldnames])
workbook.save(xlsx_path)

print(csv_path)
print(xlsx_path)
'@

$pythonCode | python - $predictionsPath $resolvedDatasetPath $csvPath $xlsxPath

Write-Host ""
Write-Host "saved folder: $outDir"
Write-Host "predictions: $predictionsPath"
Write-Host "evaluation: $evalPath"
Write-Host "plots: $plotsDir"
Write-Host "csv: $csvPath"
Write-Host "xlsx: $xlsxPath"
