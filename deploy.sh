#!/bin/bash
# GCP Cloud Run Job deployment script
# Prerequisites:
#   1) gcloud CLI installed and authenticated
#   2) GCP project selected: gcloud config set project YOUR_PROJECT_ID
#   3) APIs enabled: run.googleapis.com, cloudscheduler.googleapis.com, artifactregistry.googleapis.com

set -e

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION="us-central1"
JOB_NAME="polymarket-insider"
IMAGE="gcr.io/${PROJECT_ID}/${JOB_NAME}:latest"
SCHEDULE="0 8 * * *"  # Daily at 08:00 UTC — change as needed

echo "============================================================"
echo "  Deploying Polymarket Insider Detector"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "============================================================"

# 1) Build and push image
echo ""
echo "[1/4] Building Docker image..."
docker build -t "${IMAGE}" .

echo ""
echo "[2/4] Pushing to Google Container Registry..."
docker push "${IMAGE}"

# 2) Create or update Cloud Run Job
echo ""
echo "[3/4] Deploying Cloud Run Job..."
if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" >/dev/null 2>&1; then
    gcloud run jobs update "${JOB_NAME}" \
        --image="${IMAGE}" \
        --region="${REGION}" \
        --max-retries=2 \
        --task-timeout=600 \
        --set-env-vars="PYTHONUNBUFFERED=1"
else
    gcloud run jobs create "${JOB_NAME}" \
        --image="${IMAGE}" \
        --region="${REGION}" \
        --max-retries=2 \
        --task-timeout=600 \
        --set-env-vars="PYTHONUNBUFFERED=1"
fi

# 3) Create Cloud Scheduler to trigger the job
echo ""
echo "[4/4] Setting up Cloud Scheduler (${SCHEDULE})..."
SCHEDULER_NAME="${JOB_NAME}-scheduler"
if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --schedule="${SCHEDULE}" \
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
        --http-method=POST \
        --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com"
else
    gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --schedule="${SCHEDULE}" \
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
        --http-method=POST \
        --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

echo ""
echo "============================================================"
echo "  Deployment complete!"
echo ""
echo "  Job URL:     https://console.cloud.google.com/run/jobs/details/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo "  Logs:        https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_job%22%20resource.labels.job_name%3D%22${JOB_NAME}%22?project=${PROJECT_ID}"
echo "  Schedule:    ${SCHEDULE}"
echo ""
echo "  To run manually:"
echo "    gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo "============================================================"
