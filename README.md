# Azure Cloud Monitoring & Observability

**Azure monitoring and data engineering portfolio lab** | Azure Monitor · Log Analytics · KQL · Python · PowerShell · Microsoft Entra ID · DCR/DCE · Power BI · AKS · ARM

## Project overview

I built an Azure observability lab to investigate four operational questions:

1. **Cloud cost:** Which resources drive spending, and when does an individual resource spike above its usual baseline?
2. **Device compliance:** How do compliance checks change over time, and which departments or policies require attention?
3. **Administrative activity:** Which changes occur outside defined business hours?
4. **Kubernetes health:** Which pods/nodes report unhealthy states, restarts, or unusual workload distribution?

The project combines synthetic data generation, Azure Monitor ingestion, Kusto Query Language (KQL), an Azure Workbook, a three-page Power BI report, and a test notification workflow. A major part of the work was diagnosing and correcting authentication, schema, query, and visualization issues.

> **Lab disclosure:** Cost and Intune compliance records are **synthetic**. They demonstrate ingestion and analytical methods; they are not live Azure Cost Management exports or real Microsoft Intune tenant data. Azure Activity and AKS data come from Azure monitoring sources where configured. AKS figures below refer to historical snapshots, not necessarily a currently running cluster.

## Architecture

```text
                       DATA SOURCES
  +----------------------+------------------------+
  | Synthetic Azure cost | Synthetic Intune checks|
  | PowerShell generator | Python generator       |
  +-----------+----------+------------+-----------+
              |                       |
              +-----------+-----------+
                          |
                Microsoft Entra ID
               OAuth 2.0 access token
                          |
              Azure Monitor Logs Ingestion API
                          |
                DCE / DCR ingestion flow
                          |
              +-----------v------------+
              | Log Analytics Workspace|
              | azure-monitor-law      |
              +-----------+------------+
                          |
                Custom log tables + KQL
                          |
                 +--------+--------+
                 |                 |
           Azure Workbook      Power BI
                 |
         Azure Monitor alert rule
                 |
          Action Group (email)

  Additional monitored sources:
    Azure Activity Log --> Diagnostic settings --> Log Analytics
    AKS / Container Insights ---------------> Log Analytics
```

**Why these components?** The generators create predictable test scenarios; Microsoft Entra ID issues short-lived authentication tokens; the **Logs Ingestion API** receives HTTPS requests; the **DCE** supplies an ingestion endpoint; the **DCR** defines stream/schema transformation and destination; Log Analytics stores records for KQL. The Workbook, Power BI, and alerting layer turn that telemetry into operational decisions.

### Data pipelines

| Pipeline | Source and ingestion | Log Analytics destination | Purpose |
|---|---|---|---|
| Cost monitoring | PowerShell → OAuth → Logs Ingestion API → DCE/DCR | `AzureResourceCost_CL` | Resource/day spending, baselines, anomaly analysis |
| Compliance monitoring | Python → `DefaultAzureCredential` → Logs Ingestion API → DCE/DCR | `IntuneDeviceCompliance_CL` | Device/policy compliance and drift |
| Administrative auditing | Azure Activity Log via diagnostic settings | `AzureActivity` | Review management operations and after-hours changes |
| AKS monitoring | Azure Kubernetes Service + Container Insights | `KubePodInventory`, `KubeNodeInventory` | Historical pod, node, restart, and namespace analysis |

The cost and compliance paths use the modern Logs Ingestion API, **not** the older workspace SharedKey-based HTTP Data Collector API. OAuth still communicates over HTTPS; it is the authentication method, not a separate transport protocol.

## What I implemented

### 1. Data generation and ingestion

- Developed an OAuth-based **PowerShell** cost generator, with dry-run and explicit `-Send` modes.
- Tested **210 synthetic cost records** covering **7 resources across 30 days** (one resource/day record per observation).
- Developed an OAuth-based **Python** Intune compliance generator with structured logging, batching, configuration validation, and retry handling.
- Tested a **1,500-record compliance dataset** representing **10 simulated endpoints × 5 policy checks × 30 days**.
- Used DCE/DCR stream mapping to route both datasets to their respective custom Log Analytics tables.
- Preserved generated anomaly/drift flags as test labels, while writing detection KQL that calculates findings from observable values.

### 2. KQL monitoring and detection

The repository keeps **12 standalone queries in one file**: [`kusto-queries/cost-anomaly-detection.kql`](kusto-queries/cost-anomaly-detection.kql). Run **one numbered query at a time** in Log Analytics.

