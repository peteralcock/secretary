resource "aws_s3_bucket" "media" {
  bucket = "${var.app_name}-media"
  acl    = "private"
} 