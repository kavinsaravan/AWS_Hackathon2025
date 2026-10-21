# Weekly dispatch dashboard refresh

The app keeps its 72-hour police-dispatch snapshot and refreshes it weekly on Mondays at 9 AM America/Los_Angeles. AWS continues to prepare its daily snapshot; route-risk refresh frequency is unchanged. Tableau and Power BI are not part of this app.

`.github/workflows/weekly-dashboard-refresh.yml` runs on GitHub's hosted runner, independently of the Mac and Codex's local filesystem/network permissions. It also runs when the refresh implementation changes and can be started with **Actions → Weekly dashboard refresh → Run workflow**.

The workflow validates the AWS CSV checksum, exact schema, unique records, SF coordinates, timestamps, 72-hour window, and every spatial/category/date summary count. It rejects snapshots older than 48 hours. It then builds the frontend, commits only the three public snapshot files, and pushes to `main`. The existing Vercel Git integration publishes that commit. A final check waits up to 15 minutes for all three production files to match their local SHA-256 digests; a missing or mismatched deployment fails the workflow rather than reporting success. No Vercel CLI login or new deployment credential is required.

The workflow has only repository-content write permission and uses GitHub's short-lived token. It never updates Lambda functions, route scoring, README.md, or local user files. Validation/build failures occur before committing, so the previous published snapshot stays in place. Concurrent remote changes cause the push to fail rather than overwrite another commit. Review failed runs in GitHub Actions; GitHub notification preferences determine its email notifications.

The existing Codex task runs at 9:30 AM Mondays to mirror the **published website snapshot** into the Google Sheet and report any failed publication. It does not build, commit, push, or deploy. The Sheet is a separate export and is not read by the app. This remaining connector task requires Codex to be running and allowed to fetch the public snapshot; if access is unavailable, retain the previous Sheet data and report the issue. A permission grant in an interactive chat does not grant future unattended runs broader access.

Google Sheet updates preserve string identifiers, typed dates/numbers, formatting, and the exact 14-column schema. Stage and read back all values before one server-side values-only copy into Incidents, including blank rows to clear the old tail. RefreshInfo records the actual source, snapshot timestamp, import time and verified publication status. Do not inspect or reconnect the standalone Tableau workbook.

To run and verify the website refresh locally:

```sh
python3 scripts/export_tableau_data.py
npm ci
npm run build
# Commit/push only after validation and build succeed.
python3 scripts/verify_dashboard_publication.py
```

GitHub scheduled jobs can start late; 9 AM is the requested start time, not a publication-time guarantee.
