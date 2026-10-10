# SafePath Power BI crime analytics

This is a native Power BI Project (`SafePath.pbip`), with four report pages, six
semantic-model tables, 20 DAX measures, and Power Query CSV imports. It is distinct
from the app's built-in area-summary charts. The report definitions were checked
against Microsoft's public PBIR schemas; opening, data refresh, and visual rendering
in Power BI Desktop have not been verified on this Mac.

## Open and publish

1. Obtain access to Power BI Service using an eligible work/school account.
2. Open `SafePath.pbip` in a current Power BI Desktop installation on Windows.
   Enable PBIP/PBIR preview features if your version requires them.
3. The Power Query `DataFolder` parameter defaults to the app’s hosted CSV folder,
   `https://aws-hackathon2025.vercel.app/analytics-data/`. Use Anonymous credentials.
   The default partitions use HTTPS sources to support a browser/service workflow.
4. Click Refresh. Verify the Overview, Time patterns, Sampled risk locations, and
   Data quality pages, including native map availability in your tenant settings.
5. Publish to your Power BI workspace. Use File → Embed report → Website or portal
   to obtain the secure report URL. The app's Analytics settings accept that URL.

Power BI Service is usable in a supported Mac browser. A workspace owner can
deploy these native definitions through Fabric Git integration or Fabric REST APIs
from a Mac, then refresh the hosted CSV sources; the default data imports use
public HTTPS files instead of a local Windows file gateway. Deploying this native project
to Fabric requires workspace access and appropriate permissions; a `.pbip` file
is not a standalone browser page. Workspace access is not currently available in
this task, so the report has not been published or embedded as a live Power BI report.

## Refresh public data

```sh
python3 -m pip install -r scripts/requirements.txt
python3 scripts/export_powerbi_data.py --samples 1000
python3 scripts/build_area_analytics.py
```

The exporter updates both `powerbi/data` and `public/analytics-data`. Rebuild and
deploy the app after exporting, then refresh the Power BI semantic model to load
the updated hosted files. The timestamps remain visible so static snapshots are
not confused with a live feed.

The exporter includes police incident records from 90 days, dispatch calls from 72
hours, and open 311 reports requested in 30 days. It paginates all sources, removes
exact duplicate source record IDs, retains missing/outside-SF coordinates for data
quality counts, and writes a provenance manifest. Default date/time grouping uses
America/Los_Angeles; export timestamps are UTC. Source windows differ, so total
volumes do not represent comparable exposure or a single deduplicated event count.

Native report pages:

- Incident overview: police report volume, unique incident IDs, category breakdown,
  neighborhood centroids, date/source/neighborhood slicers.
- Time patterns: daily/hourly/weekday trends and rule-based severity categories.
- Sampled risk locations: measured feature counts and heuristic proxy labels.
- Data quality: source reconciliation, missing geocodes/times, and unknown areas.

The sampled locations are not evaluated walking routes; labels are proxies rather
than observed safety outcomes. No precision, recall, or model accuracy is claimed.

## App integration

The front page keeps two address inputs and an interactive map. After route scoring,
it shows historical area-summary charts followed by the Power BI panel. The summary
uses public aggregate data in `public/safety-analytics.json` and is labelled separately
from Power BI. Route changes update the area summary. Secure Power BI embeds receive
latitude/longitude URL filters for `Incidents` and `RiskLocations`; public Publish to
web embeds use their saved report filters instead.

Set `REACT_APP_POWER_BI_EMBED_URL` before a production build to configure the report
for all visitors, or use Analytics settings to save a connection in the current
browser. Secure reports require viewer authorization/licensing. Do not paste access
tokens or credentials; only published report/embed links are needed.

The route scorer now indexes nearby segments once per route and skips incidents
whose weight has fully decayed. Contributions beyond 1km are omitted: the upper
bound per incident is `9 * exp(-50)`, below `2e-21`. This avoids the long-route timeout
while retaining all meaningful contributions under the existing distance formula.

## Validate definitions

```sh
python3 scripts/validate_powerbi_project.py
node --test scripts/test_analytics_services.cjs
```

Microsoft schemas are cached for offline validation. See
[Power BI project documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)
and [PBIR documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report).
The main repository README is intentionally unchanged.
