$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Switching to Docker DoraDB - Administrator"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runtimePath = Join-Path $workspaceRoot ".runtime"
$markerPath = Join-Path $runtimePath "docker-doradb-switched.flag"
$errorPath = Join-Path $runtimePath "docker-doradb-switch-error.log"
$dockerPath = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$serviceName = "postgresql-x64-18"

if (Test-Path -LiteralPath $markerPath) {
    Remove-Item -LiteralPath $markerPath
}
if (Test-Path -LiteralPath $errorPath) {
    Remove-Item -LiteralPath $errorPath
}

try {
    Write-Host "Stopping the empty Windows PostgreSQL service..." -ForegroundColor Cyan
    $service = Get-Service -Name $serviceName
    if ($service.Status -ne "Stopped") {
        Stop-Service -Name $serviceName -Force
        (Get-Service -Name $serviceName).WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Stopped,
            [TimeSpan]::FromSeconds(25)
        )
    }

    Write-Host "Starting the Docker DoraDB container..." -ForegroundColor Cyan
    $running = & $dockerPath inspect -f "{{.State.Running}}" DoraDB
    if ($running -ne "true") {
        & $dockerPath start DoraDB | Out-Null
    }

    & (Join-Path $PSHOME "powershell.exe") `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File (Join-Path $workspaceRoot "scripts\configure-from-docker.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The Docker credential configuration step failed."
    }

    [IO.File]::WriteAllText(
        $markerPath,
        [DateTimeOffset]::Now.ToString("O"),
        [Text.UTF8Encoding]::new($false)
    )

    Write-Host ""
    Write-Host "SUCCESS: Docker DoraDB now owns port 5432." -ForegroundColor Green
    Write-Host "Return to Codex and say: done" -ForegroundColor Yellow
}
catch {
    [IO.File]::WriteAllText(
        $errorPath,
        $_.Exception.Message,
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host ""
    Write-Host "The switch failed: $($_.Exception.Message)" -ForegroundColor Red
}

Read-Host "Press Enter to close this window"
