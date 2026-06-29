# Deployment Guide — SATB2 Genomic Analysis Platform

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development — Docker Compose](#local-development--docker-compose)
- [Manual Local Setup — Without Docker](#manual-local-setup--without-docker)
- [AWS Production Deployment](#aws-production-deployment)
- [Environment Variables Reference](#environment-variables-reference)
- [Monitoring and Inspection](#monitoring-and-inspection)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### For Local Development

| Tool | Version | Required | Link |
|------|---------|----------|------|
| Docker Desktop | 20.10+ | ✅ | https://www.docker.com/products/docker-desktop/ |
| Docker Compose | 2.0+ | ✅ | Included with Docker Desktop |

That's all. Docker Compose handles everything else.

### For Manual Local Setup (without Docker)

| Tool | Version | Link |
|------|---------|------|
| Java JDK | 21 | https://adoptium.net |
| Maven | 3.9+ | https://maven.apache.org |
| Python | 3.12+ | https://python.org |
| PostgreSQL | 15+ | https://postgresql.org/download |

### For AWS Production

| Tool | Version | Link |
|------|---------|------|
| AWS CLI | 2.x | https://aws.amazon.com/cli/ |
| Terraform | 1.5+ | https://developer.hashicorp.com/terraform/install |
| Docker | 20.10+ | https://docs.docker.com/get-docker/ |

---

## Local Development — Docker Compose

**Single command to start the entire platform:**

```bash
cd GENETICS
docker-compose up --build
```

### What Docker Compose starts

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `satb2-postgres` | `postgres:15-alpine` | 5432 | PostgreSQL database |
| `satb2-localstack` | `localstack/localstack:3.4` | 4566 | S3 + SQS emulation |
| `satb2-init-aws` | `amazon/aws-cli:latest` | — | Creates S3 bucket, folders, SQS queues |
| `satb2-backend` | built from `./backend` | 8080 | Spring Boot REST API |
| `satb2-worker` | built from `./ai-worker` | — | Python pipeline worker |

### Startup sequence and timing

```
postgres     → healthy (pg_isready)        ~5s
localstack   → healthy (/_localstack/health) ~15s
init-aws     → runs once, exits 0           ~5s
backend      → healthy (GET /health)         ~60s (JVM startup)
worker       → starts polling SQS           ~5s
─────────────────────────────────────────────────
Total first run: ~90s (subsequent runs: ~30s)
```

### Verify everything is running

```bash
# All services healthy
docker-compose ps

# Backend API
curl http://localhost:8080/api/genomic/health
# Expected: {"status":"UP","service":"SATB2 Genomic Analysis API","version":"2.0.0"}

# LocalStack
curl http://localhost:4566/_localstack/health

# Database
docker exec -it satb2-postgres pg_isready -U satb2user -d satb2db
```

### Run the integration test

```bash
# Linux / Mac
chmod +x scripts/test-integration.sh
./scripts/test-integration.sh

# Windows
scripts\test-integration.bat
```

### Stop

```bash
docker-compose down        # stop, keep data volumes
docker-compose down -v     # stop, delete all data
```

---

## Manual Local Setup — Without Docker

### Step 1: Start PostgreSQL

```sql
CREATE DATABASE satb2db;
CREATE USER satb2user WITH PASSWORD 'satb2pass';
GRANT ALL PRIVILEGES ON DATABASE satb2db TO satb2user;
```

### Step 2: Start LocalStack

LocalStack is still required for S3 and SQS emulation. Install via pip:

```bash
pip install localstack
localstack start
```

Then create the resources:

```bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
    s3 mb s3://satb2-research-data

aws --endpoint-url=http://localhost:4566 \
    sqs create-queue --queue-name satb2-analysis-queue \
    --attributes VisibilityTimeout=300

aws --endpoint-url=http://localhost:4566 \
    sqs create-queue --queue-name satb2-dlq
```

### Step 3: Start the Backend

```bash
cd backend

# Linux / Mac
export DB_URL=jdbc:postgresql://localhost:5432/satb2db
export DB_USER=satb2user
export DB_PASS=satb2pass
export S3_BUCKET=satb2-research-data
export SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
export AWS_REGION=us-east-1
export AWS_ENDPOINT_OVERRIDE=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
mvn spring-boot:run

# Windows (cmd)
set DB_URL=jdbc:postgresql://localhost:5432/satb2db
set DB_USER=satb2user
set DB_PASS=satb2pass
set S3_BUCKET=satb2-research-data
set SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
set AWS_REGION=us-east-1
set AWS_ENDPOINT_OVERRIDE=http://localhost:4566
set AWS_ACCESS_KEY_ID=test
set AWS_SECRET_ACCESS_KEY=test
mvn spring-boot:run
```

### Step 4: Start the Worker

```bash
cd ai-worker

# Create venv
python -m venv venv

# Linux / Mac
source venv/bin/activate
export SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
export S3_BUCKET=satb2-research-data
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export BACKEND_URL=http://localhost:8080
python worker.py

# Windows (cmd)
venv\Scripts\activate
set SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
set S3_BUCKET=satb2-research-data
set AWS_REGION=us-east-1
set AWS_ENDPOINT_URL=http://localhost:4566
set AWS_ACCESS_KEY_ID=test
set AWS_SECRET_ACCESS_KEY=test
set BACKEND_URL=http://localhost:8080
python worker.py
```

---

## AWS Production Deployment

### Step 1: Provision Infrastructure

```bash
cd infra
terraform init

terraform apply \
  -var="db_username=satb2admin" \
  -var="db_password=YOUR_SECURE_PASSWORD" \
  -var="vpc_id=vpc-0123456789abcdef0" \
  -var="private_subnet_ids=[\"subnet-aaa\",\"subnet-bbb\"]" \
  -var="vpc_cidr=10.0.0.0/16"
```

Collect outputs:

```bash
BACKEND_ECR=$(terraform output -raw ecr_backend_url)
WORKER_ECR=$(terraform output -raw ecr_worker_url)
SQS_URL=$(terraform output -raw sqs_queue_url)
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
```

### Step 2: Build and Push Docker Images

```bash
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin $BACKEND_ECR

# Backend
cd backend
docker build -t satb2-backend .
docker tag satb2-backend:latest $BACKEND_ECR:latest
docker push $BACKEND_ECR:latest

# Worker
cd ../ai-worker
docker build -t satb2-worker .
docker tag satb2-worker:latest $WORKER_ECR:latest
docker push $WORKER_ECR:latest
```

### Step 3: ECS Task Environment Variables

**Backend task:**

| Variable | Value |
|----------|-------|
| `DB_URL` | `jdbc:postgresql://{RDS_ENDPOINT}/satb2db` |
| `DB_USER` | `satb2admin` |
| `DB_PASS` | *(from Secrets Manager)* |
| `S3_BUCKET` | `satb2-research-data` |
| `SQS_QUEUE_URL` | *(from Terraform output)* |
| `AWS_REGION` | `us-east-1` |

> Do **not** set `AWS_ENDPOINT_OVERRIDE` in production. Omitting it causes `AwsConfig` to use `DefaultCredentialsProvider` (IAM role).

**Worker task:**

| Variable | Value |
|----------|-------|
| `SQS_QUEUE_URL` | *(from Terraform output)* |
| `S3_BUCKET` | `satb2-research-data` |
| `AWS_REGION` | `us-east-1` |
| `BACKEND_URL` | `http://{backend-service-alb-dns}:8080` |

> Do **not** set `AWS_ENDPOINT_URL` or `AWS_ACCESS_KEY_ID` in production. The ECS task role (`satb2-ecs-task`) provides credentials automatically.

---

## Environment Variables Reference

### Backend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_URL` | ❌ | `jdbc:postgresql://localhost:5432/satb2db` | JDBC connection string |
| `DB_USER` | ❌ | `satb2user` | Database username |
| `DB_PASS` | ❌ | `satb2pass` | Database password |
| `S3_BUCKET` | ❌ | `satb2-research-data` | S3 bucket name |
| `SQS_QUEUE_URL` | ❌ | `http://localhost:4566/.../satb2-analysis-queue` | SQS queue URL |
| `AWS_REGION` | ❌ | `us-east-1` | AWS region |
| `AWS_ENDPOINT_OVERRIDE` | ❌ | — | Set to `http://localstack:4566` for local. Omit in production. |
| `AWS_ACCESS_KEY_ID` | ❌ | — | Set to `test` for local. Omit in production (IAM role). |
| `AWS_SECRET_ACCESS_KEY` | ❌ | — | Set to `test` for local. Omit in production (IAM role). |

### AI Worker

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SQS_QUEUE_URL` | ✅ | — | **Fail-fast on startup if missing.** |
| `S3_BUCKET` | ✅ | — | **Fail-fast on startup if missing.** |
| `AWS_REGION` | ❌ | `us-east-1` | AWS region |
| `BACKEND_URL` | ❌ | `http://localhost:8080` | Backend base URL |
| `AWS_ENDPOINT_URL` | ❌ | — | Set to `http://localstack:4566` for local. Omit in production. |
| `AWS_ACCESS_KEY_ID` | ❌ | — | Set to `test` for local. Omit in production. |
| `AWS_SECRET_ACCESS_KEY` | ❌ | — | Set to `test` for local. Omit in production. |

---

## Monitoring and Inspection

### Container Logs

```bash
docker logs satb2-backend -f
docker logs satb2-worker  -f
docker logs satb2-localstack --tail 20
```

### Database

```bash
docker exec -it satb2-postgres psql -U satb2user -d satb2db

# All analyses
SELECT id, patient_code, status, created_at, completed_at
FROM genomic_analyses ORDER BY created_at DESC LIMIT 20;

# Count by status
SELECT status, COUNT(*) FROM genomic_analyses GROUP BY status;

# Failed analyses
SELECT id, patient_code, result_json FROM genomic_analyses WHERE status = 'FAILED';
```

### S3 (LocalStack)

```bash
# List all objects
aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://satb2-research-data --recursive

# Download and inspect a result
aws --endpoint-url=http://localhost:4566 \
    s3 cp s3://satb2-research-data/results/{analysisId}.json - | python -m json.tool
```

### SQS (LocalStack)

```bash
# Queue depth
aws --endpoint-url=http://localhost:4566 \
    sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/satb2-analysis-queue \
    --attribute-names ApproximateNumberOfMessages

# DLQ depth (failed messages)
aws --endpoint-url=http://localhost:4566 \
    sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/satb2-dlq \
    --attribute-names ApproximateNumberOfMessages
```

---

## Troubleshooting

### Backend won't start — `Connection refused` to postgres

PostgreSQL is not healthy yet. Check:
```bash
docker-compose ps postgres
docker logs satb2-postgres --tail 20
```

### Analysis stays `PENDING` forever

Worker is not picking up messages. Check:
```bash
docker logs satb2-worker -f
# Look for: "Worker started. Polling SQS queue:"
# If missing: SQS_QUEUE_URL or S3_BUCKET env var not set
```

### Analysis stuck in `PROCESSING`

Worker failed mid-pipeline. Check:
```bash
docker logs satb2-worker 2>&1 | grep -A5 "ERROR"
```

Manually reset:
```bash
curl -X PUT http://localhost:8080/api/genomic/analysis/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status":"FAILED","resultJson":"{\"error\":\"manual reset\"}"}'
```

### Worker starts but immediately crashes

Missing required env vars:
```
EnvironmentError: Missing required environment variables: SQS_QUEUE_URL and S3_BUCKET must be set
```
Check `docker-compose.yml` — both `SQS_QUEUE_URL` and `S3_BUCKET` must be set.

### Port already in use

```bash
# Windows
netstat -ano | findstr :8080
netstat -ano | findstr :4566
netstat -ano | findstr :5432
```

Change ports in `docker-compose.yml` if needed:
```yaml
ports:
  - "8081:8080"  # host:container
```

### LocalStack not healthy after 2 minutes

```bash
docker logs satb2-localstack --tail 30
```

Try pulling a fresh image:
```bash
docker pull localstack/localstack:3.4
docker-compose up --build
```

### `Only .fasta, .fa and .vcf files are accepted`

The file extension check in `GenomicController` is case-sensitive. Rename the file if needed:
- `sequence.FASTA` → `sequence.fasta`
- `variants.VCF` → `variants.vcf`
