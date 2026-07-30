$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "DoraDB Credentials - Enter Here"

trap {
    $errorMessage = $_.Exception.Message
    $errorPath = Join-Path (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path ".runtime\doradb-config-error.log"
    [IO.File]::WriteAllText($errorPath, $errorMessage, [Text.UTF8Encoding]::new($false))
    Write-Host ""
    Write-Host "The credentials were not saved:" -ForegroundColor Red
    Write-Host $errorMessage -ForegroundColor Red
    Read-Host "Press Enter to close this window"
    break
}

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $workspaceRoot ".env"
$markerPath = Join-Path $workspaceRoot ".runtime\doradb-configured.flag"
$errorLogPath = Join-Path $workspaceRoot ".runtime\doradb-config-error.log"
if (Test-Path -LiteralPath $markerPath) {
    Remove-Item -LiteralPath $markerPath
}
if (Test-Path -LiteralPath $errorLogPath) {
    Remove-Item -LiteralPath $errorLogPath
}

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

Clear-Host
Write-Host "DORA Intelligence - DoraDB Login" -ForegroundColor Cyan
Write-Host "---------------------------------" -ForegroundColor DarkCyan
Write-Host "Target: PostgreSQL doradb at 127.0.0.1:5432 (project DCPM)"
Write-Host ""

$databaseUser = (Read-Host "PostgreSQL username [postgres]").Trim()
if ([string]::IsNullOrWhiteSpace($databaseUser)) {
    $databaseUser = "postgres"
}

do {
    $securePassword = Read-Host "DoraDB password (typing is hidden)" -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $databasePassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
} while ([string]::IsNullOrEmpty($databasePassword))

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "The .env file was not found at $envPath"
}

$script:envLines = [System.Collections.Generic.List[string]]::new()
$script:envLines.AddRange([string[]][IO.File]::ReadAllLines($envPath))
Set-DotEnvValue -Name "DORADB_USER" -Value $databaseUser
Set-DotEnvValue -Name "DORADB_PASSWORD" -Value $databasePassword
[IO.File]::WriteAllLines($envPath, $script:envLines, [Text.UTF8Encoding]::new($false))

$databasePassword = $null
$securePassword.Dispose()
$savedLines = [IO.File]::ReadAllLines($envPath)
if (-not ($savedLines -match '^DORADB_USER=".+"$')) {
    throw "The username could not be verified after saving."
}
if (-not ($savedLines -match '^DORADB_PASSWORD=".+"$')) {
    throw "The password could not be verified after saving."
}

Write-Host ""
Write-Host "Testing the read-only DoraDB login..." -ForegroundColor Cyan
& (Join-Path $workspaceRoot ".venv\Scripts\python.exe") `
    (Join-Path $workspaceRoot "scripts\test_doradb_connection.py")
if ($LASTEXITCODE -ne 0) {
    throw (
        "PostgreSQL rejected this login. Use a PostgreSQL role (usually " +
        "'postgres'), not the Windows username, and enter that role's password."
    )
}

[IO.File]::WriteAllText(
    $markerPath,
    [DateTimeOffset]::Now.ToString("O"),
    [Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "Credentials saved securely to the local .env file." -ForegroundColor Green
Write-Host "You must see this green success message before returning to Codex." -ForegroundColor Green
Write-Host "Return to Codex and say: done" -ForegroundColor Yellow
Read-Host "Press Enter to close this window"
