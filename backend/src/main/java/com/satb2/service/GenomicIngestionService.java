package com.satb2.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.satb2.exception.GenomicProcessingException;
import com.satb2.model.GenomicAnalysis;
import com.satb2.repository.GenomicAnalysisRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import software.amazon.awssdk.services.sqs.model.SqsException;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class GenomicIngestionService {

    private final S3Client s3Client;
    private final SqsClient sqsClient;
    private final ObjectMapper objectMapper;
    private final GenomicAnalysisRepository repository;

    @Value("${aws.s3.bucket-name}")
    private String bucketName;

    @Value("${aws.sqs.queue-url}")
    private String sqsQueueUrl;

    @Transactional
    public GenomicAnalysis ingestSequenceFile(MultipartFile file, String patientCode) {
        String fileKey = "raw-sequences/" + UUID.randomUUID() + "-" + file.getOriginalFilename();

        GenomicAnalysis analysis = buildAndPersistAnalysisRecord(file, patientCode, fileKey);

        try {
            uploadToS3(file, fileKey);
            dispatchToQueue(analysis);
            log.info("Ingestion complete for patient {} — ID: {} — fileKey: {}", 
                    patientCode, analysis.getId(), fileKey);
            return analysis;
        } catch (Exception e) {
            rollbackS3Upload(fileKey);
            throw new GenomicProcessingException("Failed to ingest genomic file", e);
        }
    }

    public List<GenomicAnalysis> getAnalysesByPatient(String patientCode) {
        return repository.findByPatientCodeOrderByCreatedAtDesc(patientCode);
    }

    public GenomicAnalysis getAnalysisById(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new GenomicProcessingException("Analysis not found: " + id));
    }

    @Transactional
    public void updateAnalysisStatus(String analysisId, GenomicAnalysis.AnalysisStatus status, String resultJson) {
        GenomicAnalysis analysis = getAnalysisById(analysisId);
        analysis.setStatus(status);
        analysis.setResultJson(resultJson);
        if (status == GenomicAnalysis.AnalysisStatus.COMPLETED || status == GenomicAnalysis.AnalysisStatus.FAILED) {
            analysis.setCompletedAt(LocalDateTime.now());
        }
        repository.save(analysis);
        log.info("Analysis {} status updated to {}", analysisId, status);
    }

    private void uploadToS3(MultipartFile file, String fileKey) throws IOException {
        try {
            PutObjectRequest request = PutObjectRequest.builder()
                    .bucket(bucketName)
                    .key(fileKey)
                    .contentType(file.getContentType())
                    .build();

            s3Client.putObject(request, RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
        } catch (S3Exception e) {
            log.error("S3 upload failed for key: {}", fileKey, e);
            throw new GenomicProcessingException("Failed to upload file to S3", e);
        }
    }

    private GenomicAnalysis buildAndPersistAnalysisRecord(MultipartFile file, String patientCode, String fileKey) {
        GenomicAnalysis analysis = new GenomicAnalysis();
        analysis.setPatientCode(patientCode);
        analysis.setS3FileKey(fileKey);
        analysis.setOriginalFileName(file.getOriginalFilename());
        analysis.setFileSize(file.getSize());
        return repository.save(analysis);
    }

    private void dispatchToQueue(GenomicAnalysis analysis) {
        try {
            Map<String, String> message = Map.of(
                    "analysisId", analysis.getId(),
                    "s3FileKey", analysis.getS3FileKey(),
                    "patientCode", analysis.getPatientCode(),
                    "bucketName", bucketName
            );

            sqsClient.sendMessage(SendMessageRequest.builder()
                    .queueUrl(sqsQueueUrl)
                    .messageBody(objectMapper.writeValueAsString(message))
                    .build());
        } catch (JsonProcessingException e) {
            throw new GenomicProcessingException("Failed to serialize SQS message", e);
        } catch (SqsException e) {
            throw new GenomicProcessingException("Failed to send message to SQS", e);
        }
    }

    private void rollbackS3Upload(String fileKey) {
        try {
            s3Client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucketName)
                    .key(fileKey)
                    .build());
            log.info("Rolled back S3 upload for key: {}", fileKey);
        } catch (Exception e) {
            log.error("Failed to rollback S3 upload for key: {}", fileKey, e);
        }
    }
}
