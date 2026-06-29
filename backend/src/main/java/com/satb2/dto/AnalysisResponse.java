package com.satb2.dto;

import com.satb2.model.GenomicAnalysis;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
public class AnalysisResponse {
    private String analysisId;
    private String patientCode;
    private String fileName;
    private String status;
    private String s3FileKey;
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
    private String resultJson;

    public static AnalysisResponse from(GenomicAnalysis analysis) {
        return new AnalysisResponse(
                analysis.getId(),
                analysis.getPatientCode(),
                analysis.getOriginalFileName(),
                analysis.getStatus().name(),
                analysis.getS3FileKey(),
                analysis.getCreatedAt(),
                analysis.getCompletedAt(),
                analysis.getResultJson()
        );
    }
}
