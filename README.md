# SATB2 Genomic Analysis Platform

> An end-to-end, production-grade platform for processing genomic data from patients with **SATB2-Associated Syndrome (Glass Syndrome)**, predicting the structural impact of mutations, and recommending optimized guide RNA designs for CRISPRa activation therapies.

---

## Table of Contents

- [Scientific Background](#scientific-background)
- [Platform Overview](#platform-overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Implementation Phases](#implementation-phases)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Data Sources](#data-sources)
- [Contributing](#contributing)

---

## Scientific Background

### Target Gene: SATB2

**SATB2** (Special AT-rich Sequence Binding Protein 2) is located on chromosome 2q33.1 and encodes a transcription factor that acts as a master regulator of gene expression in cortical neurons, craniofacial development, and bone formation.

- **NCBI GeneID:** 23314
- **Ensembl ID:** ENSG00000119042
- **UniProt:** Q9UPW6
- **Genomic coordinates (GRCh38):** chr2:200,124,263–200,320,351

### SATB2-Associated Syndrome (Glass Syndrome)

SATB2-Associated Syndrome is a rare neurodevelopmental disorder caused by **haploinsufficiency** — one copy of the SATB2 gene is non-functional (due to point mutation, deletion, or truncation), while the other copy remains intact but unable to compensate at 50% expression.

**Key clinical features:**
- Severe intellectual disability and absent or limited speech
- Behavioral abnormalities (autism-like behaviors)
- Cleft palate and dental anomalies
- Skeletal abnormalities (osteoporosis)

### Therapeutic Strategy: CRISPRa

Since the patient retains one healthy copy of SATB2, the most promising therapeutic strategy is **CRISPRa (CRISPR Activation)** — a modified CRISPR system that does not cut DNA, but instead recruits transcriptional activators (VP64, VPR, SAM complexes) to the SATB2 promoter region, forcing the healthy copy to produce double the normal protein output.

**Role of AI in this platform:**
- Predict which genomic variants are pathogenic using a two-tier strategy: local offline cache + live ClinVar API
- Tokenize DNA sequences into k-mers (k=6) for downstream deep learning models (DNABERT-2, Nucleotide Transformer)
- Compute cosine mutation distance to quantify divergence from the reference SATB2 sequence
- Generate clinical-grade recommendations for CRISPRa gRNA design

---

## Platform Overview

```
┌─────────────────────────────────────────────────────────┐
│                    SATB2 PLATFORM v2.0                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Static Frontend]  ──► http://localhost:3000          │
│          │                                              │
│  [Spring Boot Backend] ──► http://localhost:8080       │
│          │                                              │
│  [SQS Queue]                                           │
│          │                                              │
│  [Python AI Worker] ──► PostgreSQL + LocalStack        │
│          │                                              │
│  [S3 / LocalStack]  (raw files + result JSON)         │
│          │                                              │
│  [PostgreSQL]  (analysis history + status tracking)   │
│                                                         │
│  Local development runs entirely through Docker Compose │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture

### Component Responsibilities

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Backend | Java 21 + Spring Boot 3.2.5 | REST API, file ingestion, SQS orchestration, DB persistence, rollback |
| AI Worker | Python 3.12 + Biopython 1.83 | FASTA/VCF parsing, two-tier ClinVar lookup, k-mer tokenization, mutation scoring |
| Database | PostgreSQL 15 | Analysis records, status transitions, result storage |
| Object Storage | S3 / LocalStack S3 | Raw genomic files (`raw-sequences/`), result JSONs (`results/`) |
| Message Queue | SQS / LocalStack SQS | Async decoupling — visibility timeout 300s, DLQ after 3 failures |
| Container Registry | Amazon ECR | Docker images for backend and worker |
| AI/ML Platform | Amazon SageMaker | Phase 3 — gRNA design model inference |
| Infrastructure | Terraform 1.5+ | All AWS resources as code (IAM, SG, S3, SQS, RDS, ECR, SageMaker) |
| Local Dev | Docker Compose + LocalStack 3.4 | Full system locally, zero AWS cost, Windows-compatible |

### Data Flow

```
1. Researcher uploads .fasta or .vcf via POST /api/genomic/upload
2. Backend validates: type (.fasta/.fa/.vcf), size (≤500MB), patientCode (not blank)
3. Backend persists GenomicAnalysis record in PostgreSQL (status: PENDING)
4. Backend uploads file to S3 → raw-sequences/{uuid}-{filename}
5. Backend sends SQS message: {analysisId, s3FileKey, patientCode, bucketName}
6. Worker polls SQS (long polling, 20s wait, MaxNumberOfMessages=1)
7. Worker calls PUT /api/genomic/analysis/{id}/status → PROCESSING
8. Worker downloads file from S3
9. Worker runs bioinformatics pipeline:
   - FASTA: k-mer tokenization (k=6) + cosine mutation distance vs SATB2_REFERENCE (384bp)
   - VCF:   two-tier ClinVar lookup (local cache → live API) + SATB2 region validation
10. Worker uploads result JSON to S3 → results/{analysisId}.json
11. Worker calls PUT /api/genomic/analysis/{id}/status → COMPLETED + resultJson
12. On any exception: worker calls status → FAILED + error JSON, re-raises (SQS DLQ after 3x)
13. Researcher queries GET /api/genomic/analysis/{id} for results
```

### S3 Object Structure

```
satb2-research-data/
├── raw-sequences/    ← backend writes here on upload
│   └── {uuid}-{original-filename}
└── results/          ← worker writes here on completion
    └── {analysisId}.json
```

---

## Project Structure

```
GENETICS/
├── backend/
│   ├── src/main/java/com/satb2/
│   │   ├── Satb2Application.java
│   │   ├── controller/
│   │   │   ├── GenomicController.java       # POST /upload, GET /analysis/{id}, GET /analysis/patient/{code}, GET /health
│   │   │   └── StatusUpdateController.java  # PUT /analysis/{id}/status  (worker → backend)
│   │   ├── service/
│   │   │   └── GenomicIngestionService.java # @Transactional: persist → S3 upload → SQS dispatch → rollback
│   │   ├── repository/
│   │   │   └── GenomicAnalysisRepository.java
│   │   ├── model/
│   │   │   └── GenomicAnalysis.java         # JPA entity, @PrePersist sets status=PENDING + createdAt
│   │   ├── dto/
│   │   │   └── AnalysisResponse.java
│   │   ├── exception/
│   │   │   ├── GenomicProcessingException.java
│   │   │   └── GlobalExceptionHandler.java  # 500/413 handlers
│   │   └── config/
│   │       ├── AwsConfig.java               # S3/SQS beans — StaticCredentials for LocalStack, Default for AWS
│   │       └── SecurityConfig.java          # CSRF disabled, CORS → localhost:3000
│   ├── src/main/resources/application.yml
│   ├── Dockerfile                           # multi-stage Maven → JRE alpine
│   └── pom.xml
│
├── ai-worker/
│   ├── worker.py                            # SQS poll loop — consecutive failure tracking, graceful shutdown
│   ├── services/
│   │   ├── sequence_parser.py               # parse_fasta (Biopython SeqIO) + parse_vcf (tab-delimited)
│   │   ├── variant_classifier.py            # two-tier: local KNOWN_PATHOGENIC_POSITIONS → ClinVar API
│   │   └── status_updater.py               # PUT /api/genomic/analysis/{id}/status
│   ├── models/
│   │   └── sequence_embedder.py             # k=6 tokenization + cosine distance
│   ├── requirements.txt                     # biopython, boto3, requests, numpy (lightweight — ~50MB)
│   └── Dockerfile                           # python:3.12-slim + gcc + PYTHONPATH=/app
│
├── frontend/
│   ├── index.html                     # polished single-page UI served by nginx
│   ├── favicon.ico
│   └── Dockerfile
│
├── infra/
│   ├── main.tf       # S3+versioning+SSE, SQS+DLQ, RDS PG15, ECR×2, SageMaker, IAM roles×3, SG
│   ├── variables.tf  # aws_region, project_name, s3_bucket_name, db_*, vpc_id, vpc_cidr, private_subnet_ids
│   └── outputs.tf    # s3_bucket_name, sqs_queue_url, rds_endpoint(sensitive), ecr_*_url
│
├── test-data/
│   ├── sample_satb2.fasta   # wild-type + missense mutant sequences
│   └── sample_satb2.vcf     # 3 variants in SATB2 region (chr2:200,124,263–200,320,351)
│
├── scripts/
│   ├── test-integration.sh  # Linux/Mac E2E test
│   ├── test-integration.bat # Windows E2E test
│   └── setup-local.bat      # Windows dependency check + build
│
├── docker-compose.yml        # 5 services: postgres, localstack:3.4, init-aws, backend, worker
├── README.md
├── API_REFERENCE.md
├── ARCHITECTURE.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── DEPLOYMENT.md
├── LOCAL_SETUP.md
├── SCIENCE.md
└── VALIDATION_CHECKLIST.md
```

---

## Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | AWS infrastructure + Spring Boot API + S3 upload + SQS dispatch | ✅ Complete |
| 2 | Python worker — FASTA/VCF parsing + ClinVar classification + k-mer embeddings | ✅ Complete |
| 2.5 | DB persistence + bidirectional status tracking + rollback + error handling | ✅ Complete |
| 2.6 | 100% local mode — LocalStack 3.4 (Windows-compatible) + offline ClinVar cache | ✅ Complete |
| 3 | SageMaker integration — DNABERT-2 + gRNA design AI models | 🔴 Ready to start |
| 4 | Static frontend experience — upload workflow, analysis details, executive dashboard | ✅ Available |

---

## Quick Start

A single requirement is enough: Docker Desktop.

```bash
# Start the full local platform
docker compose up --build
```

Then open the UI at http://localhost:3000 and use the backend API at http://localhost:8080.

```bash
# Health check
curl http://localhost:8080/api/genomic/health

# Upload a FASTA sample
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.fasta" \
  -F "patientCode=SATB2-PT-001"

# Upload a VCF sample
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.vcf" \
  -F "patientCode=SATB2-PT-001"

# List analyses for a patient
curl http://localhost:8080/api/genomic/analysis/patient/SATB2-PT-001
```

See [LOCAL_SETUP.md](LOCAL_SETUP.md) for the full local guide and troubleshooting.  
See [DEPLOYMENT.md](DEPLOYMENT.md) for AWS production deployment.  
See [API_REFERENCE.md](API_REFERENCE.md) for all endpoints with schemas and examples.

---

## Data Sources

| Source | Purpose | Identifier |
|--------|---------|------------|
| NCBI GenBank / RefSeq | SATB2 reference mRNA | GeneID: 23314 / NM_001172509 |
| ClinVar | Known pathogenic variant cross-reference | Gene: SATB2 |
| AlphaFold DB | 3D protein structure prediction | UniProt: Q9UPW6 |
| Ensembl | Exon/intron annotations | ENSG00000119042 |
| gnomAD | Healthy population variant control set | ENSG00000119042 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution opportunities, code standards, and how to reach research institutions.

**Key contacts:**
- SATB2 Gene Foundation: info@satb2gene.org
- Chan Zuckerberg Initiative (Open Science): openscience@chanzuckerberg.com
