#include <string.h>
#include "unity.h"
#include "factory_session.h"
#include "factory_frame.h"
#include "mock_factory_platform.h"

#define TEST_RX_BUFFER_SIZE 8192
#define TEST_TX_SEQ_LOG_SIZE 256
#define TEST_PACKET_BUFFER_SIZE FACTORY_PACKET_MAX_SIZE

static int g_event_count;
static factory_session_event_t g_last_event;
static uint32_t g_fake_time_ms;

static uint8_t g_rx_buffer[TEST_RX_BUFFER_SIZE];
static size_t g_rx_write_idx;
static size_t g_rx_read_idx;

static bool g_auto_ack_outbound_data;
static bool g_nack_once_on_seq0;
static bool g_nack_seq0_already_sent;

static int g_outbound_data_frame_count;
static int g_outbound_ack_count;
static int g_outbound_nack_count;
static uint8_t g_outbound_control_sequences[TEST_TX_SEQ_LOG_SIZE];
static size_t g_outbound_control_sequence_count;

static uint8_t g_expected_session_id[16] = {
    0x10, 0x11, 0x12, 0x13,
    0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B,
    0x1C, 0x1D, 0x1E, 0x1F,
};

typedef struct {
    factory_frame_t super;
    uint8_t data[FACTORY_FRAME_MAX_DATA_SIZE];
} test_frame_buffer_t;

static test_frame_buffer_t g_tx_frame_buffer;

static void on_session_event(factory_session_event_t event)
{
    g_event_count++;
    g_last_event = event;
}

static uint32_t cb_get_uptime_ms(int num_calls)
{
    (void)num_calls;
    return g_fake_time_ms;
}

static void cb_sleep(uint32_t milliseconds, int num_calls)
{
    (void)num_calls;
    g_fake_time_ms += milliseconds;
}

static void append_rx_bytes(const uint8_t *data, size_t size)
{
    TEST_ASSERT_LESS_OR_EQUAL_size_t(TEST_RX_BUFFER_SIZE, g_rx_write_idx + size);
    memcpy(&g_rx_buffer[g_rx_write_idx], data, size);
    g_rx_write_idx += size;
}

static void append_control_frame_to_rx(bool is_ack, uint8_t sequence)
{
    factory_control_frame_t ctrl;
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, factory_frame_control_encode((factory_frame_t *)&ctrl, is_ack, sequence));
    append_rx_bytes((const uint8_t *)&ctrl, sizeof(ctrl));
}

static void append_packet_frames_to_rx(const uint8_t *packet, size_t packet_size, bool duplicate_seq1)
{
    static factory_frame_fragmenter_context_t fragmenter = FACTORY_FRAME_FRAGMENTER_INIT(TEST_PACKET_BUFFER_SIZE);
    factory_frame_t *tx_frame = (factory_frame_t *)&g_tx_frame_buffer;

    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, factory_frame_fragmenter_init(&fragmenter, packet_size));
    memcpy(fragmenter.packet, packet, packet_size);

    while (!fragmenter.has_finished) {
        TEST_ASSERT_EQUAL(0, factory_frame_init(tx_frame));
        TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, factory_frame_fragmenter_process(&fragmenter, tx_frame));

        size_t frame_size = FACTORY_FRAME_HEADER_SIZE + tx_frame->size;
        append_rx_bytes((const uint8_t *)tx_frame, frame_size);

        if (duplicate_seq1) {
            uint8_t sequence = 0;
            TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, factory_frame_get_sequence(tx_frame, &sequence));
            if (tx_frame->type == FACTORY_FRAME_TYPE_CONSECUTIVE && sequence == 1u) {
                append_rx_bytes((const uint8_t *)tx_frame, frame_size);
            }
        }
    }
}

static void enqueue_pc_hello_packet(const uint8_t session_id[16])
{
    uint8_t payload[2 + 16] = {0};
    payload[0] = 0x01; // payload version
    payload[1] = sizeof(payload);
    memcpy(&payload[2], session_id, 16);

    uint8_t packet[7 + sizeof(payload)] = {0};
    packet[0] = 0x01; // protocol version
    packet[1] = 0x10; // PC_HELLO
    packet[2] = 0x00; // flag
    encode_u32_be(&packet[3], sizeof(payload));
    memcpy(&packet[7], payload, sizeof(payload));

    append_packet_frames_to_rx(packet, sizeof(packet), false);
}

static void enqueue_pc_alert_packet(void)
{
    uint8_t packet[7] = {0};
    packet[0] = 0x01; // protocol version
    packet[1] = 0x12; // PC_ALERT
    packet[2] = 0x00; // flag
    encode_u32_be(&packet[3], 0u);

    append_packet_frames_to_rx(packet, sizeof(packet), false);
}

