# Running 100% Locally — SATB2 Platform

Complete guide for running the entire SATB2 platform on your machine with **zero AWS dependency**.

---

## How It Works Offline

The full platform runs locally with Docker Compose. The current user experience is a static web UI served on port 3000, with the backend API available on port 8080.

Every cloud service is replaced by a local equivalent:

| Production (AWS) | Local Equivalent | Technology |
|-----------------|-----------------|-----------|
| Amazon S3 | LocalStack S3 | `localstack/localstack:3.4` on port 4566 |
| Amazon SQS | LocalStack SQS | `localstack/localstack:3.4` on port 4566 |
| Amazon RDS (PostgreSQL) | PostgreSQL container | `postgres:15-alpine` on port 5432 |
| ECS / container runtime | Docker Compose | 5 services with health checks |
| ClinVar API (NCBI) | Local offline cache | `KNOWN_PATHOGENIC_POSITIONS` dict in `variant_classifier.py` |

### ClinVar Offline Strategy (two-tier)

```
1. KNOWN_PATHOGENIC_POSITIONS dict  →  instant, 100% offline, always works
2. Live ClinVar API (timeout=5s)    →  best-effort, skipped if network unavailable
3. Fallback                         →  "Benign" (conservative)
```

When offline, the worker logs:
```
WARNING ClinVar API unavailable (offline mode active): ...
```
The analysis **still completes correctly** using the local cache.

---

## Option 1: Docker Compose (Recommended)

**Only requirement: Docker Desktop.**

### System Requirements

- Docker Desktop installed and running
- At least 4 GB RAM allocated to Docker
- Free ports: `3000` (frontend), `8080` (backend), `5432` (postgres), `4566` (localstack)
- Disk: ~2 GB for images on first run

### Start

```bash
cd GENETICS
docker-compose up --build
```

**First run:** ~90 seconds (downloads images, compiles Java, installs Python deps).  
**Subsequent runs:** ~30 seconds (images cached).

### Verify

```bash
# Frontend UI
http://localhost:3000

# Backend API
curl http://localhost:8080/api/genomic/health
# → {"status":"UP","service":"SATB2 Genomic Analysis API","version":"2.0.0"}

# LocalStack
curl http://localhost:4566/_localstack/health

# All containers
docker compose ps
```

### Test the Full Flow

```bash
# 1. Upload a FASTA file
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.fasta" \
  -F "patientCode=SATB2-TEST-001"

# Returns: {"analysisId":"<uuid>","status":"PENDING", ...}

# 2. Wait ~15 seconds for worker to process

# 3. Check result
curl http://localhost:8080/api/genomic/analysis/<uuid>
# Returns: {"status":"COMPLETED","resultJson":"{...}"}

# 4. Upload a VCF file
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.vcf" \
  -F "patientCode=SATB2-TEST-001"

# 5. List all analyses for the patient
curl http://localhost:8080/api/genomic/analysis/patient/SATB2-TEST-001
```

### Windows Automated Test

```cmd
scripts\test-integration.bat
```

### Watch Worker Process in Real Time

```bash
docker logs satb2-worker -f
```

Expected output after upload:
```
2025-01-15 10:30:05,123 [INFO] Processing analysis abc-123 for patient SATB2-TEST-001
2025-01-15 10:30:06,456 [INFO] Successfully updated analysis abc-123 to status PROCESSING
2025-01-15 10:30:07,789 [INFO] Results uploaded to s3://satb2-research-data/results/abc-123.json
2025-01-15 10:30:08,012 [INFO] Successfully updated analysis abc-123 to status COMPLETED
2025-01-15 10:30:08,013 [INFO] Analysis abc-123 completed successfully
```

### Stop

```bash
docker-compose down        # stop, keep database data
docker-compose down -v     # stop and delete all data (clean slate)
```

---

## Option 2: Manual Setup (Without Docker)

Use this if Docker is not available. Requires Java 21, Maven, Python 3.12, and a local PostgreSQL installation.

### Windows Quick Setup

```cmd
scripts\setup-local.bat
```

This script checks all dependencies and builds both services.

### Manual Step-by-Step

#### 1. Create PostgreSQL database

```sql
CREATE DATABASE satb2db;
CREATE USER satb2user WITH PASSWORD 'satb2pass';
GRANT ALL PRIVILEGES ON DATABASE satb2db TO satb2user;
```

#### 2. Install Python worker

