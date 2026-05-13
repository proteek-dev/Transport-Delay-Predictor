resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_db_subnet_group" "default" {
  name       = "${var.project_name}-${var.environment}"
  subnet_ids = data.aws_subnets.default.ids
}

# A custom parameter group lets us nudge defaults later (max_connections,
# work_mem, etc.) without touching the AWS-managed default group.
resource "aws_db_parameter_group" "postgres" {
  name   = "${var.project_name}-${var.environment}-pg16"
  family = "postgres16"
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-${var.environment}"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = 0 # disable autoscaling — pin to free-tier 20 GB
  storage_type          = "gp2"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name

  publicly_accessible = false
  multi_az            = false
  skip_final_snapshot = true # for a learning project; flip to false + add `final_snapshot_identifier` for real envs
  deletion_protection = false

  backup_retention_period = 1 # free tier covers 20 GB of backups; we keep one day
  apply_immediately       = true

  performance_insights_enabled = false
  monitoring_interval          = 0
}

# PostGIS doesn't come enabled by default — it has to be `CREATE EXTENSION`-ed
# after provisioning. We store the SQL alongside the infra so it's obvious
# what to run; the deploy script invokes it on first boot.
resource "aws_ssm_parameter" "postgis_init_sql" {
  name  = "/${var.project_name}/${var.environment}/db/postgis_init_sql"
  type  = "String"
  value = <<-SQL
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS btree_gist;
  SQL
}
