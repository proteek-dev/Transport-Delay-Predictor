data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-6.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region            = var.aws_region
    project_name      = var.project_name
    environment       = var.environment
    ecr_registry      = split("/", aws_ecr_repository.api.repository_url)[0]
    ecr_api_repo      = aws_ecr_repository.api.name
    ecr_worker_repo   = aws_ecr_repository.worker.name
    model_s3_bucket   = aws_s3_bucket.model_artifacts.bucket
    db_host           = aws_db_instance.postgres.address
    db_port           = aws_db_instance.postgres.port
    db_name           = var.db_name
    db_user           = var.db_username
    repo_url          = "https://github.com/${var.github_repository}.git"
  })
}

resource "aws_instance" "api" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  key_name = var.ec2_ssh_key_name != "" ? var.ec2_ssh_key_name : null

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # docker containers reaching IMDS need >1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.ec2_root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = local.user_data
  user_data_replace_on_change = false # changing user_data shouldn't replace the host — let SSM redeploy

  tags = {
    Name = "${var.project_name}-${var.environment}-api"
    Role = "api-host"
  }

  depends_on = [aws_db_instance.postgres]
}
