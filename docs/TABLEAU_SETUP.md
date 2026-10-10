# SafePath Tableau Public dashboard

The React app now supports Tableau Public's Embedding API v3. It keeps the existing
crime charts and shows an actual Tableau visualization beneath them only after a
published view URL is configured. A Tableau account alone does not create a dashboard.
No dashboard has been published or rendered in the user's account yet.

## Build the dashboard in your Mac browser

1. Download [sf-crime-incidents.csv](https://aws-hackathon2025.vercel.app/tableau/sf-crime-incidents.csv).
   This contains 21,460 mapped police report rows from the existing 90-day snapshot.
   The refresh timestamp is included in every row and in `public/tableau/manifest.json`.
   This is public DataSF data, without user-entered addresses or saved routes.
2. Sign in to [Tableau Public](https://public.tableau.com/), choose **Create → Web Authoring**,
   and upload the CSV as a text file. Create an extract if prompted.
3. Check the data types: `Latitude` and `Longitude` are decimal numbers, `EventDate`
   is a date, `LocalTimestamp` is a date/time, `RecordCount` is a whole number, and
   `RecordKey` / `ExternalId` are strings. Treat `SnapshotUTC` as text for its label.
   Keep the coordinate field captions exactly **Latitude** and **Longitude**.
4. Build these worksheets, all from the same data source:
   - **Crime map:** set Latitude/Longitude geographic roles to Latitude/Longitude;
     use them on Rows/Columns, put RecordKey on Detail and Category on Color.
     Keep aggregation only where it preserves individual record locations.
   - **Crime categories:** Category on Rows, SUM(RecordCount) on Columns, descending
     sort, horizontal bars in purple.
   - **Reports over time:** EventDate as continuous day on Columns and
     SUM(RecordCount) on Rows, with a teal line.
   - **Reports by neighborhood:** Neighborhood on Rows, SUM(RecordCount) on Columns.
   - **Mapped records:** SUM(RecordCount) on Text.
   - **Unique incidents:** COUNTD(ExternalId) on Text. One incident can have multiple
     category/report rows, so this differs from the mapped-record count.
5. Configure numeric **range-of-values** filters for raw Latitude and Longitude
   (not generated Latitude/Longitude fields or SUM/AVG coordinate measures). If
   necessary, convert each raw coordinate to a continuous dimension,
   keeping its caption Latitude/Longitude. Apply both filters to **all worksheets
   using this data source**. Initially include the full numeric range.
   Do not substitute a neighborhood filter for coordinates: the app passes route
   bounding-box ranges to these exact fields, including worksheets without a map.
6. Create a dashboard named **CrimeDashboard**, with the two KPI sheets at the top,
   map and categories in the middle, and time/neighborhood charts beneath. Set its
   sizing to Automatic or an appropriate responsive range. Add Category, Neighborhood,
   and EventDate controls, applying them to all related worksheets. Add a caption
   stating this is a historical snapshot, with reporting delays and approximate areas.
7. Publish as **SafePathSF**. Copy the view's Share link. It should look like
   `https://public.tableau.com/views/SafePathSF/CrimeDashboard` or
   `https://public.tableau.com/app/profile/YOUR_PROFILE/viz/SafePathSF/CrimeDashboard`.
   A profile link or web-editor link will not work.

This guide specifies the workbook to create; it is not evidence that a native
Tableau workbook has already been built or validated. Browser control currently
cannot access the signed-in account. The final published workbook still needs
live verification for its numeric filters and responsive layout.

## Connect and verify

- For a local preview, open the gear button **Dashboard settings** in SafePath,
  paste the published dashboard URL, and save. This stores the view URL in that
  browser only. The dashboard appears after a successful route calculation.
- For all visitors, set `REACT_APP_TABLEAU_VIEW_URL` to that published URL at build
  time, rebuild, and redeploy. Do not store passwords, cookies, or access tokens.
- Test two different SF journeys, switch route alternatives, and use **All SF** /
  **Route area**. All dashboard sheets must respond to coordinate changes. The
  app hides the view while filters are updating or if they fail, so an unfiltered
  citywide view is not mislabeled as the selected route area.
- Tableau Public views require no visitor sign-in. The link **Open SF overview in
  Tableau** deliberately opens the published overview without the app's route filters.
- Route safety scores still come from AWS and are displayed in the app. They are
  not measures from Tableau's historical incident dataset.

## Refresh

```sh
python3 scripts/export_analytics_data.py
python3 scripts/build_area_analytics.py
python3 scripts/export_tableau_data.py
npm run build
```

Deploy the updated public data, then update and republish the Tableau data extract.
CSV uploads do not automatically refresh in Tableau Public. Area changes filter
that extract and do not update the source snapshot.

## Checks

```sh
node --test scripts/test_tableau_services.cjs scripts/test_analytics_services.cjs scripts/test_route_integration.cjs
python3 -m unittest discover -s scripts/tests -q
```

The tests verify URL parsing, worksheet filters, citywide clearing, rapid route
changes, failure handling, and export scope. They do not validate a user's published
workbook. The main repository README has intentionally not been changed.

Sources: [web authoring](https://help.tableau.com/current/pro/desktop/en-us/getstarted_web_authoring.htm),
[API loading](https://help.tableau.com/current/api/embedding_api/en-us/docs/embedding_api_get.html),
[worksheet filtering](https://help.tableau.com/current/api/embedding_api/en-us/docs/embedding_api_filter.html),
[Public data/refresh limitations](https://help.tableau.com/current/pro/desktop/en-us/public_faq.htm).
