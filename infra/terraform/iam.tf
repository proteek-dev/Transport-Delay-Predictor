# ----------------------------------------------------------------------------
# EC2 instance profile — pull from ECR, R/W the model artifact bucket, read SSM.
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project_name}-${var.environment}-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# SSM agent + Session Manager (so we never need port 22 open).
resource "aws_iam_role_policy_attachment" "ec2_ssm_managed" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "ec2_inline" {
  statement {
    sid    = "EcrPull"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "S3ModelArtifacts"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetObjectVersion",
    ]
    resources = [
      aws_s3_bucket.model_artifacts.arn,
      "${aws_s3_bucket.model_artifacts.arn}/*",
    ]
  }

  statement {
    sid    = "SsmParameterRead"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_name}/${var.environment}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ec2_inline" {
  name   = "${var.project_name}-${var.environment}-ec2-inline"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_inline.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-${var.environment}-ec2"
  role = aws_iam_role.ec2.name
}

# ----------------------------------------------------------------------------
# GitHub Actions OIDC role — assumed by the CI workflow to push to ECR and
# trigger the deploy command via SSM. No long-lived access keys in GitHub.
# ----------------------------------------------------------------------------

# Thumbprints are the published GitHub Actions OIDC root CA fingerprints.
# AWS no longer enforces thumbprint validation for the GitHub OIDC issuer
# (the IAM service validates the JWT signature itself), but the field is
# still required, so we list both known values for forward compatibility.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for r in var.github_allowed_refs : "repo:${var.github_repository}:${r}"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-${var.environment}-gha"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "github_actions_inline" {
  statement {
    sid    = "EcrLoginAndPush"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "SsmSendCommandForDeploy"
    effect = "Allow"
    actions = [
      "ssm:SendCommand",
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EC2DescribeForLookup"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions_inline" {
  name   = "${var.project_name}-${var.environment}-gha-inline"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_inline.json
}
