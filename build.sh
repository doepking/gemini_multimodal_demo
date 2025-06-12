#!/bin/bash

# Script to build the Docker image for the Gemini Multimodal Demo (Streamlit Frontend)

# --- Configuration ---
# Default to production environment
ENV="p"
if [ "$1" == "--dev" ]; then
  ENV="d"
fi

# Load environment variables based on the environment
if [ "$ENV" == "d" ]; then
  ENV_FILE=".env.dev"
  SECRETS_FILE=".streamlit/secrets.dev.toml"
else
  ENV_FILE=".env"
  SECRETS_FILE=".streamlit/secrets.toml"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/${ENV_FILE}"

# Project ID from .env or environment
PROJECT_ID="${GCP_PROJECT_ID:-fdap-1337}"

# Image name and tag
IMAGE_NAME="life-tracker"
IMAGE_TAG="latest"

# Google Container Registry (GCR) or Artifact Registry path
IMAGE_URI="eu.gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# --- Secrets Management ---
TARGET_SECRETS_PATH=".streamlit/secrets.toml"
BACKUP_SECRETS_PATH=".streamlit/secrets.toml.bak"

# For dev builds, backup production secrets if they exist
if [ "$ENV" == "d" ] && [ -f "${TARGET_SECRETS_PATH}" ]; then
  echo "Backing up production secrets to ${BACKUP_SECRETS_PATH}"
  mv "${TARGET_SECRETS_PATH}" "${BACKUP_SECRETS_PATH}"
fi

if [ ! -f "${SECRETS_FILE}" ]; then
    echo "ERROR: Secrets file not found at ${SECRETS_FILE}"
    exit 1
fi
cp "${SECRETS_FILE}" "${TARGET_SECRETS_PATH}"

# --- Cleanup function ---
cleanup() {
  # Only remove the secrets file if it was a temporary copy for development
  if [ "$ENV" == "d" ]; then
    echo "Cleaning up temporary secrets file..."
    rm "${TARGET_SECRETS_PATH}"
    # Restore production secrets if a backup exists
    if [ -f "${BACKUP_SECRETS_PATH}" ]; then
      echo "Restoring production secrets from ${BACKUP_SECRETS_PATH}"
      mv "${BACKUP_SECRETS_PATH}" "${TARGET_SECRETS_PATH}"
    fi
  fi
}

# Trap EXIT signal to ensure cleanup runs
trap cleanup EXIT

# --- Script ---
echo "Building Docker image for Streamlit Frontend (${ENV} environment)..."
echo "Project ID: ${PROJECT_ID}"
echo "Image URI: ${IMAGE_URI}"

# Navigate to the directory of this script (and Dockerfile)
cd "$(dirname "$0")" || exit

# Build the Docker image
# Added --platform linux/amd64 to ensure compatibility with Cloud Run
docker build --platform linux/amd64 -t "${IMAGE_URI}" .

if [ $? -eq 0 ]; then
  echo "Docker image built successfully: ${IMAGE_URI}"
  echo ""
  echo "Attempting to push the image to GCR..."
  
  # Configure Docker to authenticate with GCR
  echo "Configuring Docker for eu.gcr.io..."
  gcloud auth configure-docker eu.gcr.io -q
  
  if [ $? -ne 0 ]; then
    echo "ERROR: Failed to configure Docker authentication for eu.gcr.io. Please check gcloud setup."
    exit 1
  fi
  
  echo "Pushing image ${IMAGE_URI}..."
  docker push "${IMAGE_URI}"
  
  if [ $? -eq 0 ]; then
    echo "Docker image pushed successfully to ${IMAGE_URI}"
  else
    echo "ERROR: Docker image push failed."
    echo "Please ensure you are authenticated with gcloud and have permissions to push to ${IMAGE_URI}."
    exit 1
  fi
else
  echo "ERROR: Docker image build failed."
  exit 1
fi
