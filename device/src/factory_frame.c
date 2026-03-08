#include <string.h>
#include "factory_frame.h"

static uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
    // Standard CRC-16-CCITT implementation
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;

        for (int j = 0; j < 8; j++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

factory_frame_error_code_t factory_frame_control_encode(factory_frame_t *frame, bool is_ack, uint8_t sequence)
{
    if (!frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    factory_control_frame_t *ctrl_frame = (factory_control_frame_t *)frame;
    ctrl_frame->super.magic = FACTORY_FRAME_MAGIC;
    ctrl_frame->super.type = is_ack ? FACTORY_FRAME_TYPE_ACK : FACTORY_FRAME_TYPE_NACK;
    ctrl_frame->super.size = sizeof(ctrl_frame->sequence);
    ctrl_frame->sequence = sequence;
    ctrl_frame->super.crc16 = crc16_ccitt(&ctrl_frame->sequence, sizeof(ctrl_frame->sequence));

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_control_decode(const factory_frame_t *frame, bool *is_ack, uint8_t *sequence)
{
    if (!frame || !is_ack || !sequence) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (frame->magic != FACTORY_FRAME_MAGIC) {
        return FACTORY_FRAME_ERROR_INVALID_MAGIC;
    }
    if (frame->type != FACTORY_FRAME_TYPE_ACK && frame->type != FACTORY_FRAME_TYPE_NACK) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    const factory_control_frame_t *ctrl_frame = (const factory_control_frame_t *)frame;
    if (frame->size != sizeof(ctrl_frame->sequence)) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    uint16_t calculated_crc = crc16_ccitt(&ctrl_frame->sequence, sizeof(ctrl_frame->sequence));
    if (calculated_crc != frame->crc16) {
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

factory_frame_error_code_t factory_frame_assembler_init(
    factory_frame_assembler_context_t *ctx)
{
    if (!ctx) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    ctx->has_finished = false;
    ctx->has_error = false;
    ctx->sequence = 0;
    ctx->total_size = 0;
    ctx->packet_size = 0;

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_assembler_process(
    factory_frame_assembler_context_t *ctx, factory_frame_t *frame)
{
    if (!ctx || !frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->has_finished || ctx->has_error) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    if (frame->magic != FACTORY_FRAME_MAGIC) {
        ctx->has_error = true;
        ctx->has_finished = true;
        return FACTORY_FRAME_ERROR_INVALID_MAGIC;
    }
    if (frame->size > ctx->packet_capacity) {
        ctx->has_error = true;
        ctx->has_finished = true;
        return FACTORY_FRAME_ERROR_BUFFER_OVERFLOW;
    }
    uint16_t calculated_crc = crc16_ccitt((uint8_t *)frame + FACTORY_FRAME_HEADER_SIZE, frame->size);
    if (calculated_crc != frame->crc16) {
        ctx->has_error = true;
        ctx->has_finished = true;
        return FACTORY_FRAME_ERROR_CRC_MISMATCH;
    }

    switch (frame->type) {
        case FACTORY_FRAME_TYPE_SINGLE: {
            factory_single_frame_t *single_frame = (factory_single_frame_t *)frame;
            memcpy(ctx->packet, single_frame->data, frame->size);
            ctx->packet_size = frame->size;
            ctx->sequence = 0xFFu;
            ctx->has_finished = true;

            break;
        }
        case FACTORY_FRAME_TYPE_FIRST: {
            factory_first_frame_t *first_frame = (factory_first_frame_t *)frame;
            if (first_frame->total_size > ctx->packet_capacity) {
                ctx->has_error = true;
                ctx->has_finished = true;
                return FACTORY_FRAME_ERROR_BUFFER_OVERFLOW;
            }
            if (first_frame->sequence != 0) {
                ctx->has_error = true;
                ctx->has_finished = true;
                return FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE;
            }
            ctx->total_size = first_frame->total_size;
            size_t data_size = frame->size - sizeof(uint32_t) - sizeof(uint8_t);
            memcpy(ctx->packet, first_frame->data, data_size);
            ctx->packet_size = data_size;
            ctx->sequence = 1; // Expect the next consecutive frame to have sequence number 1

            break;
        }
        case FACTORY_FRAME_TYPE_CONSECUTIVE: {
            factory_consecutive_frame_t *consecutive_frame = (factory_consecutive_frame_t *)frame;
            if (consecutive_frame->sequence != ctx->sequence) {
                ctx->has_error = true;
                ctx->has_finished = true;
                return FACTORY_FRAME_ERROR_UNEXPECTED_SEQUENCE;
            }
            size_t data_size = frame->size - sizeof(uint8_t);
            if (ctx->packet_size + data_size > ctx->packet_capacity) {
                ctx->has_error = true;
                ctx->has_finished = true;
                return FACTORY_FRAME_ERROR_BUFFER_OVERFLOW;
            }
            memcpy(ctx->packet + ctx->packet_size, consecutive_frame->data, data_size);
            ctx->packet_size += data_size;
            ctx->sequence++; // Expect the next consecutive frame to have the next sequence number
            
            // Check if we've received all data
            if (ctx->packet_size >= ctx->total_size) {
                ctx->has_finished = true;
            }

            break;
        }
        default:
            ctx->has_error = true;
            ctx->has_finished = true;
            return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_fragmenter_init(
    factory_frame_fragmenter_context_t *ctx, size_t size)
{
    if (!ctx || size == 0) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    ctx->has_finished = false;
    ctx->has_error = false;
    ctx->need_fragmentation = (size > FACTORY_FRAME_MAX_DATA_SIZE);
    ctx->sequence = 0;
    ctx->index = 0;
    ctx->packet_size = size;

    return FACTORY_FRAME_ERROR_NONE;
}

factory_frame_error_code_t factory_frame_fragmenter_process(
    factory_frame_fragmenter_context_t *ctx, factory_frame_t *frame)
{
    if (!ctx || !frame) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->has_finished || ctx->has_error) {
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }
    if (ctx->index >= ctx->packet_size) {
        ctx->has_error = true;
        ctx->has_finished = true;
        return FACTORY_FRAME_ERROR_INVALID_ARGUMENT;
    }

    if (!ctx->need_fragmentation) {
        // No fragmentation needed, just fill the single frame
        frame->magic = FACTORY_FRAME_MAGIC;
        frame->type = FACTORY_FRAME_TYPE_SINGLE;
        frame->size = ctx->packet_size;

        factory_single_frame_t *single_frame = (factory_single_frame_t *)frame;
        memcpy(single_frame->data, ctx->packet, ctx->packet_size);
        frame->crc16 = crc16_ccitt(single_frame->data, ctx->packet_size);

        ctx->index += ctx->packet_size;
        ctx->has_finished = true;

        return FACTORY_FRAME_ERROR_NONE;
    }

    if (ctx->sequence == 0) {
        // Fill the first frame
        factory_first_frame_t *first_frame = (factory_first_frame_t *)frame;
        size_t max_data_size = FACTORY_FRAME_MAX_DATA_SIZE - sizeof(uint32_t) - sizeof(uint8_t);
        size_t chunk_size = (ctx->packet_size > max_data_size) ? max_data_size : ctx->packet_size;
        
        frame->magic = FACTORY_FRAME_MAGIC;
        frame->type = FACTORY_FRAME_TYPE_FIRST;
        frame->size = chunk_size + sizeof(uint32_t) + sizeof(uint8_t);
        
        first_frame->total_size = ctx->packet_size;
        first_frame->sequence = ctx->sequence;
        memcpy(first_frame->data, ctx->packet, chunk_size);
        frame->crc16 = crc16_ccitt((uint8_t *)first_frame + FACTORY_FRAME_HEADER_SIZE, frame->size);

        ctx->index += chunk_size;
        ctx->sequence++;

        return FACTORY_FRAME_ERROR_NONE;
    } else {
        // Fill a consecutive frame
        factory_consecutive_frame_t *consecutive_frame = (factory_consecutive_frame_t *)frame;
        size_t max_data_size = FACTORY_FRAME_MAX_DATA_SIZE - sizeof(uint8_t);
        size_t remaining_size = ctx->packet_size - ctx->index;
        size_t chunk_size = (remaining_size > max_data_size) ? max_data_size : remaining_size;

        frame->magic = FACTORY_FRAME_MAGIC;
        frame->type = FACTORY_FRAME_TYPE_CONSECUTIVE;
        frame->size = chunk_size + sizeof(uint8_t);
        
        consecutive_frame->sequence = ctx->sequence;
        memcpy(consecutive_frame->data, ctx->packet + ctx->index, chunk_size);
        frame->crc16 = crc16_ccitt((uint8_t *)consecutive_frame + FACTORY_FRAME_HEADER_SIZE, frame->size);

        ctx->index += chunk_size;
        ctx->sequence++;

        if (ctx->index >= ctx->packet_size) {
            ctx->has_finished = true;
        }
    }

    return FACTORY_FRAME_ERROR_NONE;
}

int factory_frame_init(factory_frame_t *frame)
{
    if (!frame) {
        return -1;
    }
    frame->magic = FACTORY_FRAME_MAGIC;
    frame->type = 0;
    frame->size = 0;
    frame->crc16 = 0;
    // Note: data array is not cleared as its size is determined at allocation time

    return 0;
}