# API Reference — SATB2 Genomic Analysis Platform

**Base URL (local):** `http://localhost:8080`  
**Base URL (production):** `https://<api-gateway-id>.execute-api.us-east-1.amazonaws.com`  
**API Version:** `2.0.0`  
**Authentication:** No authentication is required for the current demo experience. The frontend is served from `http://localhost:3000` and the backend API is available at `http://localhost:8080`.

---

## Endpoints

| Method | Path | Controller | Description |
|--------|------|-----------|-------------|
| `GET` | `/api/genomic/health` | `GenomicController` | Service health check |
| `POST` | `/api/genomic/upload` | `GenomicController` | Upload FASTA or VCF file |
| `GET` | `/api/genomic/analysis/{id}` | `GenomicController` | Get analysis by ID |
| `GET` | `/api/genomic/analysis/patient/{code}` | `GenomicController` | List all analyses for a patient |
| `PUT` | `/api/genomic/analysis/{id}/status` | `StatusUpdateController` | Update status (worker → backend, internal) |

---

## 1. Health Check

```
GET /api/genomic/health
```

### Response — 200 OK

```json
{
  "status": "UP",
  "service": "SATB2 Genomic Analysis API",
  "version": "2.0.0"
}
```

---

## 2. Upload Genomic File

Validates the file, persists a `GenomicAnalysis` record in PostgreSQL (status: `PENDING`), uploads to S3 under `raw-sequences/{uuid}-{filename}`, and dispatches an SQS message for async processing.

```
POST /api/genomic/upload
Content-Type: multipart/form-data
```

### Request Parameters

| Parameter | Type | Required | Constraints |
|-----------|------|----------|-------------|
| `file` | `MultipartFile` | ✅ | Extensions: `.fasta`, `.fa`, `.vcf`. Max size: 500 MB. Cannot be empty. |
| `patientCode` | `String` | ✅ | Must not be blank. Example: `SATB2-PT-001` |

### Validation logic (in order)

1. `file.isEmpty()` → 400
2. `file.getSize() > 500 * 1024 * 1024` → 400
3. filename not ending in `.fasta`, `.fa`, or `.vcf` → 400
4. Pass → persist DB record → upload S3 → send SQS → return 202

### Response — 202 Accepted

```json
{
  "message": "File received and queued for analysis",
  "analysisId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "patientCode": "SATB2-PT-001",
  "fileName": "sample_satb2.fasta",
  "fileSize": 1048576,
  "status": "PENDING"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `analysisId` | `String (UUID)` | Store this to poll for results. |
| `patientCode` | `String` | Echoed from request. |
| `fileName` | `String` | Original filename as uploaded. |
| `fileSize` | `Long` | File size in bytes. |
| `status` | `String` | Always `PENDING` at this stage. |

### Response — 400 Bad Request

```json
{ "error": "File cannot be empty" }
{ "error": "Only .fasta, .fa and .vcf files are accepted" }
{
  "error": "File size exceeds 500MB limit",
  "size": 600000000,
  "maxSize": 524288000
}
```

### Example

```bash
# FASTA
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.fasta" \
  -F "patientCode=SATB2-PT-001"

# VCF
curl -X POST http://localhost:8080/api/genomic/upload \
  -F "file=@test-data/sample_satb2.vcf" \
  -F "patientCode=SATB2-PT-001"

# Windows
curl -X POST http://localhost:8080/api/genomic/upload ^
  -F "file=@test-data/sample_satb2.fasta" ^
  -F "patientCode=SATB2-PT-001"
