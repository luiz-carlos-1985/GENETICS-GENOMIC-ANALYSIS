# Changelog — SATB2 Genomic Analysis Platform

---

## [2.6.0] — 2025 — Local Mode

### Fixed

#### AI Worker
- `status_updater.py`: added missing `import requests` at top of file (caused `NameError` on first status update)
- `variant_classifier.py`: replaced mandatory ClinVar API call with two-tier strategy — system no longer fails when network is unavailable
- `requirements.txt`: removed `torch==2.3.0` and `transformers==4.40.1` (~3GB, unused) — install time reduced from ~15min to ~2min

#### Backend
- `AwsConfig.java`: added all missing imports (`ObjectMapper`, `AwsBasicCredentials`, `StaticCredentialsProvider`, `URI`)
- `AwsConfig.java`: replaced `DefaultCredentialsProvider` with `StaticCredentialsProvider("test","test")` when `AWS_ENDPOINT_OVERRIDE` is set — no longer requires real AWS credentials locally
- `application.yml`: changed default `SQS_QUEUE_URL` from `https://sqs.us-east-1.amazonaws.com/123456789/...` to `http://localhost:4566/000000000000/satb2-analysis-queue` — safe to run without environment variables

#### Docker Compose
- Removed `unix:///var/run/docker.sock` volume mount from LocalStack — fully compatible with Windows Docker Desktop
- Pinned LocalStack image to `localstack/localstack:3.4` (was `latest`)
- Added `EAGER_SERVICE_LOADING: 1` — S3 and SQS initialize immediately instead of lazily
- Added `LOCALSTACK_HOST: localstack` for correct hostname resolution in Docker network
- Changed LocalStack volume to `/var/lib/localstack` (correct path for v3.x)
- `init-aws`: added `raw-sequences/` and `results/` folder creation in S3
- `init-aws`: added DLQ creation (`satb2-dlq`)
- Backend `healthcheck`: changed to `curl -f ... || exit 1` format (Windows-compatible)
- Worker: changed `depends_on` to wait for `backend` healthy (was waiting for `init-aws`)
- Worker: added `restart: on-failure` policy

### Added
- `scripts/setup-local.bat` — Windows dependency checker and build script
- `scripts/test-integration.bat` — Windows integration test (equivalent to `.sh`)
- `variant_classifier.py`: `KNOWN_PATHOGENIC_POSITIONS` — offline cache of ~30 known SATB2 pathogenic positions (GRCh38) organized by variant type (missense, nonsense, splice, frameshift)
- `variant_classifier.py`: `_resolve_significance()` — two-tier pathogenicity resolution
- `variant_classifier.py`: `_query_clinvar_safe()` — returns `None` on any exception, 5s timeout
- `ai-worker/Dockerfile`: added `gcc` system dependency (required for Biopython C extensions on slim image) and `ENV PYTHONPATH=/app`
- `LOCAL_SETUP.md` — complete guide for 100% offline local execution

---

## [2.5.0] — 2025 — Production Hardening

### Added

#### Backend
- `GenomicAnalysisRepository` — JPA interface with queries: `findByPatientCodeOrderByCreatedAtDesc`, `findByStatusOrderByCreatedAtDesc`, `findByS3FileKey`
- `AnalysisResponse` DTO — clean API response shape, static factory `from(GenomicAnalysis)`
- `GenomicProcessingException` — domain-level `RuntimeException`
- `GlobalExceptionHandler` — `@RestControllerAdvice`: `GenomicProcessingException` → 500, `MaxUploadSizeExceededException` → 413, `Exception` → 500
- `StatusUpdateController` — `PUT /api/genomic/analysis/{id}/status` for worker callbacks
- `GET /api/genomic/analysis/{id}` — retrieve analysis by UUID
- `GET /api/genomic/analysis/patient/{patientCode}` — list analyses ordered by `createdAt DESC`
- `fileSize` field on `GenomicAnalysis` entity
- `rollbackS3Upload()` in `GenomicIngestionService` — deletes orphaned S3 object on failure
- `ObjectMapper` registered as Spring bean in `AwsConfig`
- `@Transactional` on `ingestSequenceFile()` and `updateAnalysisStatus()`
- File size validation: 500 MB hard limit in `GenomicController`
- `AWS_ENDPOINT_OVERRIDE` environment variable support in `AwsConfig`
- `forcePathStyle(true)` on S3Client for LocalStack path-style URL compatibility

