$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[1/3] Criando ambiente Python..." -ForegroundColor Cyan
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv .venv
    } else {
        python -m venv .venv
    }
}
Write-Host "[2/3] Conferindo dependencias..." -ForegroundColor Cyan
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falha na instalacao das dependencias." }
$Url = "http://127.0.0.1:8000"
Write-Host "[3/3] Iniciando Radar em $Url" -ForegroundColor Green
$Server = Start-Process -FilePath $Python -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000') -PassThru -NoNewWindow
try {
    $Ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($Server.HasExited) { throw "O servidor fechou antes de iniciar. Verifique se a porta 8000 ja esta em uso." }
        try {
            $Response = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2
            if ($Response.status -eq 'ok') { $Ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw "A API nao respondeu. Verifique mensagens de erro acima." }
    Write-Host "Radar carregado. Abrindo navegador em $Url" -ForegroundColor Green
    Start-Process $Url
    Write-Host "Mantenha esta janela aberta. Para fechar o Radar, pressione Ctrl+C." -ForegroundColor Yellow
    Wait-Process -Id $Server.Id
} finally {
    if (-not $Server.HasExited) { Stop-Process -Id $Server.Id -Force }
}
