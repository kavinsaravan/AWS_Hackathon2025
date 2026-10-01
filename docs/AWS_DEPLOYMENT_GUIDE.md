# AWS Deployment Guide - Hotspot Detection Feature

## 📦 Package Ready!

Your Lambda deployment package is created at:
```
/Users/kavins/Projects/AWS_Hackathon2025/backend/lambda-hotspots.zip
Size: 60 MB
```

---

## 🚀 Deployment Method 1: AWS Console (Easiest - 15 min)

### Step 1: Upload to S3 (Required - File >50MB)

Since the package is 60MB, you need to upload to S3 first:

```bash
# Set your AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Upload ZIP to existing S3 bucket
aws s3 cp /Users/kavins/Projects/AWS_Hackathon2025/backend/lambda-hotspots.zip \
  s3://safepath-crime-data-${AWS_ACCOUNT_ID}/lambda-packages/
```

**Expected Output**:
```
upload: lambda-hotspots.zip to s3://safepath-crime-data-{account-id}/lambda-packages/lambda-hotspots.zip
```

---

### Step 2: Create Lambda Function

1. **Go to AWS Lambda Console**:
   - URL: https://console.aws.amazon.com/lambda

2. **Click "Create function"**

3. **Configure Function**:
   ```
   Option: Author from scratch

   Basic Information:
   - Function name: HotspotDetector
   - Runtime: Python 3.11
   - Architecture: x86_64

   Permissions:
   - Execution role: Use an existing role
   - Existing role: LambdaExecutionRole
     (This is the role from your existing ApiDataFetcher Lambda)
   ```

4. **Click "Create function"**

---

### Step 3: Upload Code from S3

1. In the **Code** tab, scroll to "Code source"

2. Click **"Upload from"** dropdown → **Amazon S3 location**

3. **Enter S3 URI**:
   ```
   s3://safepath-crime-data-{YOUR_ACCOUNT_ID}/lambda-packages/lambda-hotspots.zip
   ```

4. Click **"Save"**

5. **Set Handler**:
   - Scroll to "Runtime settings"
   - Click "Edit"
   - Handler: `lambda_hotspots.lambda_handler`
   - Click "Save"

---

### Step 4: Configure Lambda Settings

1. **Go to Configuration tab** → **General configuration** → **Edit**

   ```
   Memory: 512 MB
   Timeout: 1 min 0 sec
   Ephemeral storage: 512 MB (default)
   ```

   Click **Save**

2. **Go to Configuration tab** → **Environment variables** → **Edit**

   Add variable:
   ```
   Key: DYNAMODB_TABLE_NAME
   Value: ApiDataCache
   ```

   Click **Save**

---

### Step 5: Add API Gateway Route

1. **Go to API Gateway Console**:
   - URL: https://console.aws.amazon.com/apigateway

2. **Find your API**: "ApiDataFetcherAPI"

3. **Click on the API** → **Routes**

4. **Click "Create"**:
   ```
   Method: GET
   Resource path: /hotspots
   ```

5. **Click "Create"**

6. **Attach Integration**:
   - Click on the `/hotspots` route
   - Click "Create and attach an integration"
   - Integration type: Lambda function
   - Lambda function: HotspotDetector
   - Click "Create"

7. **Deploy**:
   - Click "Deployments" in left sidebar
   - Click your stage (probably "prod")
   - It should auto-deploy

---

### Step 6: Test the Endpoint

```bash
# Get your API endpoint from API Gateway console
# It should look like: https://{api-id}.execute-api.us-east-1.amazonaws.com/prod

# Test the endpoint
curl "https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/hotspots?eps=0.3&min_samples=5"
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

## 🚀 Deployment Method 2: AWS CLI (10 min)

### Prerequisites
```bash
# Verify AWS CLI is installed and configured
aws --version
aws sts get-caller-identity
```

### Step 1: Upload to S3
```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws s3 cp /Users/kavins/Projects/AWS_Hackathon2025/backend/lambda-hotspots.zip \
  s3://safepath-crime-data-${AWS_ACCOUNT_ID}/lambda-packages/
```

### Step 2: Get IAM Role ARN
```bash
# Get the ARN of your existing Lambda execution role
export LAMBDA_ROLE_ARN=$(aws iam get-role --role-name LambdaExecutionRole --query 'Role.Arn' --output text)

echo "Lambda Role ARN: $LAMBDA_ROLE_ARN"
```

### Step 3: Create Lambda Function
```bash
aws lambda create-function \
  --function-name HotspotDetector \
  --runtime python3.11 \
  --role $LAMBDA_ROLE_ARN \
  --handler lambda_hotspots.lambda_handler \
  --code S3Bucket=safepath-crime-data-${AWS_ACCOUNT_ID},S3Key=lambda-packages/lambda-hotspots.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables="{DYNAMODB_TABLE_NAME=ApiDataCache}" \
  --region us-east-1
