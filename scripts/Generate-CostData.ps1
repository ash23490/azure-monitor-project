# ============================================
# Generate-CostData.ps1
# Generates synthetic Azure cost data and
# pushes it to Log Analytics Workspace
# ============================================

# ---- CONFIGURATION ---- #
$WorkspaceId = "56534bda-6d47-43e0-9a84-a17d8d0ada9e"
$WorkspaceKey = "L1cFYS7Qe4ipYy7l/IMZ4h2OJ9HBeNu0+XE4h5GyPiy4QjlC10oK+OPZqbwgC02GAur3oeFIXYKgQPGu/HpCBw=="
$LogType = "AzureCostData"
$DaysToGenerate = 30

# ---- RESOURCE TYPES TO SIMULATE ---- #
$Resources = @(
    @{ Name = "vm-prod-001";        Type = "Virtual Machine";    BaseCost = 45.00  },
    @{ Name = "vm-prod-002";        Type = "Virtual Machine";    BaseCost = 45.00  },
    @{ Name = "sql-prod-db";        Type = "SQL Database";       BaseCost = 30.00  },
    @{ Name = "stmonitorproject";   Type = "Storage Account";    BaseCost = 2.00   },
    @{ Name = "law-monitor-project";Type = "Log Analytics";      BaseCost = 5.00   },
    @{ Name = "app-service-prod";   Type = "App Service";        BaseCost = 20.00  },
    @{ Name = "vnet-prod-001";      Type = "Virtual Network";    BaseCost = 1.00   }
)

# ---- FUNCTION TO BUILD SIGNATURE ---- #
Function Build-Signature {
    param(
        [string]$WorkspaceId,
        [string]$WorkspaceKey,
        [string]$Date,
        [int]$ContentLength,
        [string]$Method,
        [string]$ContentType,
        [string]$Resource
    )

    $xHeaders       = "x-ms-date:" + $Date
    $stringToHash   = $Method + "`n" + $ContentLength + "`n" + $ContentType + "`n" + $xHeaders + "`n" + $Resource
    $bytesToHash    = [Text.Encoding]::UTF8.GetBytes($stringToHash)
    $keyBytes       = [Convert]::FromBase64String($WorkspaceKey)
    $sha256         = New-Object System.Security.Cryptography.HMACSHA256
    $sha256.Key     = $keyBytes
    $calculatedHash = $sha256.ComputeHash($bytesToHash)
    $encodedHash    = [Convert]::ToBase64String($calculatedHash)
    $authorization  = 'SharedKey {0}:{1}' -f $WorkspaceId, $encodedHash
    return $authorization
}

# ---- FUNCTION TO SEND DATA TO LOG ANALYTICS ---- #
Function Send-LogAnalyticsData {
    param(
        [string]$WorkspaceId,
        [string]$WorkspaceKey,
        [string]$Body,
        [string]$LogType
    )

    $method         = "POST"
    $contentType    = "application/json"
    $resource       = "/api/logs"
    $rfc1123date    = [DateTime]::UtcNow.ToString("r")
    $contentLength  = $Body.Length
    $signature      = Build-Signature `
                        -WorkspaceId $WorkspaceId `
                        -WorkspaceKey $WorkspaceKey `
                        -Date $rfc1123date `
                        -ContentLength $contentLength `
                        -Method $method `
                        -ContentType $contentType `
                        -Resource $resource

    $uri     = "https://" + $WorkspaceId + ".ods.opinsights.azure.com" + $resource + "?api-version=2016-04-01"
    $headers = @{
        "Authorization" = $signature
        "Log-Type"      = $LogType
        "x-ms-date"     = $rfc1123date
    }

    $response = Invoke-WebRequest -Uri $uri -Method $method -ContentType $contentType -Headers $headers -Body $Body
    return $response.StatusCode
}

# ---- GENERATE SYNTHETIC COST DATA ---- #
Write-Host "Generating $DaysToGenerate days of synthetic cost data..." -ForegroundColor Cyan

$CostRecords = @()
$StartDate   = (Get-Date).AddDays(-$DaysToGenerate)

for ($i = 0; $i -lt $DaysToGenerate; $i++) {
    $CurrentDate = $StartDate.AddDays($i)

    foreach ($Resource in $Resources) {
        # Add random variance to base cost
        $Variance    = Get-Random -Minimum -5 -Maximum 15
        $DailyCost   = [Math]::Round($Resource.BaseCost + $Variance, 2)

        # Simulate a cost spike on day 20
        if ($i -eq 20) {
            $DailyCost = [Math]::Round($DailyCost * 2.5, 2)
            $IsAnomaly = $true
        } else {
            $IsAnomaly = $false
        }

        $CostRecords += [PSCustomObject]@{
            Date             = $CurrentDate.ToString("yyyy-MM-dd")
            ResourceName     = $Resource.Name
            ResourceType     = $Resource.Type
            DailyCost        = $DailyCost
            Currency         = "CAD"
            ResourceGroup    = "rg-azure-monitor-project"
            IsAnomaly        = $IsAnomaly
            SubscriptionName = "Free Subscription"
        }
    }
}

# ---- SEND DATA TO LOG ANALYTICS ---- #
Write-Host "Sending data to Log Analytics..." -ForegroundColor Cyan

$Body       = $CostRecords | ConvertTo-Json
$StatusCode = Send-LogAnalyticsData `
                -WorkspaceId $WorkspaceId `
                -WorkspaceKey $WorkspaceKey `
                -Body $Body `
                -LogType $LogType

if ($StatusCode -eq 200) {
    Write-Host "Success! $($CostRecords.Count) records sent to Log Analytics." -ForegroundColor Green
} else {
    Write-Host "Something went wrong. Status code: $StatusCode" -ForegroundColor Red
}