| Query | Analysis |
|---|---|
| 1 | Verify synthetic cost ingestion |
| 2 | Detect resource-level cost anomalies using a historical baseline, not the planted anomaly flag |
| 3 | Analyze daily spend and observed-day baseline |
| 4 | Identify highest-spending resources |
| 5 | Detect off-hours Azure administrative operations using Toronto local time |
| 6 | Show compliance trends across the sample period |
| 7 | Summarize noncompliant checks by department |
| 8 | Identify simulated compliance drift |
| 9 | Evaluate pod health using the latest observed pod snapshot |
| 10 | Evaluate node health without misclassifying `NotReady` as `Ready` |
| 11 | Estimate container restarts using counter differences instead of summing snapshots |
| 12 | Compare namespace workload distribution (**not** actual AKS cost attribution) |

For synthetic/backfilled cost records, queries use the event-day field (for example, `Date_s`) where available rather than assuming ingestion `TimeGenerated` is the spending date. Some queries use `column_ifexists()` to accommodate known legacy suffixes and DCR-mapped column names. Always confirm the deployed schema.

### 3. Azure Workbook and Power BI

- Updated the Azure Monitor Workbook's multiple monitoring views (five tabs in the current repository documentation).
- Built **three Power BI report pages**: **Azure Cost Analytics**, **Intune Compliance Analytics**, and **AKS Monitoring**.
- Used KQL aggregation for cost trends, resource comparisons, compliance rates, failed checks, and historical Kubernetes health.
- Reworked queries and report connections when schema mismatches or malformed query requests prevented charts from rendering.

The Power BI report was built locally. A `.pbix` file is not assumed to be present in this repository; the README/screenshots can document it until the report artifact is added.

### 4. Alerting and infrastructure

- Configured a **Log Analytics cost-anomaly alert**, using a historical comparison instead of filtering directly on generated `IsAnomaly` labels.
- Configured an **Action Group** and successfully tested its **email notification**.
- Set the alert evaluation frequency to **15 minutes** during the lab and left the alert **disabled** after testing to avoid ongoing charges.
- Kept an **ARM template** for a baseline workspace, storage account, action group, and optional alert. Some operational resources—custom tables, DCR/DCE, diagnostic settings, and AKS—were set up separately and are **not** all provisioned by that template.

**Alert validation boundary:** Testing an Action Group email demonstrates notification delivery; it is **not** the same as proving a cost anomaly triggered a complete, end-to-end alert incident.

## Results and validation

| Area | Observed lab result | Interpretation |
|---|---|---|
| Cost ingestion | 210 resource-day records | Successfully tested synthetic cost ingestion and querying |
| Compliance ingestion | 1,500 generated check records | Tested 10 endpoints, 5 policies, and 30 days of synthetic activity |
| KQL | 12 queries reviewed/validated | Covers ingestion, cost, activity, compliance, and AKS inventory |
| Azure Workbook | Monitoring views updated | Interactive Azure-side exploration of the log data |
| Power BI | 3 report pages completed | Separately visualizes cost, compliance, and AKS health |
| AKS | Historical pod/node inventory analyzed | Historical data remains queryable; cluster status affects freshness |
| Notification | Action Group test email received | Confirms the test notification path, not full alert triggering |

These are **observations from the lab**, not guaranteed outputs of a new deployment. Re-running generators can change counts and introduce duplicate records; validate timestamps, event dates, and identifiers before interpreting totals.

## Troubleshooting and engineering decisions

Troubleshooting was a substantial part of this project. These are the problems encountered and the actions taken, rather than generic hypothetical failure scenarios.

