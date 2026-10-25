# Technical validation checklist (run in YOUR Azure environment)

These fixes were prepared from the public repository and documentation. They were **not executed** in the user's Azure tenant or GitHub repository.

## ARM
- Validate template with `az deployment group validate` in your resource group.
- Inspect `az deployment group what-if` for an existing workspace and storage account before deployment.
- Default cost alert is not deployed. The template creates only workspace, storage account, action group, optional alert.
- This is NOT a full deploy of DCE, DCR, custom tables, AKS, diagnostics, or a budget.
- Make sure disabling workspace local authentication will not break another application.
- Storage account names are globally unique; change `storageAccountName` if Azure says taken.

## Data schema (Log Analytics)
```kusto
AzureCostData_CL | getschema
IntuneComplianceData_CL | getschema
KubePodInventory | getschema
KubeNodeInventory | getschema
```
- The new cost KQL uses `column_ifexists()` for common legacy (`_s`, `_d`) and DCR column names.
- Confirm `Date_s` or `Date` exists and parses as the correct event date, including backfilled records.
- Confirm `DailyCost_d` or `DailyCost` is numeric, the resource identifier and group are populated, and data is not duplicated.
- Confirm `ContainerRestartCount` and `ContainerName` exist in KubePodInventory.
- Confirm `TimeGenerated` is mapped properly by the DCR and the backfill is permitted.
- Verify DCR destination table is `AzureCostData_CL` and field mapping covers the generator's record schema.

## KQL
- Run queries *individually*, not the full .kql file in one execution.
- Query 2 must detect synthetic mid-month spike(s) without reading `IsAnomaly`.
- Query 2's self-join is intended for small labs. For large datasets, consider `make-series` + time-series functions/optimized partitioning.
- Query 3 averages observed daily totals (if resource data missing, baseline may be biased).
- Query 4 calculates averages from one resource-day total, not raw event counts.
- Query 5 assumes America/Toronto local office hours and Monday-Friday 08:00-18:00; adjust for your business.
- Query 11 subtracts first from last snapshot counter; a counter reset / pod re-creation can be missed. For production, use stable pod/container IDs and restart events or counter-reset-aware sampling.
- Query 12's pod counts are NOT a measure of actual dollar costs.

## Dashboard
- Run `python scripts/sync_workbook_queries.py --apply` to update three embedded cost queries.
- Existing workbook still uses fixed `crossComponentResources` workspace IDs; change them to your own subscription/workspace.
- Re-import the workbook and verify 5 tabs (existing workbook) or rebuild as desired.
- A different old six-tab workbook was erroneously stored at `arm-templates/main.json`; this patch replaces that location with IaC.

## Security
- Rotate/revoke the exposed workspace shared key BEFORE publishing any further changes.
- Old key remains in Git history until separately cleaned. Follow GitHub guidance.
- Ensure `.env` is not tracked; `.env.example` has placeholders only.
- Test DCR permissions with the account/managed identity that actually runs each generator.

## Alert and billing
- The optional scheduled rule is NOT automatically active. Review and validate its query before setting `deployCostAlert=true`.
- Historical sample data does not provide live Azure Cost Management billing telemetry.
- Azure query evaluation every five minutes ≠ guaranteed five-minute end-to-end latency.
- Confirm current Azure pricing before enabling alerts, extra retention, AKS, or high-volume ingestion.
