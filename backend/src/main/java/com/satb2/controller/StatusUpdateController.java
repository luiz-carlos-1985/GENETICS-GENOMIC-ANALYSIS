package com.satb2.controller;

import com.satb2.model.GenomicAnalysis;
import com.satb2.service.GenomicIngestionService;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/genomic")
@RequiredArgsConstructor
public class StatusUpdateController {

    private final GenomicIngestionService ingestionService;

    @PutMapping("/analysis/{id}/status")
    public ResponseEntity<Map<String, String>> updateAnalysisStatus(
            @PathVariable String id,
            @RequestBody StatusUpdateRequest request) {

        log.info("Received status update for analysis {}: {}", id, request.getStatus());

        GenomicAnalysis.AnalysisStatus status;
        try {
            status = GenomicAnalysis.AnalysisStatus.valueOf(request.getStatus().toUpperCase());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "Invalid status value. Must be: PENDING, PROCESSING, COMPLETED, or FAILED"
            ));
        }

        ingestionService.updateAnalysisStatus(id, status, request.getResultJson());

        return ResponseEntity.ok(Map.of(
                "message", "Status updated successfully",
                "analysisId", id,
                "newStatus", status.name()
        ));
    }

    @Data
    public static class StatusUpdateRequest {
        private String status;
        private String resultJson;
    }
}
