output "ec2_public_ip" {
  description = "Public IP of the API host. Hit http://<ip>:8000/docs after the user-data script finishes."
  value       = aws_instance.api.public_ip
}

output "ec2_public_dns" {
  value = aws_instance.api.public_dns
}

output "ec2_instance_id" {
  description = "Used by GitHub Actions to target SSM SendCommand during deploys."
  value       = aws_instance.api.id
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "rds_port" {
  value = aws_db_instance.postgres.port
}

output "ecr_api_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_worker_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "ecr_registry" {
  description = "ECR registry host — `docker login` target."
  value       = split("/", aws_ecr_repository.api.repository_url)[0]
}

output "s3_model_artifacts_bucket" {
  value = aws_s3_bucket.model_artifacts.bucket
}

output "github_actions_role_arn" {
  description = "Add this as the AWS_DEPLOY_ROLE_ARN secret on the GitHub repo so the workflow can assume it via OIDC."
  value       = aws_iam_role.github_actions.arn
}
