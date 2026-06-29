package com.satb2.exception;

public class GenomicProcessingException extends RuntimeException {
    public GenomicProcessingException(String message) {
        super(message);
    }

    public GenomicProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
