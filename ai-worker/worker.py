import json
import os
import time
import boto3
import logging
import traceback

from services.sequence_parser import parse_fasta, parse_vcf
from services.variant_classifier import classify_variant
from models.sequence_embedder import embed_sequence, compute_mutation_distance
from services.status_updater import update_analysis_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Validate required environment variables
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
S3_BUCKET = os.environ.get("S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

if not SQS_QUEUE_URL or not S3_BUCKET:
    raise EnvironmentError(
        "Missing required environment variables: SQS_QUEUE_URL and S3_BUCKET must be set"
    )

# SATB2 reference sequence (chromosome 2: 200124263-200320351)
# This is a representative fragment of the SATB2 coding sequence
SATB2_REFERENCE = (
    "ATGAGTCAACGGCGGCGGCAGCAGCAGCAGCAGCCGCAGCAGCAGCAGCAGCAGCAGCCGCAG"
    "CAGCAGCCGCAGCAGCAGCAGCAGCAGCAGCCGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAG"
    "CAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGCAG"
    "TCAGCAGCAGCAGCAGCAGCAGCAGCAGCAGGCTGACAACAACAACAATGCTGCGGCCGCCGCC"
    "GCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCCGCC"
    "GCCGCCGCCATGGACGAGCTGGAGAAGATCGAGCGCATCGAGGACCTGGAGCGCGCCGCCGAG"
)

s3 = boto3.client("s3", region_name=AWS_REGION, endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
sqs = boto3.client("sqs", region_name=AWS_REGION, endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))


def process_message(message: dict) -> dict:
    body = json.loads(message["Body"])
    analysis_id = body["analysisId"]
    s3_file_key = body["s3FileKey"]
    patient_code = body["patientCode"]
    bucket_name = body.get("bucketName", S3_BUCKET)

    log.info("Processing analysis %s for patient %s", analysis_id, patient_code)
    
    update_analysis_status(analysis_id, "PROCESSING")

    try:
        file_content = _download_from_s3(s3_file_key, bucket_name)
        result = _run_pipeline(s3_file_key, file_content, patient_code)
        result["analysis_id"] = analysis_id
        
        _upload_result(analysis_id, result, bucket_name)
        
        update_analysis_status(analysis_id, "COMPLETED", json.dumps(result))
        
        log.info("Analysis %s completed successfully", analysis_id)
        return result
    
    except Exception as e:
        error_msg = f"Analysis failed: {str(e)}"
        log.error("%s\n%s", error_msg, traceback.format_exc())
        
        error_result = {
            "analysis_id": analysis_id,
            "error": error_msg,
            "patient_code": patient_code
        }
        
        update_analysis_status(analysis_id, "FAILED", json.dumps(error_result))
        raise


def _download_from_s3(file_key: str, bucket: str) -> bytes:
    try:
        response = s3.get_object(Bucket=bucket, Key=file_key)
        return response["Body"].read()
    except Exception as e:
        log.error("Failed to download from S3: %s/%s", bucket, file_key)
        raise


def _run_pipeline(file_key: str, content: bytes, patient_code: str) -> dict:
    is_vcf = file_key.endswith(".vcf")

    if is_vcf:
        variants = parse_vcf(content)
        
        if not variants:
            return {
                "patient_code": patient_code,
                "file_type": "VCF",
                "total_variants": 0,
                "satb2_variants": [],
                "crispra_candidates": [],
                "warning": "No variants found in file"
            }
        
        classifications = [
            classify_variant(v.chromosome, v.position, v.ref_allele, v.alt_allele).__dict__
            for v in variants
        ]
        
        satb2_variants = [c for c in classifications if c["is_in_satb2_region"]]
        crispra_candidates = [c for c in classifications if c["requires_crispra_screening"]]
        
        return {
            "patient_code": patient_code,
            "file_type": "VCF",
            "total_variants": len(variants),
            "satb2_variants_count": len(satb2_variants),
            "satb2_variants": satb2_variants,
            "crispra_candidates_count": len(crispra_candidates),
            "crispra_candidates": crispra_candidates,
            "clinical_recommendation": _generate_clinical_recommendation(crispra_candidates)
        }

    sequences = parse_fasta(content)
    
    if not sequences:
        return {
            "patient_code": patient_code,
            "file_type": "FASTA",
            "total_sequences": 0,
            "sequences": [],
            "warning": "No sequences found in file"
        }
    
    embeddings = []
    for seq in sequences:
        if len(seq.sequence) < 6:
            log.warning("Sequence %s too short for analysis (length: %d)", seq.sequence_id, len(seq.sequence))
            continue
            
        emb = embed_sequence(seq.sequence_id, seq.sequence)
        distance = compute_mutation_distance(SATB2_REFERENCE, seq.sequence)
        
        embeddings.append({
            "sequence_id": seq.sequence_id,
            "length": seq.length,
            "gc_content": seq.gc_content,
            "vocabulary_size": emb.vocabulary_size,
            "mutation_distance_from_reference": distance,
            "divergence_flag": distance > 0.05,
            "severity": _classify_severity(distance)
        })

    return {
        "patient_code": patient_code,
        "file_type": "FASTA",
        "total_sequences": len(sequences),
        "analyzed_sequences": len(embeddings),
        "sequences": embeddings,
        "summary": _generate_fasta_summary(embeddings)
    }


def _classify_severity(distance: float) -> str:
    if distance > 0.15:
        return "HIGH"
    elif distance > 0.05:
        return "MODERATE"
    return "LOW"


def _generate_clinical_recommendation(candidates: list) -> str:
    if not candidates:
        return "No pathogenic SATB2 variants detected. Standard monitoring recommended."
    
    count = len(candidates)
    return (
        f"CRITICAL: {count} pathogenic SATB2 variant(s) detected. "
        f"Immediate CRISPRa gRNA design and therapeutic intervention evaluation recommended. "
        f"Consider genetic counseling and molecular confirmation."
    )


def _generate_fasta_summary(embeddings: list) -> dict:
    if not embeddings:
        return {"message": "No sequences analyzed"}
    
    high_risk = sum(1 for e in embeddings if e["severity"] == "HIGH")
    moderate_risk = sum(1 for e in embeddings if e["severity"] == "MODERATE")
    low_risk = sum(1 for e in embeddings if e["severity"] == "LOW")
    
    return {
        "high_risk_sequences": high_risk,
        "moderate_risk_sequences": moderate_risk,
        "low_risk_sequences": low_risk,
        "recommendation": (
            f"High priority clinical review required" if high_risk > 0 
            else f"Moderate monitoring recommended" if moderate_risk > 0
            else "Sequences within normal variation range"
        )
    }


def _upload_result(analysis_id: str, result: dict, bucket: str):
    result_key = f"results/{analysis_id}.json"
    s3.put_object(
        Bucket=bucket,
        Key=result_key,
        Body=json.dumps(result, indent=2),
        ContentType="application/json"
    )
    log.info("Results uploaded to s3://%s/%s", bucket, result_key)


def poll():
    log.info("Worker started. Polling SQS queue: %s", SQS_QUEUE_URL)
    
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                MessageAttributeNames=['All']
            )
            
            messages = response.get("Messages", [])
            
            if messages:
                consecutive_failures = 0
                
            for message in messages:
                try:
                    process_message(message)
                    sqs.delete_message(
                        QueueUrl=SQS_QUEUE_URL,
                        ReceiptHandle=message["ReceiptHandle"]
                    )
                except Exception as e:
                    log.error("Failed to process message: %s", str(e))
                    consecutive_failures += 1

            if not messages:
                time.sleep(2)
                
            if consecutive_failures >= max_consecutive_failures:
                log.critical("Too many consecutive failures (%d). Restarting worker...", consecutive_failures)
                time.sleep(60)
                consecutive_failures = 0
                
        except KeyboardInterrupt:
            log.info("Worker stopped by user")
            break
        except Exception as e:
            log.error("Unexpected error in polling loop: %s", str(e))
            time.sleep(10)


if __name__ == "__main__":
    poll()
