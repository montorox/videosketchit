$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$webRoot = Join-Path $root "web"
$legacyStateDir = Join-Path $root ".cs-board-codex"
$stateDir = Join-Path $root ".videosketchit"
$launcherErrorLog = Join-Path $stateDir "launcher-error.log"
$backendOutputLog = Join-Path $stateDir "backend-output.log"
$backendErrorLog = Join-Path $stateDir "backend-error.log"
$frontendOutputLog = Join-Path $stateDir "frontend-output.log"
$frontendErrorLog = Join-Path $stateDir "frontend-error.log"
$expectedPipelineVersion = "videosketchit_v10_codex_provider"
$backendUpdateDeferred = $false

if ((Test-Path -LiteralPath $legacyStateDir) -and -not (Test-Path -LiteralPath $stateDir)) {
    Move-Item -LiteralPath $legacyStateDir -Destination $stateDir
}
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Remove-Item -LiteralPath $launcherErrorLog -Force -ErrorAction SilentlyContinue

function Test-BackendReady {
    if ($script:backendUpdateDeferred) {
        return $true
    }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:18775/api/health" -TimeoutSec 2
        return $health.pipeline_version -eq $expectedPipelineVersion
    } catch {
        return $false
    }
}

function Stop-StaleBackend {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:18775/api/health" -TimeoutSec 2
        if ($health.pipeline_version -eq $expectedPipelineVersion) {
            return
        }
        $jobs = Invoke-RestMethod "http://127.0.0.1:18775/api/jobs?limit=100" -TimeoutSec 3
        $busyJobs = @($jobs.items | Where-Object { $_.status -eq "running" -or $_.status -eq "queued" })
        if ($busyJobs.Count -gt 0) {
            $script:backendUpdateDeferred = $true
            Write-Host "A video is still being generated. The pipeline upgrade is deferred to protect it." -ForegroundColor Yellow
            return
        }
        $listener = Get-NetTCPConnection -LocalPort 18775 -State Listen -ErrorAction Stop
        if ($listener.OwningProcess) {
            Write-Host "An older video pipeline is running. Restarting it..." -ForegroundColor Yellow
            Stop-Process -Id $listener.OwningProcess -Force
            Start-Sleep -Milliseconds 700
        }
    } catch {
        # No responding stale backend; the normal startup path handles this.
    }
}

function Test-FrontendReady {
    try {
        Invoke-WebRequest "http://127.0.0.1:13010" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

try {
    $lanAddress = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
        Select-Object -ExpandProperty IPv4Address |
        Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)' } |
        Select-Object -First 1 -ExpandProperty IPAddress

    Write-Host "Starting VideoSketchIt..." -ForegroundColor Cyan
    Write-Host "Local URL: http://127.0.0.1:13010"
    if ($lanAddress) {
        Write-Host "LAN URL: http://${lanAddress}:13010" -ForegroundColor Green
    }

    Stop-StaleBackend
    if (Test-BackendReady) {
        if ($backendUpdateDeferred) {
            Write-Host "Backend is busy; run this launcher again after the current task finishes to load the upgrade." -ForegroundColor Yellow
        } else {
            Write-Host "Backend is already running." -ForegroundColor DarkGray
        }
    } else {
        Remove-Item -LiteralPath $backendOutputLog, $backendErrorLog -Force -ErrorAction SilentlyContinue
        Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "webapp.server:app", "--host", "127.0.0.1", "--port", "18775" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $backendOutputLog -RedirectStandardError $backendErrorLog
    }

    if (Test-FrontendReady) {
        Write-Host "Frontend is already running." -ForegroundColor DarkGray
    } else {
        Remove-Item -LiteralPath $frontendOutputLog, $frontendErrorLog -Force -ErrorAction SilentlyContinue
        Start-Process -FilePath "npm.cmd" -ArgumentList "run", "start" -WorkingDirectory $webRoot -WindowStyle Hidden -RedirectStandardOutput $frontendOutputLog -RedirectStandardError $frontendErrorLog
    }

    $backendReady = $false
    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $backendReady = Test-BackendReady
        $frontendReady = Test-FrontendReady
        if ($backendReady -and $frontendReady) {
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $backendReady) {
        throw "Backend failed to start. See .videosketchit\backend-error.log."
    }
    if (-not $frontendReady) {
        throw "Frontend failed to start. See .videosketchit\frontend-error.log."
    }

    Write-Host "Ready. Opening the browser..." -ForegroundColor Green
    Start-Process "http://127.0.0.1:13010"
} catch {
    $message = "{0}`r`n{1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $_.Exception.Message
    Set-Content -LiteralPath $launcherErrorLog -Value $message -Encoding UTF8
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
