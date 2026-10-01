# Crime Hotspot Detection - Implementation Guide

## Overview

This guide walks you through implementing the **Crime Hotspot Detection** feature using DBSCAN clustering to identify and visualize unsafe areas on the SafePath map.

**Feature Benefits**:
- ✅ Data Science component (DBSCAN/K-means clustering)
- ✅ Clean separation from routing logic
- ✅ Visual impact on user safety awareness
- ✅ Uses existing crime data (no new APIs needed)
- ✅ Optional map layer (doesn't interfere with routes)

---

## Architecture

```
Crime Data (DynamoDB)
         ↓
    DBSCAN Clustering
         ↓
    Hotspot Metadata
    (center, radius, severity)
         ↓
    Lambda API Endpoint
    GET /hotspots
         ↓
    React Frontend
         ↓
    Leaflet Map Layer
    (Red circles with popups)
```

---

## Step-by-Step Implementation

### Phase 1: Backend Setup (Python)

#### 1.1 Install Dependencies

```bash
cd backend

# Install scikit-learn for clustering
pip install scikit-learn

# Or install all requirements
pip install -r requirements.txt
```

**Verify Installation**:
```bash
python3 -c "from sklearn.cluster import DBSCAN; print('✅ scikit-learn installed')"
```

#### 1.2 Test Clustering Algorithm Locally

Run the test script to verify DBSCAN works with real SF crime data:

```bash
cd scripts

# Run test script
python3 test_hotspot_detection.py
```

**Expected Output**:
```
🧪 SafePath Hotspot Detection Test Suite
============================================================
📞 Fetching crime data from SF Open Data...
✅ Got 468 crime incidents

============================================================
Testing DBSCAN (eps=0.3km, min_samples=5)
============================================================

📊 Results:
  Total clusters found: 12
  Noise points (isolated incidents): 89
  Hotspots identified: 12

🔥 Top 5 Hotspots:

  1. Hotspot #3
     Location: 37.7849, -122.4186
     Incidents: 45
     Radius: 0.287 km
     Risk Level: High (severity: 2.73)
     Top Crime: FIGHT NO WEAPON (22 incidents)

  2. Hotspot #7
     Location: 37.7621, -122.4350
     Incidents: 38
     ...
```

**Review GeoJSON**:
- Files saved to `/public/hotspots-dbscan.geojson`
- Visualize at https://geojson.io (drag & drop file)

#### 1.3 Tune Parameters

Adjust DBSCAN parameters based on your needs:

| Parameter | Default | Purpose | Effect |
|-----------|---------|---------|--------|
| `eps_km` | 0.3 | Max distance between points (km) | Larger = bigger hotspots |
| `min_samples` | 5 | Min incidents to form hotspot | Larger = stricter clusters |

**Example Tuning**:
```python
# More granular hotspots (smaller, denser)
detector = HotspotDetector(eps_km=0.2, min_samples=8)

# Broader hotspots (larger areas)
detector = HotspotDetector(eps_km=0.5, min_samples=3)
```

---

### Phase 2: AWS Lambda Deployment

#### 2.1 Package Lambda Function

```bash
cd backend

# Create deployment package directory
mkdir -p lambda-package

# Install Python dependencies
pip install -r requirements.txt -t lambda-package/

# Copy function code
cp hotspot_detection.py lambda-package/
cp lambda_hotspots.py lambda-package/

# Create ZIP file
cd lambda-package
zip -r ../lambda-hotspots-deployment.zip .
cd ..
```

#### 2.2 Create New Lambda Function (Option A: AWS Console)

1. Go to AWS Lambda Console
2. Click **Create Function**
3. Configure:
   - **Name**: `HotspotDetector`
   - **Runtime**: Python 3.11
   - **Architecture**: x86_64
   - **Memory**: 512 MB (clustering needs more RAM)
   - **Timeout**: 60 seconds
   - **Execution Role**: Use existing `LambdaExecutionRole` (from SafePath)

4. **Upload Code**:
   - Select "Upload from" → ".zip file"
   - Upload `lambda-hotspots-deployment.zip`
   - Set Handler: `lambda_hotspots.lambda_handler`

5. **Environment Variables**:
   ```
   DYNAMODB_TABLE_NAME=ApiDataCache
   ```

6. Click **Deploy**

#### 2.3 Add Lambda Function via CloudFormation (Option B: IaC)

Add to `infrastructure/cloudformation-template.yaml`:

```yaml
# Add after existing ApiDataFetcherLambda
HotspotDetectorLambda:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: HotspotDetector
    Runtime: python3.11
    Handler: lambda_hotspots.lambda_handler
    Timeout: 60
    MemorySize: 512
    Role: !GetAtt LambdaExecutionRole.Arn
    Environment:
      Variables:
        DYNAMODB_TABLE_NAME: !Ref ApiDataCacheTable
    Code:
      ZipFile: |
        # Placeholder - deploy actual code via S3
        def lambda_handler(event, context):
            return {'statusCode': 200}
```

#### 2.4 Add API Gateway Route

Add to CloudFormation:

```yaml
# Add new route
GetHotspotsRoute:
  Type: AWS::ApiGatewayV2::Route
  Properties:
    ApiId: !Ref ApiGateway
    RouteKey: 'GET /hotspots'
    Target: !Sub 'integrations/${HotspotIntegration}'

# Add integration
HotspotIntegration:
  Type: AWS::ApiGatewayV2::Integration
  Properties:
    ApiId: !Ref ApiGateway
    IntegrationType: AWS_PROXY
    IntegrationMethod: POST
    IntegrationUri: !Sub 'arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${HotspotDetectorLambda.Arn}/invocations'
    PayloadFormatVersion: '2.0'

# Add permission
HotspotLambdaPermission:
  Type: AWS::Lambda::Permission
  Properties:
    FunctionName: !Ref HotspotDetectorLambda
    Action: lambda:InvokeFunction
    Principal: apigateway.amazonaws.com
    SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${ApiGateway}/*/*/*'
```

#### 2.5 Test Lambda Endpoint

```bash
# Get your API endpoint
export API_ENDPOINT="https://{api-id}.execute-api.us-east-1.amazonaws.com/prod"

# Test hotspot endpoint
curl "${API_ENDPOINT}/hotspots?eps=0.3&min_samples=5&algorithm=dbscan&format=geojson"
```

**Expected Response**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-122.4186, 37.7849]
      },
      "properties": {
        "id": 1,
        "radius_km": 0.287,
        "incident_count": 45,
        "severity_score": 2.73,
        "risk_level": "High",
        "color": "#ef4444",
        ...
      }
    }
  ]
}
```

---

### Phase 3: Frontend Integration

#### 3.1 Update Route Map Component

Modify `src/components/route-map.tsx` to include hotspot layer:

```typescript
import { HotspotLayer } from '@/components/hotspot-layer'
import { useState } from 'react'
import type { HotspotGeoJSON } from '@/services/hotspotService'

