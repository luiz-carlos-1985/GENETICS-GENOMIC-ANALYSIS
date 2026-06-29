# Architecture — SATB2 Genomic Analysis Platform

Deep technical reference for every component of the platform.

---

## Table of Contents

- [Architectural Principles](#architectural-principles)
- [Backend — Spring Boot](#backend--spring-boot)
- [AI Worker — Python](#ai-worker--python)
- [Data Model](#data-model)
- [SQS Message Contract](#sqs-message-contract)
- [AWS Infrastructure](#aws-infrastructure)
- [Local Development Environment](#local-development-environment)
- [Security Model](#security-model)
- [Bioinformatics Pipeline](#bioinformatics-pipeline)
- [Offline Mode](#offline-mode)
- [Phase 3 Roadmap — SageMaker gRNA Design](#phase-3-roadmap--sagemaker-grna-design)

---

## Architectural Principles

### Asynchronous by Default
Genomic files range from kilobytes to hundreds of megabytes. Analysis cannot block an HTTP request. SQS decouples upload (sync, sub-second) from pipeline execution (async, seconds to minutes).

### Transactional Integrity
`ingestSequenceFile()` is `@Transactional`. The sequence is: persist DB record → upload S3 → send SQS. If S3 or SQS fails, `rollbackS3Upload()` deletes the orphaned object and the exception propagates, rolling back the DB transaction.

### Bidirectional Worker Communication
The worker has no direct DB access. All state changes go through `PUT /api/genomic/analysis/{id}/status`. This keeps the worker stateless, horizontally scalable, and independently deployable.

### Offline-First Local Development
LocalStack 3.4 emulates S3 and SQS inside Docker with no `docker.sock` mount — fully compatible with Windows Docker Desktop. The ClinVar classifier has a built-in local cache so the system works even without internet access.

---

## Backend — Spring Boot

### Stack

| Layer | Technology |
|-------|-----------|
| Language | Java 21 |
| Framework | Spring Boot 3.2.5 |
| Build | Maven 3.9+ |
| Persistence | Spring Data JPA + Hibernate (ddl-auto: update) |
| Database driver | PostgreSQL JDBC |
| AWS SDK | AWS SDK for Java v2 — 2.25.40 |
| Serialization | Jackson ObjectMapper (registered as Spring bean in `AwsConfig`) |
| Security | Spring Security (CSRF disabled, CORS: localhost:3000) |
| Utilities | Lombok |

### Class Map

```
com.satb2/
│
├── Satb2Application            Entry point
│
├── controller/
│   ├── GenomicController       POST /upload · GET /analysis/{id} · GET /analysis/patient/{code} · GET /health
│   └── StatusUpdateController  PUT /analysis/{id}/status  (worker → backend)
│
├── service/
│   └── GenomicIngestionService
│       ├── ingestSequenceFile()      @Transactional
│       │   persist → S3 upload → SQS dispatch → on error: rollbackS3Upload()
│       ├── getAnalysisById()         throws GenomicProcessingException if not found
│       ├── getAnalysesByPatient()    findByPatientCodeOrderByCreatedAtDesc
│       └── updateAnalysisStatus()   @Transactional · sets completedAt on COMPLETED/FAILED
│
├── repository/
│   └── GenomicAnalysisRepository   JpaRepository<GenomicAnalysis, String>
│       ├── findByPatientCodeOrderByCreatedAtDesc(patientCode)
│       ├── findByStatusOrderByCreatedAtDesc(status)
│       └── findByS3FileKey(s3FileKey)
│
├── model/
│   └── GenomicAnalysis             @Entity · table: genomic_analyses
│       fields: id(UUID), patientCode, s3FileKey, originalFileName, fileSize,
│               status(enum), resultJson(TEXT), createdAt, completedAt
│       @PrePersist: status=PENDING, createdAt=now()
│
├── dto/
│   └── AnalysisResponse            flat DTO · static factory: from(GenomicAnalysis)
│
├── exception/
│   ├── GenomicProcessingException  RuntimeException subclass
│   └── GlobalExceptionHandler      @RestControllerAdvice
│       ├── GenomicProcessingException     → HTTP 500
│       ├── MaxUploadSizeExceededException → HTTP 413
│       └── Exception (catch-all)          → HTTP 500
│
└── config/
    ├── AwsConfig           S3Client + SqsClient + ObjectMapper beans
    │   AWS_ENDPOINT_OVERRIDE set → StaticCredentials("test","test") + forcePathStyle(S3)
    │   AWS_ENDPOINT_OVERRIDE not set → DefaultCredentialsProvider (IAM role / env / ~/.aws)
    └── SecurityConfig      CSRF disabled · CORS: GET/POST/PUT/DELETE from localhost:3000
```

### Key Configuration (`application.yml`)

```yaml
spring.datasource.url:       ${DB_URL:jdbc:postgresql://localhost:5432/satb2db}
spring.datasource.username:  ${DB_USER:satb2user}
spring.datasource.password:  ${DB_PASS:satb2pass}
spring.jpa.hibernate.ddl-auto: update
spring.servlet.multipart.max-file-size: 500MB

aws.region:           ${AWS_REGION:us-east-1}
aws.s3.bucket-name:   ${S3_BUCKET:satb2-research-data}
aws.sqs.queue-url:    ${SQS_QUEUE_URL:http://localhost:4566/000000000000/satb2-analysis-queue}
```

> Default SQS URL points to LocalStack — safe to run locally without any environment variables set.

### Dockerfile (multi-stage)

```
Stage 1: maven:3.9.6-eclipse-temurin-21  → mvn package -DskipTests
Stage 2: eclipse-temurin:21-jre-alpine   → copies *.jar, EXPOSE 8080
```

---

## AI Worker — Python

### Stack

| Library | Version | Purpose |
|---------|---------|---------|
| Python | 3.12 | Runtime |
| boto3 | 1.34.100 | S3 + SQS clients |
| biopython | 1.83 | SeqIO FASTA parsing |
| requests | 2.31.0 | ClinVar API + backend status updates |
| numpy | 1.26.4 | Cosine distance computation |

> `torch` and `transformers` are intentionally excluded — they are ~3GB and not yet used. They will be added in Phase 3 when SageMaker inference is implemented.

### Module Map

```
ai-worker/
│
├── worker.py                     Main entry point
│   ├── Startup: validates SQS_QUEUE_URL + S3_BUCKET (EnvironmentError if missing)
│   ├── boto3 clients: endpoint_url=AWS_ENDPOINT_URL (LocalStack support)
│   ├── SATB2_REFERENCE: 384bp representative coding fragment
│   ├── poll()
│   │   └── SQS receive_message(WaitTimeSeconds=20, MaxNumberOfMessages=1)
│   │       ├── process_message() success → delete_message()
│   │       ├── process_message() failure → log error + consecutive_failures++
│   │       └── consecutive_failures ≥ 5 → 60s cooldown, reset counter
│   └── process_message(message)
│       ├── update_analysis_status(id, "PROCESSING")
│       ├── _download_from_s3(file_key, bucket)
│       ├── _run_pipeline(file_key, content, patient_code)
│       ├── _upload_result(analysis_id, result, bucket)  → results/{id}.json
│       ├── update_analysis_status(id, "COMPLETED", result_json)
│       └── on exception: update_analysis_status(id, "FAILED", error_json), re-raise
│
├── services/
│   ├── sequence_parser.py
│   │   ├── parse_fasta(bytes) → List[ParsedSequence]
│   │   │   Bio.SeqIO.parse · computes GC% per record · uppercases sequence
│   │   └── parse_vcf(bytes) → List[ParsedVariant]
│   │       tab-delimited · skips '#' lines · extracts GENEINFO from INFO field
│   │
│   ├── variant_classifier.py
│   │   ├── SATB2 region: chr2:200,124,263–200,320,351
│   │   ├── KNOWN_PATHOGENIC_POSITIONS: set of ~30 offline positions (GRCh38)
│   │   ├── classify_variant(chr, pos, ref, alt) → VariantClassification
│   │   │   1. region check → NOT_IN_SATB2_REGION if outside
│   │   │   2. _resolve_significance() → tier-1 cache, then tier-2 ClinVar
│   │   └── _query_clinvar_safe() → returns None on any exception (offline-safe, 5s timeout)
│   │
│   └── status_updater.py
│       └── update_analysis_status(id, status, result_json)
│           PUT {BACKEND_URL}/api/genomic/analysis/{id}/status · timeout=10s · non-blocking on error
│
└── models/
    └── sequence_embedder.py
        ├── tokenize_sequence(sequence, k=6) → (kmers, vocabulary)
        │   sliding window · vocabulary = {kmer: int_index}
        ├── embed_sequence(id, sequence, k=6) → SequenceEmbedding
        │   tokens = list of int indices
        └── compute_mutation_distance(wild_type, mutant, k=6) → float [0.0, 1.0]
            cosine distance between k-mer frequency vectors
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
RUN apt-get install -y gcc          # required for biopython C extensions
COPY requirements.txt . && pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app                 # resolves services/ and models/ imports
CMD ["python", "worker.py"]
```

---

## Data Model

### Table: `genomic_analyses`

```sql
CREATE TABLE genomic_analyses (
    id                  VARCHAR(36)  PRIMARY KEY,  -- UUID (GenerationType.UUID)
    patient_code        VARCHAR(255) NOT NULL,
    s3_file_key         VARCHAR(512) NOT NULL,
    original_file_name  VARCHAR(255) NOT NULL,
    file_size           BIGINT       NOT NULL,
    status              VARCHAR(20)  NOT NULL,      -- PENDING|PROCESSING|COMPLETED|FAILED
    result_json         TEXT,                       -- NULL until COMPLETED or FAILED
    created_at          TIMESTAMP    NOT NULL,      -- set by @PrePersist
    completed_at        TIMESTAMP                   -- set when status → COMPLETED or FAILED
);
```

### Status Transition Table

| From | To | Set by | When |
|------|----|--------|------|
| — | `PENDING` | `@PrePersist` | DB record created on upload |
| `PENDING` | `PROCESSING` | Worker via `PUT /status` | Worker receives SQS message |
| `PROCESSING` | `COMPLETED` | Worker via `PUT /status` | Pipeline finishes successfully |
| `PROCESSING` | `FAILED` | Worker via `PUT /status` | Any unhandled exception in pipeline |

---

## SQS Message Contract

### Backend → Worker (message body)

```json
{
  "analysisId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "s3FileKey":  "raw-sequences/3fa85f64-...-sample_satb2.fasta",
  "patientCode": "SATB2-PT-001",
  "bucketName":  "satb2-research-data"
}
```

### Queue Settings

| Setting | Value | Reason |
|---------|-------|--------|
| `visibility_timeout_seconds` | 300 | Worker has 5 min to process before re-visibility |
| `message_retention_seconds` | 86400 | Messages kept 24h |
| `maxReceiveCount` (DLQ) | 3 | After 3 failed receives → moves to DLQ |
| DLQ retention | 1,209,600s | 14 days for investigation |

---

## AWS Infrastructure

All resources defined in `infra/main.tf` (Terraform ~5.0).

### Resource Inventory

| Terraform Resource | Name | Purpose |
|-------------------|------|---------|
| `aws_s3_bucket` | `satb2-research-data` | Raw files + result JSONs |
| `aws_s3_bucket_versioning` | — | Data recovery |
| `aws_s3_bucket_server_side_encryption_configuration` | — | AES256 SSE |
| `aws_sqs_queue` | `satb2-queue` | Analysis job queue |
| `aws_sqs_queue` (DLQ) | `satb2-dlq` | Failed messages after 3 attempts |
| `aws_db_subnet_group` | `satb2-subnet-group` | RDS subnet placement |
| `aws_db_instance` | `satb2-db` | PostgreSQL 15.4, db.t3.micro, 20GB, encrypted |
| `aws_ecr_repository` | `satb2-backend` | Spring Boot image |
| `aws_ecr_repository` | `satb2-worker` | Python worker image |
| `aws_sagemaker_domain` | `satb2-ai-domain` | Phase 3 AI inference |
| `aws_iam_role` | `satb2-ecs-task-execution` | ECR pull by ECS agent |
| `aws_iam_role` | `satb2-ecs-task` | Runtime S3+SQS access (least privilege) |
| `aws_iam_role` | `satb2-sagemaker-role` | SageMaker execution |
| `aws_security_group` | `satb2-rds-sg` | Port 5432 restricted to VPC CIDR |

### IAM Least Privilege (ECS Task Role)

```json
S3: GetObject, PutObject, DeleteObject, ListBucket → satb2-research-data only
SQS: ReceiveMessage, DeleteMessage, SendMessage, GetQueueAttributes → analysis queue + DLQ only
```

### Terraform Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `aws_region` | ❌ | `us-east-1` | |
| `project_name` | ❌ | `satb2` | Resource name prefix |
| `s3_bucket_name` | ❌ | `satb2-research-data` | Must be globally unique |
| `db_username` | ✅ | — | `sensitive = true` |
| `db_password` | ✅ | — | `sensitive = true` |
| `vpc_id` | ✅ | — | Existing VPC |
| `vpc_cidr` | ❌ | `10.0.0.0/16` | For RDS security group ingress |
| `private_subnet_ids` | ✅ | — | Min 2 subnets, different AZs |

---

## Local Development Environment

### Service Startup Order

```
postgres (healthcheck: pg_isready)
    └── localstack:3.4 (healthcheck: /_localstack/health)
            └── init-aws (creates S3 bucket + folders + SQS queues)
                    └── backend (healthcheck: GET /health)
                            └── worker (restart: on-failure)
```

### LocalStack Configuration

- Image: `localstack/localstack:3.4` (pinned — avoids breaking changes from `latest`)
- Services: `s3,sqs` only — no lambda, no other services
- `EAGER_SERVICE_LOADING: 1` — S3 and SQS are initialized immediately, not on first request
- No `docker.sock` mount — compatible with Windows Docker Desktop
- `LOCALSTACK_HOST: localstack` — correct hostname resolution inside Docker network

### AwsConfig LocalStack Detection

```java
String endpoint = System.getenv("AWS_ENDPOINT_OVERRIDE");
if (endpoint != null && !endpoint.isEmpty()) {
    // Local mode: static credentials + path-style S3
    builder.endpointOverride(URI.create(endpoint))
           .forcePathStyle(true)
           .credentialsProvider(StaticCredentialsProvider.create(
                   AwsBasicCredentials.create("test", "test")));
} else {
    // Production mode: IAM role / env vars / ~/.aws/credentials
    builder.credentialsProvider(DefaultCredentialsProvider.create());
}
```

---

## Security Model

| Control | Implementation |
|---------|---------------|
| CSRF | Disabled (stateless REST API) |
| CORS | `localhost:3000` only (frontend UI) |
| File type | `.fasta`, `.fa`, `.vcf` whitelist |
| File size | 500 MB hard limit (Spring + controller) |
| RDS network | Security group: port 5432 from VPC CIDR only |
| S3 encryption | AES256 server-side encryption |
| S3 versioning | Enabled for data recovery |
| SQS access | IAM policy — least privilege per task role |
| AWS credentials | `DefaultCredentialsProvider` in production (no hardcoded keys) |

---

## Bioinformatics Pipeline

### FASTA Pipeline

```
bytes input
    │
    ▼ Bio.SeqIO.parse()
List[ParsedSequence]  ← sequence_id, sequence (uppercase), length, gc_content
    │
    ▼ (skip sequences shorter than 6 bp)
    │
    ▼ tokenize_sequence(sequence, k=6)
overlapping hexamers → vocabulary {kmer: int_index}
    │
    ▼ compute_mutation_distance(SATB2_REFERENCE_384bp, sequence, k=6)
cosine distance [0.0 – 1.0]
    │
    ▼ _classify_severity(distance)
LOW (<= 0.05) | MODERATE (0.05–0.15) | HIGH (> 0.15)
    │
    ▼ _generate_fasta_summary(embeddings)
{high_risk_sequences, moderate_risk_sequences, low_risk_sequences, recommendation}
```

### VCF Pipeline

```
bytes input
    │
    ▼ tab-delimited parse (skip '#' lines)
List[ParsedVariant]  ← chromosome, position, ref_allele, alt_allele, gene_symbol
    │
    ▼ classify_variant(chr, pos, ref, alt)
    │
    ├── position NOT in chr2:200124263–200320351
    │       → clinvar_significance="NOT_IN_SATB2_REGION"
    │
    └── position IN SATB2 region
            ▼ _resolve_significance()
            ├── Tier 1: pos in KNOWN_PATHOGENIC_POSITIONS → "Pathogenic" (offline, instant)
            ├── Tier 2: GET eutils.ncbi.nlm.nih.gov ... timeout=5s
            │           → "Pathogenic" | "Benign" (or None if network unavailable)
            └── Fallback: "Benign"
                │
                ▼ requires_crispra_screening = significance in ("Pathogenic", "Likely pathogenic")
                │
                ▼ _generate_clinical_recommendation(crispra_candidates)
```

### Cosine Mutation Distance

```
Given sequences wt and mut, k=6:

  freq_wt[kmer]  = count of kmer in wt  (or 0 if absent)
  freq_mut[kmer] = count of kmer in mut (or 0 if absent)

  distance = 1 - dot(freq_wt, freq_mut) / (||freq_wt|| × ||freq_mut||)

Interpretation:
  0.000        → identical k-mer composition
  0.001–0.050  → LOW — within normal variation
  0.051–0.150  → MODERATE — possible functional impact
  > 0.150      → HIGH — likely structural disruption
```

---

## Offline Mode

When the system has no internet access:

| Component | Behavior |
|-----------|---------|
| `variant_classifier.py` | Uses `KNOWN_PATHOGENIC_POSITIONS` cache — logs `WARNING: ClinVar API unavailable (offline mode active)` |
| `status_updater.py` | If backend unreachable → logs error, does not raise (non-blocking) |
| S3 / SQS | Always local via LocalStack |
| Database | Always local via PostgreSQL container |
| ClinVar API | Best-effort: `timeout=5s`, returns `None` → falls back to `"Benign"` |

The analysis pipeline **completes correctly in 100% offline mode**.

---

## Phase 3 Roadmap — SageMaker gRNA Design

Planned architecture for automated gRNA design from CRISPRa candidates:

```
crispra_candidates (from VCF pipeline)
    │
    ▼ Extract SATB2 promoter 200bp windows around each candidate position
    │
    ▼ Enumerate all 20-mer sequences with NGG PAM sites (SpCas9)
    │
    ▼ SageMaker Endpoint (gRNA scoring model)
    │   Input:  20-mer + flanking context
    │   Model:  DNABERT-2 fine-tuned on CRISPRa activity data
    │   Output: on-target efficiency score [0–1]
    │
    ▼ Off-target filtering
    │   Cas-OFFinder: genome-wide 20-mer similarity search
    │   Filter: off-target score > threshold → excluded
    │
    ▼ Output: top-3 ranked gRNAs per patient
        {sequence, gc_content, on_target_score, off_target_count, pam_site}
```

**New files required:**
- `ai-worker/services/grna_designer.py`
- `ai-worker/services/offtarget_scorer.py`
- `infra/sagemaker_endpoint.tf`
- Worker `requirements.txt`: add `torch`, `transformers`
