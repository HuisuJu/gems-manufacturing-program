#include <string.h>

#include "factory_frame.h"

static uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
    // Standard CRC-16-CCITT implementation
    uint16_t crc = 0xFFFFu;

    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;

        for (int j = 0; j < 8; j++) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((crc << 1) ^ 0x1021u);
            } else {
                crc <<= 1;
            }
        }
    }

    return crc;
}

static factory_frame_error_code_t factory_frame_fail(
    bool *has_error,
    bool *has_finished,
    factory_frame_error_code_t error)
{
    if (has_error) {
        *has_error = true;
    }
    if (has_finished) {
        *has_finished = true;
    }

    return error;
}

factory_frame_error_code_t factory_frame_control_encode(factory_frame_t *frame, bool is_ack, uint8_t sequence)
{
    if (!frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    factory_control_frame_t *ctrl_frame = (factory_control_frame_t *)frame;

    factory_frame_set_magic(&ctrl_frame->super, FACTORY_FRAME_MAGIC);
    ctrl_frame->super.type = is_ack ? FACTORY_FRAME_TYPE_ACK : FACTORY_FRAME_TYPE_NACK;
    factory_frame_set_size(&ctrl_frame->super, (uint16_t)sizeof(ctrl_frame->sequence));
    ctrl_frame->sequence = sequence;
    factory_frame_set_crc16(&ctrl_frame->super, crc16_ccitt(&ctrl_frame->sequence, sizeof(ctrl_frame->sequence)));

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_control_decode(const factory_frame_t *frame, bool *is_ack, uint8_t *sequence)
{
    if (!frame || !is_ack || !sequence) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (factory_frame_get_magic(frame) != FACTORY_FRAME_MAGIC) {
        return FACTORY_FRAME_ERROR_INVALID_MAGIC;
    }
    if (frame->type != FACTORY_FRAME_TYPE_ACK && frame->type != FACTORY_FRAME_TYPE_NACK) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    const factory_control_frame_t *ctrl_frame = (const factory_control_frame_t *)frame;
    if (factory_frame_get_size(frame) != sizeof(ctrl_frame->sequence)) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    const uint16_t calculated_crc = crc16_ccitt(&ctrl_frame->sequence, sizeof(ctrl_frame->sequence));
    if (calculated_crc != factory_frame_get_crc16(frame)) {
        return FACTORY_FRAME_ERROR_CRC_MISMATCH;
    }

    *is_ack = (frame->type == FACTORY_FRAME_TYPE_ACK);
    *sequence = ctrl_frame->sequence;

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_get_sequence(const factory_frame_t *frame, uint8_t *sequence)
{
    if (!frame || !sequence) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    switch ((factory_frame_type_t)frame->type) {
        case FACTORY_FRAME_TYPE_SINGLE:
            *sequence = 0xFFu;
            return FACTORY_FRAME_ERROR_NONE;

        case FACTORY_FRAME_TYPE_FIRST:
            *sequence = ((const factory_first_frame_t *)frame)->sequence;
            return FACTORY_FRAME_ERROR_NONE;

        case FACTORY_FRAME_TYPE_CONSECUTIVE:
            *sequence = ((const factory_consecutive_frame_t *)frame)->sequence;
            return FACTORY_FRAME_ERROR_NONE;

        case FACTORY_FRAME_TYPE_ACK:
        case FACTORY_FRAME_TYPE_NACK:
            *sequence = ((const factory_control_frame_t *)frame)->sequence;
            return FACTORY_FRAME_ERROR_NONE;

        default:
            return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
}

factory_frame_error_code_t factory_frame_assembler_init(factory_frame_assembler_context_t *ctx)
{
    if (!ctx || !ctx->packet) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    ctx->has_finished = false;
    ctx->has_error = false;
    ctx->sequence = 0u;
    ctx->total_size = 0u;
    ctx->packet_size = 0u;

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_assembler_process(factory_frame_assembler_context_t *ctx, factory_frame_t *frame)
{
    if (!ctx || !ctx->packet || !frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->has_finished || ctx->has_error) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    if (factory_frame_get_magic(frame) != FACTORY_FRAME_MAGIC) {
        return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_INVALID_MAGIC);
    }

    const uint16_t frame_size = factory_frame_get_size(frame);
    const uint16_t frame_crc16 = factory_frame_get_crc16(frame);
    const uint16_t calculated_crc =
        crc16_ccitt((const uint8_t *)frame + FACTORY_FRAME_HEADER_SIZE, frame_size);

    if ((size_t)frame_size > ctx->packet_capacity) {
        return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_BUFFER_OVERFLOW);
    }
    if (calculated_crc != frame_crc16) {
        return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_CRC_MISMATCH);
    }

    switch ((factory_frame_type_t)frame->type) {
        case FACTORY_FRAME_TYPE_SINGLE: {
            const factory_single_frame_t *single_frame = (const factory_single_frame_t *)frame;

            memcpy(ctx->packet, single_frame->data, frame_size);
            ctx->packet_size = frame_size;
            ctx->sequence = 0xFFu;
            ctx->has_finished = true;

            return FACTORY_FRAME_ERROR_NONE;
        }

        case FACTORY_FRAME_TYPE_FIRST: {
            const factory_first_frame_t *first_frame = (const factory_first_frame_t *)frame;
            const size_t metadata_size = sizeof(first_frame->total_size) + sizeof(first_frame->sequence);

            if (frame_size < metadata_size) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_INVALID_ARGUMENT);
            }
            if (first_frame->sequence != 0u) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE);
            }

            const uint32_t total_size = decode_u32_be(first_frame->total_size);
            const size_t data_size = (size_t)frame_size - metadata_size;

            if ((size_t)total_size > ctx->packet_capacity) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_BUFFER_OVERFLOW);
            }
            if (data_size > (size_t)total_size) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_BUFFER_OVERFLOW);
            }

            ctx->total_size = (size_t)total_size;
            memcpy(ctx->packet, first_frame->data, data_size);
            ctx->packet_size = data_size;
            ctx->sequence = 1u;

            if (ctx->packet_size == ctx->total_size) {
                ctx->has_finished = true;
            }

            return FACTORY_FRAME_ERROR_NONE;
        }

        case FACTORY_FRAME_TYPE_CONSECUTIVE: {
            const factory_consecutive_frame_t *consecutive_frame = (const factory_consecutive_frame_t *)frame;
            const size_t metadata_size = sizeof(consecutive_frame->sequence);

            if (frame_size < metadata_size) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_INVALID_ARGUMENT);
            }
            if (ctx->total_size == 0u) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE);
            }
            if (consecutive_frame->sequence != ctx->sequence) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE);
            }

            const size_t data_size = (size_t)frame_size - metadata_size;

            if (ctx->packet_size + data_size > ctx->packet_capacity) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_BUFFER_OVERFLOW);
            }
            if (ctx->packet_size + data_size > ctx->total_size) {
                return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_BUFFER_OVERFLOW);
            }

            memcpy(ctx->packet + ctx->packet_size, consecutive_frame->data, data_size);
            ctx->packet_size += data_size;
            ctx->sequence++;

            if (ctx->packet_size == ctx->total_size) {
                ctx->has_finished = true;
            }

            return FACTORY_FRAME_ERROR_NONE;
        }

        default:
            return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_INVALID_ARGUMENT);
    }
}

