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

#define FACTORY_PC_HELLO_PAYLOAD_VERSION         (0x01u)
#define FACTORY_DEVICE_HELLO_UUID_MAX_SIZE       (0xFFu)
#define FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE    (1u + 1u) /* UUID_SIZE + AUTH_REQUIRED */
#define FACTORY_DEVICE_HELLO_PAYLOAD_MAX_SIZE    (1u + FACTORY_DEVICE_HELLO_UUID_MAX_SIZE + 1u)
#define FACTORY_PC_HELLO_PAYLOAD_MIN_SIZE        (2u + FACTORY_SESSION_ID_SIZE)

#define FACTORY_UART_MAX_RETRIES                 (3u)
#define FACTORY_UART_RETRY_DELAY_MS              (100u)
#define FACTORY_UART_POLL_DELAY_MS               (3u)
#define FACTORY_READ_TIMEOUT_MS                  (1000u)
#define FACTORY_WRITE_TIMEOUT_MS                 (1000u)
#define FACTORY_FLOW_CONTROL_TIMEOUT_MS          (500u)

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

typedef struct {
    factory_packet_type_t type;
    uint8_t flag;
    const uint8_t *payload;
    size_t payload_size;
    bool sessionless;
} factory_packet_view_t;

static const factory_packet_type_t sessionless_packets[] = {
    FACTORY_PACKET_TYPE_PC_HELLO,
    FACTORY_PACKET_TYPE_PC_ALERT,
    FACTORY_PACKET_TYPE_DEVICE_HELLO,
    FACTORY_PACKET_TYPE_DEVICE_ALERT,
    FACTORY_PACKET_TYPE_DEVICE_CHALLENGE,
};

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

static uint8_t tx_packet_buffer[FACTORY_PACKET_MAX_SIZE];
static uint8_t rx_packet_buffer[FACTORY_PACKET_MAX_SIZE];

static factory_frame_fragmenter_context_t tx_fragmenter =
    FACTORY_FRAME_FRAGMENTER_INIT(tx_packet_buffer);

static factory_frame_assembler_context_t rx_assembler =
    FACTORY_FRAME_ASSEMBLER_INIT(rx_packet_buffer);

static bool is_sessionless_packet(factory_packet_type_t type)
{
    for (size_t i = 0; i < sizeof(sessionless_packets) / sizeof(sessionless_packets[0]); i++) {
        if (sessionless_packets[i] == type) {
            return true;
        }
    }

    return false;
}

static bool is_alert_packet(factory_packet_type_t type)
{
    return (type == FACTORY_PACKET_TYPE_PC_ALERT) ||
           (type == FACTORY_PACKET_TYPE_DEVICE_ALERT);
}

static bool is_bye_packet(factory_packet_type_t type)
{
    return (type == FACTORY_PACKET_TYPE_PC_BYE) ||
           (type == FACTORY_PACKET_TYPE_DEVICE_BYE);
}

static size_t frame_encoded_size(const factory_frame_t *frame_ptr)
{
    return FACTORY_FRAME_HEADER_SIZE + (size_t)factory_frame_get_size(frame_ptr);
}

static void frame_copy(factory_frame_t *dst, const factory_frame_t *src)
{
    memcpy(dst, src, frame_encoded_size(src));
}

static void notify_event(factory_session_event_t event)
{
    if (session_context.event_handler) {
        session_context.event_handler(event);
    }
}

static void set_session_error(void)
{
    session_context.is_error = true;
    notify_event(FACTORY_SESSION_EVENT_ERROR);
}

static void clear_session_state(bool keep_auth_flag)
{
    const bool require_auth = session_context.require_auth;

    session_context.is_opened = false;
    session_context.is_error = false;
    session_context.has_session_id = false;
    memset(session_context.session_id, 0, sizeof(session_context.session_id));
    session_context.require_auth = keep_auth_flag ? require_auth : false;

    has_pending_rx_frame = false;
}

static void close_session_and_notify(void)
{
    const bool had_session = session_context.is_opened || session_context.has_session_id;

    clear_session_state(false);

    if (had_session) {
        notify_event(FACTORY_SESSION_EVENT_CLOSED);
    }
}

