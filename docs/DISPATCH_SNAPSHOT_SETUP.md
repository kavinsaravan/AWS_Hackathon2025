# Single-source police dispatch snapshot

The dashboard dataset uses one source: DataSF's mapped police dispatch records from the
past 72 hours. The snapshot verified on October 12, 2026 contains 2,764 records. These are calls for
service, not confirmed crimes. Its timestamp is `2026-10-12T09:00:30.972698+00:00`.
The original file name `sf-crime-incidents.csv` is kept to help update the existing
Tableau text-file connection without renaming its table or fields.

- [CSV snapshot](https://aws-hackathon2025.vercel.app/tableau/sf-crime-incidents.csv)
- [Prepared Google Sheet](https://docs.google.com/spreadsheets/d/1yROYPqBwni6skjdibmfFOvSKewLyoPel7b5Gcb2uKnE/edit)
- [AWS export](https://scdwndv5z4.execute-api.us-east-1.amazonaws.com/prod/analytics.csv)
- [AWS provenance](https://scdwndv5z4.execute-api.us-east-1.amazonaws.com/prod/analytics-manifest)

The Sheet's Incidents tab matches all 14 CSV fields, preserving identifiers as text,
coordinates/counts as numbers, and event dates/times as typed date values. All 38,710
cells were read back and matched against the verified AWS snapshot. RefreshInfo
records the source, weekly import schedule, and pending Tableau connection.

## Update the existing Tableau snapshot

Download the CSV, then open SafePathSF for editing. Use the Data Source page's
text-file connection menu to look for Edit Connection / a file replacement action.
Select the new CSV with the same file name. If your web editor does not expose a
replacement action, use the free Mac Tableau Desktop Public Edition to edit the
text-file connection; this preserves the existing workbook rather than rebuilding
its charts. Do not assume that adding a second data source replaces the first one.

Keep the field names and types intact:

| Field | Tableau type / purpose |
| --- | --- |
| RecordKey | String dimension on map Detail; one mark per dispatch record |
| ExternalId | CAD number stored as text |
| Category | String; dispatch call type |
| EventDate | Date; dispatch date in SF time |
| LocalTimestamp | Date/time; dispatch time in SF time |
| Latitude / Longitude | Decimal numbers, raw range filters on all three sheets |
| RecordCount | Integer, SUM counts dispatch records |
| SnapshotUTC | String; snapshot provenance timestamp |

Set both coordinate filters to their full ranges after the update. Keep Record Key
as a dimension, not ATTR. Rename chart titles to **Dispatch Locations**, **Dispatch
Call Types**, and **Dispatch Records Over Time**. For the 72-hour window, using the
continuous Hour of Local Timestamp for the time chart is more detailed than Day.
Keep the map, category bars, and time chart in CrimeDashboard, then publish over
SafePathSF. The dashboard URL can stay unchanged.

The existing public Tableau workbook still uses the earlier police-incident CSV
until this upload and republish step is completed. Compatibility checks on the CSV
and Sheet are not proof that the published Tableau extract has been replaced. After
publishing, verify the actual source data, record count, coordinate filters, route
switching, and All SF behavior through the embedded view.

## Snapshot mode and optional daily automation

SafePath's built-in dispatch charts use the checked-in snapshot in
`public/safety-analytics.json`. Changing routes filters it; it does not fetch new
records. Route risk scores still use the separate AWS dispatch/311 scorer.

A separate `safepath-daily-analytics` stack now exports dispatch snapshots to private
versioned S3 objects with a DynamoDB pointer. It refreshes daily at 09:00 UTC and
exposes read-only CSV, summary, and manifest API endpoints. Failed exports do not
replace an existing snapshot. Reads verify checksums and reject snapshots older
than 72 hours. The original route-scoring stack was not modified.

Google Sheet imports and web snapshot publication are now scheduled weekly through Codex.
The Tableau source connection is still pending. `google-sheets/Code.gs` and its optional manifest
are prepared for later use. No Apps Script trigger has been installed or authorized.
If enabled as an alternative later, its weekly import runs Monday during the 9 AM hour in America/Los_Angeles,
stages the complete dataset before copying it in one operation, and clears any old
tail by copying blank staging rows. It does not store credentials. Tableau Public's
Google Sheets extract refresh is a separate daily schedule, not a live feed.

Preserving existing charts while replacing CSV with Google Sheets requires Tableau
Desktop; the web editor does not support the general Replace Data Source operation.
Use the free Mac Public Edition for that one-time replacement when automatic refresh
is desired. After publishing, enable the Google Sheets data-sync option and verify
refreshes rather than assuming they are enabled.

## Manual snapshot refresh

```sh
python3 scripts/export_tableau_data.py
```

This downloads and checks the current AWS CSV and matching area-summary snapshot
before rebuilding the web app. Upload the same CSV to Tableau and republish when you want Tableau to match.
The main README is unchanged.

Sources: [dispatch data](https://data.sf.gov/Public-Safety/Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t),
[Tableau data-source replacement](https://help.tableau.com/current/pro/desktop/en-us/connect_basic_replace.htm),
[Tableau Public refresh limitations](https://help.tableau.com/current/pro/desktop/en-us/public_faq.htm).

## Weekly dashboard updates

Dashboard updates are scheduled for Mondays at 9 AM America/Los_Angeles through a Codex thread automation. Each run validates the latest AWS CSV and matching summary, updates the existing Google Sheet Incidents tab without changing its 14-field schema, refreshes the checked-in web snapshot, builds and deploys the frontend, and commits/pushes only refresh files. RefreshInfo records the imported snapshot and published status. Preserve previous data if validation or publication fails, and report any blocked step without claiming a successful refresh.

The AWS export producer remains daily and the route safety engine keeps its existing frequent refresh. Weekly publication currently keeps the last 72 hours of dispatch records; it is not a seven-day historical archive. Codex scheduled runs require the desktop host and connected tools to be available. The optional Apps Script installer is now installWeeklyRefresh, Monday during the 9 AM hour. It is prepared but has not been installed or owner-authorized; do not enable it alongside the Codex automation.

Tableau's published CSV extract does not automatically change when the website or Google Sheet changes. Connect the workbook to the Incidents tab once, preserve field names and all-sheet coordinate filters, and enable its Google Sheets data-sync option. Tableau may check that Sheet daily, but its source data changes weekly. Until this is completed, the website/Sheet update schedule does not imply that Tableau is refreshing.
