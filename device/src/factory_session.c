#include <string.h>
#include "factory_platform.h"
#include "factory_frame.h"
#include "factory_session.h"

/*
 * Header format (big-endian):
 * - Session packet    : VERSION(1) | TYPE(1) | FLAG(1) | SESSION_ID(16) | SIZE(4) | PAYLOAD
 * - Sessionless packet: VERSION(1) | TYPE(1) | FLAG(1) | SIZE(4) | PAYLOAD
 */

#define FACTORY_PROTOCOL_VERSION                 (0x01u)
#define FACTORY_SESSION_ID_SIZE                  (16u)
#define FACTORY_SESSIONLESS_HEADER_SIZE          (7u)
#define FACTORY_SESSION_HEADER_SIZE              (3u + FACTORY_SESSION_ID_SIZE + 4u)
#define FACTORY_PACKET_HEADER_SIZE(has_session)  ((has_session) ? FACTORY_SESSION_HEADER_SIZE : FACTORY_SESSIONLESS_HEADER_SIZE)

#define FACTORY_DEVICE_HELLO_PAYLOAD_VERSION     (0x01u)
#define FACTORY_PC_HELLO_PAYLOAD_VERSION         (0x01u)
#define FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE    (2u + 8u + 1u)
#define FACTORY_PC_HELLO_PAYLOAD_MIN_SIZE        (2u + FACTORY_SESSION_ID_SIZE)

#define FACTORY_UART_MAX_RETRIES    (3u)
#define FACTORY_UART_RETRY_DELAY_MS (100u)
#define FACTORY_UART_POLL_DELAY_MS  (3u)
#define FACTORY_READ_TIMEOUT_MS     (1000u)
#define FACTORY_WRITE_TIMEOUT_MS    (1000u)
#define FACTORY_FLOW_CONTROL_TIMEOUT_MS (500u)

typedef enum {
    FACTORY_PACKET_TYPE_MESSAGE = 0x01,

    FACTORY_PACKET_TYPE_PC_HELLO = 0x10,
    FACTORY_PACKET_TYPE_PC_BYE   = 0x11,
    FACTORY_PACKET_TYPE_PC_ALERT = 0x12,

    FACTORY_PACKET_TYPE_DEVICE_HELLO     = 0x20,
    FACTORY_PACKET_TYPE_DEVICE_BYE       = 0x21,
    FACTORY_PACKET_TYPE_DEVICE_ALERT     = 0x22,
    FACTORY_PACKET_TYPE_DEVICE_CHALLENGE = 0x23,
} factory_packet_type_t;

static const factory_packet_type_t sessionless_packets[] = {
    FACTORY_PACKET_TYPE_PC_HELLO,
    FACTORY_PACKET_TYPE_PC_ALERT,
    FACTORY_PACKET_TYPE_DEVICE_HELLO,
    FACTORY_PACKET_TYPE_DEVICE_ALERT,
    FACTORY_PACKET_TYPE_DEVICE_CHALLENGE,
};

static bool is_sessionless_packet(factory_packet_type_t type)
{
    for (size_t i = 0; i < sizeof(sessionless_packets) / sizeof(sessionless_packets[0]); i++) {
        if (sessionless_packets[i] == type) {
            return true;
        }
    }
    return false;
}

typedef struct {
    factory_packet_type_t type;
    uint8_t flag;
    const uint8_t *payload;
    size_t payload_size;
    bool sessionless;
} factory_packet_view_t;

static struct {
    bool is_opened;
    bool is_error;
    bool has_session_id;
    uint8_t session_id[FACTORY_SESSION_ID_SIZE];
    bool require_auth;
    factory_session_event_handler_t event_handler;
} session_context;

FACTORY_FRAME_DEFINE(frame);
FACTORY_FRAME_DEFINE(pending_frame);

static bool has_pending_rx_frame;

