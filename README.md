Azure Cloud Monitoring & Observability
My Azure monitoring and data engineering portfolio lab | Azure Monitor · Log Analytics · KQL · Python · PowerShell · Microsoft Entra ID · DCR/DCE · Power BI · AKS · ARM
Project overview
I built an Azure observability lab to investigate four operational questions:
1. Cloud cost: Which resources drive spending, and when does an individual resource spike above its usual baseline?
2. Device compliance: How do compliance checks change over time, and which departments or policies require attention?
3. Administrative activity: Which changes occur outside defined business hours?
4. Kubernetes health: Which pods/nodes report unhealthy states, restarts, or unusual workload distribution?
I combined synthetic data generation, Azure Monitor ingestion, Kusto Query Language (KQL), an Azure Workbook, a three-page Power BI report, and an email notification test. This project was as much about solving real configuration and monitoring problems as it was about building dashboards.
Lab disclosure: I generated the cost and Intune compliance records myself for testing. They are synthetic, not live Azure Cost Management exports or real Intune tenant data. I used Azure Activity and AKS monitoring data where configured. AKS statistics describe historical snapshots, not necessarily the cluster’s current state.

Architecture
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

Why I chose this architecture: I needed a repeatable way to create test data, authenticate securely, and inspect monitoring results. I used Microsoft Entra ID for short-lived OAuth tokens, the Logs Ingestion API to accept HTTPS requests, a DCE for the ingestion endpoint, a DCR to define the data stream and destination, and Log Analytics to store and query the records. I then used the Workbook, Power BI, and an alert rule to make the data useful.
Data pipelines
Pipeline	Source and ingestion	Log Analytics destination	Purpose
Cost monitoring	PowerShell → OAuth → Logs Ingestion API → DCE/DCR	AzureResourceCost_CL	Resource/day spending, baselines, anomaly analysis
Compliance monitoring	Python → DefaultAzureCredential → Logs Ingestion API → DCE/DCR	IntuneDeviceCompliance_CL	Device/policy compliance and drift
Administrative auditing	Azure Activity Log via diagnostic settings	AzureActivity	Review management operations and after-hours changes
AKS monitoring	Azure Kubernetes Service + Container Insights	KubePodInventory, KubeNodeInventory	Historical pod, node, restart, and namespace analysis


I migrated the cost and compliance scripts to the modern Logs Ingestion API instead of the older SharedKey-based HTTP Data Collector API. OAuth determines how the scripts authenticate; HTTPS is how they communicate.
What I implemented
1. Data generation and ingestion
- I developed an OAuth-based PowerShell cost generator with a dry-run mode and an explicit -Send option.
- I tested ingestion of 210 synthetic cost records representing 7 resources across 30 days.
- I developed an OAuth-based Python Intune compliance generator with structured logging, batching, configuration checks, and retry handling.
- I tested 1,500 synthetic compliance records: 10 simulated devices × 5 policies × 30 days.
- I configured DCE/DCR ingestion streams to route the generated records to separate Log Analytics custom tables.
- I used generated anomaly and drift flags as test labels, but calculated cost anomalies from actual spending values rather than simply filtering those labels.
2. KQL monitoring and detection
I keep 12 individually runnable KQL queries in one file: kusto-queries/cost-anomaly-detection.kql. I run one numbered query at a time in Log Analytics.
Query	Analysis
1	Verify synthetic cost ingestion
2	Detect resource-level cost anomalies using a historical baseline, not the planted anomaly flag
3	Analyze daily spend and observed-day baseline
4	Identify highest-spending resources
5	Detect off-hours Azure administrative operations using Toronto local time
6	Show compliance trends across the sample period
7	Summarize noncompliant checks by department
8	Identify simulated compliance drift
9	Evaluate pod health using the latest observed pod snapshot
10	Evaluate node health without misclassifying NotReady as Ready
11	Estimate container restarts using counter differences instead of summing snapshots
12	Compare namespace workload distribution (not actual AKS cost attribution)


