package com.satb2.controller;

import com.satb2.dto.AnalysisResponse;
import com.satb2.model.GenomicAnalysis;
import com.satb2.service.GenomicIngestionService;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/genomic")
@RequiredArgsConstructor
public class GenomicController {

    private final GenomicIngestionService ingestionService;
    private static final long MAX_FILE_SIZE = 500 * 1024 * 1024;

    @PostMapping("/upload")
    public ResponseEntity<?> uploadSequenceFile(
            @RequestParam("file") MultipartFile file,
            @RequestParam("patientCode") @NotBlank String patientCode) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "File cannot be empty"));
        }

        if (file.getSize() > MAX_FILE_SIZE) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "File size exceeds 500MB limit",
                    "size", file.getSize(),
                    "maxSize", MAX_FILE_SIZE
            ));
        }

        String filename = file.getOriginalFilename();
        if (filename == null || (!filename.endsWith(".fasta") && !filename.endsWith(".fa") && !filename.endsWith(".vcf"))) {
            return ResponseEntity.badRequest().body(Map.of("error", "Only .fasta, .fa and .vcf files are accepted"));
        }

        GenomicAnalysis analysis = ingestionService.ingestSequenceFile(file, patientCode);
        return ResponseEntity.accepted().body(Map.of(
                "message", "File received and queued for analysis",
                "analysisId", analysis.getId(),
                "patientCode", analysis.getPatientCode(),
                "fileName", analysis.getOriginalFileName(),
                "fileSize", analysis.getFileSize(),
                "status", analysis.getStatus().name()
        ));
    }

    @GetMapping("/analysis/{id}")
    public ResponseEntity<AnalysisResponse> getAnalysis(@PathVariable String id) {
        GenomicAnalysis analysis = ingestionService.getAnalysisById(id);
        return ResponseEntity.ok(AnalysisResponse.from(analysis));
    }

    @GetMapping("/analysis/patient/{patientCode}")
    public ResponseEntity<List<AnalysisResponse>> getAnalysesByPatient(@PathVariable String patientCode) {
        List<AnalysisResponse> analyses = ingestionService.getAnalysesByPatient(patientCode)
                .stream()
                .map(AnalysisResponse::from)
                .toList();
        return ResponseEntity.ok(analyses);
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of(
                "status", "UP", 
                "service", "SATB2 Genomic Analysis API",
                "version", "2.0.0"
        ));
    }
}
