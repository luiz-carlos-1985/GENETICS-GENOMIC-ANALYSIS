#!/bin/bash
set -e

echo "================================================"
echo "SATB2 Genomic Analysis - Local Integration Test"
echo "================================================"

BACKEND_URL="http://localhost:8080"
TEST_DATA_DIR="test-data"
PATIENT_CODE="SATB2-TEST-001"

echo ""
echo "1. Checking backend health..."
response=$(curl -s -o /dev/null -w "%{http_code}" ${BACKEND_URL}/api/genomic/health)
if [ "$response" -eq 200 ]; then
    echo "✓ Backend is UP"
else
    echo "✗ Backend is DOWN (HTTP $response)"
    exit 1
fi

echo ""
echo "2. Uploading FASTA file..."
fasta_response=$(curl -s -X POST ${BACKEND_URL}/api/genomic/upload \
  -F "file=@${TEST_DATA_DIR}/sample_satb2.fasta" \
  -F "patientCode=${PATIENT_CODE}")

echo "$fasta_response" | jq .

fasta_analysis_id=$(echo "$fasta_response" | jq -r '.analysisId')

echo ""
echo "3. Uploading VCF file..."
vcf_response=$(curl -s -X POST ${BACKEND_URL}/api/genomic/upload \
  -F "file=@${TEST_DATA_DIR}/sample_satb2.vcf" \
  -F "patientCode=${PATIENT_CODE}")

echo "$vcf_response" | jq .

vcf_analysis_id=$(echo "$vcf_response" | jq -r '.analysisId')

echo ""
echo "4. Waiting 30 seconds for worker processing..."
sleep 30

echo ""
echo "5. Checking FASTA analysis status..."
curl -s ${BACKEND_URL}/api/genomic/analysis/${fasta_analysis_id} | jq .

echo ""
echo "6. Checking VCF analysis status..."
curl -s ${BACKEND_URL}/api/genomic/analysis/${vcf_analysis_id} | jq .

echo ""
echo "7. Listing all analyses for patient ${PATIENT_CODE}..."
curl -s ${BACKEND_URL}/api/genomic/analysis/patient/${PATIENT_CODE} | jq .

echo ""
echo "================================================"
echo "Test completed successfully!"
echo "================================================"
