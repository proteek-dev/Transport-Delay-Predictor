variable "aws_region" {
  description = "AWS region. Free tier eligibility is identical across regions, but us-east-1 has the broadest service support and the cheapest data transfer."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Logical environment name (also used as a tag suffix on most resources)."
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Used as the prefix for resource names — keep lowercase + hyphens to stay valid for S3 buckets, ECR repos, etc."
  type        = string
  default     = "transport-delay-predictor"
}

# ---- EC2 ----

variable "ec2_instance_type" {
  description = "Free tier eligible: t2.micro. t3.micro is also free-tier eligible in many regions."
  type        = string
  default     = "t2.micro"
}

variable "ec2_root_volume_size_gb" {
  description = "EBS root volume size. Free tier covers 30 GB of gp2/gp3 storage; we stay well under that."
  type        = number
  default     = 20
}

variable "ec2_ssh_key_name" {
  description = "Optional EC2 key pair name for SSH fallback access. Leave empty to disable SSH entirely (recommended — use SSM Session Manager)."
  type        = string
  default     = ""
}

variable "ec2_allowed_http_cidrs" {
  description = "CIDRs allowed to reach the API on port 80. Default open to the world for a demo; lock down for prod."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ---- RDS ----

variable "db_instance_class" {
  description = "Free tier eligible: db.t3.micro (or db.t4g.micro in supported regions)."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage_gb" {
  description = "RDS storage in GB. Free tier covers 20 GB of gp2."
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "Postgres engine version. PostGIS 3.4 is available on Postgres 16."
  type        = string
  default     = "16.3"
}

variable "db_name" {
  description = "Initial database name created by RDS at provisioning time."
  type        = string
  default     = "tdp"
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "tdp_app"
}

# ---- GitHub Actions OIDC ----

variable "github_repository" {
  description = "GitHub `owner/repo` — used to scope the OIDC trust policy so only this repo can assume the deploy role."
  type        = string
  default     = "proteek-dev/Transport-Delay-Predictor"
}

variable "github_allowed_refs" {
  description = "List of `ref:` patterns allowed to assume the deploy role. Restricts which branches/tags can deploy."
  type        = list(string)
  default     = ["ref:refs/heads/main"]
}
