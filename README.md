# SafePath - AI-Powered Pedestrian Safety Routing

SafePath helps pedestrians find the safest walking routes in San Francisco by analyzing real-time crime data, infrastructure hazards, and temporal patterns to recommend routes that prioritize personal safety.

## Problem Statement

Traditional navigation apps optimize for speed and distance but ignore critical safety factors:
- Recent crime incidents in the area
- Broken streetlights and poor visibility
- Time-of-day risks (e.g., walking at night)
- Active police calls and ongoing incidents
- Infrastructure hazards (blocked sidewalks, construction, encampments)

**SafePath solves this** by combining real-time safety data with intelligent routing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Web App (React)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                   AWS API Gateway                           │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ↓                     ↓
┌──────────────────┐  ┌──────────────────┐
│  AWS Lambda      │  │   DynamoDB       │
│  (Python 3.11)   │  │  (3-day cache)   │
└──────────────────┘  └──────────────────┘
          ↓                     ↓
┌──────────────────┐  ┌──────────────────┐
│  Risk Analysis   │  │     AWS S3       │
│   Algorithm      │  │  (Data backup)   │
└──────────────────┘  └──────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│          San Francisco Open Data APIs (DataSF)              │
│  • Police Dispatch (gnap-fj3t) - 5-min refresh              │
│  • 311 Service Requests (vw6y-z8j6) - Real-time             │
│  • 2M+ datasets available (4 actively used)                 │
└─────────────────────────────────────────────────────────────┘

GitHub Actions (Weekly Dashboard Refresh)
          ↓
┌─────────────────────────────────────────────────────────────┐
│  72-hour Analytics Export (CSV + JSON) → public/            │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Tech Stack

### Backend (AWS Serverless)
- **AWS Lambda** - Python 3.11 & Node.js serverless functions
- **DynamoDB** - Caches API data with 3-day TTL
- **S3** - Backup storage for crime/hazard data
- **API Gateway v2** - HTTP API endpoints with CORS
- **EventBridge** - 5-min safety refresh, daily analytics export
- **CloudFormation** - Infrastructure as Code
- **CloudWatch** - Logging and monitoring

### Frontend (Web App)
- **React 19.2** - Modern web framework
- **TypeScript 4.9** - Type-safe JavaScript
- **Leaflet 1.9 / React Leaflet 5** - Interactive maps
- **Recharts 2.15** - Data visualization (Crime Analytics Dashboard)

### Machine Learning (Available for Training/Analysis)
- **Logistic Regression** - Route preference prediction
- **Multi-factor Safety Analyzer** - 6-dimension risk scoring
- **DBSCAN Clustering** - Crime hotspot detection
- **K-means Clustering** - Alternative clustering comparison
- **scikit-learn** - Machine learning algorithms
- **NumPy + Pandas** - Data processing
- **Geopy** - Geospatial calculations

### Data Sources (All Free)
- **SF Crime Data (gnap-fj3t)** - data.sfgov.org, 5-min refresh
- **311 Service Requests (vw6y-z8j6)** - Real-time updates
- **GraphHopper API** - Routing and geocoding (free tier)
- **2M+ DataSF datasets available** (4 actively used)

## ✨ Key Features

### 🛡️ Intelligent Safety Scoring
- **Physics-inspired risk algorithm** with time and distance decay
- **3-tier incident classification**: High (robbery, assault), Medium (theft), Low (suspicious activity)
- **Multi-factor analysis**: Environmental (25%), Social (20%), Infrastructure (15%), Temporal (15%), Crime (15%), Real-time (10%)

### 🗺️ Route Comparison
- **Up to 3 distinct route alternatives**:
  - **Lowest Reported Risk** (green) - Lowest incident risk among returned candidates
  - **Alternative Route** (blue) - Additional candidate for comparison
  - **Fastest Route** (amber, or green if also lowest risk) - Lowest travel time among returned candidates
- Side-by-side comparison with metrics
- Visual map display with color-coded routes

### 📊 Crime Analytics Dashboard
- **72-hour police dispatch data visualization**
- **Interactive bar charts** showing most reported call types by category
- **Route-area vs citywide toggle** for contextual comparison
- **Real-time incident metrics** with Recharts visualization
- **Category-based analysis** of crime patterns

### 📊 Real-Time Data Integration
- **Hourly crime data refresh** via Lambda automation
- **15-minute 311 hazard updates**
- **5-minute active police call updates**
- **3-day DynamoDB cache** with automatic TTL
- **SHA256 deduplication** to prevent duplicates

### Machine Learning Models
- **30+ input features**: User profile, route characteristics, temporal factors
- **Binary classification**: Predicts user route preference
- **Comprehensive analyzer**: 6 risk dimensions with specific warnings

### 🔴 Crime Hotspot Detection
- **DBSCAN clustering algorithm**: Identifies statistically significant clusters of unsafe areas
- **Risk-level classification**: Auto-classifies hotspots as High/Medium/Low based on severity
- **Interactive visualization**: Click hotspots on map for detailed crime breakdown
- **Configurable parameters**: Adjust cluster size (eps) and density (min_samples)
- **Real-time updates**: Hotspots recalculated from latest crime data
- **Optional map layer**: Toggle visibility without affecting route display

## 🔌 API Endpoints