static void clear_session_state(bool keep_auth_flag)
{
    bool require_auth = session_context.require_auth;

    session_context.is_opened = false;
    session_context.is_error = false;
    session_context.has_session_id = false;
    memset(session_context.session_id, 0, sizeof(session_context.session_id));
    session_context.require_auth = keep_auth_flag ? require_auth : false;
    has_pending_rx_frame = false;
}

static void close_session_and_notify(void)
{
    if (session_context.is_opened || session_context.has_session_id) {
        clear_session_state(false);
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_CLOSED);
        }
    } else {
        clear_session_state(false);
    }
}

static int parse_packet_view(
    const uint8_t *packet,
    size_t packet_size,
    bool require_session_match,
    factory_packet_view_t *view)
{
    if (!packet || !view) {
        return -1;
    }
    if (packet_size < FACTORY_SESSIONLESS_HEADER_SIZE) {
        return -2;
    }
    if (packet[0] != FACTORY_PROTOCOL_VERSION) {
        return -3;
    }

    factory_packet_type_t type = (factory_packet_type_t)packet[1];
    bool sessionless = is_sessionless_packet(type);

    size_t header_size = sessionless ? FACTORY_SESSIONLESS_HEADER_SIZE : FACTORY_SESSION_HEADER_SIZE;
    if (packet_size < header_size) {
        return -4;
    }

    const uint8_t *size_ptr = sessionless ? &packet[3] : &packet[3 + FACTORY_SESSION_ID_SIZE];
    if (!sessionless && require_session_match) {
        if (!session_context.is_opened || !session_context.has_session_id) {
            return -5;
        }
        if (memcmp(&packet[3], session_context.session_id, FACTORY_SESSION_ID_SIZE) != 0) {
            return -6;
        }
    }

    size_t payload_size = (size_t)decode_u32_be(size_ptr);
    if (header_size + payload_size > packet_size) {
        return -7;
    }

    view->type = type;
    view->flag = packet[2];
    view->payload = &packet[header_size];
    view->payload_size = payload_size;
    view->sessionless = sessionless;

    return 0;
}

static int build_device_hello_payload(uint8_t *payload, size_t payload_capacity, size_t *payload_size)
{
    if (!payload || !payload_size || payload_capacity < FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE) {
        return -1;
    }

    payload[0] = FACTORY_DEVICE_HELLO_PAYLOAD_VERSION;
    payload[1] = FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE;
    encode_u64_be(&payload[2], factory_platform_get_uuid());
    payload[10] = session_context.require_auth ? 1u : 0u;

    *payload_size = FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE;
    return 0;
}

static int parse_pc_hello_payload(const uint8_t *payload, size_t payload_size, uint8_t *session_id_out)
{
    if (!payload || !session_id_out || payload_size < FACTORY_PC_HELLO_PAYLOAD_MIN_SIZE) {
        return -1;
    }
    if (payload[0] != FACTORY_PC_HELLO_PAYLOAD_VERSION) {
        return -2;
    }

    uint8_t declared_size = payload[1];
    if (declared_size > payload_size || declared_size < FACTORY_PC_HELLO_PAYLOAD_MIN_SIZE) {
        return -3;
    }

    memcpy(session_id_out, &payload[2], FACTORY_SESSION_ID_SIZE);
    return 0;
}