For historical synthetic cost records, I use the event-date field (such as Date_s) when available because the ingestion timestamp (TimeGenerated) can be different. I also use column_ifexists() in some queries to handle differences between older table columns and DCR-mapped columns. I check the actual table schema before running a query.
3. Azure Workbook and Power BI
- I built and updated multiple Azure Workbook monitoring views. I keep the workbook definition in dashboards/workbook.json and document five tabs; I verify the exported JSON separately from the live workbook in Azure.
- I built three Power BI report pages: Azure Cost Analytics, Intune Compliance Analytics, and AKS Monitoring.
- I used KQL to aggregate cost trends, compare resource spending, calculate compliance rates, count failed checks, and examine historical Kubernetes health.
- I fixed queries and report connections when schema mismatches and malformed requests prevented charts from rendering.
I built the Power BI report locally. My screenshots show the report pages; I will only include the editable .pbix file if I verify that the file is safe to publish.
4. Alerting and infrastructure
- I configured a Log Analytics cost-anomaly alert using a comparison against historical spending, instead of relying on the generated IsAnomaly label.
- I configured an Action Group and successfully tested its email notification.
- I set the alert evaluation frequency to 15 minutes and disabled the alert after testing to avoid unnecessary ongoing charges.
- I kept an ARM template for the baseline workspace, storage account, action group, and optional alert. I configured other parts, such as DCR/DCE, custom tables, diagnostic settings, and AKS, separately; the ARM template does not recreate the entire lab.
What I verified: The Action Group successfully sent a test email. I do not claim this proves a cost anomaly triggered the entire alert workflow end to end.
Results and validation
Area	Observed lab result	Interpretation
Cost ingestion	210 resource-day records	Successfully tested synthetic cost ingestion and querying
Compliance ingestion	1,500 generated check records	Tested 10 endpoints, 5 policies, and 30 days of synthetic activity
KQL	12 queries reviewed/validated	Covers ingestion, cost, activity, compliance, and AKS inventory
Azure Workbook	Monitoring views updated	Interactive Azure-side exploration of the log data
Power BI	3 report pages completed	Separately visualizes cost, compliance, and AKS health
AKS	Historical pod/node inventory analyzed	Historical data remains queryable; cluster status affects freshness
Notification	Action Group test email received	Confirms the test notification path, not full alert triggering


These are results I observed in my lab, not guarantees for a new deployment. Re-running a generator may create additional or duplicate records, so I check dates, record counts, and identifiers before interpreting totals.
Troubleshooting and engineering decisions
I spent a significant part of this project troubleshooting. The issues below are problems I encountered and investigated, rather than hypothetical examples.
Issue	Diagnosis / investigation	Resolution or learning
Azure Cost Management CLI errors	My direct cost queries returned BadRequest and were not dependable for the lab	I generated clearly labeled synthetic cost data instead of pretending it was real billing data
Logs Ingestion API returned HTTP 403	I learned that an OAuth token alone is not enough; the identity also needs permission on the DCR	I signed in again, checked Monitoring Metrics Publisher on the DCR, allowed role propagation, and retested
PowerShell script execution blocked	My system blocked an unsigned local .ps1 script	I used a process-specific PowerShell invocation instead of weakening the execution policy for the whole machine
DCE/DCR and custom-table mapping confusion	I had to align the stream name, DCR immutable ID, and destination table schema	I corrected the mappings and checked that records actually appeared in Log Analytics
Historical dates differed from ingestion dates	My backfilled records had recent ingestion timestamps even when they described older days	I used the source event date to calculate historical spending baselines
Anomaly detection depended on a planted label	I realized filtering IsAnomaly == true would only find spikes already tagged by my generator	I rewrote the query to compare resource spending with a historical average and require both percentage and absolute increases
AKS provisioning constraints	I encountered resource-provider, VM availability, and regional vCPU quota issues	I investigated supported configurations and quotas before continuing the AKS lab
Kubernetes inventory and unavailable cluster	When I stopped AKS to control cost, recent monitoring views no longer reflected live activity	I used historical last-seen data and explained that it does not represent current cluster health
Misleading AKS restart/readiness counts	I found that restart counters are cumulative and that NotReady contains the word Ready	I used restart-counter differences and explicit state comparisons, while documenting limitations after resets
Power BI query/connection errors	A malformed or truncated Power Query request gave me HTTP 400 errors	I corrected the query request and tested the report visuals again
Secrets in older Git revisions	I found legacy workspace shared keys in old scripts and a tracked .env file	I regenerated both shared keys, moved current scripts to OAuth, removed the obsolete script and tracked .env, and added .env to .gitignore. I also documented that old Git history remains
Two local Git project folders	I had a azure-monitor-project - Copy folder with older scripts alongside my newer working repository	I compared script versions and confirmed the active branch and remote before editing the correct folder


What I learned
- I learned that a successful HTTP response does not prove the whole pipeline works: I still need to query the destination table and inspect record counts and field mappings.
- I learned the difference between authentication (an OAuth token proving identity) and authorization (the DCR RBAC role granting permission).
- I learned to distinguish event time from ingestion time, especially with synthetic or backfilled data.
- I learned to calculate anomaly conditions from spending data rather than trust a label planted by the generator.
- I learned to interpret Kubernetes snapshots, cumulative restart counters, and the effects of a stopped cluster carefully.
- I learned to protect credentials in active code and rotate them if they have been exposed.
Reproducing the lab
Prerequisites
- Azure subscription and permission to create/configure monitoring resources.
- Azure CLI (az), PowerShell 7 (pwsh), and Python 3.
- A Log Analytics workspace plus appropriate custom tables, DCR(s), and DCE/ingestion endpoint.
- Monitoring Metrics Publisher on the relevant DCR for the identity that runs ingestion.
- Azure Monitor / Log Analytics access to run the queries.
- Optional: AKS with Container Insights; Power BI Desktop for the local report.
Azure Monitor, Log Analytics ingestion/retention, alerts, AKS, and related resources can incur charges. Review pricing and keep nonessential resources stopped or removed when not in use.

1. Authenticate and inspect the deployment template
az login
az account show
az group show --name azure-monitor-project

az deployment group validate --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
az deployment group what-if --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"

