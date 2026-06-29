package com.satb2.repository;

import com.satb2.model.GenomicAnalysis;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface GenomicAnalysisRepository extends JpaRepository<GenomicAnalysis, String> {
    List<GenomicAnalysis> findByPatientCodeOrderByCreatedAtDesc(String patientCode);
    List<GenomicAnalysis> findByStatusOrderByCreatedAtDesc(GenomicAnalysis.AnalysisStatus status);
    Optional<GenomicAnalysis> findByS3FileKey(String s3FileKey);
}