static int read_frame(factory_frame_t *frame, uint32_t timeout_ms)
{
    if (!frame) {
        return -1;
    }

    const uint32_t start_ms = factory_platform_get_uptime_ms();
    uint8_t magic_buf[2] = {0, 0};
    uint32_t negative_read_count = 0;

    // Search for magic number (0xFAC0) byte by byte
    while (1) {
        if ((factory_platform_get_uptime_ms() - start_ms) >= timeout_ms) {
            return -2;  // Timeout
        }

        // Read one byte for magic detection
        magic_buf[0] = magic_buf[1];
        size_t total_reads = 0;
        while (total_reads < 1) {
            ssize_t num_reads = factory_platform_uart_read(&magic_buf[1], 1);
            if (num_reads < 0) {
                negative_read_count++;
                if (negative_read_count >= FACTORY_UART_MAX_RETRIES) {
                    return -3;
                }
                factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
                continue;
            }
            if (num_reads > 0) {
                total_reads += (size_t)num_reads;
                negative_read_count = 0;
            } else {
                factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
            }
        }

        // Check if we found the magic number
        uint16_t magic = ((uint16_t)magic_buf[0] << 8) | (uint16_t)magic_buf[1];
        if (magic == FACTORY_FRAME_MAGIC) {
            break;
        }
    }

    // Write magic to frame header
    frame->magic = FACTORY_FRAME_MAGIC;

    // Read rest of header (type, size, crc16)
    uint8_t *header_ptr = ((uint8_t *)frame) + 2;
    size_t header_remaining = FACTORY_FRAME_HEADER_SIZE - 2;
    size_t total_reads = 0;
    negative_read_count = 0;

    while (total_reads < header_remaining) {
        if ((factory_platform_get_uptime_ms() - start_ms) >= timeout_ms) {
            return -4;
        }

        ssize_t num_reads = factory_platform_uart_read(header_ptr + total_reads, header_remaining - total_reads);
        if (num_reads < 0) {
            negative_read_count++;
            if (negative_read_count >= FACTORY_UART_MAX_RETRIES) {
                return -5;
            }
            factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
            continue;
        }
        if (num_reads > 0) {
            total_reads += (size_t)num_reads;
            negative_read_count = 0;
        } else {
            factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
        }
    }

    // Validate frame size
    if (frame->size > FACTORY_FRAME_MAX_DATA_SIZE) {
        return -6;
    }

    // Read data payload
    if (frame->size > 0) {
        uint8_t *data_ptr = ((uint8_t *)frame) + FACTORY_FRAME_HEADER_SIZE;
        total_reads = 0;
        negative_read_count = 0;

        while (total_reads < frame->size) {
            if ((factory_platform_get_uptime_ms() - start_ms) >= timeout_ms) {
                return -7;
            }

            ssize_t num_reads = factory_platform_uart_read(data_ptr + total_reads, frame->size - total_reads);
            if (num_reads < 0) {
                negative_read_count++;
                if (negative_read_count >= FACTORY_UART_MAX_RETRIES) {
                    return -8;
                }
                factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
                continue;
            }
            if (num_reads > 0) {
                total_reads += (size_t)num_reads;
                negative_read_count = 0;
            } else {
                factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
            }
        }
    }

    return 0;
}

static int load_next_rx_frame(factory_frame_t *out_frame, uint32_t timeout_ms)
{
    if (!out_frame) {
        return -1;
    }

    if (has_pending_rx_frame) {
        memcpy(out_frame, pending_frame, FACTORY_FRAME_HEADER_SIZE + pending_frame->size);
        has_pending_rx_frame = false;
        return 0;
    }

    return read_frame(out_frame, timeout_ms);
}

static int write_frame(const factory_frame_t *frame, uint32_t timeout_ms)
{
    if (!frame) {
        return -1;
    }

    const size_t frame_size = FACTORY_FRAME_HEADER_SIZE + frame->size;
    const uint8_t *buffer = (const uint8_t *)frame;
    size_t total_written = 0;
    uint32_t negative_write_count = 0;
    const uint32_t start_ms = factory_platform_get_uptime_ms();

    while (total_written < frame_size) {
        if ((factory_platform_get_uptime_ms() - start_ms) >= timeout_ms) {
            return -2;
        }

        ssize_t num_written = factory_platform_uart_write(buffer + total_written, frame_size - total_written);
        if (num_written < 0) {
            negative_write_count++;
            if (negative_write_count >= FACTORY_UART_MAX_RETRIES) {
                return -3;
            }
            factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
            continue;
        }

        if (num_written > 0) {
            total_written += (size_t)num_written;
            negative_write_count = 0;
        } else {
            factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
        }
    }

    return 0;
}

