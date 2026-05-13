# Use the default VPC + its subnets. Building a dedicated VPC would mean
# either a NAT gateway (~$33/mo) or splitting public/private subnets carefully —
# both push us out of free tier for a learning project.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}
