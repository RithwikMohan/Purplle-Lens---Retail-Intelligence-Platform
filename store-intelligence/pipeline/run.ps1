# Store Intelligence Pipeline PowerShell Runner

Write-Host "=== Starting Store Intelligence Pipeline ===" -ForegroundColor Green

# 1. Determine Python path
$PythonCmd = "python"
if (Test-Path ".\venv\Scripts\python.exe") {
    $PythonCmd = ".\venv\Scripts\python.exe"
} elseif (Test-Path "..\venv\Scripts\python.exe") {
    $PythonCmd = "..\venv\Scripts\python.exe"
}

Write-Host "Using Python: $PythonCmd"

# 2. Run detection pipeline
Write-Host "Running detection & tracking script against Store 2 videos..." -ForegroundColor Cyan
& $PythonCmd pipeline/detect.py --store_id ST1076 --video_dir "d:\purple_hackathon\Store 2" --output events_output.jsonl --frame_skip 15 --staff_color purple

# 3. Feed events to API
Write-Host "Feeding generated events to local API..." -ForegroundColor Cyan
& $PythonCmd pipeline/feed_to_api.py events_output.jsonl

Write-Host "=== Pipeline execution completed successfully! ===" -ForegroundColor Green