```

**Expected Output**:
```json
{
    "FunctionName": "HotspotDetector",
    "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:HotspotDetector",
    "Runtime": "python3.11",
    "Handler": "lambda_hotspots.lambda_handler",
    ...
}
```

### Step 4: Get API Gateway ID
```bash
# Find your API Gateway ID
export API_ID=$(aws apigatewayv2 get-apis --query 'Items[?Name==`ApiDataFetcherAPI`].ApiId' --output text)

echo "API Gateway ID: $API_ID"
```

### Step 5: Create Lambda Integration
```bash
# Get Lambda function ARN
export LAMBDA_ARN=$(aws lambda get-function --function-name HotspotDetector --query 'Configuration.FunctionArn' --output text)

# Create integration
export INTEGRATION_ID=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-method POST \
  --integration-uri $LAMBDA_ARN \
  --payload-format-version '2.0' \
  --query 'IntegrationId' \
  --output text)

echo "Integration ID: $INTEGRATION_ID"
```

### Step 6: Create Route
```bash
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key 'GET /hotspots' \
  --target integrations/$INTEGRATION_ID
```

### Step 7: Grant API Gateway Permission to Invoke Lambda
```bash
aws lambda add-permission \
  --function-name HotspotDetector \
  --statement-id apigateway-hotspots \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:us-east-1:${AWS_ACCOUNT_ID}:${API_ID}/*/*/hotspots"
```

### Step 8: Test
```bash
# Get API endpoint
export API_ENDPOINT="https://${API_ID}.execute-api.us-east-1.amazonaws.com/prod"

echo "API Endpoint: $API_ENDPOINT"

# Test hotspots endpoint
curl "${API_ENDPOINT}/hotspots?eps=0.3&min_samples=5&algorithm=dbscan"
```

---

## 🚀 Deployment Method 3: CloudFormation (Production - 20 min)

Add this to your existing `infrastructure/cloudformation-template.yaml`:

```yaml
# Add to Resources section

  # Hotspot Detector Lambda Function
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
        S3Bucket: !Sub 'safepath-crime-data-${AWS::AccountId}'
        S3Key: 'lambda-packages/lambda-hotspots.zip'
      Tags:
        - Key: Environment
          Value: Production

  # API Gateway Integration for Hotspots
  HotspotIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref ApiGateway
      IntegrationType: AWS_PROXY
      IntegrationMethod: POST
      IntegrationUri: !Sub 'arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${HotspotDetectorLambda.Arn}/invocations'
      PayloadFormatVersion: '2.0'

  # Route for GET /hotspots
  GetHotspotsRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ApiGateway
      RouteKey: 'GET /hotspots'
      Target: !Sub 'integrations/${HotspotIntegration}'

  # Lambda Permission for API Gateway
  HotspotLambdaPermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref HotspotDetectorLambda
      Action: lambda:InvokeFunction
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${ApiGateway}/*/*/*'
```

**Deploy Stack**:
```bash
# First, upload Lambda package to S3
aws s3 cp /Users/kavins/Projects/AWS_Hackathon2025/backend/lambda-hotspots.zip \
  s3://safepath-crime-data-${AWS_ACCOUNT_ID}/lambda-packages/

# Update CloudFormation stack
aws cloudformation update-stack \
  --stack-name safepath-stack \
  --template-body file://infrastructure/cloudformation-template.yaml \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for completion
aws cloudformation wait stack-update-complete --stack-name safepath-stack
```

---

## 🧪 Testing & Validation

### Test 1: Basic Functionality
```bash
curl "${API_ENDPOINT}/hotspots"
```

Expected: GeoJSON with crime hotspots

### Test 2: DBSCAN Parameters
```bash
curl "${API_ENDPOINT}/hotspots?eps=0.5&min_samples=10"
```

Expected: Larger, denser hotspots

### Test 3: K-means Algorithm
```bash
curl "${API_ENDPOINT}/hotspots?algorithm=kmeans"
```

Expected: Fixed number of clusters

### Test 4: JSON Format
```bash
curl "${API_ENDPOINT}/hotspots?format=json"
```

Expected: Full response with metadata

### Test 5: CORS
```bash
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     "${API_ENDPOINT}/hotspots"
```

Expected: CORS headers in response

---

## 🐛 Troubleshooting

### Issue: Lambda timeout

**Symptoms**:
```
{"message": "Endpoint request timed out"}
```

**Solution**:
1. Increase Lambda timeout to 90 seconds
2. Increase memory to 1024 MB
3. Check CloudWatch Logs for errors

```bash
aws lambda update-function-configuration \
  --function-name HotspotDetector \
  --timeout 90 \
  --memory-size 1024