```

---

## 3. Get Analysis by ID

Returns full details and results of a specific analysis.

```
GET /api/genomic/analysis/{id}
```

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | `String (UUID)` | The `analysisId` returned from the upload endpoint. |

### Response — 200 OK (`AnalysisResponse` DTO)

```json
{
  "analysisId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "patientCode": "SATB2-PT-001",
  "fileName": "sample_satb2.fasta",
  "status": "COMPLETED",
  "s3FileKey": "raw-sequences/3fa85f64-5717-4562-b3fc-2c963f66afa6-sample_satb2.fasta",
  "createdAt": "2025-01-15T10:30:00",
  "completedAt": "2025-01-15T10:31:45",
  "resultJson": "{ ... }"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `analysisId` | `String` | UUID of this analysis. |
| `patientCode` | `String` | Patient identifier. |
| `fileName` | `String` | Original uploaded filename. |
| `status` | `String` | `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED` |
| `s3FileKey` | `String` | Full S3 object key of the raw file. |
| `createdAt` | `LocalDateTime` | When the record was created. |
| `completedAt` | `LocalDateTime` | When processing ended. `null` if still pending/processing. |
| `resultJson` | `String` | Stringified JSON result from the worker. `null` until `COMPLETED`. |

### Response — 500 (not found)

```json
{
  "error": "Analysis not found: 3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "timestamp": "2025-01-15T10:30:00"
}
```

### Example

```bash
curl http://localhost:8080/api/genomic/analysis/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

## 4. Get Analyses by Patient

Returns all analyses for a given patient, ordered by `createdAt` descending.

```
GET /api/genomic/analysis/patient/{patientCode}
```

### Response — 200 OK

Array of `AnalysisResponse` objects (same schema as endpoint 3). Returns `[]` if no analyses found.

```bash
curl http://localhost:8080/api/genomic/analysis/patient/SATB2-PT-001
```

---

## 5. Update Analysis Status (Internal)

> ⚠️ Called exclusively by the Python AI Worker. Do not call from external clients.

```
PUT /api/genomic/analysis/{id}/status
Content-Type: application/json
```

### Request Body (`StatusUpdateRequest`)

```json
{
  "status": "COMPLETED",
  "resultJson": "{\"patient_code\": \"SATB2-PT-001\", ...}"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `String` | ✅ | `PROCESSING`, `COMPLETED`, or `FAILED`. Case-insensitive. |
| `resultJson` | `String` | ❌ | Stringified result or error JSON from worker. |

### Response — 200 OK

```json
{
  "message": "Status updated successfully",
  "analysisId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "newStatus": "COMPLETED"
}
```

### Response — 400 Bad Request

```json
{ "error": "Invalid status value. Must be: PENDING, PROCESSING, COMPLETED, or FAILED" }
```

---

## Analysis Status Lifecycle

```
[Upload accepted]
      │
      ▼
  PENDING  ─────────────────────► (worker receives SQS message)
      │
      ▼
 PROCESSING ──────────────────────► (worker runs pipeline)
      │
  ┌───┴────┐
  ▼        ▼
COMPLETED  FAILED
```

When status becomes `COMPLETED` or `FAILED`, `completedAt` is set automatically via `updateAnalysisStatus()`.

---

## Result JSON Schemas

### FASTA Result

```json
{
  "analysis_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "patient_code": "SATB2-PT-001",
  "file_type": "FASTA",
  "total_sequences": 2,
  "analyzed_sequences": 2,
  "sequences": [
    {
      "sequence_id": "SATB2_PATIENT_001_WILDTYPE",
      "length": 384,
      "gc_content": 62.76,
      "vocabulary_size": 187,
      "mutation_distance_from_reference": 0.0,
      "divergence_flag": false,
      "severity": "LOW"
    },
    {
      "sequence_id": "SATB2_PATIENT_001_MUTANT",
      "length": 384,
      "gc_content": 62.50,
      "vocabulary_size": 189,
      "mutation_distance_from_reference": 0.032451,
      "divergence_flag": false,
      "severity": "LOW"
    }
  ],
  "summary": {
    "high_risk_sequences": 0,
    "moderate_risk_sequences": 0,
    "low_risk_sequences": 2,
    "recommendation": "Sequences within normal variation range"
  }
}
```

#### Severity Thresholds

| Severity | Cosine Distance Range | Clinical Meaning |
|----------|----------------------|-----------------|
| `LOW` | 0.000 – 0.050 | Within normal polymorphism range |
| `MODERATE` | 0.050 – 0.150 | Potential functional impact — molecular confirmation recommended |
| `HIGH` | > 0.150 | High divergence — immediate clinical review + CRISPRa screening |

`divergence_flag` is `true` when distance > 0.05 (i.e., MODERATE or HIGH).

---

### VCF Result

```json
{
  "analysis_id": "7b3a1c2d-9f8e-4a5b-c6d7-1e2f3a4b5c6d",
  "patient_code": "SATB2-PT-001",
  "file_type": "VCF",
  "total_variants": 3,
  "satb2_variants_count": 3,
  "satb2_variants": [
    {
      "position": 200150000,
      "ref_allele": "C",
      "alt_allele": "T",
      "is_in_satb2_region": true,
      "clinvar_significance": "Pathogenic",
      "requires_crispra_screening": true,
      "recommended_action": "Evaluate gRNA library for CRISPRa promoter upregulation"
    },
    {
      "position": 200200000,
      "ref_allele": "G",
      "alt_allele": "A",
      "is_in_satb2_region": true,
      "clinvar_significance": "Benign",
      "requires_crispra_screening": false,
      "recommended_action": "Monitor as variant of uncertain significance"
    }
  ],
  "crispra_candidates_count": 1,
  "crispra_candidates": [ { "position": 200150000, "..." : "..." } ],
  "clinical_recommendation": "CRITICAL: 1 pathogenic SATB2 variant(s) detected. Immediate CRISPRa gRNA design and therapeutic intervention evaluation recommended. Consider genetic counseling and molecular confirmation."
}
```

#### ClinVar Classification Logic (two-tier, offline-safe)

1. **Tier 1 — Local cache:** checks `KNOWN_PATHOGENIC_POSITIONS` dict in `variant_classifier.py` — instant, works offline
2. **Tier 2 — Live API:** queries `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` with 5s timeout — optional, skipped when network is unavailable
3. **Fallback:** returns `"Benign"` conservatively

---

### Failed Analysis Result

```json
{
  "analysis_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "patient_code": "SATB2-PT-001",
  "error": "Analysis failed: Failed to download file from S3"
}
```

---

## Error Response Format

All errors use a consistent shape:

```json
{
  "error": "Human-readable description",
  "timestamp": "2025-01-15T10:30:00"
}
```

### HTTP Status Codes

| Code | Meaning | Trigger |
|------|---------|---------|
| `200 OK` | Success | GET requests, successful status update |
| `202 Accepted` | Queued for async processing | Successful file upload |
| `400 Bad Request` | Validation failed | Empty file, wrong format, invalid status value |
| `413 Payload Too Large` | File exceeds 500MB | `MaxUploadSizeExceededException` |
| `500 Internal Server Error` | Processing error | Analysis not found, S3/SQS failure, unexpected exception |
