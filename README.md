# SafePath - AI-Powered Pedestrian Safety Routing

> Built for AWS Hackathon 2025 | A smart routing application that prioritizes pedestrian safety over speed

A web application that helps users find the safest walking routes in San Francisco by analyzing real-time crime data, infrastructure hazards, and temporal patterns to recommend routes that prioritize personal safety.

## 🎯 Problem Statement

Traditional navigation apps optimize for speed and distance but ignore critical safety factors:
- Recent crime incidents in the area
- Broken streetlights and poor visibility
- Time-of-day risks (e.g., walking at night)
- Active police calls and ongoing incidents
- Infrastructure hazards (blocked sidewalks, construction, encampments)

**SafePath solves this** by combining real-time safety data with intelligent routing.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Web App (React)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                   AWS API Gateway                            │
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
│          San Francisco Open Data APIs (DataSF)               │
│  • Crime Reports (hourly)  • 311 Hazards (15-min)           │
│  • Police Calls (5-min)    • Street Lights (daily)          │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Tech Stack

### Backend (AWS Serverless)
- **AWS Lambda** - Python 3.11 serverless functions
- **DynamoDB** - Caches API data with 3-day TTL
- **S3** - Backup storage for crime/hazard data
- **API Gateway** - REST endpoints with CORS
- **CloudWatch Events** - Hourly scheduled data refresh
- **CloudFormation** - Infrastructure as Code

### Frontend (Web App)
- **React** - Modern web framework
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first styling
- **Radix UI** - Accessible component library
- **Leaflet** - Interactive maps
- **React Leaflet** - React wrapper for Leaflet

### Machine Learning
- **Logistic Regression** - Route preference prediction
- **Multi-factor Safety Analyzer** - 6-dimension risk scoring
- **NumPy + Pandas** - Data processing
- **Geopy** - Geospatial calculations

### Data Sources (All Free)
- **SF Crime Data** - data.sfgov.org (hourly updates)
- **311 Service Requests** - 15-minute updates
- **Active Police Calls** - 5-minute real-time updates
- **Street Light Inventory** - Daily updates

## ✨ Key Features

### 🛡️ Intelligent Safety Scoring
- **Physics-inspired risk algorithm** with time and distance decay
- **3-tier incident classification**: High (robbery, assault), Medium (theft), Low (suspicious activity)
- **Multi-factor analysis**: Environmental (25%), Social (20%), Infrastructure (15%), Temporal (15%), Crime (15%), Real-time (10%)

### 🗺️ Route Comparison
- **3 route alternatives**:
  - **Safest Route** (green) - Maximizes safety score
  - **Balanced Route** (blue) - Balances safety and time
  - **Fastest Route** (amber) - Minimizes travel time
- Side-by-side comparison with metrics
- Visual map display with color-coded routes

### 📊 Real-Time Data Integration
- **Hourly crime data refresh** via Lambda automation
- **15-minute 311 hazard updates**
- **5-minute active police call updates**
- **3-day DynamoDB cache** with automatic TTL
- **SHA256 deduplication** to prevent duplicates

### 🤖 Machine Learning Models
- **30+ input features**: User profile, route characteristics, temporal factors
- **Binary classification**: Predicts user route preference
- **Comprehensive analyzer**: 6 risk dimensions with specific warnings

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

1. **Deploy CloudFormation stack**
   ```bash
   cd infrastructure
   aws cloudformation create-stack \
     --stack-name safepath-backend \
     --template-body file://cloudformation-template.yaml \
     --capabilities CAPABILITY_IAM
   ```

2. **Package Lambda functions**
   ```bash
   cd backend
   pip install -r requirements.txt -t .
   zip -r lambda_package.zip .
   ```

3. **Upload to Lambda**
   ```bash
   aws lambda update-function-code \
     --function-name ApiDataFetcher \
     --zip-file fileb://lambda_package.zip
   ```

## 📁 Project Structure

```
AWS_Hackathon2025/
├── backend/                 # AWS Lambda functions
│   ├── lambda_fetch_api.py # API data fetcher
│   ├── path_risk_analysis.py # Risk scoring engine
│   └── requirements.txt    # Python dependencies
│
├── scripts/                 # Data processing
│   ├── generate_*.py       # Dataset generation scripts
│   └── analyze_sample_coverage.py
│
├── infrastructure/          # AWS CloudFormation
│   └── cloudformation-template.yaml
│
├── docs/                    # Documentation
│   ├── API_KEYS_AND_DATA_SOURCES.md
│   ├── DATASF_IMPLEMENTATION.md
│   └── ...
│
├── src/                     # React web frontend
│   ├── components/         # React components & UI primitives
│   ├── services/           # ML models & API services
│   └── lib/                # Utility functions
│
├── public/                  # Static assets
├── .gitignore              # Git exclusions
├── package.json            # Node dependencies
└── README.md               # This file
```

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
safety_score = 100 - normalize(total_risk)  # 0-100 scale
```

## 📊 Data Pipeline

```
DataSF (2M+ files available)
    ↓
Filter to 4 essential datasets (~125MB)
    ↓
AWS Lambda (scheduled hourly)
    ↓
DynamoDB Cache (3-day TTL)
    ↓
S3 Backup Storage
    ↓
API Gateway → Mobile App
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
S3_BUCKET_NAME=my-path-risk-data

# DataSF API (optional - no key required for basic use)
DATASF_API_KEY=optional_for_higher_rate_limits
```

## 📈 Performance Metrics

- **API Response Time**: <500ms average
- **Route Calculation**: <2s for 3 routes
- **Data Freshness**:
  - Crime data: Hourly updates
  - 311 hazards: 15-minute updates
  - Police calls: 5-minute updates
- **Cache Hit Rate**: ~85% (3-day TTL)

## 🎯 Use Cases

1. **Night Commuters** - Find well-lit, populated routes
2. **Tourists** - Avoid high-crime areas while sightseeing
3. **Solo Walkers** - Prioritize safety over speed
4. **Elderly/Mobility-Impaired** - Avoid construction, broken sidewalks
5. **Parents** - Safe routes to/from schools
6. **Event-Goers** - Navigate safely after concerts, nightlife

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
npm test
```

### Lint Code
```bash
npm run lint
```



