# Generate-CostData.ps1
# Synthetic lab data, sent via Azure Monitor Logs Ingestion API (OAuth).
# NO workspace shared keys; rotate/remove any previously committed keys!
# Requires: PowerShell 7+, Azure CLI login, configured DCR/DCE, RBAC.
# The DCR stream must accept the fields below and map them into AzureCostData_CL.
[CmdletBinding()]
param(
    [ValidateRange(7,365)][int]$DaysToGenerate = 30,
    [ValidateRange(1,1000)][int]$BatchSize = 100,
    [switch]$Send
)
$ErrorActionPreference = 'Stop'

$resources = @(
    @{ Name='vm-prod-001';         Type='Virtual Machine'; BaseCost=45.00 },
    @{ Name='vm-prod-002';         Type='Virtual Machine'; BaseCost=45.00 },
    @{ Name='sql-prod-db';         Type='SQL Database';    BaseCost=30.00 },
    @{ Name='stmonitorproject';    Type='Storage Account'; BaseCost=2.00 },
    @{ Name='law-monitor-project'; Type='Log Analytics';   BaseCost=5.00 },
    @{ Name='app-service-prod';    Type='App Service';     BaseCost=20.00 },
    @{ Name='vnet-prod-001';       Type='Virtual Network'; BaseCost=1.00 }
)
$records = [System.Collections.Generic.List[object]]::new()
$today = [DateTime]::UtcNow.Date
for ($dayOffset = $DaysToGenerate - 1; $dayOffset -ge 0; $dayOffset--) {
    $day = $today.AddDays(-$dayOffset)
    foreach ($resource in $resources) {
        $variance = Get-Random -Minimum -5 -Maximum 15
        $amount = [Math]::Max(0, [double]$resource.BaseCost + $variance)
        # Spike 9 days ago so historical detection must find it on its own.
        $testSpike = $dayOffset -eq 9
        if ($testSpike) { $amount *= 2.5 }
        $records.Add([PSCustomObject]@{
            TimeGenerated = $day.ToString("yyyy-MM-ddTHH:mm:ssZ")
            Date = $day.ToString("yyyy-MM-dd")
            ResourceName = $resource.Name
            ResourceType = $resource.Type
            DailyCost = [Math]::Round($amount, 2)
            Currency = 'CAD'
            ResourceGroup = 'rg-azure-monitor-project'
            IsAnomaly = $testSpike  # ground truth for tests; detection MUST ignore it
            SubscriptionName = 'Synthetic Demo'
        })
    }
}
Write-Host "Generated $($records.Count) synthetic cost observations." -ForegroundColor Cyan
if (-not $Send) {
    Write-Host "DRY RUN: no Azure ingestion. Re-run with -Send after configuring DCR/DCE." -ForegroundColor Yellow
    return
}

$dce = $env:AZURE_DCE_URI
$dcr = $env:AZURE_DCR_IMMUTABLE_ID
$stream = if ($env:AZURE_COST_STREAM_NAME) { $env:AZURE_COST_STREAM_NAME } else { 'Custom-AzureCostData' }
if ([string]::IsNullOrWhiteSpace($dce) -or [string]::IsNullOrWhiteSpace($dcr)) {
    throw "Set AZURE_DCE_URI and AZURE_DCR_IMMUTABLE_ID first."
}
if ($dce -notmatch '^https://[a-zA-Z0-9.-]+/?$') {
    throw "AZURE_DCE_URI must be an HTTPS endpoint without a path (optional trailing slash)."
}
if ($dcr -notmatch '^dcr-[a-zA-Z0-9-]+$') {
    throw "Invalid DCR immutable ID; expected dcr-..."
}
if ($stream -notmatch '^[a-zA-Z0-9_-]+$') {
    throw "Invalid stream name."
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required. Run az login before -Send."
}
$token = (& az account get-access-token --resource 'https://monitor.azure.com/' --query accessToken -o tsv)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
    throw "Azure CLI token unavailable. Run az login and check DCR RBAC."
}
$endpoint = $dce.TrimEnd('/')
$uri = "$endpoint/dataCollectionRules/$dcr/streams/$stream" + '?api-version=2023-01-01'
$headers = @{ Authorization = "Bearer $token" }
for ($offset=0; $offset -lt $records.Count; $offset += $BatchSize) {
    $count = [Math]::Min($BatchSize, $records.Count - $offset)
    $batch = $records.GetRange($offset, $count).ToArray()
    # Force array JSON for all batch sizes including a one-record final batch.
    $body = ConvertTo-Json -InputObject $batch -Depth 8 -Compress
    $null = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers `
        -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
        -ContentType 'application/json' -TimeoutSec 60
    Write-Host "Submitted $count records (offset $offset)." -ForegroundColor Green
}
Write-Host "Done. Verify ingestion and the DCR output column schema in Log Analytics." -ForegroundColor Green
