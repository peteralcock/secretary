provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  name    = "${var.app_name}-vpc"
  cidr    = "10.0.0.0/16"
  azs     = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnets = ["10.0.3.0/24", "10.0.4.0/24"]
  enable_nat_gateway = true
}

# RDS, ElastiCache, ECS, ALB, and S3 modules/files will be included here as separate resources/files.
# See rds.tf, elasticache.tf, ecs.tf, alb.tf, s3.tf for details. 