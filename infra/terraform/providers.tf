provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "transport-delay-predictor"
      ManagedBy = "terraform"
      Env       = var.environment
    }
  }
}