The backend exposes the following REST API endpoints via AWS API Gateway v2:

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| `POST` | `/routing/geocode` | Node.js Lambda | Address → SF coordinates (GraphHopper) |
| `POST` | `/routing/route` | Node.js Lambda | Coordinates → Walking paths (GraphHopper) |
| `POST` | `/score-routes` | Python Lambda | **Main feature**: Score routes for safety |
| `GET` | `/analytics.csv` | Python Lambda | Daily dispatch CSV export (gzipped) |
| `GET` | `/analytics-summary` | Python Lambda | Daily analytics summary (JSON) |
| `GET` | `/analytics-manifest` | Python Lambda | Analytics metadata & schema |
| `POST` | `/fetch-new` | Python Lambda | Legacy generic API ingestion |
| `GET` | `/data` | Python Lambda | Legacy cached data retrieval |

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ / npm or yarn
- Python 3.11+ (for backend)
- AWS Account (Free Tier eligible)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/kavinsaravan/AWS_Hackathon2025.git
   cd AWS_Hackathon2025
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Add your API keys to .env
   ```

4. **Generate safety datasets** (optional)
   ```bash
   cd scripts
   python generate_production_dataset.py
   ```

### Running the App

**Development Mode:**
```bash
npm start
```

The app will open in your default browser at `http://localhost:3000`

**Production Build:**
```bash
npm run build
```

### AWS Backend Deployment

1. **Create S3 bucket for Lambda deployment and data backups**
   ```bash
   export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   aws s3 mb s3://safepath-crime-data-${AWS_ACCOUNT_ID} --region us-east-1
   aws s3api put-bucket-versioning --bucket safepath-crime-data-${AWS_ACCOUNT_ID} --versioning-configuration Status=Enabled
   ```

2. **Package Lambda functions**
   ```bash
   # Package routing backend (Python)
   bash scripts/package_routing_backend.sh /tmp/lambda-routing.zip

   # Package daily analytics (Python)
   bash scripts/package_daily_analytics.sh /tmp/lambda-analytics.zip
   ```

3. **Deploy main infrastructure stack (DynamoDB, Lambda, API Gateway)**
   ```bash
   python3 scripts/deploy_aws_backend.py \
     --account ${AWS_ACCOUNT_ID} \
     --api-id YOUR_API_ID \
     --stack-name SafePathStack \
     --lambda-zip /tmp/lambda-routing.zip \
     --apply
   ```

4. **Deploy analytics stack**
   ```bash
   python3 scripts/deploy_daily_analytics.py --apply
   ```

5. **Deploy GraphHopper proxy (Node.js Lambda)**
   ```bash
   python3 scripts/deploy_graphhopper_proxy.py
   ```

6. **Update environment variables**
   ```bash
   # Set REACT_APP_API_ENDPOINT in .env to your API Gateway URL
   # Configure GRAPHHOPPER_API_KEY for the Node.js proxy Lambda
   ```

See `docs/DEPLOYMENT_AND_DATASETS.md` for detailed deployment instructions.

## 🧮 Safety Scoring Algorithm

The core risk calculation uses a physics-inspired formula:

```
risk_score = ReLU(w - w*t/decay_hours)² × e^(-(d²)/0.02)

Where:
  w = Risk weight (1, 2, or 3)
  t = Time since incident (hours)
  d = Distance to incident (km)
  decay_hours = 72 for high-risk, 24 for medium/low
```

**Risk Classification:**
- **Level 3 (High)**: Robbery, Assault, Weapons (72-hour decay)
- **Level 2 (Medium)**: Theft, Fights, Harassment (24-hour decay)
- **Level 1 (Low)**: Suspicious activity, Encampments (no time decay)

**Route Safety Score:**
```
total_risk = sum(calculate_risk_score(incident) for incident in nearby_incidents)
safety_score = round(100 / (1 + total_risk), 1)  # 0-100 scale
```

**Implementation Details:**
- **RouteSegmentIndex**: Spatial indexing using 0.005-degree cells for efficient lookups
- **Point-to-segment distance**: Measures distance to route line segments (not just vertices)
- **SF bounds enforcement**: 37.70-37.83 lat, -122.53 to -122.35 lng
- **1 km cutoff**: Incidents >1 km away are ignored (below detection threshold)
- **Local planar projection**: Appropriate coordinate transformation for San Francisco

## 📊 Data Pipeline

```
DataSF (2M+ files available)
    ↓
Filter to 4 essential datasets (~125MB)
    ↓
AWS Lambda (scheduled hourly)
    ↓
    ├─→ DynamoDB Cache (3-day TTL)
    └─→ S3 Backup Storage (timestamped backups)
    ↓
API Gateway → Frontend App
    ↓
ML Model Analysis
    ↓
Route Recommendations
```

## 🔑 Environment Variables

Create a `.env` file in the root directory:

```env
# GraphHopper API (for routing)
REACT_APP_GRAPHHOPPER_API_KEY=your_api_key_here

# AWS Configuration (for backend)
AWS_REGION=us-east-1
DYNAMODB_TABLE_NAME=ApiDataCache
S3_BUCKET_NAME=safepath-crime-data-{AWS_ACCOUNT_ID}

# DataSF API (optional - no key required for basic use)
DATASF_API_KEY=optional_for_higher_rate_limits

# AWS Backend API Endpoint
REACT_APP_API_ENDPOINT=https://your-api-id.execute-api.us-east-1.amazonaws.com/prod
```

## 🛠️ Development

### Generate Datasets
```bash
cd scripts
python generate_safety_dataset.py        # Full dataset
python generate_production_dataset.py    # Production-ready
python generate_binary_dataset.py        # Binary classification
```

### Run Tests
```bash
# Frontend tests
npm test

# Backend Python tests (107 total tests - all passing)
cd backend && python -m pytest tests/
cd scripts && python -m pytest tests/

# Node.js tests (27 tests)
cd backend/graphhopper-proxy && npm test
```

### Lint Code
```bash
npm run lint
```