static int read_exact_until_deadline(uint8_t *buffer, size_t size, uint32_t deadline_ms)
{
    if (!buffer && size > 0u) {
        return -1;
    }

    size_t total_reads = 0u;
    uint32_t negative_read_count = 0u;

    while (total_reads < size) {
        if (factory_platform_get_uptime_ms() >= deadline_ms) {
            return -2;
        }

        ssize_t num_reads = factory_platform_uart_read(buffer + total_reads, size - total_reads);
        if (num_reads < 0) {
            negative_read_count++;
            if (negative_read_count >= FACTORY_UART_MAX_RETRIES) {
                return -3;
            }

            factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
            continue;
        }

        if (num_reads == 0) {
            factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
            continue;
        }

        total_reads += (size_t)num_reads;
        negative_read_count = 0u;
    }

    return 0;
}

static int write_exact_until_deadline(const uint8_t *buffer, size_t size, uint32_t deadline_ms)
{
    if (!buffer && size > 0u) {
        return -1;
    }

    size_t total_written = 0u;
    uint32_t negative_write_count = 0u;

    while (total_written < size) {
        if (factory_platform_get_uptime_ms() >= deadline_ms) {
            return -2;
        }

        ssize_t num_written = factory_platform_uart_write(buffer + total_written, size - total_written);
        if (num_written < 0) {
            negative_write_count++;
            if (negative_write_count >= FACTORY_UART_MAX_RETRIES) {
                return -3;
            }

            factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
            continue;
        }

        if (num_written == 0) {
            factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
            continue;
        }

        total_written += (size_t)num_written;
        negative_write_count = 0u;
    }

    return 0;
}

static int read_frame(factory_frame_t *out_frame, uint32_t timeout_ms)
{
    if (!out_frame) {
        return -1;
    }

    const uint32_t start_ms = factory_platform_get_uptime_ms();
    const uint32_t deadline_ms = start_ms + timeout_ms;

    uint8_t magic_window[2] = {0u, 0u};
    uint32_t negative_read_count = 0u;

    while (true) {
        if (factory_platform_get_uptime_ms() >= deadline_ms) {
            return -2;
        }

        magic_window[0] = magic_window[1];

        ssize_t num_reads = factory_platform_uart_read(&magic_window[1], 1u);
        if (num_reads < 0) {
            negative_read_count++;
            if (negative_read_count >= FACTORY_UART_MAX_RETRIES) {
                return -3;
            }

            factory_platform_sleep(FACTORY_UART_RETRY_DELAY_MS);
            continue;
        }

        if (num_reads == 0) {
            factory_platform_sleep(FACTORY_UART_POLL_DELAY_MS);
            continue;
        }

        negative_read_count = 0u;

        if (decode_u16_be(magic_window) == FACTORY_FRAME_MAGIC) {
            break;
        }
    }

    out_frame->magic[0] = magic_window[0];
    out_frame->magic[1] = magic_window[1];

    if (read_exact_until_deadline(
            ((uint8_t *)out_frame) + 2u,
            FACTORY_FRAME_HEADER_SIZE - 2u,
            deadline_ms) != 0) {
        return -4;
    }

    if (factory_frame_get_size(out_frame) > FACTORY_FRAME_MAX_DATA_SIZE) {
        return -5;
    }

    if (read_exact_until_deadline(
            ((uint8_t *)out_frame) + FACTORY_FRAME_HEADER_SIZE,
            factory_frame_get_size(out_frame),
            deadline_ms) != 0) {
        return -6;
    }

    return 0;
}

static int load_next_rx_frame(factory_frame_t *out_frame, uint32_t timeout_ms)
{
    if (!out_frame) {
        return -1;
    }

    if (has_pending_rx_frame) {
        frame_copy(out_frame, pending_frame);
        has_pending_rx_frame = false;
        return 0;
    }

    return read_frame(out_frame, timeout_ms);
}

static int write_frame(const factory_frame_t *frame_ptr, uint32_t timeout_ms)
{
    if (!frame_ptr) {
        return -1;
    }

    if (factory_frame_get_size(frame_ptr) > FACTORY_FRAME_MAX_DATA_SIZE) {
        return -2;
    }

    const uint32_t deadline_ms = factory_platform_get_uptime_ms() + timeout_ms;
    return write_exact_until_deadline((const uint8_t *)frame_ptr, frame_encoded_size(frame_ptr), deadline_ms);
}

