#!/bin/bash

# Script to build the Docker image for the Gemini Multimodal Demo (Streamlit Frontend)

# --- Configuration ---
# Project ID from .env or environment
PROJECT_ID="${GCP_PROJECT_ID:-fdap-1337}"

# Image name and tag
IMAGE_NAME="gemini-multimodal-demo"
IMAGE_TAG="latest"

# Google Container Registry (GCR) or Artifact Registry path
IMAGE_URI="eu.gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# --- Script ---
echo "Building Docker image for Streamlit Frontend..."
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