# Run deployment only after reviewing what-if and possible resource/cost impacts:
# az deployment group create --resource-group azure-monitor-project --template-file arm-templates/main.json --parameters notificationEmail="YOUR_EMAIL"
I treat the ARM template as a partial deployment definition, not a one-click recreation of the entire lab. Before deploying, I review resource names, costs, and any disableLocalAuth changes affecting an existing workspace.
2. Run synthetic Intune ingestion
python -m pip install requests azure-identity

$env:AZURE_DCE_URI="https://YOUR_DCE.REGION.ingest.monitor.azure.com"
$env:AZURE_DCR_IMMUTABLE_ID="dcr-YOUR_INTUNE_DCR_ID"
$env:AZURE_DCR_STREAM_NAME="Custom-IntuneDeviceComplianceRaw"

python scripts/generate_intune_data.py
For local development, my Python script uses DefaultAzureCredential to obtain a token from an authorized identity. I make sure the DCR stream, column mappings, and IntuneDeviceCompliance_CL table match the records the script sends.
3. Run synthetic cost ingestion
For the cost generator, I set the DCE endpoint and select the cost DCR with stream Custom-AzureResourceCostRaw, as required by scripts/Generate-CostData.ps1. I use the matching DCR immutable ID for each generator, because cost and compliance have different streams.
# Verify local behavior before transmitting anything:
pwsh -NoProfile -File .\scripts\Generate-CostData.ps1 -DaysToGenerate 30

# Example send (requires valid DCR/DCE configuration and RBAC):
pwsh -NoProfile -File .\scripts\Generate-CostData.ps1 -DaysToGenerate 30 -BatchSize 100 -Send
When PowerShell execution policy blocked my script, I used a process-specific execution-policy option rather than changing the machine-wide policy. I keep the generator's synthetic IsAnomaly flag as test ground truth; my anomaly query does not depend on it.
4. Verify in Log Analytics
I run each of the 12 KQL examples individually in Log Analytics. To confirm my actual schemas, I use these checks:
AzureResourceCost_CL | getschema
IntuneDeviceCompliance_CL | getschema
KubePodInventory | getschema
I then check the record counts, exact table and column names, and event-date range. Data ingestion is asynchronous, so I allow for a delay before deciding a record is missing.
5. Review and import the Workbook
I review [`dashboards/workbook.json`](dashboards/workbook.json) and its embedded KQL before importing it into Azure. I check that the queries refer to AzureResourceCost_CL and IntuneDeviceCompliance_CL, rather than older custom table names, and that the cost anomaly query calculates its own baseline.

The repository includes a sync_workbook_queries.py helper, but I inspect its output before using it because a synchronization script can overwrite manually updated workbook queries. Workbook resource IDs may also need to be changed when importing into another subscription.
Repository layout
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
│   ├── screenshots/                       # 41 screenshots of my project
│   └── Azure Cost, Compliance & AKS Monitoring Architecture.png
├── .env.example                           # Placeholder configuration only
├── .gitignore                             # Excludes local .env and generated files
└── README.md

I added 41 project screenshots under [`docs/screenshots/`](docs/screenshots/) to document the workbook, queries, Power BI visuals, AKS, and alert testing. I can add the Power BI .pbix file and a recorded walkthrough separately after checking them for sensitive information.
Screenshots and demonstration
My screenshots document ingestion results, cost anomaly queries, Intune compliance, Azure Activity, AKS monitoring, workbook views, three Power BI pages, and the successful Action Group test notification. Before publishing additional screenshots, I check for personal emails, account identifiers, tokens, keys, and other sensitive information.

In a short walkthrough, I can explain the architecture, demonstrate a synthetic cost spike in KQL, show the Workbook and Power BI reports, and discuss the troubleshooting and security decisions.
Security and limitations
- Historical credential exposure: Earlier Git revisions contained a Log Analytics workspace shared key. Both primary and secondary keys were regenerated during project cleanup. The current scripts use OAuth, but historical Git objects may still contain the now-invalid keys. Removing a file in a new commit does not erase Git history.
- Environment files: I removed the tracked .env from the current branch and added it to .gitignore. I keep .env.example only for nonsecret configuration placeholders.
- Lab data: Cost and Intune readings are simulated. The project does not claim a live Cost Management export pipeline or production Microsoft Intune ingestion.
- Operational state: The AKS cluster may be stopped; historical inventory is not evidence of live current health. Node/pod counts depend on the selected time range.
- Alerting: The Action Group notification was tested. The cost alert was configured then disabled; full end-to-end triggering was not established.
- Latency/cost: A 15-minute alert evaluation interval does not guarantee 15-minute detection. Actual behavior depends on ingestion latency, query windows, permissions, and resource state. No fixed low-cost estimate is promised.
- Reproducibility: DCR/DCE, custom tables, diagnostic settings, AKS, RBAC, and report connections may require manual configuration. The ARM template alone does not reconstruct the complete environment.
I document my validation steps and their limitations directly in this README. I have not claimed that the ARM template, scripts, or alert workflow recreate a fully tested production system.