static int send_flow_control(bool is_ack, uint8_t sequence)
{
    if (factory_frame_init(frame) != 0) {
        return -1;
    }

    if (factory_frame_control_encode(frame, is_ack, sequence) != FACTORY_FRAME_ERROR_NONE) {
        return -2;
    }

    return write_frame((const factory_frame_t *)frame, FACTORY_WRITE_TIMEOUT_MS);
}

static int wait_flow_control(uint8_t sequence, bool *is_ack)
{
    if (!is_ack) {
        return -1;
    }

    const uint32_t start_ms = factory_platform_get_uptime_ms();

    while ((factory_platform_get_uptime_ms() - start_ms) < FACTORY_FLOW_CONTROL_TIMEOUT_MS) {
        if (factory_frame_init(frame) != 0) {
            return -2;
        }

        uint32_t elapsed = factory_platform_get_uptime_ms() - start_ms;
        uint32_t remaining = FACTORY_FLOW_CONTROL_TIMEOUT_MS - elapsed;
        if (load_next_rx_frame(frame, remaining) != 0) {
            return -3;
        }

        uint8_t response_sequence = 0;
        factory_frame_error_code_t err = factory_frame_control_decode(frame, is_ack, &response_sequence);
        if (err == FACTORY_FRAME_ERROR_INVALID_ARGUMENT) {
            if (!has_pending_rx_frame) {
                memcpy(pending_frame, frame, FACTORY_FRAME_HEADER_SIZE + frame->size);
                has_pending_rx_frame = true;
            }
            continue;
        }
        if (err != FACTORY_FRAME_ERROR_NONE) {
            return -4;
        }
        if (response_sequence != sequence) {
            continue;
        }

        return 0;
    }

    return -5;
}

static factory_frame_fragmenter_context_t *setup_fragmenter(
    factory_packet_type_t type, uint8_t flag, const uint8_t *payload, size_t payload_size)
{
    static factory_frame_fragmenter_context_t ctx = FACTORY_FRAME_FRAGMENTER_INIT(FACTORY_PACKET_MAX_SIZE);

    const bool sessionless = is_sessionless_packet(type);
    const size_t header_size = FACTORY_PACKET_HEADER_SIZE(!sessionless);
    const size_t packet_size = header_size + payload_size;

    if (packet_size > FACTORY_PACKET_MAX_SIZE) {
        return NULL;
    }
    if (!sessionless && (!session_context.is_opened || !session_context.has_session_id)) {
        return NULL;
    }

    if (factory_frame_fragmenter_init(&ctx, packet_size) != FACTORY_FRAME_ERROR_NONE) {
        return NULL;
    }

    uint8_t *packet = ctx.packet;
    packet[0] = FACTORY_PROTOCOL_VERSION;
    packet[1] = (uint8_t)type;
    packet[2] = flag;

    if (sessionless) {
        encode_u32_be(&packet[3], (uint32_t)payload_size);
        if (payload_size > 0 && payload != NULL) {
            memcpy(&packet[FACTORY_SESSIONLESS_HEADER_SIZE], payload, payload_size);
        }
    } else {
        memcpy(&packet[3], session_context.session_id, FACTORY_SESSION_ID_SIZE);
        encode_u32_be(&packet[3 + FACTORY_SESSION_ID_SIZE], (uint32_t)payload_size);
        if (payload_size > 0 && payload != NULL) {
            memcpy(&packet[FACTORY_PACKET_HEADER_SIZE(true)], payload, payload_size);
        }
    }

    return &ctx;
}

