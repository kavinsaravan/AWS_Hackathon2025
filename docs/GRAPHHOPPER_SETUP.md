# GraphHopper routing through AWS

SafePath sends addresses and SF walking-route endpoints to API Gateway. SafePathGraphHopperProxy authenticates to GraphHopper using its server-only GRAPHHOPPER_API_KEY environment variable. The browser receives coordinates and route geometry; AWS /score-routes continues to rank the alternatives using incident data.

## Configuration

- Lambda: SafePathGraphHopperProxy, us-east-1, Node.js 24.x, index.handler, timeout 25 seconds, memory 256 MB. No VPC or Function URL is needed.
- Set GRAPHHOPPER_API_KEY under the Lambda configuration. Use a replacement key and revoke any exposed key through GraphHopper. Do not paste credentials into source, a command argument, or logs.
- Frontend configuration contains only REACT_APP_API_ENDPOINT and REACT_APP_TABLEAU_VIEW_URL. Do not use REACT_APP_GRAPHHOPPER_API_KEY; React build variables are public.
- .env.production remains local and ignored. Vercel's build configuration does not contain a routing key.

## Deploy

Run `python3 scripts/deploy_graphhopper_proxy.py` with authorized AWS credentials. This updates the existing console-created Lambda, migrates a legacy REACT_APP_GRAPHHOPPER_API_KEY variable to the backend-only name, backs up code/configuration to a private temporary directory, and creates or updates:

- POST /routing/geocode: JSON `{ "address": "Ferry Building" }`
- POST /routing/route: JSON `{ "origin": { "lat": 37.79, "lng": -122.39 }, "destination": { "lat": 37.78, "lng": -122.41 } }`

The new routes use the existing prod stage with automatic deployments. Lambda invocation permission is scoped to POST /routing/*. Each route is throttled to 2 requests/second with a burst of 10. These console-created resources are managed by this script separately from the existing backend CloudFormation stack.

The proxy accepts only bounded requests and SF coordinates, fixes the upstream host, walking profile and number of alternatives, and returns only the required coordinates/distance/time. It never relays or logs upstream error payloads or authenticated URLs. Origin checks are an extra browser restriction, not authentication: the endpoints remain public and API Gateway throttling reduces bursts rather than imposing a daily quota. Monitor GraphHopper usage and adjust limits for traffic.

## Test

`node --test backend/graphhopper-proxy/proxy.test.mjs scripts/test_route_integration.cjs`

Test a production journey from Union Square to Ferry Building. Browser requests should go to the AWS /routing endpoints and /score-routes, with no GraphHopper key or direct GraphHopper request. A backend or provider failure should show an error without simulated routes or scores.