static void enqueue_session_message_packet(const uint8_t session_id[16], const uint8_t *payload, size_t payload_size, bool duplicate_seq1)
{
    uint8_t packet[3 + 16 + 4 + 256] = {0};
    size_t packet_size = 3 + 16 + 4 + payload_size;

    TEST_ASSERT_LESS_OR_EQUAL_size_t(sizeof(packet), packet_size);

    packet[0] = 0x01; // protocol version
    packet[1] = 0x01; // MESSAGE
    packet[2] = 0x00; // flag
    memcpy(&packet[3], session_id, 16);
    encode_u32_be(&packet[19], (uint32_t)payload_size);
    memcpy(&packet[23], payload, payload_size);

    append_packet_frames_to_rx(packet, packet_size, duplicate_seq1);
}

static ssize_t cb_uart_read(uint8_t *buffer, size_t size, int num_calls)
{
    (void)num_calls;
    if (g_rx_read_idx >= g_rx_write_idx) {
        return 0;
    }

    size_t available = g_rx_write_idx - g_rx_read_idx;
    size_t chunk = (size < available) ? size : available;
    memcpy(buffer, &g_rx_buffer[g_rx_read_idx], chunk);
    g_rx_read_idx += chunk;
    return (ssize_t)chunk;
}

static ssize_t cb_uart_write(const uint8_t *buffer, size_t size, int num_calls)
{
    (void)num_calls;

    TEST_ASSERT_GREATER_THAN_size_t(FACTORY_FRAME_HEADER_SIZE, size);

    const factory_frame_t *out = (const factory_frame_t *)buffer;
    uint8_t sequence = 0;
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, factory_frame_get_sequence(out, &sequence));

    if (out->type == FACTORY_FRAME_TYPE_ACK) {
        g_outbound_ack_count++;
        if (g_outbound_control_sequence_count < TEST_TX_SEQ_LOG_SIZE) {
            g_outbound_control_sequences[g_outbound_control_sequence_count++] = sequence;
        }
    } else if (out->type == FACTORY_FRAME_TYPE_NACK) {
        g_outbound_nack_count++;
        if (g_outbound_control_sequence_count < TEST_TX_SEQ_LOG_SIZE) {
            g_outbound_control_sequences[g_outbound_control_sequence_count++] = sequence;
        }
    } else {
        g_outbound_data_frame_count++;

        if (g_auto_ack_outbound_data) {
            if (g_nack_once_on_seq0 && sequence == 0u && !g_nack_seq0_already_sent) {
                append_control_frame_to_rx(false, sequence);
                g_nack_seq0_already_sent = true;
            } else {
                append_control_frame_to_rx(true, sequence);
            }
        }
    }

    return (ssize_t)size;
}

static void install_platform_stubs(void)
{
    factory_platform_get_uptime_ms_StubWithCallback(cb_get_uptime_ms);
    factory_platform_sleep_StubWithCallback(cb_sleep);
    factory_platform_uart_read_StubWithCallback(cb_uart_read);
    factory_platform_uart_write_StubWithCallback(cb_uart_write);
    factory_platform_get_uuid_IgnoreAndReturn(0x1122334455667788ULL);
}

static void open_session_successfully(void)
{
    enqueue_pc_hello_packet(g_expected_session_id);
    int err = factory_session_open(false);
    TEST_ASSERT_EQUAL(0, err);
    TEST_ASSERT_EQUAL(1, g_event_count);
    TEST_ASSERT_EQUAL(FACTORY_SESSION_EVENT_OPENED, g_last_event);
}

static size_t expected_fragment_count_for_packet_size(size_t packet_size)
{
    if (packet_size <= FACTORY_FRAME_MAX_DATA_SIZE) {
        return 1;
    }

    size_t first_data_size = FACTORY_FRAME_MAX_DATA_SIZE - sizeof(uint32_t) - sizeof(uint8_t);
    size_t consecutive_data_size = FACTORY_FRAME_MAX_DATA_SIZE - sizeof(uint8_t);
    size_t remaining = packet_size - first_data_size;
    size_t consecutive_count = (remaining + consecutive_data_size - 1u) / consecutive_data_size;
    return 1u + consecutive_count;
}

