$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $workspaceRoot ".env"
$markerPath = Join-Path $workspaceRoot ".runtime\docker-doradb-configured.flag"

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

$container = (docker inspect DoraDB | ConvertFrom-Json)[0]
$containerEnvironment = @{}
foreach ($entry in $container.Config.Env) {
    $parts = $entry -split "=", 2
    if ($parts.Count -eq 2) {
        $containerEnvironment[$parts[0]] = $parts[1]
    }
}

$databaseName = $containerEnvironment["POSTGRES_DB"]
if ([string]::IsNullOrWhiteSpace($databaseName)) {
    $databaseName = "postgres"
}
$databaseUser = $containerEnvironment["POSTGRES_USER"]
if ([string]::IsNullOrWhiteSpace($databaseUser)) {
    $databaseUser = "postgres"
}
$databasePassword = $containerEnvironment["POSTGRES_PASSWORD"]
if ([string]::IsNullOrWhiteSpace($databasePassword)) {
    throw "The DoraDB container does not have a POSTGRES_PASSWORD value."
}

$script:envLines = [System.Collections.Generic.List[string]]::new()
$script:envLines.AddRange([string[]][IO.File]::ReadAllLines($envPath))
Set-DotEnvValue -Name "DORADB_HOST" -Value "127.0.0.1"
Set-DotEnvValue -Name "DORADB_PORT" -Value "5432"
Set-DotEnvValue -Name "DORADB_NAME" -Value $databaseName
Set-DotEnvValue -Name "DORADB_USER" -Value $databaseUser
Set-DotEnvValue -Name "DORADB_PASSWORD" -Value $databasePassword
[IO.File]::WriteAllLines($envPath, $script:envLines, [Text.UTF8Encoding]::new($false))

$databasePassword = $null
[IO.File]::WriteAllText(
    $markerPath,
    [DateTimeOffset]::Now.ToString("O"),
    [Text.UTF8Encoding]::new($false)
)

Write-Output "DoraDB container credentials were written to .env without displaying them."
Write-Output "Configured database: $databaseName"
