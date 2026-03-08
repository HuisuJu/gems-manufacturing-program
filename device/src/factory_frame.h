/**
 * @file factory_frame.h
 * @brief Factory provisioning frame layer protocol
 * 
 * Provides framing, fragmentation, and reassembly for factory provisioning packets.
 * Supports CRC validation and automatic packet fragmentation for large payloads.
 */

#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/** Maximum size of a single frame (including header) */
#ifdef TEST
#define FACTORY_FRAME_MAX_SIZE 64  // Smaller size for testing purposes
#else
#define FACTORY_FRAME_MAX_SIZE 512 // Production size
#endif

/** Frame magic number for validation */
#define FACTORY_FRAME_MAGIC 0xFAC0

/** Error codes for frame operations */
typedef enum {
    FACTORY_FRAME_ERROR_NONE = 0,                  /**< Success */
    FACTORY_FRAME_ERROR_INVALID_ARGUMENT = -1,     /**< Invalid function argument */
    FACTORY_FRAME_ERROR_INVALID_MAGIC = -2,        /**< Frame magic number mismatch */
    FACTORY_FRAME_ERROR_CRC_MISMATCH = -3,         /**< CRC validation failed */
    FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE = -4,  /**< Unexpected sequence number */
    FACTORY_FRAME_ERROR_BUFFER_OVERFLOW = -5,      /**< Buffer capacity exceeded */
} factory_frame_error_code_t;

/** Frame type identifiers */
typedef enum {
    FACTORY_FRAME_TYPE_SINGLE       = 0x01, /**< Single-frame packet */
    FACTORY_FRAME_TYPE_FIRST        = 0x02, /**< First frame of multi-frame packet */
    FACTORY_FRAME_TYPE_CONSECUTIVE  = 0x03, /**< Consecutive frame of multi-frame packet */
    FACTORY_FRAME_TYPE_ACK          = 0xF1, /**< Acknowledgment frame */
    FACTORY_FRAME_TYPE_NACK         = 0xF2, /**< Negative acknowledgment frame */
} factory_frame_type_t;

/**
 * @brief Common frame header (7 bytes)
 * 
 * Present at the start of every frame type.
 */
typedef struct __attribute__((packed)) {
    uint16_t magic;  /**< Magic number (0xFAC0) for frame validation */
    uint8_t type;    /**< Frame type (factory_frame_type_t) */
    uint16_t size;   /**< Size of frame data excluding this header, including type-specific fields */
    uint16_t crc16;  /**< CRC16-CCITT checksum of data (excluding this header) */
} factory_frame_t;

#define FACTORY_FRAME_HEADER_SIZE   sizeof(factory_frame_t)
#define FACTORY_FRAME_MAX_DATA_SIZE (FACTORY_FRAME_MAX_SIZE - FACTORY_FRAME_HEADER_SIZE)

/**
 * @brief Encodes 16-bit unsigned integer to big-endian bytes
 */
static inline void encode_u16_be(uint8_t *dst, uint16_t src)
{
    dst[0] = (uint8_t)((src >> 8) & 0xFFu);
    dst[1] = (uint8_t)(src & 0xFFu);
}

/**
 * @brief Encodes 32-bit unsigned integer to big-endian bytes
 */
static inline void encode_u32_be(uint8_t *dst, uint32_t src)
{
    dst[0] = (uint8_t)((src >> 24) & 0xFFu);
    dst[1] = (uint8_t)((src >> 16) & 0xFFu);
    dst[2] = (uint8_t)((src >> 8) & 0xFFu);
    dst[3] = (uint8_t)(src & 0xFFu);
}

/**
 * @brief Encodes 64-bit unsigned integer to big-endian bytes
 */
static inline void encode_u64_be(uint8_t *dst, uint64_t src)
{
    dst[0] = (uint8_t)((src >> 56) & 0xFFu);
    dst[1] = (uint8_t)((src >> 48) & 0xFFu);
    dst[2] = (uint8_t)((src >> 40) & 0xFFu);
    dst[3] = (uint8_t)((src >> 32) & 0xFFu);
    dst[4] = (uint8_t)((src >> 24) & 0xFFu);
    dst[5] = (uint8_t)((src >> 16) & 0xFFu);
    dst[6] = (uint8_t)((src >> 8) & 0xFFu);
    dst[7] = (uint8_t)(src & 0xFFu);
}

