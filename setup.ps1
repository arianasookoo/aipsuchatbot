# One-time setup on Windows: venv, deps, index, model choice, .env. Safe to re-run.
# Usage (PowerShell, from the repo folder):  .\setup.ps1
# If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
$py = ".venv\Scripts\python.exe"
& $py -m pip install --quiet chromadb==1.5.9 -r requirements-dev.txt
if (-not (Test-Path "vector_db\active_index.json")) { & $py vector_search.py index chunks.json }
& $py answer.py --selfcheck
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }

$hasGpu = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
$hasOllama = [bool](Get-Command ollama -ErrorAction SilentlyContinue)
$envText = Get-Content .env -Raw
if ($hasOllama -and $envText -notmatch "(?m)^NAVIGATOR_LLM_MODEL=") {
    $model = if ($hasGpu) { "gemma3:12b" } else { "gemma3:4b" }
    Write-Host "Ollama found. Pulling $model (GPU: $hasGpu)..."
    ollama pull $model
    Add-Content .env "`nNAVIGATOR_LLM_BASE=http://127.0.0.1:11434/v1`nNAVIGATOR_LLM_KEY=ollama`nNAVIGATOR_LLM_MODEL=$model"
    if (-not $hasGpu) { Write-Host "No NVIDIA GPU: gemma3:4b runs on CPU, ~15-25 s per answer. Its citation rate is not measured yet (run eval\run_answers.py then eval\claims.py to measure)." }
} elseif (-not $hasOllama -and $envText -notmatch "(?m)^NVIDIA_API_KEY=\S") {
    Write-Host "No Ollama installed. Either install it from https://ollama.com and re-run, or put a free key from https://build.nvidia.com into .env as NVIDIA_API_KEY=..."
}

Write-Host ""
Write-Host "Setup done. Start the server with:"
Write-Host "    .venv\Scripts\python.exe serve.py"
Write-Host "then open http://localhost:8008/app.html"
