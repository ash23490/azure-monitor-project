# Apply the monitoring fixes in VS Code and push to GitHub

Repository: https://github.com/ash23490/azure-monitor-project

## First: urgent key exposure remediation

The old public `scripts/Generate-CostData.ps1` contained a workspace shared key. Do **not** paste that key into issues, chats, commit messages, or new files.

1. In Azure, regenerate/rotate both primary/secondary workspace shared keys (or delete the workspace if no longer needed) and disable legacy local auth once all clients use modern DCR/OAuth ingestion.
2. Review Azure Monitor activity and ingestion for unusual access.
3. **Git history still contains the key after the new file is committed.** Follow GitHub's official history-cleanup instructions, preferably with a separate coordinated plan: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
4. If collaborators exist, coordinate history rewriting and ensure nobody pushes the compromised branch again.
5. If the tracked `.env` has real credentials, rotate them too and remove `.env` from tracking as shown below. Never commit secrets in `.env` or `.env.example`.

## 1. Clone and open in VS Code (PowerShell terminal)

```powershell
git clone https://github.com/ash23490/azure-monitor-project.git
cd azure-monitor-project
code .
git switch -c fix/azure-monitoring-review
```

Or open your existing local clone instead, run `git status`, pull the latest branch only if safe to do so, and create a branch. Do NOT replace an uncommitted local file without backing it up.

## 2. Apply the ZIP files

Extract `azure-monitor-fixes.zip` to a temporary folder and copy its contents into the repository root **preserving folders**. On Windows, in VS Code Explorer, replace the matching files.

The ZIP intentionally does **not** contain the entire repository. Keep existing:
- `scripts/generate_intune_data.py` (the actual existing generator)
- `dashboards/workbook.json` (the existing workbook, refreshed next)
- `docs/Azure_Cost_and_AKS_Monitoring_Architecture.png`, if present
- all your other project files

You will replace:
- `arm-templates/main.json`
- `kusto-queries/cost-anomaly-detection.kql`
- `scripts/Generate-CostData.ps1`
- `README.md`
- `.gitignore`

You will add:
- `.env.example`
- `scripts/sync_workbook_queries.py`
- `docs/VALIDATION.md`
- this guide
- `tests/test_bundle.py`

## 3. Update the existing workbook

```powershell
python scripts/sync_workbook_queries.py
python scripts/sync_workbook_queries.py --apply
```

It updates three embedded cost tiles. Run after copying this bundle into the real repository with `dashboards/workbook.json` present. Review `git diff -- dashboards/workbook.json`.

## 4. Untrack .env if tracked

```powershell
git ls-files .env
git rm --cached .env
```

The second command only removes the file from Git's index, not from your disk. If `git ls-files .env` shows nothing, skip `git rm`. `.gitignore` now ignores `.env`.

## 5. Validate changes locally

```powershell
python -m unittest discover -s tests -v
python -m json.tool arm-templates/main.json > $null
python -m json.tool dashboards/workbook.json > $null
git diff --check
git status
```

The unit tests check bundled files and synthetic baseline math, **not actual execution in Azure**. You still must run KQL against real tables.

## 6. Validate Azure infrastructure BEFORE deploying

In an account/subscription that you control:

```powershell
az login
az account show
az group show --name azure-monitor-project
az deployment group validate `
  --resource-group azure-monitor-project `
  --template-file arm-templates/main.json `
  --parameters notificationEmail="YOUR_EMAIL"
az deployment group what-if `
  --resource-group azure-monitor-project `
  --template-file arm-templates/main.json `
  --parameters notificationEmail="YOUR_EMAIL"
```

Do NOT deploy if `what-if` shows unexpected destructive updates. Existing workspace `disableLocalAuth` will be enabled: migrate clients away from legacy shared keys first. The template defaults `deployCostAlert=false`, because the custom table is not deployed here.

If you are happy with the results:

```powershell
az deployment group create `
  --resource-group azure-monitor-project `
  --template-file arm-templates/main.json `
  --parameters notificationEmail="YOUR_EMAIL"
```

Only deploy a cost alert after verifying that the custom table exists, KQL validates, and the synthetic ingestion/pipeline freshness assumptions match your environment.

## 7. Commit and push a review branch

```powershell
git status
git diff --check
git add README.md .gitignore .env.example arm-templates/main.json `
  kusto-queries/cost-anomaly-detection.kql scripts/Generate-CostData.ps1 `
  scripts/sync_workbook_queries.py dashboards/workbook.json `
  docs/VALIDATION.md docs/VS_CODE_PUSH_GUIDE.md tests/test_bundle.py
git status
git diff --cached --stat
git diff --cached  # inspect carefully; ensure there are NO secrets
git commit -m "Fix ARM deployment, cost detection KQL, and Azure ingestion security"
git push -u origin fix/azure-monitoring-review
```

Then open your repository on GitHub. Click **Compare & pull request**, review the diff, and merge to `main` when validations pass. VS Code's Source Control / Publish Branch UI is an alternative to the final `git push`.

**Never use `git push --force` just to apply this patch.** Purging credentials from Git history is a separate security operation and can require a coordinated force-push, branch protection adjustments, and clone cleanup.

## 8. Check before you describe it as complete

- KQL queries are executed one at a time against the actual table schema.
- The anomaly test catches a known synthetic spike without using `IsAnomaly`.
- Alert evaluation / notification latency is measured (not assumed).
- Workbook tiles render after import with your own workspace IDs.
- The PowerShell DCR stream and Python DCR stream both exist and ingest correctly.
- No credentials remain in active files or Git history.
