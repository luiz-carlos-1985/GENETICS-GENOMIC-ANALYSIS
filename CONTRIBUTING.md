# Contributing Guide — SATB2 Genomic Analysis Platform

This guide explains how to contribute to the platform as a software engineer, bioinformatician, or research collaborator.

---

## Table of Contents

- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Code Standards](#code-standards)
- [Adding a New Analysis Feature](#adding-a-new-analysis-feature)
- [Testing Guidelines](#testing-guidelines)
- [Roadmap and Open Items](#roadmap-and-open-items)
- [Research Collaboration](#research-collaboration)

---

## Ways to Contribute

### For Software Engineers

| Area | Skills Needed | Impact |
|------|--------------|--------|
| Phase 3: SageMaker gRNA design | Python, PyTorch, AWS SageMaker | High — enables direct therapeutic tool |
| Phase 4: Angular frontend | TypeScript, Angular 17+ | High — makes platform accessible to biologists |
| ClinVar variant-level lookup | Python, REST APIs | Medium — improves classification accuracy |
| NCBI API rate limiting | Python | Medium — prevents ClinVar query failures |
| CI/CD pipeline | GitHub Actions, Docker | Medium — enables automated testing |
| Performance optimization | Java, PostgreSQL | Low-Medium — scaling for large cohorts |

### For Bioinformaticians

| Area | Skills Needed | Impact |
|------|--------------|--------|
| Expand SATB2 reference sequence | Biopython, NCBI APIs | High — improves mutation distance accuracy |
| Validate ClinVar classification logic | ACMG guidelines, Python | High — clinical accuracy |
| Add gnomAD population frequency filter | Python, REST APIs | Medium — reduces false positives |
| Protein structure impact prediction | AlphaFold API, Python | High — adds structural context |

### For Researchers / Clinicians

| Area | Contribution | Impact |
|------|-------------|--------|
| Test with real patient data | Upload anonymized FASTA/VCF files | High — validates the pipeline |
| Review clinical recommendations | Assess accuracy of generated text | High — improves clinical output |
| Provide SATB2 variant annotations | Share curated variant classifications | High — improves training data |
| Connect with research networks | Introduce platform to SATB2 Portal, SATB2 Gene Foundation | Very High |

---

## Development Setup

See [DEPLOYMENT.md](DEPLOYMENT.md) for full setup instructions. Quick start:

```bash
docker-compose up --build
```

For backend-only development:
```bash
cd backend
export DB_URL=jdbc:postgresql://localhost:5432/satb2db
export DB_USER=satb2user
export DB_PASS=satb2pass
export S3_BUCKET=satb2-research-data
export SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_ENDPOINT_OVERRIDE=http://localhost:4566
mvn spring-boot:run
```

For worker-only development:
```bash
cd ai-worker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
export S3_BUCKET=satb2-research-data
export AWS_ENDPOINT_URL=http://localhost:4566
export BACKEND_URL=http://localhost:8080
python worker.py
```

---

## Code Standards

### Java (Backend)

- Java 21 features are encouraged (records, pattern matching, text blocks)
- Lombok annotations (`@Data`, `@RequiredArgsConstructor`, `@Slf4j`) are standard
- All service methods that modify data must be annotated with `@Transactional`
- Custom exceptions should extend `GenomicProcessingException`
- All new endpoints must follow existing patterns in `GenomicController`

**Naming conventions:**
- Controllers: `{Domain}Controller.java`
- Services: `{Domain}Service.java`
- DTOs: suffix with `Request` or `Response`
- Repositories: `{Entity}Repository.java`

### Python (Worker)

- Type hints are required on all function signatures
- Dataclasses preferred over plain dicts for structured data
- All public functions should have a brief docstring
- Logging via the `logging` module (not `print`)
- Environment variables read once at module level, validated at startup

**File structure:**
- `services/` — external integrations (parsers, APIs, HTTP clients)
- `models/` — computational/mathematical logic (embeddings, scoring)
- `worker.py` — orchestration only, no business logic

### Terraform

- All resources must use the `${var.project_name}-` prefix for names
- New resources must have corresponding outputs in `outputs.tf`
- Sensitive variables must be marked `sensitive = true`

---

## Adding a New Analysis Feature

### Backend (Java)

To add a new analysis capability (e.g., a new file format or annotation):

1. Add file format validation in `GenomicController.uploadSequenceFile()` if needed
2. Add any new fields to `GenomicAnalysis` entity and update `AnalysisResponse` DTO
3. If new metadata needs to be persisted, add columns to the JPA entity
4. Add new SQS message fields in `GenomicIngestionService.dispatchToQueue()` if the worker needs them

### Worker (Python)

To add a new analysis step:

1. Create a new module in `services/` or `models/`
2. Call it from `_run_pipeline()` in `worker.py`
3. Add the results to the returned dict
4. Ensure error handling: wrap in try/except and log before re-raising

**Example: Adding gnomAD frequency lookup**

```python
# services/gnomad_lookup.py
import requests

GNOMAD_API = "https://gnomad.broadinstitute.org/api"

def get_allele_frequency(chromosome: str, position: int, ref: str, alt: str) -> float:
    """Returns population allele frequency from gnomAD v4."""
    query = """
    query Variant($variantId: String!) {
      variant(variantId: $variantId, dataset: gnomad_r4) {
        genome { af }
      }
    }
    """
    variant_id = f"{chromosome}-{position}-{ref}-{alt}"
    response = requests.post(GNOMAD_API, json={"query": query, "variables": {"variantId": variant_id}}, timeout=10)
    data = response.json()
    return data.get("data", {}).get("variant", {}).get("genome", {}).get("af", 0.0)
```

Then in `worker.py`, inside `_run_pipeline()` for the VCF path:

```python
from services.gnomad_lookup import get_allele_frequency

for v in variants:
    freq = get_allele_frequency(v.chromosome, v.position, v.ref_allele, v.alt_allele)
    # Add freq to classification output
```

---

## Testing Guidelines

### Running Existing Tests

```bash
# Backend unit tests
cd backend
mvn test

# Worker tests (once test files are added)
cd ai-worker
python -m pytest tests/
```

### Integration Test

```bash
chmod +x scripts/test-integration.sh
./scripts/test-integration.sh
```

### Manual Testing Checklist

Before submitting any change, verify manually:

- [ ] `GET /api/genomic/health` returns `200 OK`
- [ ] `POST /api/genomic/upload` with `sample_satb2.fasta` returns `202` with `analysisId`
- [ ] `POST /api/genomic/upload` with `sample_satb2.vcf` returns `202` with `analysisId`
- [ ] Worker processes both files (check logs: `docker logs satb2-worker -f`)
- [ ] `GET /api/genomic/analysis/{id}` returns `status: COMPLETED` after worker finishes
- [ ] `resultJson` in the response is valid JSON with expected fields
- [ ] `POST /api/genomic/upload` with an invalid file type returns `400`
- [ ] `GET /api/genomic/analysis/patient/{code}` returns an array

### Writing Tests for New Features

**Backend test example (JUnit 5):**

```java
@SpringBootTest
@AutoConfigureMockMvc
class GenomicControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void healthEndpointShouldReturn200() throws Exception {
        mockMvc.perform(get("/api/genomic/health"))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.status").value("UP"));
    }
}
```

**Worker test example (pytest):**

```python
from services.sequence_parser import parse_fasta

def test_parse_fasta_returns_sequences():
    content = b">SEQ1\nATGCATGC\n>SEQ2\nGCATGCAT\n"
    result = parse_fasta(content)
    assert len(result) == 2
    assert result[0].sequence_id == "SEQ1"
    assert result[0].sequence == "ATGCATGC"
    assert result[0].length == 8

def test_parse_fasta_empty_returns_empty_list():
    result = parse_fasta(b"")
    assert result == []
```

---

## Roadmap and Open Items

### Phase 3: SageMaker gRNA Design

**Goal:** Given a set of CRISPRa candidates from VCF analysis, automatically design and rank gRNA sequences targeting the SATB2 promoter.

**Technical approach:**
1. Extract 200bp windows around each pathogenic variant position in the SATB2 promoter
2. Enumerate all possible 20-mer sequences with adjacent NGG PAM sites
3. Score each candidate using:
   - Rule-based: GC content (40–70% preferred), absence of TTTT runs
   - ML-based: DNABERT-2 fine-tuned on CRISPRa activity data
4. Filter by off-target risk using Cas-OFFinder alignment scores
5. Return top-3 ranked gRNAs per patient with predicted efficiency and safety scores

**Files to create:**
- `ai-worker/services/grna_designer.py`
- `ai-worker/services/offtarget_scorer.py`
- `infra/sagemaker_endpoint.tf`

### Phase 4: Angular Frontend

**Goal:** A web portal where researchers can upload genomic files, view results visually, and export reports.

**Key screens:**
- Dashboard with analysis history table
- File upload form with drag-and-drop
- Analysis detail view with:
  - Mutation distance chart (bar chart per sequence)
  - Variant table with ClinVar significance color coding
  - CRISPRa candidates panel with gRNA library (Phase 3)
- PDF/CSV export for clinical reports

**Technology:** Angular 17 + PrimeNG or Angular Material

---

## Research Collaboration

### Target Institutions

If you are interested in connecting this platform with active SATB2 research:

| Institution | Contact | Focus |
|-------------|---------|-------|
| SATB2 Gene Foundation | info@satb2gene.org | Patient registry, research funding |
| Chan Zuckerberg Initiative | openscience@chanzuckerberg.com | Open science software funding |
| SATB2 Connect (Australia) | Via satb2connect.org | Australasian patient community + research |

### Cold Outreach Template

When contacting research labs directly (find the PI via PubMed search for "SATB2 CRISPRa" or "SATB2 syndrome AI"):

```
Subject: Collaboration Inquiry: AI & Cloud Engineering Support for SATB2 Research

Dear Dr. [Name],

I am a Software Engineer specializing in AI and cloud architecture on AWS. I have built 
an open-source platform for automated genomic variant analysis specific to SATB2-Associated 
Syndrome — including ClinVar cross-referencing, k-mer mutation distance scoring, and an 
asynchronous processing pipeline designed to handle clinical-scale FASTA and VCF files.

My commitment to this field is deeply personal: my brother has been diagnosed with 
SATB2-Associated Syndrome (Glass Syndrome), which has driven me to apply my engineering 
background directly to accelerating therapeutic research.

I noticed your recent work on [specific paper/project] and believe the computational 
infrastructure challenges you face — particularly [mention a specific bottleneck like 
"processing single-cell RNA-seq data at scale" or "building CRISPRa gRNA design pipelines"] 
— align directly with what this platform addresses.

I would welcome the opportunity to discuss how my expertise in cloud-scalable bioinformatics 
architecture could support your lab's computational needs.

Best regards,
[Your Name]
Software & AI Engineer
[LinkedIn] | [GitHub with this project]
```

### Showcasing the Platform

Before reaching out to research institutions, prepare:

1. **A live demo** — run `docker-compose up` and record a short screen recording of:
   - Uploading `sample_satb2.fasta`
   - Watching the worker process it in real time
   - Querying the result JSON showing mutation distances

2. **A GitHub repository** — make the code public and ensure the README renders correctly

3. **A one-page technical summary** — derived from [ARCHITECTURE.md](ARCHITECTURE.md), explaining the pipeline for a biologist audience

4. **A validation run** — attach the output of `./scripts/test-integration.sh` showing all checks passing
