$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "PostgreSQL Password Recovery - Do Not Close"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $workspaceRoot ".env"
$runtimePath = Join-Path $workspaceRoot ".runtime"
$markerPath = Join-Path $runtimePath "postgres-password-reset.flag"
$errorLogPath = Join-Path $runtimePath "postgres-password-reset-error.log"
$dataPath = "D:\DevTools\PostgreSQLData"
$hbaPath = Join-Path $dataPath "pg_hba.conf"
$serviceName = "postgresql-x64-18"
$pythonPath = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$resetHelper = Join-Path $workspaceRoot "scripts\set_postgres_password.py"
$connectionTest = Join-Path $workspaceRoot "scripts\test_doradb_connection.py"

function ConvertTo-DotEnvValue {
    param([Parameter(Mandatory = $true)][string]$Value)

    $singleLine = $Value.Replace("`r", "").Replace("`n", "")
    $escaped = $singleLine.Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $replacement = "$Name=$(ConvertTo-DotEnvValue -Value $Value)"
    for ($index = 0; $index -lt $script:envLines.Count; $index++) {
        if ($script:envLines[$index] -match "^$([regex]::Escape($Name))=") {
            $script:envLines[$index] = $replacement
            return
        }
    }
    $script:envLines.Add($replacement)
}

function Restart-Postgres {
    Restart-Service -Name $serviceName -Force
    (Get-Service -Name $serviceName).WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(25)
    )
}

if (Test-Path -LiteralPath $markerPath) {
    Remove-Item -LiteralPath $markerPath
}
if (Test-Path -LiteralPath $errorLogPath) {
    Remove-Item -LiteralPath $errorLogPath
}

Clear-Host
Write-Host "PostgreSQL 18 password recovery" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor DarkCyan
Write-Host "This will reset only the local 'postgres' role password."
Write-Host "Authentication will be restored to scram-sha-256 automatically."
Write-Host "Do not close this window while the recovery is running." -ForegroundColor Yellow
Write-Host ""

do {
    $firstSecure = Read-Host "New postgres password (typing is hidden)" -AsSecureString
    $firstPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($firstSecure)
    try {
        $newPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($firstPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($firstPointer)
    }

    $secondSecure = Read-Host "Confirm new password (typing is hidden)" -AsSecureString
    $secondPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secondSecure)
    try {
        $confirmedPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secondPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secondPointer)
    }

    if ([string]::IsNullOrEmpty($newPassword)) {
        Write-Host "Password cannot be empty." -ForegroundColor Red
    }
    elseif ($newPassword -ne $confirmedPassword) {
        Write-Host "Passwords did not match. Try again." -ForegroundColor Red
        $newPassword = $null
        $confirmedPassword = $null
    }
} while ([string]::IsNullOrEmpty($newPassword))

$originalHba = [IO.File]::ReadAllText($hbaPath)
$backupPath = "$hbaPath.codex-backup-$([DateTime]::Now.ToString('yyyyMMdd-HHmmss'))"
[IO.File]::WriteAllText($backupPath, $originalHba, [Text.UTF8Encoding]::new($false))
$trustEnabled = $false

try {
    Write-Host ""
    Write-Host "Opening a localhost-only recovery window..." -ForegroundColor Cyan
    $trustRules = @"
# Temporary Codex recovery rule - removed automatically
host    all    postgres    127.0.0.1/32    trust
host    all    postgres    ::1/128         trust

"@
    [IO.File]::WriteAllText(
        $hbaPath,
        $trustRules + $originalHba,
        [Text.UTF8Encoding]::new($false)
    )
    $trustEnabled = $true
    Restart-Postgres

    $env:DORA_NEW_POSTGRES_PASSWORD = $newPassword
    & $pythonPath $resetHelper
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL did not accept the password-reset command."
    }
    Write-Host "Password reset completed." -ForegroundColor Green
}
catch {
    [IO.File]::WriteAllText(
        $errorLogPath,
        $_.Exception.Message,
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host ""
    Write-Host "Password recovery failed: $($_.Exception.Message)" -ForegroundColor Red
    throw
}
finally {
    Remove-Item Env:\DORA_NEW_POSTGRES_PASSWORD -ErrorAction SilentlyContinue
    if ($trustEnabled) {
        Write-Host "Restoring scram-sha-256 authentication..." -ForegroundColor Cyan
        [IO.File]::WriteAllText(
            $hbaPath,
            $originalHba,
            [Text.UTF8Encoding]::new($false)
        )
        Restart-Postgres
    }
}

$script:envLines = [System.Collections.Generic.List[string]]::new()
$script:envLines.AddRange([string[]][IO.File]::ReadAllLines($envPath))
Set-DotEnvValue -Name "DORADB_USER" -Value "postgres"
Set-DotEnvValue -Name "DORADB_PASSWORD" -Value $newPassword
[IO.File]::WriteAllLines($envPath, $script:envLines, [Text.UTF8Encoding]::new($false))

$newPassword = $null
$confirmedPassword = $null
$firstSecure.Dispose()
$secondSecure.Dispose()

Write-Host "Validating secure DoraDB login..." -ForegroundColor Cyan
& $pythonPath $connectionTest
if ($LASTEXITCODE -ne 0) {
    $message = "The reset completed, but the secure DoraDB validation failed."
    [IO.File]::WriteAllText(
        $errorLogPath,
        $message,
        [Text.UTF8Encoding]::new($false)
    )
    throw $message
}

[IO.File]::WriteAllText(
    $markerPath,
    [DateTimeOffset]::Now.ToString("O"),
    [Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "SUCCESS: PostgreSQL password reset and DoraDB login validated." -ForegroundColor Green
Write-Host "Secure scram-sha-256 authentication has been restored." -ForegroundColor Green
Write-Host "Return to Codex and say: done" -ForegroundColor Yellow
Read-Host "Press Enter to close this window"
