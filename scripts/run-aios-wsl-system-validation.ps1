param(
    [ValidateSet("Ubuntu-24.04", "Ubuntu")]
    [string]$Distro = "Ubuntu-24.04",

    [ValidateSet("validate", "system-validation", "full")]
    [string]$Stage = "system-validation",

    [switch]$PreflightOnly,

    [switch]$KeepGoing,

    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,

    [string]$OutputPrefix
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $PSBoundParameters.ContainsKey("OutputPrefix")) {
    $OutputPrefix = Join-Path $RepoPath "out\validation\wsl-system-validation"
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-HypervisorPresent {
    try {
        $system = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        return [bool]$system.HypervisorPresent
    }
    catch {
        return $false
    }
}

function Test-CommandAvailable {
    param([string]$Name)

    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Normalize-ExternalText {
    param([string]$Value)

    if ($null -eq $Value) {
        return ""
    }

    return ($Value -replace "`0", "").Trim()
}

function Invoke-ExternalCapture {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $lines = & $FilePath @ArgumentList 2>&1
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    return [pscustomobject]@{
        ExitCode = [int]$exitCode
        Output   = Normalize-ExternalText ((($lines | ForEach-Object { $_.ToString() }) -join "`n"))
    }
}

function Convert-ToWslPath {
    param([string]$WindowsPath)

    $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
    $drive = $fullPath.Substring(0, 1).ToLowerInvariant()
    $suffix = $fullPath.Substring(2).Replace("\", "/")
    return "/mnt/$drive$suffix"
}

function Convert-ToLiteralBashSingleQuoted {
    param([string]$Value)

    return $Value
}

function Invoke-WslBash {
    param(
        [string]$TargetDistro,
        [string]$Command
    )

    return Invoke-ExternalCapture -FilePath "wsl.exe" -ArgumentList @(
        "-d",
        $TargetDistro,
        "--",
        "bash",
        "-lc",
        $Command
    )
}

function Parse-KeyValueLines {
    param([string]$Content)

    $data = [ordered]@{}
    foreach ($line in ($Content -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $data[$parts[0].Trim()] = $parts[1].Trim()
    }

    return $data
}

function Write-JsonReport {
    param(
        [string]$Path,
        [hashtable]$Payload
    )

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    ($Payload | ConvertTo-Json -Depth 8) + "`n" | Set-Content -Path $Path -Encoding UTF8
}

$repoPathResolved = (Resolve-Path $RepoPath).Path
$wslRepoPath = Convert-ToWslPath -WindowsPath $repoPathResolved
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$preflightReportPath = "${OutputPrefix}-preflight.json"
$runLogPath = "${OutputPrefix}-${Stage}.log"
$runReportPath = "${OutputPrefix}-${Stage}.json"

$wslList = Invoke-ExternalCapture -FilePath "wsl.exe" -ArgumentList @("-l", "-q")
$registeredDistros = @(
    ($wslList.Output -replace "`0", "") -split "`r?`n" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)

$dockerVersion = $null
if (Test-CommandAvailable -Name "docker") {
    $dockerVersion = Invoke-ExternalCapture -FilePath "docker" -ArgumentList @("version")
}

$isAdministrator = Test-IsAdministrator
$hypervisorPresent = Get-HypervisorPresent

$preflight = [ordered]@{
    generated_at_utc  = (Get-Date).ToUniversalTime().ToString("o")
    timestamp         = $timestamp
    windows_repo_path = $repoPathResolved
    wsl_repo_path     = $wslRepoPath
    distro            = $Distro
    stage             = $Stage
    preflight_only    = [bool]$PreflightOnly
    host              = [ordered]@{
        is_administrator      = $isAdministrator
        hypervisor_present    = $hypervisorPresent
        wsl_list_exit_code    = $wslList.ExitCode
        wsl_distro_list       = $registeredDistros
        distro_available      = ($registeredDistros -contains $Distro)
        docker_cli_available  = [bool](Test-CommandAvailable -Name "docker")
        docker_engine_ready   = [bool]($dockerVersion -and $dockerVersion.ExitCode -eq 0)
        docker_version_output = if ($dockerVersion) { $dockerVersion.Output } else { "" }
    }
    wsl               = [ordered]@{
        invocation_exit_code = $null
        invocation_ok        = $false
        probe                = [ordered]@{}
        error                = ""
    }
}

if ($preflight.host.distro_available) {
    $quotedRepo = Convert-ToLiteralBashSingleQuoted -Value $wslRepoPath
    $probeLines = @(
        "repo='$quotedRepo'",
        'source "$HOME/.cargo/env" >/dev/null 2>&1 || true',
        'printf ''repo=%s\n'' "$repo"',
        'printf ''repo_ready=%s\n'' "$( [ -d "$repo" ] && [ -f "$repo/scripts/build-aios-image.sh" ] && echo true || echo false )"',
        'printf ''uname=%s\n'' "$(uname -a 2>/dev/null || true)"',
        'printf ''python3=%s\n'' "$(python3 --version 2>/dev/null || true)"',
        'printf ''cargo=%s\n'' "$(cargo --version 2>/dev/null || true)"',
        'printf ''rustc=%s\n'' "$(rustc --version 2>/dev/null || true)"',
        'printf ''qemu=%s\n'' "$(command -v qemu-system-x86_64 2>/dev/null || true)"',
        'printf ''mkosi=%s\n'' "$(command -v mkosi 2>/dev/null || true)"',
        'printf ''docker=%s\n'' "$(docker --version 2>/dev/null || true)"'
    )
    $probeCommand = $probeLines -join "`n"

    $probe = Invoke-WslBash -TargetDistro $Distro -Command $probeCommand
    $preflight.wsl.invocation_exit_code = $probe.ExitCode
    $preflight.wsl.invocation_ok = ($probe.ExitCode -eq 0)
    if ($probe.ExitCode -eq 0) {
        $preflight.wsl.probe = Parse-KeyValueLines -Content $probe.Output
    }
    else {
        $preflight.wsl.error = $probe.Output
    }
}
else {
    $preflight.wsl.error = "distro not found in wsl.exe -l -q output"
}

$preflightBlocked = (
    $preflight.host.wsl_list_exit_code -ne 0 -or
    -not $preflight.host.distro_available -or
    -not $preflight.wsl.invocation_ok -or
    $preflight.wsl.probe["repo_ready"] -ne "true"
)

$preflight["status"] = if ($preflightBlocked) { "blocked" } else { "ready" }
$preflight["preflight_report"] = $preflightReportPath
$preflight["run_report"] = $runReportPath
$preflight["run_log"] = $runLogPath
$hints = @()
if (-not $isAdministrator) {
    $hints += "当前 PowerShell 不是管理员；无法修复 BCD / 可选功能 / Hyper-V 启动项。"
}
if (-not $hypervisorPresent) {
    $hints += "Hyper-V hypervisor 当前未启动；WSL2 / vmcompute 依赖它创建 VM。"
}
if (-not $preflight.host.docker_engine_ready -and $preflight.host.docker_cli_available) {
    $hints += "Docker CLI 存在，但 Linux engine 未启动。"
}
if (-not $preflight.host.distro_available) {
    $hints += "目标发行版当前不可用，或 wsl.exe 枚举发行版失败。"
}
$preflight["hints"] = $hints

Write-JsonReport -Path $preflightReportPath -Payload $preflight
Write-Output ($preflight | ConvertTo-Json -Depth 8)

if ($PreflightOnly) {
    exit 0
}

if ($preflightBlocked) {
    throw "WSL preflight is blocked; inspect $preflightReportPath"
}

$keepGoingArg = ""
if ($KeepGoing) {
    $keepGoingArg = " --keep-going"
}

$quotedRepo = Convert-ToLiteralBashSingleQuoted -Value $wslRepoPath
$runLines = @(
    'set -e',
    "cd '$quotedRepo'",
    'source "$HOME/.cargo/env" >/dev/null 2>&1 || true',
    "python3 scripts/run-aios-ci-local.py --stage $Stage$keepGoingArg"
)
$runCommand = $runLines -join "`n"

$run = Invoke-WslBash -TargetDistro $Distro -Command $runCommand
$runOutput = $run.Output
if (-not [string]::IsNullOrWhiteSpace($runOutput)) {
    $parent = Split-Path -Parent $runLogPath
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $runOutput + "`n" | Set-Content -Path $runLogPath -Encoding UTF8
    Write-Output $runOutput
}

$runReport = [ordered]@{
    generated_at_utc  = (Get-Date).ToUniversalTime().ToString("o")
    timestamp         = $timestamp
    distro            = $Distro
    stage             = $Stage
    windows_repo_path = $repoPathResolved
    wsl_repo_path     = $wslRepoPath
    keep_going        = [bool]$KeepGoing
    command           = "python3 scripts/run-aios-ci-local.py --stage $Stage$keepGoingArg"
    exit_code         = $run.ExitCode
    status            = if ($run.ExitCode -eq 0) { "passed" } else { "failed" }
    log_path          = $runLogPath
    preflight_report  = $preflightReportPath
}

Write-JsonReport -Path $runReportPath -Payload $runReport
exit $run.ExitCode