static int send_packet(factory_frame_fragmenter_context_t *fragmenter)
{
    while (!fragmenter->has_finished && !fragmenter->has_error) {
        if (factory_frame_init(frame) != 0) {
            return -1;
        }
        if (factory_frame_fragmenter_process(fragmenter, frame) != FACTORY_FRAME_ERROR_NONE) {
            return -2;
        }

        uint8_t sequence = 0;
        if (factory_frame_get_sequence(frame, &sequence) != FACTORY_FRAME_ERROR_NONE) {
            return -3;
        }

        uint32_t retry_count = 0;
        bool sent = false;
        while (retry_count < FACTORY_PACKET_RETRY_COUNT) {
            if (write_frame(frame, FACTORY_WRITE_TIMEOUT_MS) != 0) {
                retry_count++;
                continue;
            }

            bool is_ack = false;
            if (wait_flow_control(sequence, &is_ack) != 0) {
                retry_count++;
                continue;
            }

            if (is_ack) {
                sent = true;
                break;
            }

            retry_count++;
        }

        if (!sent) {
            return -4;
        }
    }
    if (fragmenter->has_error) {
        return -5;
    }

    return 0;
}

static factory_frame_assembler_context_t *setup_assembler(void)
{
    static factory_frame_assembler_context_t ctx = FACTORY_FRAME_ASSEMBLER_INIT(FACTORY_PACKET_MAX_SIZE);

    if (factory_frame_assembler_init(&ctx) != FACTORY_FRAME_ERROR_NONE) {
        return NULL;
    }

    return &ctx;
}

static int receive_packet(factory_frame_assembler_context_t *assembler, uint8_t **packet_out, size_t *packet_size_out)
{
    if (!assembler || !packet_out || !packet_size_out) {
        return -1;
    }

    while (!assembler->has_finished && !assembler->has_error) {
        if (factory_frame_init(frame) != 0) {
            return -2;
        }

        if (load_next_rx_frame(frame, FACTORY_READ_TIMEOUT_MS) != 0) {
            return -3;
        }

        if (frame->type == FACTORY_FRAME_TYPE_ACK || frame->type == FACTORY_FRAME_TYPE_NACK) {
            continue;
        }

        uint8_t sequence = 0;
        if (factory_frame_get_sequence(frame, &sequence) != FACTORY_FRAME_ERROR_NONE) {
            return -4;
        }

        if (frame->type == FACTORY_FRAME_TYPE_CONSECUTIVE && sequence < assembler->sequence) {
            (void)send_flow_control(true, sequence);
            continue;
        }
        if (frame->type == FACTORY_FRAME_TYPE_FIRST && assembler->sequence > 0 && sequence == 0) {
            (void)send_flow_control(true, sequence);
            continue;
        }

        factory_frame_error_code_t err = factory_frame_assembler_process(assembler, frame);
        if (err != FACTORY_FRAME_ERROR_NONE) {
            (void)send_flow_control(false, sequence);
            return -6;
        }

        if (send_flow_control(true, sequence) != 0) {
            return -7;
        }
    }

    if (assembler->has_error) {
        return -8;
    }

    *packet_out = assembler->packet;
    *packet_size_out = assembler->packet_size;
    return 0;
}

static int session_send_device_hello(void)
{
    uint8_t payload[FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE] = {0};
    size_t payload_size = 0;

    if (build_device_hello_payload(payload, sizeof(payload), &payload_size) != 0) {
        return -1;
    }

    factory_frame_fragmenter_context_t *ctx = setup_fragmenter(
        FACTORY_PACKET_TYPE_DEVICE_HELLO,
        0,
        payload,
        payload_size);
    if (!ctx) {
        return -2;
    }
    return send_packet(ctx);
}

