#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#define FACTORY_FRAME_MAGIC 0xFAC0

#ifdef TEST
#define FACTORY_FRAME_MAX_SIZE 64 // Smaller size for testing purposes
#else
#define FACTORY_FRAME_MAX_SIZE 512 // Maximum size of a single frame (including header)
#endif

typedef enum {
    FACTORY_FRAME_TYPE_SINGLE       = 0x01,
    FACTORY_FRAME_TYPE_FIRST        = 0x02,
    FACTORY_FRAME_TYPE_CONSECUTIVE  = 0x03,
    FACTORY_FRAME_TYPE_ACK          = 0xF1,
    FACTORY_FRAME_TYPE_NACK         = 0xF2,
} factory_frame_type_t;

typedef enum {
    FACTORY_FRAME_ERROR_NONE = 0,
    FACTORY_FRAME_ERROR_INVALID_ARGUMENT = -1,
    FACTORY_FRAME_ERROR_INVALID_MAGIC = -2,
    FACTORY_FRAME_ERROR_CRC_MISMATCH = -3,
    FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE = -4,
    FACTORY_FRAME_ERROR_BUFFER_OVERFLOW = -5,
} factory_frame_error_code_t;

typedef struct __attribute__((packed)) {
    uint16_t magic;     // 0xFAC0
    uint8_t type;       // Frame type
    uint16_t size;      // Size of the frame data (excluding this common header, but including type-specific fields like sequence, total_size)
    uint16_t crc16;     // CRC16 checksum of the data (excluding this common header)
} factory_frame_t;

#define FACTORY_FRAME_HEADER_SIZE   sizeof(factory_frame_t)
#define FACTORY_FRAME_MAX_DATA_SIZE (FACTORY_FRAME_MAX_SIZE - FACTORY_FRAME_HEADER_SIZE)

typedef struct {
    factory_frame_t super;  // Common frame header
    uint8_t data[];         // Data payload
} factory_base_frame_t;

#define FACTORY_BASE_FRAME_INIT                                    \
    {                                                              \
        .super = {                                                 \
            .magic = FACTORY_FRAME_MAGIC,                          \
            .type = 0,                                             \
            .size = 0,                                             \
            .crc16 = 0,                                            \
        },                                                         \
        .data = { [0 ... (FACTORY_FRAME_MAX_DATA_SIZE) - 1] = 0 }  \
    }

int factory_base_frame_reset(factory_base_frame_t *base_frame);

typedef struct __attribute__((packed)) {
    factory_frame_t super;  // Common frame header
    uint32_t total_size;    // Total size of the data being sent (for multi-frame packets)
    uint8_t sequence;       // Frame sequence number
    uint8_t data[];         // Data payload
} factory_first_frame_t;

typedef struct __attribute__((packed)) {
    factory_frame_t super;  // Common frame header
    uint8_t sequence;       // Frame sequence number
    uint8_t data[];         // Data payload
} factory_consecutive_frame_t;

typedef struct __attribute__((packed)) {
    factory_frame_t super;  // Common frame header
    uint8_t data[];         // Data payload
} factory_single_frame_t;

typedef struct __attribute__((packed)) {
    factory_frame_t super;  // Common frame header
    uint8_t sequence;       // Expected sequence number (Set to 0xFF for the single frame)
} factory_ack_frame_t;

typedef struct __attribute__((packed)) {
    factory_frame_t super;  // Common frame header
    uint8_t sequence;       // Erroneous sequence number (Set to 0xFF for the single frame)
    uint8_t reason;         // Reason code for the negative acknowledgment
} factory_nack_frame_t;

typedef struct {
    bool has_finished;            // Indicates if the current packet has been fully assembled
    bool has_error;               // Indicates if an error occurred during assembly
    uint8_t sequence;             // Expected sequence number for the next frame
    size_t total_size;            // Total expected size for multi-frame packets
    size_t packet_size;           // Current size of data assembled so far
    const size_t packet_capacity;       // Maximum capacity of the packet buffer
    uint8_t packet[];             // Buffer to hold the incoming data being processed. The actual size is determined by packet_capacity.
} factory_frame_assembler_context_t;

/* Initialization macro for factory_frame_assembler_context_t (Only for static assignment) */
#define FACTORY_FRAME_ASSEMBLER_INIT(capacity)      \
    {                                               \
        .has_finished = false,                      \
        .has_error = false,                         \
        .sequence = 0,                              \
        .total_size = 0,                            \
        .packet_size = 0,                           \
        .packet_capacity = (capacity),              \
        .packet = { [0 ... (capacity) - 1] = 0 }    \
    }

typedef struct {
    bool has_finished;              // Indicates if the current packet has been fully fragmented
    bool has_error;                 // Indicates if an error occurred during fragmentation
    bool need_fragmentation;        // Indicates if the packet needs to be fragmented (true if packet_size > FACTORY_FRAME_MAX_DATA_SIZE)
    uint8_t sequence;               // Current sequence number for the next frame to be sent
    size_t index;                   // Current index in the packet being processed
    size_t packet_size;             // Total size of the packet being processed
    const size_t packet_capacity;   // Maximum capacity of the packet buffer
    uint8_t packet[];               // Buffer to hold the outgoing data being processed. The actual size is determined by packet_capacity.
} factory_frame_fragmenter_context_t; 

#define FACTORY_FRAME_FRAGMENTER_INIT(size)                           \
    {                                                                 \
        .has_finished = false,                                        \
        .has_error = false,                                           \
        .need_fragmentation = ((size) > FACTORY_FRAME_MAX_DATA_SIZE), \
        .sequence = 0,                                                \
        .index = 0,                                                   \
        .packet_size = (size),                                        \
        .packet_capacity = (size),                                    \
        .packet = { [0 ... (size) - 1] = 0 }                          \
    }

/*
 * Initializes the frame assembler context. Must be called before processing any frames. 
 */
factory_frame_error_code_t factory_frame_assembler_init(factory_frame_assembler_context_t *ctx);

/*
 * Processes an incoming frame. This function should be called for each received frame. It will handle assembling multi-frame packets and validating single frames.
 * Returns 0 on success, or a negative error code on failure (e.g., CRC mismatch, unexpected sequence number, etc.).
 */
factory_frame_error_code_t factory_frame_assembler_process(factory_frame_assembler_context_t *ctx, factory_frame_t *frame);

/*
 * Initializes the frame fragmenter context. Must be called before sending any frames.
 */
factory_frame_error_code_t factory_frame_fragmenter_init(factory_frame_fragmenter_context_t *ctx, size_t size);

/*
 * Processes an outgoing frame. This function should be called for each frame to be sent. It will handle fragmenting multi-frame packets and preparing single frames.
 * Returns 0 on success, or a negative error code on failure (e.g., buffer overflow, unexpected sequence number, etc.).
 */
factory_frame_error_code_t factory_frame_fragmenter_process(factory_frame_fragmenter_context_t *ctx, factory_frame_t *frame);