```bash
cd ai-worker
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate

pip install -r requirements.txt
# Installs: biopython, boto3, requests, numpy (~50MB total)
```

#### 3. Start the backend

```bash
cd backend

# Linux/Mac
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

# Windows
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

#### 4. Start the worker

```bash
cd ai-worker

# Linux/Mac
source venv/bin/activate
export SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
export S3_BUCKET=satb2-research-data
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export BACKEND_URL=http://localhost:8080
python worker.py

# Windows
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

## Inspecting Local Resources

### Database

```bash
docker exec -it satb2-postgres psql -U satb2user -d satb2db

# Recent analyses
SELECT id, patient_code, status, created_at FROM genomic_analyses ORDER BY created_at DESC LIMIT 10;
```

### S3 (LocalStack)

```bash
# List everything in the bucket
aws --endpoint-url=http://localhost:4566 s3 ls s3://satb2-research-data --recursive

# Download and pretty-print a result
aws --endpoint-url=http://localhost:4566 \
    s3 cp s3://satb2-research-data/results/{analysisId}.json - | python -m json.tool
```

### SQS (LocalStack)

```bash
# Messages waiting to be processed
aws --endpoint-url=http://localhost:4566 \
    sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/satb2-analysis-queue \
    --attribute-names ApproximateNumberOfMessages

# Failed messages in DLQ
aws --endpoint-url=http://localhost:4566 \
    sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/satb2-dlq \
    --attribute-names ApproximateNumberOfMessages
```

---

## Complete Local Flow Diagram

```
You              Backend              LocalStack S3/SQS       Worker
 │                  │                       │                    │
 │─ POST /upload ──►│                       │                    │
 │                  │─ INSERT (PENDING) ───►│                    │
 │                  │─ PutObject S3 ────────►│                    │
 │                  │─ SendMessage SQS ─────►│                    │
 │◄── 202 {id} ────│                       │                    │
 │                  │                       │◄─ ReceiveMessage ──│
 │                  │◄──────── PUT /status PROCESSING ──────────│
 │                  │─ UPDATE DB ──────────►│                    │
 │                  │                       │◄─ GetObject ───────│
 │                  │                       │────── file ────────►│
 │                  │                       │     parse+classify  │
 │                  │                       │◄─ PutObject (result)│
 │                  │◄──────── PUT /status COMPLETED + resultJson │
 │                  │─ UPDATE DB ──────────►│                    │
 │                  │                       │◄─ DeleteMessage ───│
 │─ GET /analysis ─►│                       │                    │
 │◄── {COMPLETED}──│                       │                    │
```

---

## Troubleshooting

### Port already in use

```bash
# Windows: find and kill process on a port
netstat -ano | findstr :8080
taskkill /PID <pid> /F
```

Change the host port in `docker-compose.yml`:
```yaml
ports:
  - "8081:8080"   # use 8081 externally
```

### Backend crashes on startup

```bash
docker logs satb2-backend --tail 50
```

Common causes:
- `Connection refused` to postgres → postgres not healthy yet, retry `docker-compose up`
- `BeanCreationException` on `AwsConfig` → `AWS_ENDPOINT_OVERRIDE` env var missing
- `Could not create connection pool` → wrong `DB_URL`, `DB_USER`, or `DB_PASS`

### Worker exits immediately

```bash
docker logs satb2-worker
```

Look for:
```
EnvironmentError: Missing required environment variables: SQS_QUEUE_URL and S3_BUCKET must be set
```
Both variables must be set in `docker-compose.yml` under `worker.environment`.

### LocalStack unhealthy

```bash
docker logs satb2-localstack --tail 30
```

Try:
```bash
docker-compose down -v
docker pull localstack/localstack:3.4
docker-compose up --build
```

### Python import errors when running worker manually

```bash
cd ai-worker
python -c "from services.sequence_parser import parse_fasta; print('OK')"
python -c "from models.sequence_embedder import tokenize_sequence; print('OK')"
```

If these fail, verify:
1. Virtual environment is activated
2. `PYTHONPATH` includes the `ai-worker/` directory:
   ```bash
   # Linux/Mac
   export PYTHONPATH=/path/to/GENETICS/ai-worker
   # Windows
   set PYTHONPATH=C:\PROJETOS\GENETICS\ai-worker
   ```

### File extension rejected

The check in `GenomicController` is case-sensitive. Rename if needed:
- `file.FASTA` → `file.fasta`
- `file.VCF` → `file.vcf`