static int send_flow_control(bool is_ack, uint8_t sequence)
{
    if (factory_frame_init(frame) != FACTORY_FRAME_ERROR_NONE) {
        return -1;
    }

    if (factory_frame_control_encode(frame, is_ack, sequence) != FACTORY_FRAME_ERROR_NONE) {
        return -2;
    }

    return write_frame(frame, FACTORY_WRITE_TIMEOUT_MS);
}

static int wait_flow_control(uint8_t sequence, bool *is_ack)
{
    if (!is_ack) {
        return -1;
    }

    const uint32_t start_ms = factory_platform_get_uptime_ms();

    while ((factory_platform_get_uptime_ms() - start_ms) < FACTORY_FLOW_CONTROL_TIMEOUT_MS) {
        if (factory_frame_init(frame) != FACTORY_FRAME_ERROR_NONE) {
            return -2;
        }

        const uint32_t elapsed = factory_platform_get_uptime_ms() - start_ms;
        const uint32_t remaining = FACTORY_FLOW_CONTROL_TIMEOUT_MS - elapsed;

        int load_result;
        if (has_pending_rx_frame) {
            load_result = read_frame(frame, remaining);
        } else {
            load_result = load_next_rx_frame(frame, remaining);
        }

        if (load_result != 0) {
            return -3;
        }

        uint8_t response_sequence = 0u;
        factory_frame_error_code_t err = factory_frame_control_decode(frame, is_ack, &response_sequence);

        if (err == FACTORY_FRAME_ERROR_INVALID_ARGUMENT) {
            if (!has_pending_rx_frame) {
                frame_copy(pending_frame, frame);
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

    const factory_packet_type_t type = (factory_packet_type_t)packet[1];
    const bool sessionless = is_sessionless_packet(type);
    const size_t header_size = sessionless ? FACTORY_SESSIONLESS_HEADER_SIZE : FACTORY_SESSION_HEADER_SIZE;
    const uint8_t *size_ptr = sessionless ? &packet[3] : &packet[3 + FACTORY_SESSION_ID_SIZE];

    if (packet_size < header_size) {
        return -4;
    }

    if (!sessionless && require_session_match) {
        if (!session_context.is_opened || !session_context.has_session_id) {
            return -5;
        }

        if (memcmp(&packet[3], session_context.session_id, FACTORY_SESSION_ID_SIZE) != 0) {
            return -6;
        }
    }

    const size_t payload_size = (size_t)decode_u32_be(size_ptr);
    if (header_size + payload_size != packet_size) {
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
    size_t uuid_size;

    if (!payload || !payload_size) {
        return -1;
    }
    if (payload_capacity < FACTORY_DEVICE_HELLO_PAYLOAD_MIN_SIZE) {
        return -2;
    }

    uuid_size = payload_capacity - 2u;
    if (uuid_size > FACTORY_DEVICE_HELLO_UUID_MAX_SIZE) {
        uuid_size = FACTORY_DEVICE_HELLO_UUID_MAX_SIZE;
    }

    if (factory_platform_get_uuid(&payload[1], &uuid_size) != 0) {
        return -3;
    }
    if (uuid_size == 0u || uuid_size > FACTORY_DEVICE_HELLO_UUID_MAX_SIZE) {
        return -4;
    }

    payload[0] = (uint8_t)uuid_size;
    payload[1u + uuid_size] = session_context.require_auth ? 1u : 0u;

    *payload_size = 1u + uuid_size + 1u;
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

    const uint8_t declared_size = payload[1];
    if (declared_size < FACTORY_PC_HELLO_PAYLOAD_MIN_SIZE || declared_size > payload_size) {
        return -3;
    }

    memcpy(session_id_out, &payload[2], FACTORY_SESSION_ID_SIZE);
    return 0;
}

static int build_packet(
    factory_packet_type_t type,
    uint8_t flag,
    const uint8_t *payload,
    size_t payload_size,
    uint8_t *packet_out,
    size_t packet_capacity,
    size_t *packet_size_out)
{
    if ((!payload && payload_size > 0u) || !packet_out || !packet_size_out) {
        return -1;
    }

    const bool sessionless = is_sessionless_packet(type);
    const bool has_session = !sessionless;
    const size_t header_size = FACTORY_PACKET_HEADER_SIZE(has_session);
    const size_t packet_size = header_size + payload_size;

    if (packet_size > packet_capacity) {
        return -2;
    }

    if (has_session && (!session_context.is_opened || !session_context.has_session_id)) {
        return -3;
    }

    packet_out[0] = FACTORY_PROTOCOL_VERSION;
    packet_out[1] = (uint8_t)type;
    packet_out[2] = flag;

    if (sessionless) {
        encode_u32_be(&packet_out[3], (uint32_t)payload_size);
        if (payload_size > 0u) {
            memcpy(&packet_out[FACTORY_SESSIONLESS_HEADER_SIZE], payload, payload_size);
        }
    } else {
        memcpy(&packet_out[3], session_context.session_id, FACTORY_SESSION_ID_SIZE);
        encode_u32_be(&packet_out[3 + FACTORY_SESSION_ID_SIZE], (uint32_t)payload_size);
        if (payload_size > 0u) {
            memcpy(&packet_out[FACTORY_SESSION_HEADER_SIZE], payload, payload_size);
        }
    }

    *packet_size_out = packet_size;
    return 0;
}

static int prepare_tx_fragmenter(
    factory_packet_type_t type,
    uint8_t flag,
    const uint8_t *payload,
    size_t payload_size)
{
    size_t packet_size = 0u;

    if (build_packet(type,
                     flag,
                     payload,
                     payload_size,
                     tx_packet_buffer,
                     sizeof(tx_packet_buffer),
                     &packet_size) != 0) {
        return -1;
    }

    if (factory_frame_fragmenter_init(&tx_fragmenter, packet_size) != FACTORY_FRAME_ERROR_NONE) {
        return -2;
    }

    return 0;
}

static int prepare_rx_assembler(void)
{
    return (factory_frame_assembler_init(&rx_assembler) == FACTORY_FRAME_ERROR_NONE) ? 0 : -1;
}

static int send_current_packet(void)
{
    while (!tx_fragmenter.has_finished && !tx_fragmenter.has_error) {
        if (factory_frame_init(frame) != FACTORY_FRAME_ERROR_NONE) {
            return -1;
        }

        if (factory_frame_fragmenter_process(&tx_fragmenter, frame) != FACTORY_FRAME_ERROR_NONE) {
            return -2;
        }

        uint8_t sequence = 0u;
        if (factory_frame_get_sequence(frame, &sequence) != FACTORY_FRAME_ERROR_NONE) {
            return -3;
        }

        uint32_t retry_count = 0u;
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

    return tx_fragmenter.has_error ? -5 : 0;
}

static int receive_one_packet(uint8_t **packet_out, size_t *packet_size_out)
{
    if (!packet_out || !packet_size_out) {
        return -1;
    }

    if (prepare_rx_assembler() != 0) {
        return -2;
    }

    while (!rx_assembler.has_finished && !rx_assembler.has_error) {
        if (factory_frame_init(frame) != FACTORY_FRAME_ERROR_NONE) {
            return -3;
        }

        if (load_next_rx_frame(frame, FACTORY_READ_TIMEOUT_MS) != 0) {
            return -4;
        }

        if (frame->type == FACTORY_FRAME_TYPE_ACK || frame->type == FACTORY_FRAME_TYPE_NACK) {
            continue;
        }

        uint8_t sequence = 0u;
        if (factory_frame_get_sequence(frame, &sequence) != FACTORY_FRAME_ERROR_NONE) {
            return -5;
        }

        if (frame->type == FACTORY_FRAME_TYPE_CONSECUTIVE && sequence < rx_assembler.sequence) {
            (void)send_flow_control(true, sequence);
            continue;
        }

        if (frame->type == FACTORY_FRAME_TYPE_FIRST && rx_assembler.sequence > 0u && sequence == 0u) {
            (void)send_flow_control(true, sequence);
            continue;
        }

        factory_frame_error_code_t err = factory_frame_assembler_process(&rx_assembler, frame);
        if (err != FACTORY_FRAME_ERROR_NONE) {
            (void)send_flow_control(false, sequence);
            return -6;
        }

        if (send_flow_control(true, sequence) != 0) {
            return -7;
        }
    }

    if (rx_assembler.has_error) {
        return -8;
    }

    *packet_out = rx_assembler.packet;
    *packet_size_out = rx_assembler.packet_size;
    return 0;
}

static int send_packet(
    factory_packet_type_t type,
    uint8_t flag,
    const uint8_t *payload,
    size_t payload_size)
{
    if (prepare_tx_fragmenter(type, flag, payload, payload_size) != 0) {
        return -1;
    }

    return send_current_packet();
}

static int session_send_device_hello(void)
{
    uint8_t payload[FACTORY_DEVICE_HELLO_PAYLOAD_MAX_SIZE] = {0u};
    size_t payload_size = 0u;

    if (build_device_hello_payload(payload, sizeof(payload), &payload_size) != 0) {
        return -1;
    }

    return send_packet(FACTORY_PACKET_TYPE_DEVICE_HELLO, 0u, payload, payload_size);
}

static int session_wait_pc_hello(void)
{
    const uint32_t start_ms = factory_platform_get_uptime_ms();

    while ((factory_platform_get_uptime_ms() - start_ms) < FACTORY_OPEN_TIMEOUT_MS) {
        uint8_t *packet = NULL;
        size_t packet_size = 0u;
        factory_packet_view_t view;

        int receive_result = receive_one_packet(&packet, &packet_size);
        if (receive_result != 0) {
            if (receive_result == -4) {
                continue;
            }
            return -1;
        }

        if (parse_packet_view(packet, packet_size, false, &view) != 0) {
            continue;
        }

        if (is_alert_packet(view.type)) {
            close_session_and_notify();
            return -2;
        }

        if (view.type != FACTORY_PACKET_TYPE_PC_HELLO) {
            continue;
        }

        if (parse_pc_hello_payload(view.payload, view.payload_size, session_context.session_id) != 0) {
            return -3;
        }

        session_context.has_session_id = true;
        return 0;
    }

    return -4;
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
        set_session_error();
        return -1;
    }

    if (session_wait_pc_hello() != 0) {
        clear_session_state(false);
        set_session_error();
        return -2;
    }

    session_context.is_opened = true;
    session_context.is_error = false;
    notify_event(FACTORY_SESSION_EVENT_OPENED);

    return 0;
}

void factory_session_close(void)
{
    if (!session_context.is_opened && !session_context.has_session_id) {
        clear_session_state(false);
        return;
    }

    (void)send_packet(FACTORY_PACKET_TYPE_DEVICE_BYE, 0u, NULL, 0u);
    close_session_and_notify();
}

int factory_session_send(const uint8_t *data, size_t size)
{
    if (!session_context.is_opened) {
        return -2;
    }
    if (!data && size > 0u) {
        return -1;
    }

    if (send_packet(FACTORY_PACKET_TYPE_MESSAGE, 0u, data, size) != 0) {
        set_session_error();
        return -3;
    }

    return 0;
}

int factory_session_receive(uint8_t *data, size_t *size)
{
    if (!data || !size) {
        return -1;
    }
    if (!session_context.is_opened) {
        return -2;
    }

    uint8_t *packet = NULL;
    size_t packet_size = 0u;

    if (receive_one_packet(&packet, &packet_size) != 0) {
        set_session_error();
        return -3;
    }

    factory_packet_view_t view;
    if (parse_packet_view(packet, packet_size, true, &view) != 0) {
        return -4;
    }

    if (is_alert_packet(view.type)) {
        close_session_and_notify();
        return -5;
    }

    if (is_bye_packet(view.type)) {
        close_session_and_notify();
        *size = 0u;
        return 0;
    }

    if (*size < view.payload_size) {
        return -6;
    }

    if (view.payload_size > 0u) {
        memcpy(data, view.payload, view.payload_size);
    }
    *size = view.payload_size;

    return 0;
}