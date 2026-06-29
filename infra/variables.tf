variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for all resource names"
  type        = string
  default     = "satb2"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for genomic data"
  type        = string
  default     = "satb2-research-data"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC for security group rules"
  type        = string
  default     = "10.0.0.0/16"
}

variable "vpc_id" {
  description = "VPC ID where resources will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for RDS and SageMaker"
  type        = list(string)
}
