#!/usr/bin/env bash
# Invoked on the EC2 host via SSM SendCommand from the deploy workflow.
# Expects ECR_REGISTRY, ECR_API_REPO, ECR_WORKER_REPO, IMAGE_TAG, AWS_REGION
# to be present in the environment (the GH Actions workflow injects them
# into the SendCommand parameters).
set -euo pipefail

echo "ECR_REGISTRY=${ECR_REGISTRY}"
echo "ECR_API_REPO=${ECR_API_REPO}"
echo "ECR_WORKER_REPO=${ECR_WORKER_REPO}"
echo "IMAGE_TAG=${IMAGE_TAG}"

PROJECT="transport-delay-predictor"
APP_DIR="/opt/$PROJECT"
DEPLOY_LOG="/tmp/deploy-${IMAGE_TAG}.log"

# Docker compose progress is very verbose and hits SSM's 48KB output cap,
# hiding the actual error. Redirect stderr to a log file; on any failure
# the trap tails the log into stdout so the real error is always visible.
exec 2>"$DEPLOY_LOG"
trap 'ec=$?; [ $ec -ne 0 ] && { echo "=== FAILED (exit $ec) — last 80 lines of deploy log ==="; tail -80 "$DEPLOY_LOG"; }' EXIT

echo "STEP 1: git pull"
cd "$APP_DIR"
sudo git fetch --all --prune
sudo git checkout main
sudo git pull --ff-only

echo "STEP 2: write ECR vars to .env"
# sudo resets the process environment (Defaults env_reset in sudoers),
# so these vars must come from the file, not the process env.
for kv in \
  "ECR_REGISTRY=${ECR_REGISTRY}" \
  "ECR_API_REPO=${ECR_API_REPO}" \
  "ECR_WORKER_REPO=${ECR_WORKER_REPO}" \
  "IMAGE_TAG=${IMAGE_TAG}"; do
  key="${kv%%=*}"
  grep -q "^${key}=" .env 2>/dev/null \
    && sed -i "s|^${key}=.*|${kv}|" .env \
    || echo "${kv}" >> .env
done

echo "STEP 3: ECR login"
aws ecr get-login-password --region "${AWS_REGION}" \
  | sudo docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "STEP 4: prune dangling images before pull (free disk space)"
sudo docker image prune -f

echo "STEP 5: docker compose pull"
sudo docker compose -f docker-compose.aws.yml pull

echo "STEP 6: docker compose up"
sudo docker compose -f docker-compose.aws.yml up -d

echo "STEP 7: alembic migrate"
sudo docker compose -f docker-compose.aws.yml run --rm api alembic upgrade head

echo "STEP 8: prune stale images"
sudo docker image prune -af --filter "until=72h" || true

echo "deploy ok — image_tag=${IMAGE_TAG}"
