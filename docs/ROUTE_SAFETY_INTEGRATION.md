# Incident-based route scoring

The browser geocodes addresses and requests walking alternatives from GraphHopper,
then posts the actual distinct paths to `POST /score-routes`. The Python endpoint
loads a shared AWS snapshot of DataSF police calls from the past 72 hours and currently open encampment /
aggressive or threatening 311 reports for San Francisco, then filters it to the route bounding box plus a buffer.
It applies the path risk engine to each candidate. No synthetic alternatives,
random metrics, or fabricated safe waypoint markers are displayed.

Risk combines severity, age, and distance to route **segments**. High-severity
incidents decay over 72 hours; others over 24 hours. Open encampment reports persist.
Naive DataSF dates use America/Los_Angeles. The index is `100 / (1 + totalRisk)`:
higher means less reported incident risk, not a calibrated probability of safety.
Routes sort by raw total risk, then travel time; the shortest-time candidate is
marked fastest. This ranks the candidates GraphHopper supplies, not every possible
path through the street network. Lighting and pedestrian traffic are not measured.

Lambda refreshes both sources every five minutes through EventBridge. S3 stores
compressed, encrypted incident snapshots; DynamoDB stores their checksum, location,
and freshness metadata. Each route request uses a snapshot at most five minutes
old and applies time decay at request time. A missing, corrupt, or expired snapshot
is refreshed on demand. Local development without AWS storage variables reads
DataSF directly. Queries use pagination, bounded sizes, and timeouts.
Source publication latency still applies; this is near-real-time incident data
with request-time scoring, not a continuous police dispatch feed. If a source fails,
returns unusable data, or exceeds the pagination limit, scoring fails with HTTP
503 rather than substituting a zero-risk score. Successful empty queries mean no
matching reports were retrieved, not proven safety. Scoring is limited to SF.

## Request and response

```json
{"routes":[{"id":1,"coordinates":[{"lat":37.7849,"lng":-122.414},{"lat":37.788,"lng":-122.41}]}]}
```

Response includes `routes` with `id`, `totalRisk`, `crimeRisk`, `hazardRisk`,
`safetyScore`, plus `assessedAt` and source record counts. Route IDs retain their
identity after sorting. Clients must set `REACT_APP_API_ENDPOINT` to the API stage.

## Deploying the change

The source changes do not update an already deployed AWS API or Vercel build.

1. Run `bash scripts/package_routing_backend.sh` to produce
   `backend/lambda-routing.zip` (requires Python/pip and package registry access).
2. Upload the ZIP to an existing S3 deployment bucket in the Lambda region.
3. Deploy/update `infrastructure/cloudformation-template.yaml`, supplying its
   existing parameters plus `LambdaDeploymentBucket`, `LambdaDeploymentKey`, and `LambdaDeploymentCodeSha256`.
   The template now uses actual packaged code and adds `POST /score-routes` to
   the existing Lambda integration. Use a new S3 key for each code revision.
   For manually managed infrastructure, update the `ApiDataFetcher` Lambda ZIP
   and create this POST route targeting its existing integration instead.
4. Rebuild/deploy the frontend with `REACT_APP_API_ENDPOINT` pointing to that API.
5. Verify a route request returns measured scores. If DataSF is unavailable the
   app deliberately shows an error instead of an unverified safety recommendation.

The route-scoring code needs requests, boto3 (provided by AWS), and Python
standard-library modules. No NumPy/scikit-learn layer is needed
for this endpoint. Hotspot deployment is separate. Optional `DATASF_API_KEY` is
read as a Socrata app token when configured on Lambda.

## Verification

```sh
python3 -B -m unittest discover -s backend/tests -v
node --test scripts/test_route_integration.cjs
npm run build
```

The Node offline service checks require Node 22.6+ for built-in TypeScript
stripping; they stub network access and exercise the production service code.
The Python suite stubs AWS and DataSF, covering segment distance, age/timezone
handling, route ordering, pagination, validation, and source failures.

## Deployment ownership and rollback

Use the CloudFormation-managed deployment procedure in
[Deployment reliability and dataset exports](DEPLOYMENT_AND_DATASETS.md).
The deployment script refuses unmanaged resources or Lambda code drift. Each
applied deployment creates a unique private backup directory, submits a guarded
stack update, warms the snapshot, and verifies the deployed code checksum. A
post-update failure restores the previous stack template and code parameters.
Rollback failures are reported with retained artifacts.

The scoring route, refresh schedule, refresh permission, and S3 bucket have been
imported into the existing stack. The Lambda code baseline points to a verified
copy of the working package in S3 rather than placeholder inline code. Fresh
stack deployments also require `LambdaDeploymentCodeSha256` alongside the
package bucket and key; `DataSfToken` remains optional.

Scoring responses include `dataFetchedAt` and `dataMode` separately from
`assessedAt`. CloudWatch receives structured `routes_scored` and
`safety_snapshot_refreshed` events. Snapshot metadata is not returned as an
incident by the legacy `/data` endpoint; expired legacy records are explicitly
filtered instead of waiting for DynamoDB's asynchronous TTL deletion.