/**
 * @brief Decodes 16-bit unsigned integer from big-endian bytes
 */
static inline uint16_t decode_u16_be(const uint8_t *src)
{
    return (uint16_t)(((uint16_t)src[0] << 8) | (uint16_t)src[1]);
}

/**
 * @brief Decodes 32-bit unsigned integer from big-endian bytes
 */
static inline uint32_t decode_u32_be(const uint8_t *src)
{
    return ((uint32_t)src[0] << 24)
         | ((uint32_t)src[1] << 16)
         | ((uint32_t)src[2] << 8)
         | (uint32_t)src[3];
}

/**
 * @brief Decodes 64-bit unsigned integer from big-endian bytes
 */
static inline uint64_t decode_u64_be(const uint8_t *src)
{
    return ((uint64_t)src[0] << 56)
         | ((uint64_t)src[1] << 48)
         | ((uint64_t)src[2] << 40)
         | ((uint64_t)src[3] << 32)
         | ((uint64_t)src[4] << 24)
         | ((uint64_t)src[5] << 16)
         | ((uint64_t)src[6] << 8)
         | (uint64_t)src[7];
}

/**
 * @brief Base frame structure with flexible array member
 * 
 * Used as a generic frame buffer. Cast to specific frame types as needed.
 */
typedef struct {
    factory_frame_t super; /**< Common frame header */
    uint8_t data[];        /**< Flexible array for frame payload */
} factory_base_frame_t;

/** Initializer for static factory_base_frame_t allocation */
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

/**
 * @brief Helper macro to declare and initialize a frame buffer
 * 
 * Creates a base frame structure and a pointer for convenient access.
 * Usage: FACTORY_FRAME_DEFINE(my_frame) creates:
 *   - factory_base_frame_t my_framebase (the actual buffer)
 *   - factory_frame_t *my_frame (pointer to the frame header)
 * 
 * @param name Base name for the frame variables (will create name##base and name)
 */
#define FACTORY_FRAME_DEFINE(name)                              \
    factory_base_frame_t name##base = FACTORY_BASE_FRAME_INIT; \
    factory_frame_t *name = (factory_frame_t *)&name##base

/**
 * @brief Initializes a frame header to default values
 * 
 * Resets the frame header fields to initial state (magic number set, other fields zeroed).
 * The data array is not modified. Typically used with FACTORY_FRAME_DEFINE or similar allocations.
 * 
 * @param frame Pointer to frame structure to initialize
 * @return 0 on success, -1 if frame pointer is NULL
 */
int factory_frame_init(factory_frame_t *frame);

/**
 * @brief First frame of a multi-frame packet
 * 
 * Contains total size and initial data chunk.
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint32_t total_size;   /**< Total size of complete packet across all frames */
    uint8_t sequence;      /**< Sequence number (always 0 for first frame) */
    uint8_t data[];        /**< First chunk of packet data */
} factory_first_frame_t;

/**
 * @brief Consecutive frame of a multi-frame packet
 * 
 * Contains subsequent data chunks with incrementing sequence numbers.
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t sequence;      /**< Sequence number (1, 2, 3, ...) */
    uint8_t data[];        /**< Data chunk */
} factory_consecutive_frame_t;

/**
 * @brief Single-frame packet (no fragmentation)
 * 
 * Used when entire packet fits in one frame.
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t data[];        /**< Complete packet data */
} factory_single_frame_t;

/**
 * @brief Control frame for ACK/NACK
 * 
 * Used for flow control and error notification.
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t sequence;      /**< Acknowledged/rejected sequence number (0xFF for single frames) */
} factory_control_frame_t;

#define FACTORY_CONTROL_FRAME_SIZE (sizeof(factory_control_frame_t))

