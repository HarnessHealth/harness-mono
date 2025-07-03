#!/usr/bin/env bash
set -euo pipefail

############################
# 1---EDIT THESE VARIABLES #
############################
SERVICE_NAME="harness-admin-development"
REGION="us-east-1"
GITHUB_REPO="https://github.com/HarnessHealth/harness-mono"
GITHUB_BRANCH="master"
RUNTIME="NODEJS_18"
BUILD_CMD="cd admin-frontend && npm ci && npm run build"
START_CMD="cd admin-frontend && npm start"

# Get API URL from backend App Runner service
BACKEND_SERVICE_ARN="arn:aws:apprunner:us-east-1:285641110801:service/harness-api-development/755e28dd802748f39364f2f9ac456c7d"
BACKEND_URL=$(aws apprunner describe-service --service-arn "$BACKEND_SERVICE_ARN" --query "Service.ServiceUrl" --output text --region "$REGION")
API_URL="https://$BACKEND_URL"

echo "🔧 Using API URL: $API_URL"

############################
# 2---CREATE / REUSE CONNECTION
############################
echo "🔍 Trying to find an existing GitHub connection…"
CONN_ARN=$(aws apprunner list-connections \
              --query "ConnectionSummaryList[?ProviderType=='GITHUB'] | [0].ConnectionArn" \
              --output text --region "$REGION" || true)

if [[ -z "$CONN_ARN" || "$CONN_ARN" == "None" ]]; then
  echo "🛠  No connection found. Creating one…"
  CONN_ARN=$(aws apprunner create-connection \
                --connection-name "${SERVICE_NAME}-github" \
                --provider-type GITHUB \
                --query "Connection.ConnectionArn" \
                --output text --region "$REGION")
  echo "✅  Created connection: $CONN_ARN"
  echo "⚠️  Please authorize the connection in the AWS Console before continuing"
  echo "    Visit: https://console.aws.amazon.com/apprunner/home?region=${REGION}#/connections"
  read -p "Press Enter once you've authorized the connection..."
else
  echo "✅  Re-using connection: $CONN_ARN"
fi

############################
# 3---WRITE SOURCE CONFIG JSON
############################
cat > admin-source-config.json <<EOF
{
  "CodeRepository": {
    "RepositoryUrl": "${GITHUB_REPO}",
    "SourceCodeVersion": {
      "Type": "BRANCH",
      "Value": "${GITHUB_BRANCH}"
    },
    "CodeConfiguration": {
      "ConfigurationSource": "API",
      "CodeConfigurationValues": {
        "Runtime": "${RUNTIME}",
        "BuildCommand": "${BUILD_CMD}",
        "StartCommand": "${START_CMD}",
        "RuntimeEnvironmentVariables": {
          "PORT": "8080",
          "NODE_ENV": "production",
          "VITE_API_URL": "${API_URL}"
        }
      }
    }
  },
  "AuthenticationConfiguration": {
    "ConnectionArn": "${CONN_ARN}"
  },
  "AutoDeploymentsEnabled": true
}
EOF

############################
# 4---CREATE (OR RE-CREATE) THE SERVICE
############################
echo "🚀 Deploying ${SERVICE_NAME} to App Runner…"

# Check if service already exists
if aws apprunner list-services --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}']" --output text --region "$REGION" | grep -q "${SERVICE_NAME}"; then
  echo "⚠️  Service ${SERVICE_NAME} already exists. Deleting it first..."
  SERVICE_ARN=$(aws apprunner list-services \
                  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
                  --output text --region "$REGION")
  aws apprunner delete-service --service-arn "$SERVICE_ARN" --region "$REGION"
  echo "🕒 Waiting for service to be deleted..."
  aws apprunner wait service-deleted --service-arn "$SERVICE_ARN" --region "$REGION"
fi

aws apprunner create-service \
    --service-name "${SERVICE_NAME}" \
    --source-configuration file://admin-source-config.json \
    --instance-configuration Cpu="0.25 vCPU",Memory="0.5 GB" \
    --health-check-configuration Protocol=HTTP,Path="/health",Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5 \
    --tags Key=Name,Value="${SERVICE_NAME}" Key=Environment,Value=development Key=Project,Value=Harness Key=Component,Value=admin-frontend \
    --region "${REGION}"

echo "🎉  Initial deployment started. Watch your service in the App Runner console."

############################
# 5---GET SERVICE INFO
############################
echo "🔍 Getting service information..."
SERVICE_ARN=$(aws apprunner list-services \
                --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
                --output text --region "$REGION")

SERVICE_URL=$(aws apprunner describe-service \
                --service-arn "$SERVICE_ARN" \
                --query "Service.ServiceUrl" \
                --output text --region "$REGION")

echo "✅ Admin frontend deployed successfully!"
echo "   Service ARN: $SERVICE_ARN"
echo "   Service URL: https://$SERVICE_URL"
echo "   Health Check: https://$SERVICE_URL/health"
echo "   API Backend: $API_URL"

############################
# 6---CLEANUP
############################
rm -f admin-source-config.json

echo "🎯 Next steps:"
echo "1. Monitor deployment progress in AWS Console"
echo "2. Test the admin interface once deployment is complete"
echo "3. Verify API connectivity from frontend"
echo ""
echo "🗑️  To delete the service later:"
echo "   aws apprunner delete-service --service-arn $SERVICE_ARN --region $REGION"