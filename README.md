# Azure Cloud Monitoring & Observability (Lab)

An Azure observability **portfolio/lab project** for detecting synthetic cloud cost spikes, monitoring simulated Intune compliance, auditing administrative activity, and querying AKS health telemetry.

> **Security:** An earlier revision of `scripts/Generate-CostData.ps1` published a Log Analytics workspace shared key. Treat it as exposed: rotate/revoke the key **before** relying on this repository. Replacing the script in a new commit does not remove secrets from Git history. See `docs/VS_CODE_PUSH_GUIDE.md`.

## What is implemented

- KQL examples for Azure cost, AzureActivity, synthetic Intune checks, and AKS inventory.
- Historical cost anomaly detection from resource/day spending (does not rely on `IsAnomaly`).
- Resource-day baseline using actually observed dates; percentage and absolute threshold.
- Time-zone-aware off-hours activity analysis (`America/Toronto` by default).
- Kubernetes restart counter deltas across snapshots (approximate; resets may undercount).
- Azure Monitor workbook in `dashboards/workbook.json` (refresh embedded queries using the sync script).
- Resource-group ARM template for Log Analytics, a hardened storage account, action group, and **optional** cost alert.
- OAuth-based Python synthetic Intune generator, and OAuth-based PowerShell synthetic cost generator.

## Important scope limits

This project uses **simulated** cost and Intune compliance data; it does not by itself read live Azure Cost Management exports or real Intune tenant data. AKS inventory requires a connected cluster and enabled container collection.

`arm-templates/main.json` creates a baseline workspace, storage account, and action group; the cost alert is **off by default**. It does **not** provision custom log tables, data collection rules/endpoints, diagnostic settings, AKS, Intune integration, or a subscription budget. Configure those separately before uploading data or enabling the alert. The `dashboards/workbook.json` is a workbook **definition**, not an ARM template.

The historical KQL relies on `Date_s` / `DailyCost_d` style fields from older custom log tables, with fallbacks for column names without suffixes. Validate the **actual** DCR and Log Analytics schemas in your subscription.

## Repository files

```text
arm-templates/main.json                     # Real resource-group ARM template
kusto-queries/cost-anomaly-detection.kql     # 12 individually runnable KQL samples
scripts/Generate-CostData.ps1                # OAuth cost data generator (dry-run by default)
scripts/generate_intune_data.py              # Existing Python DCR/DCE compliance generator
scripts/sync_workbook_queries.py             # Synchronize embedded dashboard cost queries
dashboards/workbook.json                     # Existing workbook (update locally)
docs/VS_CODE_PUSH_GUIDE.md                   # Fix and push instructions
docs/VALIDATION.md                           # Verify in Azure before enabling alerts
```

## Getting started (VS Code terminal)

Prerequisites: Azure CLI, PowerShell 7+, Python 3, permissions for Azure deployment and Logs Ingestion, and an existing DCR/DCE plus custom tables for ingestion.

```powershell
az login
az account show
az group show --name azure-monitor-project
az deployment group validate --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
az deployment group what-if --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
# Deploy only after reviewing what-if and the resource names/cost impacts:
az deployment group create --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
```

The default workspace name is `azure-monitor-law`. If an existing workspace is managed through this template, changes to `disableLocalAuth` may disrupt legacy clients; rotate the leaked key and migrate all clients first.

### Synthetic Intune data

```powershell
python -m pip install requests azure-identity
$env:AZURE_DCE_URI="https://YOUR_DCE.REGION.ingest.monitor.azure.com"
$env:AZURE_DCR_IMMUTABLE_ID="dcr-YOUR_IMMUTABLE_ID"
$env:AZURE_DCR_STREAM_NAME="Custom-IntuneCompliance"
python scripts/generate_intune_data.py
```

The existing Python script's required configuration, DCR mappings, and RBAC permissions must match your Azure environment. Verify its stream and target table schema before ingestion.

### Synthetic cost data

```powershell
pwsh -File scripts/Generate-CostData.ps1              # Dry run
$env:AZURE_COST_STREAM_NAME="Custom-AzureCostData"
pwsh -File scripts/Generate-CostData.ps1 -Send        # OAuth ingestion (only after DCR setup)
```

Your signed-in Azure identity needs **Monitoring Metrics Publisher** on the DCR, and the DCR must map the generated fields to `AzureCostData_CL`. The synthetic `IsAnomaly` field is retained only as test ground truth; the KQL does not filter on it.

### Update embedded workbook queries

Run after copying this bundle on top of a clone that contains `dashboards/workbook.json`:

```powershell
python scripts/sync_workbook_queries.py --apply
```

Re-import `dashboards/workbook.json` in the Azure Portal. The workbook still contains hardcoded workspace resource IDs; update those for your subscription. The existing dashboard has five tabs and is not a fully automated deployment.

## Verification and caveats

Run each numbered KQL query separately in Log Analytics. Use `AzureCostData_CL | getschema` and `KubePodInventory | getschema` to check columns.

The 5-minute Azure alert evaluation cadence is **not** a guarantee of 5-minute anomaly detection; ingestion and data availability add latency. Cost estimates depend on actual Azure pricing, region, ingestion, retention, and running workloads. Nothing here has been live-deployed or KQL-executed automatically by the patch author.

See `docs/VALIDATION.md` and `docs/VS_CODE_PUSH_GUIDE.md` for safe deployment, checks, and git commands.
