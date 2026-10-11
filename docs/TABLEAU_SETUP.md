# SafePath Tableau Public dashboard

Current work uses a single police-dispatch snapshot. See [dispatch snapshot setup](DISPATCH_SNAPSHOT_SETUP.md) for the new CSV, typed Google Sheet, and the pending Tableau upload. The published workbook described below still uses the earlier police-incident extract until it is republished. Automatic Google/Tableau refresh is deferred.

The published report is [SafePathSF / CrimeDashboard](https://public.tableau.com/views/SafePathSF/CrimeDashboard).
It contains three native Tableau worksheets: Crime Map, Crime Categories, and
Reports Over Time. It uses the 21,460 mapped police records in the existing 90-day
DataSF snapshot. The app keeps its original crime charts and embeds this report
below them after a successful route calculation.

## Connection and area filtering

The production view URL is configured in `.env.production` and `vercel.json` as
`REACT_APP_TABLEAU_VIEW_URL`. This makes the report available to all visitors without
Microsoft or Tableau account sign-in. Dashboard settings can override the URL for
one browser; clear its saved link and reload the page to use the configured production report again.
Only Tableau Public view/share URLs are accepted, not authoring or profile URLs.

Tableau's Embedding API v3 is loaded from the same public.tableau.com instance that
hosts the report. All three worksheets have range filters on the raw coordinate
fields named exactly **Latitude** and **Longitude**, applied to all worksheets using
the data source. When a route or alternative is selected, the app passes its padded
bounding box to each worksheet. **All SF** clears those ranges. Other report filters
remain available. Updates are serialized so a rapid route change cannot leave an
older route's bounds applied last. The view is hidden while updates run or if they
fail, avoiding a citywide report mislabeled as the selected route area.

This is a rectangular area around the route, not a precise street corridor. The
built-in summary selects intersecting grid cells, while Tableau filters individual
coordinates, so their approximate-area record counts may differ. AWS calculates
route safety scores from recent dispatch/311 reports separately; those scores are
not measures from this historical Tableau dataset.

## Verified behavior

The actual published report was checked through Tableau's documented API inside
the app, rather than only against a mocked embed. Desktop checks confirmed that
all three sheets share the selected coordinate ranges and report consistent counts:

- Golden Gate Park → Ferry Building: 12,550 report records in the selected area.
- Union Square → Ferry Building: 1,737 report records in the selected area.
- All SF: 21,460 report records, with route-area restoration and alternative-route
  switching also checked.

These counts describe the current snapshot and route geometry, not safety
probabilities. They can change after updating data or routing-provider results.
The browser checks also retain the app's two original charts. The real Phone
layout was verified at a 390-pixel viewport, with three filtered sheets and no
horizontal page overflow.

## Data and refresh

Download the [Tableau CSV](https://aws-hackathon2025.vercel.app/tableau/sf-crime-incidents.csv).
`public/tableau/manifest.json` records the source and refresh timestamp. The CSV
contains public DataSF police records without user-entered addresses or saved routes.
`SUM(Record Count)` counts report rows; `COUNTD(External Id)` would count distinct
incident IDs, which can appear in more than one category/report row.

```sh
python3 scripts/export_analytics_data.py
python3 scripts/build_area_analytics.py
python3 scripts/export_tableau_data.py
npm run build
```

Deploy the updated public exports, then update and republish the Tableau extract
through Tableau Public's web editor. CSV uploads do not automatically refresh there.
Selecting a route changes filters on the published snapshot and does not fetch new
police records. Keep the snapshot timestamp and reporting-delay context visible.

## Editing and publishing

Use Tableau Public web authoring to update the workbook. Its layout has the map
and category chart across the top and daily timeline underneath, with Automatic
sizing and a Phone device layout. Record Key must be a **dimension on Detail** for
the map, producing one mark per mapped record rather than category-average locations.
Use AVG(Longitude) on Columns and AVG(Latitude) on Rows, with Category on Color.
Keep coordinate field captions and filter ranges intact when editing the workbook.

Publish over **SafePathSF**, retain the dashboard name **CrimeDashboard**, and check
both the default and phone layouts. If either workbook or dashboard name changes,
update the production URL, rebuild, redeploy, and repeat route-filter checks.

## Checks

```sh
node --test scripts/test_tableau_services.cjs scripts/test_analytics_services.cjs scripts/test_route_integration.cjs
python3 -m unittest discover -s scripts/tests -q
```

The unit tests cover URL parsing, worksheet filters, citywide clearing, rapid route
changes, failure handling, and export scope. Live browser checks are also needed
after changing the published workbook. The main repository README is unchanged.

Sources: [web authoring](https://help.tableau.com/current/pro/desktop/en-us/getstarted_web_authoring.htm),
[API loading](https://help.tableau.com/current/api/embedding_api/en-us/docs/embedding_api_get.html),
[worksheet filtering](https://help.tableau.com/current/api/embedding_api/en-us/docs/embedding_api_filter.html),
[Public data/refresh limitations](https://help.tableau.com/current/pro/desktop/en-us/public_faq.htm).