export function RouteMap({ routes, selectedRouteId }) {
  const [hotspots, setHotspots] = useState<HotspotGeoJSON | null>(null)
  const [hotspotsVisible, setHotspotsVisible] = useState(false)

  return (
    <div className="relative">
      <MapContainer
        center={[37.7749, -122.4194]}
        zoom={13}
        style={{ height: '500px', width: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='© OpenStreetMap contributors'
        />

        {/* Existing route polylines */}
        {routes.map(route => (
          <Polyline key={route.id} positions={route.coordinates} ... />
        ))}

        {/* NEW: Hotspot layer */}
        {hotspots && (
          <HotspotLayer
            hotspots={hotspots}
            visible={hotspotsVisible}
          />
        )}
      </MapContainer>

      {/* Pass callbacks to parent */}
      <HotspotControls
        onHotspotsChange={setHotspots}
        onVisibilityChange={setHotspotsVisible}
      />
    </div>
  )
}
```

#### 3.2 Add Hotspot Toggle to Sidebar

Modify `src/components/safe-path-app.tsx`:

```typescript
import { HotspotToggle } from '@/components/hotspot-toggle'
import { useState } from 'react'

export function SafePathApp() {
  const [hotspots, setHotspots] = useState(null)
  const [hotspotsVisible, setHotspotsVisible] = useState(false)

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      {/* Left Sidebar */}
      <div className="lg:col-span-1 space-y-4">
        <RouteInputCard ... />
        <RouteSelectionCard ... />

        {/* NEW: Hotspot Toggle */}
        <HotspotToggle
          onHotspotsChange={setHotspots}
          onVisibilityChange={setHotspotsVisible}
        />
      </div>

      {/* Map */}
      <div className="lg:col-span-2">
        <RouteMap
          routes={routes}
          selectedRouteId={selectedRouteId}
          hotspots={hotspots}
          hotspotsVisible={hotspotsVisible}
        />
      </div>
    </div>
  )
}
```

#### 3.3 Configure Environment Variable

Add to `.env`:

```bash
# Existing
REACT_APP_GRAPHHOPPER_API_KEY=your_key_here
REACT_APP_API_ENDPOINT=https://{api-id}.execute-api.us-east-1.amazonaws.com/prod
```

Verify `REACT_APP_API_ENDPOINT` points to your AWS API Gateway.

---

### Phase 4: Testing

#### 4.1 Local Frontend Testing

```bash
cd /Users/kavins/Projects/AWS_Hackathon2025

# Start development server
npm start
```

**Test Checklist**:
- [ ] "Crime Hotspots" card appears in sidebar
- [ ] Click "Show" button
- [ ] Red/orange/yellow circles appear on map
- [ ] Hover over circle → tooltip shows risk level
- [ ] Click circle → popup shows detailed statistics
- [ ] Click "Hide" button → circles disappear
- [ ] Click "Refresh Hotspots" → data reloads

#### 4.2 Algorithm Validation

**Sanity Checks**:
1. **Hotspot Locations Match Crime Patterns**:
   - Tenderloin (37.78°, -122.41°) should be high-risk
   - Financial District may have clusters during business hours
   - Mission District typically has multiple hotspots

2. **Risk Levels Make Sense**:
   - Areas with robbery/assault → High risk (red)
   - Areas with theft/vandalism → Medium risk (orange)
   - Areas with suspicious activity → Low risk (yellow)

3. **Cluster Sizes Are Reasonable**:
   - Radius should be 0.1-0.5 km (not 5 km)
   - Incident counts: 5-50 per hotspot (not 200+)

---

### Phase 5: Optimization

#### 5.1 Add Caching (Optional)

Create `HotspotCache` DynamoDB table:

```yaml
HotspotCacheTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: HotspotCache
    AttributeDefinitions:
      - AttributeName: cache_key
        AttributeType: S
    KeySchema:
      - AttributeName: cache_key
        KeyType: HASH
    BillingMode: PAY_PER_REQUEST
    TimeToLiveSpecification:
      AttributeName: ttl
      Enabled: true
```

Modify `lambda_hotspots.py`:

```python
# Check cache first
cache_key = f"hotspots_dbscan_{eps_km}_{min_samples}"
cached = get_from_cache(cache_key)

if cached:
    return cached

# Calculate hotspots
result = calculate_hotspots(...)

# Store in cache (6-hour TTL)
store_in_cache(cache_key, result, ttl=21600)

return result
```

#### 5.2 Add Loading States

In `hotspot-toggle.tsx`:

```typescript
{loading && (
  <div className="animate-pulse">
    <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
  </div>
)}
```

---

## API Reference

### GET /hotspots

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `eps` | float | 0.3 | DBSCAN epsilon (km) |
| `min_samples` | int | 5 | Minimum incidents per hotspot |
| `algorithm` | string | `dbscan` | `dbscan` or `kmeans` |
| `format` | string | `geojson` | `geojson` or `json` |

**Example Requests**:

```bash
# Default parameters
GET /hotspots

# Stricter clustering (larger hotspots)
GET /hotspots?eps=0.5&min_samples=10

# K-means for comparison
GET /hotspots?algorithm=kmeans

# Full data (not just GeoJSON)
GET /hotspots?format=json
```

**Response Format** (`format=geojson`):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-122.4186, 37.7849]
      },
      "properties": {
        "id": 1,
        "radius_km": 0.287,
        "incident_count": 45,
        "severity_score": 2.73,
        "risk_level": "High",
        "color": "#ef4444",
        "top_crimes": [
          {"type": "ROBBERY", "count": 15},
          {"type": "ASSAULT", "count": 12}
        ],
        "description": "High risk area with 45 incidents. Most common: ROBBERY."
      }
    }
  ]
}
```

---

## Troubleshooting

### Issue: No hotspots found

**Cause**: Parameters too strict (eps too small or min_samples too large)

**Fix**:
```bash
# Relax parameters
GET /hotspots?eps=0.5&min_samples=3
```

### Issue: Lambda timeout

**Cause**: Too many crime records to process

**Fix**:
1. Increase Lambda timeout to 90 seconds
2. Increase Lambda memory to 1024 MB
3. Add sampling: only analyze recent crimes

### Issue: Circles not showing on map

**Check**:
1. Browser console for errors
2. Verify `REACT_APP_API_ENDPOINT` is set
3. Check CORS headers in Lambda response
4. Verify hotspots state is populated: `console.log(hotspots)`

---

## Next Steps

### Short-term Enhancements
1. **Time-based Hotspots**: Separate analysis for day vs. night
2. **Historical Trends**: Track how hotspots change week-over-week
3. **Export Feature**: Download hotspots as GeoJSON/CSV

### Advanced Features
4. **Predictive Hotspots**: Use time-series forecasting to predict future hotspots
5. **Hotspot Alerts**: Notify users if their route passes through a hotspot
6. **Comparison View**: Side-by-side DBSCAN vs. K-means

---

## Algorithm Details

### DBSCAN Parameters Explained

**Epsilon (eps)**:
- Defines neighborhood radius
- In km (converted to degrees: `eps / 111`)
- Smaller = tighter clusters
- Recommended: 0.2-0.5 km for urban areas

**Min Samples**:
- Minimum points to form a core point
- Higher = stricter (fewer but denser hotspots)
- Lower = more permissive (more but smaller hotspots)
- Recommended: 5-10 for crime data

**How DBSCAN Works**:
1. Pick a random point P
2. Find all points within `eps` distance
3. If ≥ `min_samples` neighbors → P is core point (start cluster)
4. Recursively add all density-reachable points
5. Points not in any cluster = noise (isolated incidents)

**Advantages**:
- ✅ Discovers arbitrary-shaped clusters (real crime patterns)
- ✅ Handles noise/outliers (isolated incidents)
- ✅ No need to specify number of clusters
- ✅ Deterministic (same results every time)

---

## Cost Estimate

**AWS Costs** (1000 daily users, each viewing hotspots once):

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Lambda (HotspotDetector) | 30K invocations × 2s × 512MB | $0.40 |
| DynamoDB (HotspotCache) | Optional caching | $0.10 |
| **Total** | | **$0.50/month** |

**Why so cheap?**
- Hotspots calculated from existing cached crime data
- Results can be cached for 6 hours
- Lightweight clustering algorithm (DBSCAN is O(n log n))

---

## References

- DBSCAN Algorithm: [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html)
- GeoJSON Specification: [RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)
- Leaflet Circle API: [Leaflet docs](https://leafletjs.com/reference.html#circle)

---

**Implementation Complete! 🎉**

You now have a production-ready crime hotspot detection feature using DBSCAN clustering.