| Issue | Diagnosis / investigation | Resolution or learning |
|---|---|---|
| **Azure Cost Management CLI errors** | Direct cost queries returned `BadRequest` or were not usable as a dependable input in the lab | Used explicitly labeled **synthetic cost records** to test the monitoring pipeline. Did not misrepresent them as billing exports |
| **Logs Ingestion API returned HTTP 403** | An authenticated call still requires a valid Azure Monitor token **and** the correct DCR role assignment | Reauthenticated with `az login` (including MFA where needed), checked **Monitoring Metrics Publisher** on the DCR, and allowed for role propagation before retesting |
| **PowerShell script execution blocked** | Execution policy prevented an unsigned local `.ps1` from running | Used PowerShell 7 with a **process-specific invocation** such as `pwsh -NoProfile -ExecutionPolicy Bypass -File ...`; did not recommend globally weakening policy |
| **DCE/DCR and custom-table mapping confusion** | Stream names, immutable DCR IDs, and destination table schemas must match exactly | Verified custom tables and stream mappings, used the modern Logs Ingestion API, and checked records in Log Analytics after ingestion |
| **Historical dates differed from ingestion dates** | Backfilled records can arrive with a recent `TimeGenerated` even when they describe older spending days | Analyzed the source event-day column for daily cost baselines, rather than assuming ingestion time represented the event date |
| **Anomaly detection depended on a planted label** | Filtering `IsAnomaly == true` only retrieved pre-tagged synthetic spikes | Changed detection to compare each resource's daily spend with its historical baseline and apply percentage/absolute thresholds |
| **AKS provisioning constraints** | Encountered resource-provider registration, VM-size availability, and regional vCPU quota issues while preparing the Kubernetes lab | Investigated provider availability, compatible compute options, and quotas rather than assuming every region/SKU was usable |
| **Kubernetes inventory and unavailable cluster** | An AKS cluster may be stopped to control cost; `kubectl` cannot reach an unavailable API server, and recent-data panels can be empty | Distinguished **historical last-seen snapshots** from live state and adjusted analysis accordingly; kept the cluster stopped when not required |
| **Misleading AKS restart/readiness counts** | Restart values are cumulative counters; counting every snapshot inflates totals. `NotReady` contains the text `Ready` | Used counter deltas and explicit readiness-state comparisons; documented undercount possibilities after resets |
| **Power BI query/connection errors** | A malformed or truncated Power Query request produced an HTTP 400 response | Corrected the query request and retested report visuals against Log Analytics data |
| **Secrets in older Git revisions** | Legacy scripts used Log Analytics workspace shared keys, and an `.env` file was tracked | Regenerated **both** workspace shared keys, migrated current scripts to OAuth, staged removal of the obsolete script and tracked `.env`, and added `.env` to `.gitignore`. Older commits still exist unless separately rewritten |
| **Two local Git project folders** | An older `azure-monitor-project - Copy` directory contained legacy scripts while the active repo had newer DCR/DCE implementations | Compared scripts and verified branch/remote/status before editing, avoiding accidental replacement of the tested versions |

### Practical lessons

- A successful HTTP request is not sufficient evidence of a usable pipeline; **query the destination table and validate counts and field mappings**.
- Authentication (`OAuth token`) and authorization (`DCR RBAC role`) solve different problems.
- For historical or synthetic telemetry, distinguish **event time** from **ingestion time**.
- Alert conditions should derive from data, not merely reuse a label planted by a test generator.
- Kubernetes metrics must be interpreted as snapshots and counters, especially when a cluster has been stopped.
- Credentials require both prevention in current code and **rotation after accidental exposure**.

## Reproducing the lab

### Prerequisites

- Azure subscription and permission to create/configure monitoring resources.
- Azure CLI (`az`), PowerShell 7 (`pwsh`), and Python 3.
- A Log Analytics workspace plus appropriate **custom tables**, **DCR(s)**, and **DCE/ingestion endpoint**.
- **Monitoring Metrics Publisher** on the relevant DCR for the identity that runs ingestion.
- Azure Monitor / Log Analytics access to run the queries.
- Optional: AKS with Container Insights; Power BI Desktop for the local report.

> Azure Monitor, Log Analytics ingestion/retention, alerts, AKS, and related resources can incur charges. Review pricing and keep nonessential resources stopped or removed when not in use.

### 1. Authenticate and inspect the deployment template

```powershell
az login
az account show
az group show --name azure-monitor-project

az deployment group validate --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
az deployment group what-if --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"

# Run deployment only after reviewing what-if and possible resource/cost impacts:
# az deployment group create --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
```

The ARM template is a **partial deployment definition**, not an automated recreation of the entire lab. Review resource names and `disableLocalAuth` behavior for any existing workspace before deploying.

### 2. Run synthetic Intune ingestion

```powershell
python -m pip install requests azure-identity

$env:AZURE_DCE_URI="https://YOUR_DCE.REGION.ingest.monitor.azure.com"
$env:AZURE_DCR_IMMUTABLE_ID="dcr-YOUR_INTUNE_DCR_ID"
$env:AZURE_DCR_STREAM_NAME="Custom-IntuneDeviceComplianceRaw"

python scripts/generate_intune_data.py
```

`DefaultAzureCredential` can use an appropriate signed-in development identity. The DCR stream, mappings, and `IntuneDeviceCompliance_CL` table must match the script's record structure.

