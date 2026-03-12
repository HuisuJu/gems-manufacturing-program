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

#ifdef __cplusplus
extern "C" {
#endif

/** Maximum size of a single frame (including header) */
#ifdef TEST
#define FACTORY_FRAME_MAX_SIZE 64u   /**< Smaller size for testing purposes */
#else
#define FACTORY_FRAME_MAX_SIZE 512u  /**< Production size */
#endif

/** Frame magic number for validation */
#define FACTORY_FRAME_MAGIC 0xFAC0u

/** Error codes for frame operations */
typedef enum {
    FACTORY_FRAME_ERROR_NONE                 = 0,  /**< Success */
    FACTORY_FRAME_ERROR_INVALID_ARGUMENT     = -1, /**< Invalid function argument */
    FACTORY_FRAME_ERROR_INVALID_MAGIC        = -2, /**< Frame magic number mismatch */
    FACTORY_FRAME_ERROR_CRC_MISMATCH         = -3, /**< CRC validation failed */
    FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE  = -4, /**< Unexpected sequence number */
    FACTORY_FRAME_ERROR_BUFFER_OVERFLOW      = -5, /**< Buffer capacity exceeded */
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
 * @brief Common frame header (7 bytes)
 *
 * All multi-byte fields are stored in big-endian wire format.
 */
typedef struct __attribute__((packed)) {
    uint8_t magic[2];  /**< Magic number in big-endian wire format */
    uint8_t type;      /**< Frame type */
    uint8_t size[2];   /**< Payload size in big-endian wire format */
    uint8_t crc16[2];  /**< CRC16 in big-endian wire format */
} factory_frame_t;

#define FACTORY_FRAME_HEADER_SIZE   ((size_t)sizeof(factory_frame_t))
#define FACTORY_FRAME_MAX_DATA_SIZE (FACTORY_FRAME_MAX_SIZE - FACTORY_FRAME_HEADER_SIZE)

/**
 * @brief Returns frame magic value
 */
static inline uint16_t factory_frame_get_magic(const factory_frame_t *frame)
{
    return decode_u16_be(frame->magic);
}

/**
 * @brief Sets frame magic value
 */
static inline void factory_frame_set_magic(factory_frame_t *frame, uint16_t magic)
{
    encode_u16_be(frame->magic, magic);
}

/**
 * @brief Returns frame payload size
 */
static inline uint16_t factory_frame_get_size(const factory_frame_t *frame)
{
    return decode_u16_be(frame->size);
}

/**
 * @brief Sets frame payload size
 */
static inline void factory_frame_set_size(factory_frame_t *frame, uint16_t size)
{
    encode_u16_be(frame->size, size);
}

/**
 * @brief Returns frame CRC16 value
 */
static inline uint16_t factory_frame_get_crc16(const factory_frame_t *frame)
{
    return decode_u16_be(frame->crc16);
}

/**
 * @brief Sets frame CRC16 value
 */
static inline void factory_frame_set_crc16(factory_frame_t *frame, uint16_t crc16)
{
    encode_u16_be(frame->crc16, crc16);
}

/**
 * @brief Concrete frame storage buffer
 *
 * Provides concrete storage large enough for any frame.
 */
typedef struct {
    factory_frame_t frame;                     /**< Frame header */
    uint8_t data[FACTORY_FRAME_MAX_DATA_SIZE]; /**< Frame payload storage */
} factory_frame_storage_t;

/** Initializer for static factory_frame_storage_t allocation */
#define FACTORY_FRAME_STORAGE_INIT             \
    {                                          \
        .frame = {                             \
            .magic = { 0xFAu, 0xC0u },         \
            .type = 0u,                        \
            .size = { 0x00u, 0x00u },          \
            .crc16 = { 0x00u, 0x00u },         \
        },                                     \
        .data = { 0 },                         \
    }

/**
 * @brief Helper macro to declare one frame buffer and pointer
 */
#define FACTORY_FRAME_DEFINE(name)                             \
    factory_frame_storage_t name##_storage = FACTORY_FRAME_STORAGE_INIT; \
    factory_frame_t *name = &name##_storage.frame

/**
 * @brief Initializes a frame header to default values
 *
 * @param frame Pointer to frame structure
 * @return FACTORY_FRAME_ERROR_NONE on success, negative error code on failure
 */
factory_frame_error_code_t factory_frame_init(factory_frame_t *frame);

/**
 * @brief First frame of a multi-frame packet
 *
 * All multi-byte fields are stored in big-endian wire format.
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t total_size[4]; /**< Total packet size in big-endian wire format */
    uint8_t sequence;      /**< Sequence number (always 0 for first frame) */
    uint8_t data[];        /**< First data chunk */
} factory_first_frame_t;

/**
 * @brief Consecutive frame of a multi-frame packet
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t sequence;      /**< Sequence number */
    uint8_t data[];        /**< Data chunk */
} factory_consecutive_frame_t;

