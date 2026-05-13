resource "aws_security_group" "ec2" {
  name        = "${var.project_name}-${var.environment}-ec2"
  description = "API host: allow HTTP from the world, all egress."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.ec2_allowed_http_cidrs
  }

  ingress {
    description = "API direct (8000) — useful while bringing the stack up; can be removed once a reverse proxy is in front."
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = var.ec2_allowed_http_cidrs
  }

  dynamic "ingress" {
    for_each = var.ec2_ssh_key_name != "" ? [1] : []
    content {
      description = "SSH (optional — SSM Session Manager is preferred)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds"
  description = "RDS Postgres: 5432 only from the EC2 SG."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
