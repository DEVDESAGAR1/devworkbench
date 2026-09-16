variable "aws_region" {
  type        = string
  description = "AWS region for deployments"
  default     = "us-east-1"
}

variable "bucket_name" {
  type        = string
  description = "Target S3 bucket name"
}
