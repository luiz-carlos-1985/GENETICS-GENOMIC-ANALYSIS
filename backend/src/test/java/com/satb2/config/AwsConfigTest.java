package com.satb2.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AwsConfigTest {

    @Test
    void objectMapperShouldSerializeLocalDateTime() {
        AwsConfig config = new AwsConfig();
        ObjectMapper mapper = config.objectMapper();

        String json = assertDoesNotThrow(() -> mapper.writeValueAsString(LocalDateTime.of(2024, 1, 2, 3, 4, 5)));

        assertTrue(json.contains("2024-01-02T03:04:05"));
    }
}