void setUp(void)
{
    g_event_count = 0;
    g_last_event = FACTORY_SESSION_EVENT_CLOSED;
    g_fake_time_ms = 0;

    g_rx_write_idx = 0;
    g_rx_read_idx = 0;
    memset(g_rx_buffer, 0, sizeof(g_rx_buffer));

    g_auto_ack_outbound_data = true;
    g_nack_once_on_seq0 = false;
    g_nack_seq0_already_sent = false;

    g_outbound_data_frame_count = 0;
    g_outbound_ack_count = 0;
    g_outbound_nack_count = 0;
    g_outbound_control_sequence_count = 0;
    memset(g_outbound_control_sequences, 0, sizeof(g_outbound_control_sequences));

    install_platform_stubs();
    TEST_ASSERT_EQUAL(0, factory_session_init(on_session_event));
}

void tearDown(void)
{
}

void test_factory_session_init_allows_null_handler(void)
{
    int err = factory_session_init(NULL);
    TEST_ASSERT_EQUAL(0, err);
}

void test_factory_session_open_times_out_after_fixed_5s_when_pc_hello_missing(void)
{
    int err = factory_session_open(true);

    TEST_ASSERT_EQUAL(-2, err);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT32(FACTORY_OPEN_TIMEOUT_MS, g_fake_time_ms);
    TEST_ASSERT_EQUAL(1, g_event_count);
    TEST_ASSERT_EQUAL(FACTORY_SESSION_EVENT_ERROR, g_last_event);
}

void test_factory_session_send_fragment_retries_once_on_nack_then_succeeds(void)
{
    open_session_successfully();

    g_event_count = 0;
    g_outbound_data_frame_count = 0;
    g_outbound_ack_count = 0;
    g_outbound_nack_count = 0;
    g_nack_once_on_seq0 = true;

    uint8_t payload[700];
    for (size_t i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(i & 0xFFu);
    }

    int err = factory_session_send(payload, sizeof(payload));
    TEST_ASSERT_EQUAL(0, err);
    TEST_ASSERT_EQUAL(0, g_event_count);
    TEST_ASSERT_TRUE(g_nack_seq0_already_sent);

    size_t packet_size = 3u + 16u + 4u + sizeof(payload);
    size_t expected_frames = expected_fragment_count_for_packet_size(packet_size);
    TEST_ASSERT_EQUAL((int)(expected_frames + 1u), g_outbound_data_frame_count);
}

void test_factory_session_receive_fragment_with_duplicate_sequence_sends_ack_and_ignores_duplicate(void)
{
    open_session_successfully();

    g_event_count = 0;
    g_outbound_data_frame_count = 0;
    g_outbound_ack_count = 0;
    g_outbound_nack_count = 0;
    g_outbound_control_sequence_count = 0;

    uint8_t rx_payload[140];
    for (size_t i = 0; i < sizeof(rx_payload); i++) {
        rx_payload[i] = (uint8_t)(0xA0u + (i & 0x0Fu));
    }

    enqueue_session_message_packet(g_expected_session_id, rx_payload, sizeof(rx_payload), true);

    uint8_t out_payload[200] = {0};
    size_t out_size = sizeof(out_payload);
    int err = factory_session_receive(out_payload, &out_size);

    TEST_ASSERT_EQUAL(0, err);
    TEST_ASSERT_EQUAL(sizeof(rx_payload), out_size);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(rx_payload, out_payload, sizeof(rx_payload));

    // 3 fragments + duplicate seq1 => 4 ACK frames expected
    TEST_ASSERT_EQUAL(4, g_outbound_ack_count);
    TEST_ASSERT_EQUAL(0, g_outbound_nack_count);
    TEST_ASSERT_EQUAL(4, (int)g_outbound_control_sequence_count);
    TEST_ASSERT_EQUAL_UINT8(0u, g_outbound_control_sequences[0]);
    TEST_ASSERT_EQUAL_UINT8(1u, g_outbound_control_sequences[1]);
    TEST_ASSERT_EQUAL_UINT8(1u, g_outbound_control_sequences[2]);
}

void test_factory_session_receive_pc_alert_closes_session_and_notifies_closed_event(void)
{
    open_session_successfully();

    g_event_count = 0;
    g_outbound_ack_count = 0;
    g_outbound_nack_count = 0;

    enqueue_pc_alert_packet();

    uint8_t out_payload[16] = {0};
    size_t out_size = sizeof(out_payload);
    int err = factory_session_receive(out_payload, &out_size);

    TEST_ASSERT_EQUAL(-5, err);
    TEST_ASSERT_EQUAL(1, g_event_count);
    TEST_ASSERT_EQUAL(FACTORY_SESSION_EVENT_CLOSED, g_last_event);

    // Session should be closed now
    err = factory_session_send(out_payload, 1);
    TEST_ASSERT_EQUAL(-2, err);
}
