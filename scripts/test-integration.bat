@echo off
setlocal enabledelayedexpansion

set BACKEND_URL=http://localhost:8080
set PATIENT_CODE=SATB2-TEST-001

echo ================================================
echo  SATB2 - Integration Test (Windows)
echo ================================================
echo.

REM ── 1. Health check ───────────────────────────────
echo [1/5] Checking backend health...
curl -s -o nul -w "HTTP %%{http_code}" %BACKEND_URL%/api/genomic/health
echo.

REM ── 2. Upload FASTA ───────────────────────────────
echo.
echo [2/5] Uploading FASTA file...
curl -s -X POST %BACKEND_URL%/api/genomic/upload ^
  -F "file=@test-data/sample_satb2.fasta" ^
  -F "patientCode=%PATIENT_CODE%"
echo.

REM ── 3. Upload VCF ─────────────────────────────────
echo.
echo [3/5] Uploading VCF file...
curl -s -X POST %BACKEND_URL%/api/genomic/upload ^
  -F "file=@test-data/sample_satb2.vcf" ^
  -F "patientCode=%PATIENT_CODE%"
echo.

REM ── 4. Wait for worker ────────────────────────────
echo.
echo [4/5] Waiting 30 seconds for worker processing...
timeout /t 30 /nobreak >nul

REM ── 5. Query patient analyses ─────────────────────
echo.
echo [5/5] Querying all analyses for patient %PATIENT_CODE%...
curl -s %BACKEND_URL%/api/genomic/analysis/patient/%PATIENT_CODE%
echo.

echo.
echo ================================================
echo  Test completed!
echo  Check the output above for analysis results.
echo ================================================
pause
