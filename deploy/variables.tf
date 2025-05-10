variable "aws_region" { default = "us-east-1" }
variable "app_name" { default = "paralegal-app" }
variable "db_username" { default = "paralegal" }
variable "db_password" {}
variable "db_name" { default = "paralegaldb" }
variable "docker_image" {} # e.g. "123456789012.dkr.ecr.us-east-1.amazonaws.com/paralegal:latest" 