```

---

### Issue: No hotspots found

**Symptoms**:
```json
{
  "type": "FeatureCollection",
  "features": []
}
```

**Solution**:
1. Relax DBSCAN parameters:
   ```bash
   curl "${API_ENDPOINT}/hotspots?eps=0.5&min_samples=3"
   ```

2. Check crime data exists in DynamoDB:
   ```bash
   aws dynamodb scan --table-name ApiDataCache --max-items 10
   ```

---

### Issue: Import error (sklearn)

**Symptoms (in CloudWatch Logs)**:
```
ModuleNotFoundError: No module named 'sklearn'
```

**Solution**: Package is corrupted. Rebuild:
```bash
cd /Users/kavins/Projects/AWS_Hackathon2025/backend
rm -rf lambda-hotspot-package lambda-hotspots.zip
mkdir lambda-hotspot-package
pip3 install -r requirements.txt -t lambda-hotspot-package/
cp hotspot_detection.py lambda_hotspots.py lambda-hotspot-package/
cd lambda-hotspot-package && zip -r ../lambda-hotspots.zip .
```

---

### Issue: Permission denied (DynamoDB)

**Symptoms**:
```
AccessDeniedException: User is not authorized to perform: dynamodb:Scan
```

**Solution**: Add DynamoDB permissions to Lambda role:
```bash
aws iam put-role-policy \
  --role-name LambdaExecutionRole \
  --policy-name HotspotDynamoDBAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "dynamodb:Scan",
        "dynamodb:Query",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/ApiDataCache"
    }]
  }'
```

---

## 📊 Monitor & Optimize

### View CloudWatch Logs
```bash
# Get log group
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/HotspotDetector

# Tail logs (real-time)
aws logs tail /aws/lambda/HotspotDetector --follow
```

### Check Lambda Metrics
```bash
# Invocation count (last hour)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=HotspotDetector \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

### Optimize Cold Starts

Add **Provisioned Concurrency** (costs ~$15/month):
```bash
aws lambda put-provisioned-concurrency-config \
  --function-name HotspotDetector \
  --provisioned-concurrent-executions 1
```

Or use **Lambda SnapStart** (free, Python 3.11 not supported yet).

---

## 🔄 Update Lambda Code

When you make changes:

```bash
# Rebuild package
cd /Users/kavins/Projects/AWS_Hackathon2025/backend
rm -rf lambda-hotspot-package lambda-hotspots.zip
mkdir lambda-hotspot-package
pip3 install -r requirements.txt -t lambda-hotspot-package/
cp hotspot_detection.py lambda_hotspots.py lambda-hotspot-package/
cd lambda-hotspot-package && zip -r ../lambda-hotspots.zip .

# Upload to S3
aws s3 cp ../lambda-hotspots.zip s3://safepath-crime-data-${AWS_ACCOUNT_ID}/lambda-packages/

# Update Lambda function
aws lambda update-function-code \
  --function-name HotspotDetector \
  --s3-bucket safepath-crime-data-${AWS_ACCOUNT_ID} \
  --s3-key lambda-packages/lambda-hotspots.zip
```

---

## 💰 Cost Estimate

**Monthly costs** (1,000 daily users, each viewing hotspots once):

| Service | Usage | Cost |
|---------|-------|------|
| Lambda (HotspotDetector) | 30K invocations × 2s × 512MB | $0.40 |
| API Gateway | 30K requests | $0.03 |
| DynamoDB Reads | From existing cache | $0.00 |
| S3 Storage | 60MB Lambda package | $0.001 |
| **Total** | | **~$0.45/month** |

Very affordable! 🎉

---

## ✅ Deployment Checklist

Before going live:

- [ ] Lambda package uploaded to S3
- [ ] Lambda function created (HotspotDetector)
- [ ] Lambda timeout ≥60 seconds
- [ ] Lambda memory ≥512 MB
- [ ] Environment variable `DYNAMODB_TABLE_NAME` set
- [ ] API Gateway route `/hotspots` created
- [ ] Lambda permission for API Gateway granted
- [ ] Endpoint tested with `curl`
- [ ] CORS headers verified
- [ ] Frontend `.env` updated with API endpoint
- [ ] CloudWatch Logs reviewed for errors
- [ ] Frontend integration tested

---

## 🎉 You're Done!

Your hotspot detection feature is now deployed to AWS!

**Next Steps**:
1. Update frontend `.env` with your API endpoint
2. Test in the React app
3. Monitor CloudWatch Logs
4. Optimize parameters based on user feedback

**API Endpoint**:
```
GET https://{api-id}.execute-api.us-east-1.amazonaws.com/prod/hotspots
```

**Query Parameters**:
- `eps` - DBSCAN epsilon (default: 0.3)
- `min_samples` - Minimum incidents (default: 5)
- `algorithm` - dbscan or kmeans (default: dbscan)
- `format` - geojson or json (default: geojson)

---

**Need help?** Check the troubleshooting section or review CloudWatch Logs.