static int session_wait_pc_hello(void)
{
    uint8_t *packet = NULL;
    size_t packet_size = 0;
    factory_packet_view_t view;

    factory_frame_assembler_context_t *assembler = setup_assembler();
    if (!assembler) {
        return -1;
    }

    const uint32_t start_ms = factory_platform_get_uptime_ms();

    while (true) {
        if ((factory_platform_get_uptime_ms() - start_ms) >= FACTORY_OPEN_TIMEOUT_MS) {
            return -5;
        }

        if (receive_packet(assembler, &packet, &packet_size) != 0) {
            return -2;
        }

        if (parse_packet_view(packet, packet_size, false, &view) != 0) {
            continue;
        }

        if (view.type == FACTORY_PACKET_TYPE_PC_ALERT || view.type == FACTORY_PACKET_TYPE_DEVICE_ALERT) {
            close_session_and_notify();
            return -3;
        }

        if (view.type != FACTORY_PACKET_TYPE_PC_HELLO) {
            continue;
        }

        if (parse_pc_hello_payload(view.payload, view.payload_size, session_context.session_id) != 0) {
            return -4;
        }

        session_context.has_session_id = true;
        return 0;
    }
}

int factory_session_init(factory_session_event_handler_t event_handler)
{
    session_context.event_handler = event_handler;
    clear_session_state(false);

    return 0;
}

int factory_session_open(bool require_auth)
{
    if (session_context.is_opened) {
        return 0;
    }

    clear_session_state(true);
    session_context.require_auth = require_auth;

    if (session_send_device_hello() != 0) {
        clear_session_state(false);
        session_context.is_error = true;
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -1;
    }

    if (session_wait_pc_hello() != 0) {
        clear_session_state(false);
        session_context.is_error = true;
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -2;
    }

    session_context.is_opened = true;
    session_context.is_error = false;

    if (session_context.event_handler) {
        session_context.event_handler(FACTORY_SESSION_EVENT_OPENED);
    }
    return 0;
}

void factory_session_close(void)
{
    if (!session_context.is_opened && !session_context.has_session_id) {
        clear_session_state(false);
        return;
    }

    factory_frame_fragmenter_context_t *ctx = setup_fragmenter(FACTORY_PACKET_TYPE_DEVICE_BYE, 0, NULL, 0);
    if (ctx) {
        (void)send_packet(ctx);
    }

    close_session_and_notify();
}

int factory_session_send(const uint8_t *data, size_t size)
{
    if ((size > 0 && data == NULL) || size > FACTORY_PACKET_MAX_SIZE) {
        return -1;
    }
    if (!session_context.is_opened) {
        return -2;
    }

    factory_frame_fragmenter_context_t *ctx = setup_fragmenter(FACTORY_PACKET_TYPE_MESSAGE, 0, data, size);
    if (!ctx) {
        session_context.is_error = true;
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -3;
    }

    if (send_packet(ctx) != 0) {
        session_context.is_error = true;
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -4;
    }

    return 0;
}

int factory_session_receive(uint8_t *data, size_t *size)
{
    if (!data || !size) {
        return -1;
    }

    uint8_t *packet = NULL;
    size_t packet_size = 0;
    factory_frame_assembler_context_t *assembler = setup_assembler();
    if (!assembler) {
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -2;
    }

    int err = receive_packet(assembler, &packet, &packet_size);
    if (err != 0) {
        session_context.is_error = true;
        if (session_context.event_handler) {
            session_context.event_handler(FACTORY_SESSION_EVENT_ERROR);
        }
        return -3;
    }

    factory_packet_view_t view;
    if (parse_packet_view(packet, packet_size, true, &view) != 0) {
        return -4;
    }

    if (view.type == FACTORY_PACKET_TYPE_PC_ALERT || view.type == FACTORY_PACKET_TYPE_DEVICE_ALERT) {
        close_session_and_notify();
        return -5;
    }

    if (*size < view.payload_size) {
        return -6;
    }

    if (view.payload_size > 0) {
        memcpy(data, view.payload, view.payload_size);
    }
    *size = view.payload_size;

    if (view.type == FACTORY_PACKET_TYPE_PC_BYE || view.type == FACTORY_PACKET_TYPE_DEVICE_BYE) {
        close_session_and_notify();
    }

    return 0;
}