/**
 * @brief Encodes an ACK/NACK control frame
 *
 * Fills magic/type/size/sequence and calculates CRC16 for the control payload.
 *
 * @param frame Destination frame buffer
 * @param is_ack True for ACK, false for NACK
 * @param sequence Sequence number to acknowledge/reject
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_control_encode(factory_frame_t *frame, bool is_ack, uint8_t sequence);

/**
 * @brief Decodes and validates an ACK/NACK control frame
 *
 * Validates magic/type/size/CRC and returns decoded control fields.
 *
 * @param frame Source frame
 * @param is_ack Output ACK/NACK flag
 * @param sequence Output sequence number from control frame
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_control_decode(const factory_frame_t *frame, bool *is_ack, uint8_t *sequence);

/**
 * @brief Extracts logical frame sequence number
 *
 * Returns sequence from FIRST/CONSECUTIVE/ACK/NACK frames.
 * For SINGLE frame, returns 0xFF by definition.
 *
 * @param frame Source frame
 * @param sequence Output sequence number
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_get_sequence(const factory_frame_t *frame, uint8_t *sequence);

/**
 * @brief Context for assembling multi-frame packets
 * 
 * Maintains state for receiving and reassembling fragmented packets.
 * Must be initialized with FACTORY_FRAME_ASSEMBLER_INIT or factory_frame_assembler_init().
 */
typedef struct {
    bool has_finished;         /**< True when packet assembly is complete */
    bool has_error;            /**< True if an error occurred during assembly */
    uint8_t sequence;          /**< Next expected sequence number */
    size_t total_size;         /**< Total expected packet size (from first frame) */
    size_t packet_size;        /**< Current size of assembled data */
    const size_t packet_capacity; /**< Maximum buffer capacity */
    uint8_t packet[];          /**< Buffer for assembled packet data */
} factory_frame_assembler_context_t;

/** 
 * @brief Initializer for static factory_frame_assembler_context_t allocation
 * 
 * @param capacity Maximum packet buffer size
 */
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

/**
 * @brief Context for fragmenting packets into frames
 * 
 * Maintains state for fragmenting large packets into multiple frames.
 * Must be initialized with FACTORY_FRAME_FRAGMENTER_INIT or factory_frame_fragmenter_init().
 */
typedef struct {
    bool has_finished;         /**< True when all frames have been generated */
    bool has_error;            /**< True if an error occurred during fragmentation */
    bool need_fragmentation;   /**< True if packet requires multiple frames */
    uint8_t sequence;          /**< Current sequence number for next frame */
    size_t index;              /**< Current position in packet being fragmented */
    size_t packet_size;        /**< Total packet size */
    const size_t packet_capacity; /**< Maximum buffer capacity */
    uint8_t packet[];          /**< Source packet buffer */
} factory_frame_fragmenter_context_t;

/** 
 * @brief Initializer for static factory_frame_fragmenter_context_t allocation
 * 
 * @param size Packet size to fragment
 */
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

/**
 * @brief Initializes frame assembler context
 * 
 * Must be called before processing any frames with the assembler.
 * 
 * @param ctx Pointer to assembler context
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_assembler_init(factory_frame_assembler_context_t *ctx);

/**
 * @brief Processes an incoming frame for packet reassembly
 * 
 * Handles single frames and multi-frame packet assembly. Validates frame integrity
 * (magic, CRC) and sequence numbers. Updates context state accordingly.
 * 
 * @param ctx Pointer to assembler context
 * @param frame Pointer to received frame
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_assembler_process(factory_frame_assembler_context_t *ctx, factory_frame_t *frame);

/**
 * @brief Initializes frame fragmenter context
 * 
 * Must be called before fragmenting a packet.
 * 
 * @param ctx Pointer to fragmenter context
 * @param size Size of packet to fragment
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_fragmenter_init(factory_frame_fragmenter_context_t *ctx, size_t size);

/**
 * @brief Generates the next frame for transmission
 * 
 * Call repeatedly until ctx->has_finished is true. Each call produces one frame
 * (single, first, or consecutive) with proper headers, sequence numbers, and CRC.
 * 
 * @param ctx Pointer to fragmenter context
 * @param frame Pointer to frame buffer to populate
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_fragmenter_process(factory_frame_fragmenter_context_t *ctx, factory_frame_t *frame);