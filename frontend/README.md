# SATB2 Frontend

This is a polished single-page interface for the SATB2 platform. It provides:
- analysis submission for FASTA and VCF files
- a detailed analysis view
- an executive dashboard
- direct access without a login screen

## Run locally

```bash
cd frontend
python -m http.server 3000
```

Then open:

- http://localhost:3000

The UI communicates with the backend at:

- http://localhost:8080/api/genomic

## Run with Docker

```bash
docker compose up -d --build frontend
```

Then open:

- http://localhost:3000
