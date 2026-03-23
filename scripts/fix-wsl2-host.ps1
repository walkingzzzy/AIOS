param(
    [switch]$EnableHyperV
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Normalize-ExternalText {
    param([string]$Value)

    if ($null -eq $Value) {
        return ""
    }

    return ($Value -replace "`0", "").Trim()
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-FeatureEnabled {
    param([string]$FeatureName)

    $feature = Get-WindowsOptionalFeature -Online -FeatureName $FeatureName
    if ($feature.State -eq "Enabled") {
        return [pscustomobject]@{
            FeatureName = $FeatureName
            Changed = $false
            RestartNeeded = $false
            State = $feature.State.ToString()
        }
    }

    $result = Enable-WindowsOptionalFeature -Online -FeatureName $FeatureName -All -NoRestart
    $featureAfter = Get-WindowsOptionalFeature -Online -FeatureName $FeatureName
    $restartNeeded = $false
    if ($null -ne $result -and $null -ne $result.PSObject.Properties["RestartNeeded"]) {
        $restartNeeded = [bool]$result.RestartNeeded
    }

    return [pscustomobject]@{
        FeatureName = $FeatureName
        Changed = $true
        RestartNeeded = $restartNeeded
        State = $featureAfter.State.ToString()
    }
}

function Ensure-ServiceRunning {
    param([string]$ServiceName)

    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        return [pscustomobject]@{
            Name = $ServiceName
            Exists = $false
            Running = $false
        }
    }

    if ($service.Status -ne "Running") {
        Start-Service -Name $ServiceName -ErrorAction Stop
        $service = Get-Service -Name $ServiceName
    }

    return [pscustomobject]@{
        Name = $ServiceName
        Exists = $true
        Running = ($service.Status -eq "Running")
    }
}

if (-not (Test-IsAdministrator)) {
    throw "This script must be run from an elevated PowerShell session."
}

$featureNames = @(
    "Microsoft-Windows-Subsystem-Linux",
    "VirtualMachinePlatform",
    "HypervisorPlatform"
)

if ($EnableHyperV) {
    $featureNames += "Microsoft-Hyper-V-All"
}

$featureResults = @()
$restartNeeded = $false
foreach ($featureName in $featureNames) {
    $result = Ensure-FeatureEnabled -FeatureName $featureName
    $featureResults += $result
    if ($result.RestartNeeded) {
        $restartNeeded = $true
    }
}

$bcdOutput = & "$env:SystemRoot\System32\bcdedit.exe" /set hypervisorlaunchtype auto 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set hypervisorlaunchtype=auto. Output: $bcdOutput"
}

$serviceResults = @()
foreach ($serviceName in @("vmcompute", "LxssManager")) {
    try {
        $serviceResults += Ensure-ServiceRunning -ServiceName $serviceName
    }
    catch {
        $serviceResults += [pscustomobject]@{
            Name = $serviceName
            Exists = $true
            Running = $false
            Error = $_.Exception.Message
        }
    }
}

$wslVersion = & wsl.exe --version 2>&1
$wslStatus = & wsl.exe --status 2>&1

$report = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    restart_needed = $restartNeeded
    features = $featureResults
    services = $serviceResults
    bcdedit = Normalize-ExternalText (($bcdOutput | Out-String))
    wsl_version = Normalize-ExternalText (($wslVersion | Out-String))
    wsl_status = Normalize-ExternalText (($wslStatus | Out-String))
}

$reportPath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "out\validation\fix-wsl2-host-report.json"
$reportDir = Split-Path -Parent $reportPath
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}
($report | ConvertTo-Json -Depth 8) + "`n" | Set-Content -Path $reportPath -Encoding UTF8

Write-Output ($report | ConvertTo-Json -Depth 8)
if ($restartNeeded) {
    Write-Output "A reboot is required before WSL2 can be validated again."
}
