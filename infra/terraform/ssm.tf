# SSM Parameter Store for application secrets/config. SecureString parameters
# are free up to 10,000 standard parameters per account.

resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.project_name}/${var.environment}/db/password"
  type  = "SecureString"
  value = random_password.db.result
}

resource "aws_ssm_parameter" "db_url_async" {
  name  = "/${var.project_name}/${var.environment}/db/database_url"
  type  = "SecureString"
  value = "postgresql+asyncpg://${var.db_username}:${urlencode(random_password.db.result)}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
}

resource "aws_ssm_parameter" "db_url_sync" {
  name  = "/${var.project_name}/${var.environment}/db/database_sync_url"
  type  = "SecureString"
  value = "postgresql+psycopg://${var.db_username}:${urlencode(random_password.db.result)}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
}

resource "aws_ssm_parameter" "s3_bucket" {
  name  = "/${var.project_name}/${var.environment}/model/s3_bucket"
  type  = "String"
  value = aws_s3_bucket.model_artifacts.bucket
}

resource "aws_ssm_parameter" "ecr_registry" {
  name  = "/${var.project_name}/${var.environment}/ecr/registry"
  type  = "String"
  value = split("/", aws_ecr_repository.api.repository_url)[0]
}