#### AI Worker
- `status_updater.py` — HTTP client for backend REST status updates
- Environment variable validation at startup — `EnvironmentError` if `SQS_QUEUE_URL` or `S3_BUCKET` missing
- Status lifecycle: `PROCESSING` → `COMPLETED` / `FAILED`
- Error capture on failure — `error_json` sent to backend on `FAILED`
- `_classify_severity()` — `LOW` (≤0.05) / `MODERATE` (0.05–0.15) / `HIGH` (>0.15)
- `_generate_clinical_recommendation()` — CRISPRa recommendation text based on candidate count
- `_generate_fasta_summary()` — aggregate statistics per risk level
- Short sequence guard — skips sequences shorter than 6bp with warning log
- Empty file guard — returns `warning` field for empty FASTA/VCF files
- `bucketName` extracted from SQS message body (no longer hardcoded)
- `analysis_id` injected into all result JSON payloads
- Consecutive failure tracking — 60s cooldown after 5 failures
- `KeyboardInterrupt` handler — graceful shutdown
- `SATB2_REFERENCE` expanded from 130bp to 384bp
- LocalStack support via `AWS_ENDPOINT_URL` in boto3 clients

#### Infrastructure (Terraform)
- `aws_iam_role.ecs_task_execution_role` — ECR pull role for ECS agent
- `aws_iam_role.ecs_task_role` — least-privilege S3+SQS runtime permissions
- `aws_iam_role_policy.ecs_task_s3_sqs` — scoped to `satb2-research-data` and analysis queues only
- `aws_security_group.rds` — port 5432 restricted to `vpc_cidr`
- `vpc_security_group_ids` attached to `aws_db_instance`
- `vpc_cidr` variable added

#### DevOps
- `docker-compose.yml` — 5-service local environment with health checks and named volumes
- `test-data/sample_satb2.fasta` — wild-type + missense mutant sequences (384bp each)
- `test-data/sample_satb2.vcf` — 3 variants in SATB2 region

#### Documentation
- `API_REFERENCE.md`
- `ARCHITECTURE.md`
- `DEPLOYMENT.md`
- `SCIENCE.md`
- `CONTRIBUTING.md`
- `VALIDATION_CHECKLIST.md`
- `CHANGELOG.md`

---

## [2.0.0] — 2025 — Core Platform

### Added

#### Backend
- Initial project: Spring Boot 3.2.5, Java 21
- `GenomicController`: `POST /upload`, `GET /health`
- `GenomicIngestionService`: S3 upload + SQS dispatch
- `GenomicAnalysis` JPA entity with `PENDING/PROCESSING/COMPLETED/FAILED` enum
- `AwsConfig`: S3Client + SqsClient beans
- `SecurityConfig`: CSRF disabled, CORS for `localhost:4200`
- `application.yml`: environment variable placeholders with sane defaults
- `pom.xml`: Spring Boot, AWS SDK v2 2.25.40, JPA, Security, Lombok, PostgreSQL JDBC
- Multi-stage `Dockerfile`: Maven build → `eclipse-temurin:21-jre-alpine`

#### AI Worker
- `worker.py`: SQS polling loop
- `sequence_parser.py`: FASTA (Biopython) + VCF (tab-delimited) parsing
- `variant_classifier.py`: SATB2 region check + ClinVar API query
- `sequence_embedder.py`: k=6 hexamer tokenization + cosine mutation distance
- `requirements.txt`: biopython, boto3, requests, numpy
- `Dockerfile`: python:3.12-slim

#### Infrastructure
- `main.tf`: S3 + versioning + AES256 SSE, SQS + DLQ, RDS PostgreSQL 15.4 (encrypted), ECR×2, SageMaker domain
- `variables.tf`: aws_region, project_name, s3_bucket_name, db_*, vpc_id, private_subnet_ids
- `outputs.tf`: S3 name, SQS URL, RDS endpoint (sensitive), ECR URLs