factory_frame_error_code_t factory_frame_fragmenter_init(factory_frame_fragmenter_context_t *ctx, size_t size)
{
    if (!ctx || !ctx->packet || size == 0u) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (size > ctx->packet_capacity) {
        return FACTORY_FRAME_ERROR_BUFFER_OVERFLOW;
    }

    ctx->has_finished = false;
    ctx->has_error = false;
    ctx->need_fragmentation = (size > FACTORY_FRAME_MAX_DATA_SIZE);
    ctx->sequence = 0u;
    ctx->index = 0u;
    ctx->packet_size = size;

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_fragmenter_process(factory_frame_fragmenter_context_t *ctx, factory_frame_t *frame)
{
    if (!ctx || !ctx->packet || !frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->has_finished || ctx->has_error) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->index >= ctx->packet_size) {
        return factory_frame_fail(&ctx->has_error, &ctx->has_finished, FACTORY_FRAME_ERROR_INVALID_ARGUMENT);
    }

    if (!ctx->need_fragmentation) {
        factory_single_frame_t *single_frame = (factory_single_frame_t *)frame;

        factory_frame_set_magic(&single_frame->super, FACTORY_FRAME_MAGIC);
        single_frame->super.type = FACTORY_FRAME_TYPE_SINGLE;
        factory_frame_set_size(&single_frame->super, (uint16_t)ctx->packet_size);

        memcpy(single_frame->data, ctx->packet, ctx->packet_size);
        factory_frame_set_crc16(&single_frame->super, crc16_ccitt(single_frame->data, ctx->packet_size));

        ctx->index = ctx->packet_size;
        ctx->has_finished = true;

        return FACTORY_FRAME_ERROR_NONE;
    }

    if (ctx->sequence == 0u) {
        factory_first_frame_t *first_frame = (factory_first_frame_t *)frame;
        const size_t overhead_size = sizeof(first_frame->total_size) + sizeof(first_frame->sequence);
        const size_t max_data_size = FACTORY_FRAME_MAX_DATA_SIZE - overhead_size;
        const size_t chunk_size = (ctx->packet_size > max_data_size) ? max_data_size : ctx->packet_size;
        const uint16_t encoded_size = (uint16_t)(overhead_size + chunk_size);

        factory_frame_set_magic(&first_frame->super, FACTORY_FRAME_MAGIC);
        first_frame->super.type = FACTORY_FRAME_TYPE_FIRST;
        factory_frame_set_size(&first_frame->super, encoded_size);

        encode_u32_be(first_frame->total_size, (uint32_t)ctx->packet_size);
        first_frame->sequence = 0u;
        memcpy(first_frame->data, ctx->packet, chunk_size);
        factory_frame_set_crc16(
            &first_frame->super,
            crc16_ccitt((const uint8_t *)first_frame + FACTORY_FRAME_HEADER_SIZE, encoded_size));

        ctx->index += chunk_size;
        ctx->sequence++;

        return FACTORY_FRAME_ERROR_NONE;
    }

    {
        factory_consecutive_frame_t *consecutive_frame = (factory_consecutive_frame_t *)frame;
        const size_t overhead_size = sizeof(consecutive_frame->sequence);
        const size_t max_data_size = FACTORY_FRAME_MAX_DATA_SIZE - overhead_size;
        const size_t remaining_size = ctx->packet_size - ctx->index;
        const size_t chunk_size = (remaining_size > max_data_size) ? max_data_size : remaining_size;
        const uint16_t encoded_size = (uint16_t)(overhead_size + chunk_size);

        factory_frame_set_magic(&consecutive_frame->super, FACTORY_FRAME_MAGIC);
        consecutive_frame->super.type = FACTORY_FRAME_TYPE_CONSECUTIVE;
        factory_frame_set_size(&consecutive_frame->super, encoded_size);

        consecutive_frame->sequence = ctx->sequence;
        memcpy(consecutive_frame->data, ctx->packet + ctx->index, chunk_size);
        factory_frame_set_crc16(
            &consecutive_frame->super,
            crc16_ccitt((const uint8_t *)consecutive_frame + FACTORY_FRAME_HEADER_SIZE, encoded_size));

        ctx->index += chunk_size;
        ctx->sequence++;

        if (ctx->index >= ctx->packet_size) {
            ctx->has_finished = true;
        }
    }

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_init(factory_frame_t *frame)
{
    if (!frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    /*
     * The session module always provides concrete frame storage.
     * Initialize the full storage area including payload bytes.
     */
    memset(frame, 0, sizeof(factory_frame_storage_t));

    factory_frame_set_magic(frame, FACTORY_FRAME_MAGIC);
    frame->type = 0u;
    factory_frame_set_size(frame, 0u);
    factory_frame_set_crc16(frame, 0u);

    return FACTORY_FRAME_ERROR_NONE;
}