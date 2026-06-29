package com.satb2.model;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@Entity
@Table(name = "genomic_analyses")
public class GenomicAnalysis {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @Column(nullable = false)
    private String patientCode;

    @Column(nullable = false)
    private String s3FileKey;

    @Column(nullable = false)
    private String originalFileName;

    @Column(nullable = false)
    private Long fileSize;

    @Enumerated(EnumType.STRING)
    private AnalysisStatus status;

    @Column(columnDefinition = "TEXT")
    private String resultJson;

    private LocalDateTime createdAt;
    private LocalDateTime completedAt;

    @PrePersist
    void prePersist() {
        this.createdAt = LocalDateTime.now();
        this.status = AnalysisStatus.PENDING;
    }

    public enum AnalysisStatus {
        PENDING, PROCESSING, COMPLETED, FAILED
    }
}
