output "s3_bucket_name" {
  description = "S3 bucket name for genomic data"
  value       = aws_s3_bucket.satb2_data.bucket
}

output "sqs_queue_url" {
  description = "SQS queue URL for the analysis pipeline"
  value       = aws_sqs_queue.satb2_analysis_queue.url
}

output "rds_endpoint" {
  description = "PostgreSQL RDS endpoint"
  value       = aws_db_instance.satb2_postgres.endpoint
  sensitive   = true
}

output "ecr_backend_url" {
  description = "ECR repository URL for the Spring Boot backend"
  value       = aws_ecr_repository.satb2_backend.repository_url
}

output "ecr_worker_url" {
  description = "ECR repository URL for the Python AI worker"
  value       = aws_ecr_repository.satb2_worker.repository_url
}
