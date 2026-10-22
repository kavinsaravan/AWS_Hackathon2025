# Build, AWS verification and frontend cleanup

Verified October 21, 2026 at approximately 7:43 PM America/Los_Angeles (October 22 at 02:43 UTC).

## Production build and offline checks

`npm ci --no-audit --no-fund` completed using the checked-in package lock. `CI=true npm run build` compiled successfully after the cleanup. The output is in the ignored `build/` directory. The toolchain reported old browser compatibility data and dependency deprecation notices; no compilation failure occurred.

All 107 offline tests passed:

```sh
python3 -B -m unittest discover -s backend/tests
python3 -B -m unittest discover -s scripts/tests
node --test backend/graphhopper-proxy/proxy.test.mjs scripts/test_route_integration.cjs scripts/test_analytics_services.cjs scripts/test_sheets_importer.cjs scripts/test_hotspot_client.cjs
```

This comprises 36 backend Python tests, 44 tooling Python tests and 27 Node tests. Four new Node tests verify that the archived optional hotspot client propagates missing configuration, HTTP and network failures, and preserves successful empty results without simulated incidents.

## Live verification

AWS CLI checks in `us-east-1` confirmed the following:

| Function | State | Last update | Runtime |
| --- | --- | --- | --- |
| ApiDataFetcher | Active | Successful | Python 3.11 |
| SafePathGraphHopperProxy | Active | Successful | Node.js 24 |
| SafePathDailyAnalytics | Active | Successful | Python 3.11 |

The hourly legacy fetch rule, five-minute safety snapshot rule and daily 09:00 UTC analytics rule were all enabled. DynamoDB safety metadata showed 2,608 police calls and 6,446 open 311 reports, fetched at `2026-10-22T02:40:37.635574+00:00`.

The public website returned HTTP 200. A representative walking-route comparison from Ferry Building to Union Square successfully exercised both backend geocoding requests, the routing proxy and the Python scorer. GraphHopper returned two alternatives with 50 and 37 coordinates. The scoring response used a snapshot 184 seconds old, reported 807 police calls and 1,518 open 311 records within the combined route-area bounds, and returned valid indices under `incident-distance-time-v2`.

The AWS analytics CSV checksum matched its manifest and its 2,535 records matched the summary count. Its refresh timestamp was `2026-10-21T09:00:30.855027+00:00`.

The website's published analytics CSV checksum also matched its manifest; its 2,435 records and `2026-10-20T09:00:30.914973+00:00` timestamp matched the summary. All three published snapshot files matched the local checkout byte for byte. The website intentionally publishes a separate weekly snapshot, so it can differ from the latest daily AWS export.

These were point-in-time account/configuration reads and representative HTTP checks. They do not establish a historical error rate, every route's behavior, or a service-level guarantee. No AWS configuration repair was necessary based on these results. No deployment or schedule change was made.

## Cleanup

Twelve unreferenced frontend files were moved from the application `src/` tree into `legacy/frontend/src/`, preserving their original directory structure. This includes the logistic models, broader analyzer/optimizer/data collector, optional hotspot UI/client, unused route components and old mock fixtures. They remain available for reference but no longer participate in the frontend TypeScript compilation. See [the archive guide](../legacy/frontend/README.md) before restoring them.

The archived hotspot client's simulated incident fallback was removed. Missing configuration and failed requests now reject instead of inventing data. The backend hotspot implementation and deployed HotspotDetector function were preserved; the current route comparison screen does not use them.