### 3. Run synthetic cost ingestion

Set the required ingestion configuration for the **cost** DCR, including its DCE endpoint and the stream `Custom-AzureResourceCostRaw`, according to `scripts/Generate-CostData.ps1`. When running both generators, **switch to the correct DCR immutable ID for each stream**.

```powershell
# Verify local behavior before transmitting anything:
pwsh -NoProfile -File .\scripts\Generate-CostData.ps1 -DaysToGenerate 30

# Example send (requires valid DCR/DCE configuration and RBAC):
pwsh -NoProfile -File .\scripts\Generate-CostData.ps1 -DaysToGenerate 30 -BatchSize 100 -Send
```

If execution policy prevents running the file, review your machine's policy; a locally authorized, process-specific `-ExecutionPolicy Bypass` invocation was used during lab troubleshooting. The generator's synthetic `IsAnomaly` flag is **test ground truth**, not the basis for anomaly detection.

### 4. Verify in Log Analytics

Run each of the 12 KQL examples **individually**. Useful schema checks:

```kusto
AzureResourceCost_CL | getschema
```

```kusto
IntuneDeviceCompliance_CL | getschema
```

```kusto
KubePodInventory | getschema
```

Check row counts, the actual table/column names, and the event-time range. Ingestion is asynchronous; results may not appear immediately.

### 5. Refresh the Workbook

```powershell
python scripts/sync_workbook_queries.py --apply
```

Inspect the updated `dashboards/workbook.json` and re-import it into Azure if needed. Workbook resource IDs may still refer to the original lab environment and must be adapted for another subscription.

## Repository layout

```text
azure-monitor-project/
├── arm-templates/
│   └── main.json                         # Partial infrastructure template
├── dashboards/
│   └── workbook.json                     # Azure Monitor workbook definition
├── kusto-queries/
│   └── cost-anomaly-detection.kql         # 12 individually runnable KQL queries
├── scripts/
│   ├── Generate-CostData.ps1              # OAuth-based synthetic cost ingestion
│   ├── generate_intune_data.py            # OAuth-based synthetic Intune ingestion
│   └── sync_workbook_queries.py           # Workbook query synchronization
├── docs/
│   ├── VALIDATION.md                      # Additional validation instructions
│   └── VS_CODE_PUSH_GUIDE.md              # Repository / Git workflow notes
├── .env.example                           # Placeholder configuration only
├── .gitignore                             # Excludes local .env and generated files
└── README.md
```

**Screenshots will be organized under `docs/screenshots/` before the final repository push.** The Power BI `.pbix` file and a demo-video link can also be added when prepared; neither is implied to be in this repository today.

## Screenshots and demonstration

Planned evidence for the repository includes: the ingestion results/custom tables, the cost anomaly query, Intune compliance analysis, Azure Activity query, AKS monitoring, Workbook views, three Power BI pages, and the successful Action Group test notification. Crop or redact **account identifiers, emails, tokens, subscription details, and other sensitive information** before committing screenshots.

A short walkthrough can demonstrate the architecture, show a synthetic cost spike being detected through KQL, tour the Workbook and Power BI pages, and discuss the security/troubleshooting decisions.

## Security and limitations

- **Historical credential exposure:** Earlier Git revisions contained a Log Analytics workspace shared key. **Both primary and secondary keys were regenerated** during project cleanup. The current scripts use OAuth, but historical Git objects may still contain the *now-invalid* keys. Removing a file in a new commit does not erase Git history.
- **Environment files:** `.env` is ignored; cleanup removes the tracked `.env` from the current branch. `.env.example` contains configuration placeholders, never live secrets.
- **Lab data:** Cost and Intune readings are simulated. The project does **not** claim a live Cost Management export pipeline or production Microsoft Intune ingestion.
- **Operational state:** The AKS cluster may be stopped; historical inventory is not evidence of live current health. Node/pod counts depend on the selected time range.
- **Alerting:** The Action Group notification was tested. The cost alert was configured then disabled; full end-to-end triggering was not established.
- **Latency/cost:** A 15-minute alert evaluation interval does not guarantee 15-minute detection. Actual behavior depends on ingestion latency, query windows, permissions, and resource state. No fixed low-cost estimate is promised.
- **Reproducibility:** DCR/DCE, custom tables, diagnostic settings, AKS, RBAC, and report connections may require manual configuration. The ARM template alone does not reconstruct the complete environment.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) for further checks. This README documents **work completed and observed in the lab**, while making its remaining limitations explicit.
