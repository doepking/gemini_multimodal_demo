#!/bin/bash

# Script to deploy the Gemini Multimodal Demo (Streamlit Frontend) to a DEV environment

# --- Configuration ---
SERVICE_NAME="life-tracker-d"
IMAGE_NAME="life-tracker"
IMAGE_TAG="latest"

# --- Environment File ---
# Load environment variables from .env.dev
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.dev"

if [ -f "${ENV_FILE}" ]; then
  echo "Sourcing environment variables from ${ENV_FILE}"
  set -a
  source "${ENV_FILE}"
  set +a
else
  echo "ERROR: .env.dev file not found in ${SCRIPT_DIR}. Cannot proceed."
  exit 1
fi

# --- GCP Settings ---
PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
IMAGE_URI="eu.gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# --- Construct ENV_VARS string for gcloud ---
# This will pass all necessary environment variables to the Cloud Run instance
ENV_VARS="PYTHONUNBUFFERED=1"
ENV_VARS+=",STREAMLIT_SERVER_PORT=8080"
ENV_VARS+=",CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}"
ENV_VARS+=",CLOUD_SQL_USER=${CLOUD_SQL_USER}"
ENV_VARS+=",CLOUD_SQL_PASSWORD=${CLOUD_SQL_PASSWORD}"
ENV_VARS+=",CLOUD_SQL_DATABASE_NAME=${CLOUD_SQL_DATABASE_NAME}"
ENV_VARS+=",LLM_API_KEY=${LLM_API_KEY}"
ENV_VARS+=",GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}"
ENV_VARS+=",GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}"
ENV_VARS+=",SMTP_HOST=${SMTP_HOST}"
ENV_VARS+=",SMTP_PORT=${SMTP_PORT}"
ENV_VARS+=",SMTP_USER=${SMTP_USER}"
ENV_VARS+=",SMTP_PASSWORD=${SMTP_PASSWORD}"
ENV_VARS+=",NEWSLETTER_SENDER_EMAIL=${NEWSLETTER_SENDER_EMAIL}"

# --- Runtime Service Account ---
# This is sourced from the .env.dev file
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT}"

# --- Deployment ---
echo "Deploying ${SERVICE_NAME} to Cloud Run in project ${PROJECT_ID}..."
read -p "Are you sure you want to proceed? (y/N): " confirmation
if [[ "$confirmation" != "y" ]] && [[ "$confirmation" != "Y" ]]; then
  echo "Deployment cancelled."
  exit 0
fi

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_URI}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --allow-unauthenticated \
  --port=8080 \
  --set-env-vars="${ENV_VARS}" \
  --service-account="${RUNTIME_SERVICE_ACCOUNT}" \
  --add-cloudsql-instances="${CLOUD_SQL_CONNECTION_NAME}" \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=300s \
  --concurrency=80

if [ $? -eq 0 ]; then
  SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform=managed --region=${REGION} --project=${PROJECT_ID} --format='value(status.url)')
  echo "Service '${SERVICE_NAME}' deployed successfully."
  echo "Service URL: ${SERVICE_URL}"
else
  echo "ERROR: Cloud Run deployment failed."
  exit 1
fi