/**
 * @brief Single-frame packet
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t data[];        /**< Complete packet data */
} factory_single_frame_t;

/**
 * @brief Control frame for ACK/NACK
 */
typedef struct __attribute__((packed)) {
    factory_frame_t super; /**< Common frame header */
    uint8_t sequence;      /**< Sequence number */
} factory_control_frame_t;

#define FACTORY_CONTROL_FRAME_SIZE ((size_t)sizeof(factory_control_frame_t))

/**
 * @brief Encodes an ACK/NACK control frame
 */
factory_frame_error_code_t factory_frame_control_encode(factory_frame_t *frame, bool is_ack, uint8_t sequence);

/**
 * @brief Decodes and validates an ACK/NACK control frame
 */
factory_frame_error_code_t factory_frame_control_decode(const factory_frame_t *frame, bool *is_ack, uint8_t *sequence);

/**
 * @brief Extracts logical frame sequence number
 */
factory_frame_error_code_t factory_frame_get_sequence(const factory_frame_t *frame, uint8_t *sequence);

/**
 * @brief Context for assembling fragmented frames into one packet
 *
 * The packet buffer is externally provided and owned by the caller.
 */
typedef struct {
    bool has_finished;     /**< True when packet assembly is complete */
    bool has_error;        /**< True if an error occurred during assembly */
    uint8_t sequence;      /**< Next expected sequence number */
    size_t total_size;     /**< Total expected packet size */
    size_t packet_size;    /**< Current assembled packet size */
    size_t packet_capacity;/**< Capacity of packet buffer */
    uint8_t *packet;       /**< Packet buffer provided by caller */
} factory_frame_assembler_context_t;

/**
 * @brief Context for fragmenting one packet into multiple frames
 *
 * The packet buffer is externally provided and owned by the caller.
 */
typedef struct {
    bool has_finished;      /**< True when all frames have been generated */
    bool has_error;         /**< True if an error occurred during fragmentation */
    bool need_fragmentation;/**< True if packet requires multiple frames */
    uint8_t sequence;       /**< Current sequence number */
    size_t index;           /**< Current packet offset */
    size_t packet_size;     /**< Total packet size */
    size_t packet_capacity; /**< Capacity of packet buffer */
    uint8_t *packet;        /**< Packet buffer provided by caller */
} factory_frame_fragmenter_context_t;

/**
 * @brief Initializer for assembler context bound to a packet buffer
 */
#define FACTORY_FRAME_ASSEMBLER_INIT(buffer_) \
    {                                         \
        .has_finished = false,                \
        .has_error = false,                   \
        .sequence = 0u,                       \
        .total_size = 0u,                     \
        .packet_size = 0u,                    \
        .packet_capacity = sizeof(buffer_),   \
        .packet = (buffer_),                  \
    }

/**
 * @brief Initializer for fragmenter context bound to a packet buffer
 */
#define FACTORY_FRAME_FRAGMENTER_INIT(buffer_) \
    {                                          \
        .has_finished = false,                 \
        .has_error = false,                    \
        .need_fragmentation = false,           \
        .sequence = 0u,                        \
        .index = 0u,                           \
        .packet_size = 0u,                     \
        .packet_capacity = sizeof(buffer_),    \
        .packet = (buffer_),                   \
    }

/**
 * @brief Initializes frame assembler context
 */
factory_frame_error_code_t factory_frame_assembler_init(factory_frame_assembler_context_t *ctx);

/**
 * @brief Processes an incoming frame for reassembly
 */
factory_frame_error_code_t factory_frame_assembler_process(factory_frame_assembler_context_t *ctx, factory_frame_t *frame);

/**
 * @brief Initializes frame fragmenter context
 */
factory_frame_error_code_t factory_frame_fragmenter_init(factory_frame_fragmenter_context_t *ctx, size_t size);

/**
 * @brief Generates the next frame for transmission
 */
factory_frame_error_code_t factory_frame_fragmenter_process(factory_frame_fragmenter_context_t *ctx, factory_frame_t *frame);

#ifdef __cplusplus
}
#endif