#include <string.h>
#include "unity.h"
#include "factory_frame.h"

// Test stub for CRC16-CCITT calculation
static uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
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

#define PACKET_BUFFER_SIZE 1024
static uint8_t assembler_packet[PACKET_BUFFER_SIZE];
static uint8_t fragmenter_packet[PACKET_BUFFER_SIZE];

static factory_frame_assembler_context_t assembler_ctx =
    FACTORY_FRAME_ASSEMBLER_INIT(assembler_packet);
static factory_frame_fragmenter_context_t fragmenter_ctx =
    FACTORY_FRAME_FRAGMENTER_INIT(fragmenter_packet);
FACTORY_FRAME_DEFINE(frame);

void setUp(void)
{
    // Reset contexts before each test
    factory_frame_assembler_init(&assembler_ctx);
    factory_frame_fragmenter_init(&fragmenter_ctx, sizeof(fragmenter_packet));
    factory_frame_init(frame);
}

void test_factory_frame_assembler_init(void)
{
    factory_frame_error_code_t err = factory_frame_assembler_init(&assembler_ctx);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_FALSE(assembler_ctx.has_finished);
    TEST_ASSERT_FALSE(assembler_ctx.has_error);
    TEST_ASSERT_EQUAL(0, assembler_ctx.sequence);
    TEST_ASSERT_EQUAL(0, assembler_ctx.total_size);
    TEST_ASSERT_EQUAL(0, assembler_ctx.packet_size);
}

void test_factory_frame_assembler_process_invalid_arguments(void)
{
    factory_frame_error_code_t err = factory_frame_assembler_process(NULL, NULL);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);

    factory_frame_t frame = {0};
    err = factory_frame_assembler_process(&assembler_ctx, NULL);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);

    err = factory_frame_assembler_process(NULL, &frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);
}

void test_factory_frame_assembler_process_invalid_magic(void)
{
    factory_frame_set_magic(frame, 0xDEADu); // Invalid magic
    frame->type = FACTORY_FRAME_TYPE_SINGLE;
    factory_frame_set_size(frame, 10u);
    factory_frame_set_crc16(frame, crc16_ccitt((uint8_t *)frame + FACTORY_FRAME_HEADER_SIZE, 10u));

    factory_frame_error_code_t err = factory_frame_assembler_process(&assembler_ctx, frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_MAGIC, err);
    TEST_ASSERT_TRUE(assembler_ctx.has_error);
    TEST_ASSERT_TRUE(assembler_ctx.has_finished);
}

void test_factory_frame_assembler_process_crc_mismatch(void)
{
    factory_frame_set_magic(frame, FACTORY_FRAME_MAGIC);
    frame->type = FACTORY_FRAME_TYPE_SINGLE;
    factory_frame_set_size(frame, 10u);
    factory_frame_set_crc16(frame, 0x1234u); // Invalid CRC

    factory_frame_error_code_t err = factory_frame_assembler_process(&assembler_ctx, frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_CRC_MISMATCH, err);
    TEST_ASSERT_TRUE(assembler_ctx.has_error);
    TEST_ASSERT_TRUE(assembler_ctx.has_finished);
}

