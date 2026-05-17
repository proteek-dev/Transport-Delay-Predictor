#!/usr/bin/env bash
echo "ECR_REGISTRY=${ECR_REGISTRY}"
echo "ECR_API_REPO=${ECR_API_REPO}"
echo "ECR_WORKER_REPO=${ECR_WORKER_REPO}"
echo "IMAGE_TAG=${IMAGE_TAG}"
# Invoked on the EC2 host via SSM SendCommand from the deploy workflow.
# Expects ECR_REGISTRY, ECR_API_REPO, ECR_WORKER_REPO, IMAGE_TAG, AWS_REGION
# to be present in the environment (the GH Actions workflow injects them
# into the SendCommand parameters).
set -euo pipefail

PROJECT="transport-delay-predictor"
APP_DIR="/opt/$PROJECT"

cd "$APP_DIR"
sudo git fetch --all --prune
sudo git checkout main
sudo git pull --ff-only

# Update IMAGE_TAG in .env so docker compose picks up the new build.
sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|" .env || echo "IMAGE_TAG=${IMAGE_TAG}" >> .env

aws ecr get-login-password --region ${AWS_REGION} \
  | sudo -E docker login --username AWS --password-stdin ${ECR_REGISTRY}

sudo -E docker compose -f docker-compose.aws.yml pull
sudo -E docker compose -f docker-compose.aws.yml up -d

# Apply pending Alembic migrations in a one-shot container against RDS.
sudo -E docker compose -f docker-compose.aws.yml run --rm api alembic upgrade head

# Drop dangling images to reclaim disk on the 20 GB root volume.
sudo -E docker image prune -af --filter "until=72h" || true

echo "deploy ok — image_tag=$IMAGE_TAG"