void test_factory_frame_assembler_process_single_frame(void)
{
    const char *test_data = "Hello, Factory Frame!";
    size_t data_len = strlen(test_data) + 1; // Include null terminator

    factory_single_frame_t *single_frame = (factory_single_frame_t *)frame;
    
    factory_frame_set_magic(&single_frame->super, FACTORY_FRAME_MAGIC);
    single_frame->super.type = FACTORY_FRAME_TYPE_SINGLE;
    factory_frame_set_size(&single_frame->super, (uint16_t)data_len);
    memcpy(single_frame->data, test_data, data_len);
    factory_frame_set_crc16(&single_frame->super, crc16_ccitt(single_frame->data, data_len));

    factory_frame_error_code_t err = factory_frame_assembler_process(&assembler_ctx, frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_FALSE(assembler_ctx.has_error);
    TEST_ASSERT_TRUE(assembler_ctx.has_finished);
    TEST_ASSERT_EQUAL(data_len, assembler_ctx.packet_size);
    TEST_ASSERT_EQUAL_STRING(test_data, (char *)assembler_ctx.packet);
}

void test_factory_frame_fragmenter_init(void)
{
    factory_frame_error_code_t err = factory_frame_fragmenter_init(
        &fragmenter_ctx,
        sizeof(fragmenter_packet));
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_FALSE(fragmenter_ctx.has_finished);
    TEST_ASSERT_FALSE(fragmenter_ctx.has_error);
    TEST_ASSERT_EQUAL(0, fragmenter_ctx.sequence);
    TEST_ASSERT_EQUAL(0, fragmenter_ctx.index);
    TEST_ASSERT_EQUAL(sizeof(fragmenter_packet), fragmenter_ctx.packet_capacity);
}

void test_factory_frame_fragmenter_process_invalid_arguments(void)
{
    factory_frame_error_code_t err = factory_frame_fragmenter_process(NULL, NULL);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);

    factory_frame_t frame = {0};
    err = factory_frame_fragmenter_process(&fragmenter_ctx, NULL);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);

    err = factory_frame_fragmenter_process(NULL, &frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_INVALID_ARGUMENT, err);
}

void test_factory_frame_fragmenter_process_no_fragmentation(void)
{
    const char *test_data = "Hello, Factory Frame!";
    size_t data_len = strlen(test_data) + 1; // Include null terminator

    // Prepare packet data
    memcpy(fragmenter_ctx.packet, test_data, data_len);
    factory_frame_error_code_t err = factory_frame_fragmenter_init(&fragmenter_ctx, data_len);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_FALSE(fragmenter_ctx.need_fragmentation); // Should not need fragmentation

    err = factory_frame_fragmenter_process(&fragmenter_ctx, frame);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_FALSE(fragmenter_ctx.has_error);
    TEST_ASSERT_TRUE(fragmenter_ctx.has_finished);
    TEST_ASSERT_EQUAL(data_len, fragmenter_ctx.index); // Index should advance to data_len
}

void test_factory_frame_fragmenter_process_fragmentation(void)
{
    // This test will check the fragmentation and reassembly process
    const char *test_data = "This is a long packet that exceeds the maximum data size for a single frame,"
                            "so it needs to be fragmented. Let's see how it handles fragmentation!"
                            "I hope everyone who see this would have a good time."
                            "Although I am having a hard time writing such a long string,"
                            "I will keep going until I reach the desired length.";
    size_t data_len = strlen(test_data) + 1; // Include null terminator

    // Prepare fragmenter with test data
    memcpy(fragmenter_ctx.packet, test_data, data_len);
    factory_frame_error_code_t err = factory_frame_fragmenter_init(&fragmenter_ctx, data_len);
    TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
    TEST_ASSERT_TRUE(fragmenter_ctx.need_fragmentation); // Should need fragmentation
    
    // Reset assembler to receive fragmented frames
    factory_frame_assembler_init(&assembler_ctx);
    
    // Fragment and reassemble
    int frame_count = 0;
    while (!fragmenter_ctx.has_finished) {
        err = factory_frame_fragmenter_process(&fragmenter_ctx, frame);
        TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
        TEST_ASSERT_FALSE(fragmenter_ctx.has_error);
        
        // Feed the frame to assembler
        err = factory_frame_assembler_process(&assembler_ctx, frame);
        TEST_ASSERT_EQUAL(FACTORY_FRAME_ERROR_NONE, err);
        TEST_ASSERT_FALSE(assembler_ctx.has_error);
        
        frame_count++;
        
        // Reset frame for next iteration
        factory_frame_init(frame);
    }
    
    // Verify reassembly
    TEST_ASSERT_TRUE(assembler_ctx.has_finished);
    TEST_ASSERT_EQUAL(data_len, assembler_ctx.packet_size);
    TEST_ASSERT_EQUAL_STRING(test_data, (char *)assembler_ctx.packet);
    TEST_ASSERT_GREATER_THAN(1, frame_count); // Should have used multiple frames
}