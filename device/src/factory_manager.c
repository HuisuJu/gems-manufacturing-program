#include "factory_manager.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <pb_decode.h>
#include <pb_encode.h>

#include "factory_command.pb.h"
#include "factory_data.pb.h"
#include "factory_transaction.pb.h"
#include "factory_data.h"
#include "factory_session.h"

#ifndef FACTORY_MANAGER_RX_BUFFER_SIZE
#define FACTORY_MANAGER_RX_BUFFER_SIZE FACTORY_PACKET_MAX_SIZE
#endif

#ifndef FACTORY_MANAGER_TX_BUFFER_SIZE
#define FACTORY_MANAGER_TX_BUFFER_SIZE FACTORY_PACKET_MAX_SIZE
#endif

#ifndef FACTORY_MANAGER_MAX_READ_ITEMS
#define FACTORY_MANAGER_MAX_READ_ITEMS 32u
#endif

#ifndef FACTORY_MANAGER_MAX_STRING_SIZE
#define FACTORY_MANAGER_MAX_STRING_SIZE 256u
#endif

#ifndef FACTORY_MANAGER_MAX_BYTES_SIZE
#define FACTORY_MANAGER_MAX_BYTES_SIZE 2048u
#endif

typedef struct
{
    bool present;
    uint8_t * buffer;
    size_t capacity;
    size_t size;
} factory_field_buffer_t;

typedef struct
{
    factory_field_buffer_t serial_number;
    factory_field_buffer_t manufactured_date;
    bool has_vendor_id;
    uint32_t vendor_id;
    bool has_product_id;
    uint32_t product_id;
    factory_field_buffer_t dac_cert;
    factory_field_buffer_t dac_public_key;
    factory_field_buffer_t dac_private_key;
    factory_field_buffer_t pai_cert;
    factory_field_buffer_t certification_declaration;
    factory_field_buffer_t onboarding_payload;
    bool has_spake2p_passcode;
    uint32_t spake2p_passcode;
    factory_field_buffer_t spake2p_salt;
    bool has_spake2p_iteration_count;
    uint32_t spake2p_iteration_count;
    factory_field_buffer_t spake2p_verifier;
} factory_write_data_t;

typedef struct
{
    factory_data_FactoryDataItem items[FACTORY_MANAGER_MAX_READ_ITEMS];
    size_t count;
} factory_read_items_t;

typedef struct
{
    const factory_data_FactoryDataItem * items;
    size_t count;
} factory_enum_list_encode_ctx_t;

typedef struct
{
    const uint8_t * data;
    size_t size;
} factory_bytes_encode_ctx_t;

typedef struct
{
    bool present;
    uint8_t data[FACTORY_MANAGER_MAX_STRING_SIZE];
    size_t size;
} factory_string_value_t;

typedef struct
{
    bool present;
    uint8_t data[FACTORY_MANAGER_MAX_BYTES_SIZE];
    size_t size;
} factory_bytes_value_t;

typedef struct
{
    factory_string_value_t serial_number;
    factory_string_value_t manufactured_date;
    bool has_vendor_id;
    uint32_t vendor_id;
    bool has_product_id;
    uint32_t product_id;
    factory_bytes_value_t dac_cert;
    factory_bytes_value_t dac_public_key;
    factory_bytes_value_t dac_private_key;
    factory_bytes_value_t pai_cert;
    factory_bytes_value_t certification_declaration;
    factory_bytes_value_t onboarding_payload;
    bool has_spake2p_passcode;
    uint32_t spake2p_passcode;
    factory_bytes_value_t spake2p_salt;
    bool has_spake2p_iteration_count;
    uint32_t spake2p_iteration_count;
    factory_bytes_value_t spake2p_verifier;
} factory_read_response_data_t;

static factory_transaction_FactoryStatusCode
factory_status_invalid_transaction(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_INVALID_TRANSACTION;
}

static factory_transaction_FactoryStatusCode
factory_status_invalid_argument(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_INVALID_ARGUMENT;
}

static factory_transaction_FactoryStatusCode
factory_status_invalid_item(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_INVALID_ITEM;
}

static factory_transaction_FactoryStatusCode
factory_status_invalid_data(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_INVALID_DATA;
}

static factory_transaction_FactoryStatusCode
factory_status_internal_error(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_INTERNAL_ERROR;
}

static factory_transaction_FactoryStatusCode
factory_status_unsupported(void)
{
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_UNSUPPORTED;
}

static void factory_manager_session_event_handler(factory_session_event_t event)
{
    (void) event;
}

static void factory_field_buffer_init(
    factory_field_buffer_t * field,
    uint8_t * buffer,
    size_t capacity)
{
    field->present = false;
    field->buffer = buffer;
    field->capacity = capacity;
    field->size = 0;
}

static bool factory_decode_bytes_field(
    pb_istream_t * stream,
    const pb_field_t * field,
    void ** arg)
{
    (void) field;

    if ((stream == NULL) || (arg == NULL) || (*arg == NULL))
    {
        return false;
    }

    factory_field_buffer_t * dst = (factory_field_buffer_t *) *arg;

    if (stream->bytes_left > dst->capacity)
    {
        return false;
    }

    dst->present = true;
    dst->size = (size_t) stream->bytes_left;

    if (dst->size == 0u)
    {
        return true;
    }

    return pb_read(stream, dst->buffer, stream->bytes_left);
}

static bool factory_decode_read_items(
    pb_istream_t * stream,
    const pb_field_t * field,
    void ** arg)
{
    (void) field;

    if ((stream == NULL) || (arg == NULL) || (*arg == NULL))
    {
        return false;
    }

    factory_read_items_t * list = (factory_read_items_t *) *arg;
    uint64_t value = 0;

    if (!pb_decode_varint(stream, &value))
    {
        return false;
    }

    if (list->count >= FACTORY_MANAGER_MAX_READ_ITEMS)
    {
        return false;
    }

    list->items[list->count++] = (factory_data_FactoryDataItem) value;
    return true;
}

static bool factory_encode_enum_list(
    pb_ostream_t * stream,
    const pb_field_t * field,
    void * const * arg)
{
    if ((stream == NULL) || (field == NULL) || (arg == NULL) || (*arg == NULL))
    {
        return false;
    }

    const factory_enum_list_encode_ctx_t * ctx =
        (const factory_enum_list_encode_ctx_t *) *arg;

    for (size_t i = 0; i < ctx->count; ++i)
    {
        if (!pb_encode_tag_for_field(stream, field))
        {
            return false;
        }

        if (!pb_encode_varint(stream, (uint64_t) ctx->items[i]))
        {
            return false;
        }
    }

    return true;
}

static bool factory_encode_bytes_field(
    pb_ostream_t * stream,
    const pb_field_t * field,
    void * const * arg)
{
    if ((stream == NULL) || (field == NULL) || (arg == NULL) || (*arg == NULL))
    {
        return false;
    }

    const factory_bytes_encode_ctx_t * ctx =
        (const factory_bytes_encode_ctx_t *) *arg;

    if (!pb_encode_tag_for_field(stream, field))
    {
        return false;
    }

    return pb_encode_string(stream, ctx->data, ctx->size);
}

static void factory_prepare_write_decode_callbacks(
    factory_command_FactoryWriteRequest * request,
    factory_write_data_t * data)
{
    request->data.serial_number.funcs.decode = factory_decode_bytes_field;
    request->data.serial_number.arg = &data->serial_number;

    request->data.manufactured_date.funcs.decode = factory_decode_bytes_field;
    request->data.manufactured_date.arg = &data->manufactured_date;

    request->data.dac_cert.funcs.decode = factory_decode_bytes_field;
    request->data.dac_cert.arg = &data->dac_cert;

    request->data.dac_public_key.funcs.decode = factory_decode_bytes_field;
    request->data.dac_public_key.arg = &data->dac_public_key;

    request->data.dac_private_key.funcs.decode = factory_decode_bytes_field;
    request->data.dac_private_key.arg = &data->dac_private_key;

    request->data.pai_cert.funcs.decode = factory_decode_bytes_field;
    request->data.pai_cert.arg = &data->pai_cert;

    request->data.certification_declaration.funcs.decode = factory_decode_bytes_field;
    request->data.certification_declaration.arg = &data->certification_declaration;

    request->data.onboarding_payload.funcs.decode = factory_decode_bytes_field;
    request->data.onboarding_payload.arg = &data->onboarding_payload;

    request->data.spake2p_salt.funcs.decode = factory_decode_bytes_field;
    request->data.spake2p_salt.arg = &data->spake2p_salt;

    request->data.spake2p_verifier.funcs.decode = factory_decode_bytes_field;
    request->data.spake2p_verifier.arg = &data->spake2p_verifier;
}

static void factory_prepare_read_decode_callbacks(
    factory_command_FactoryReadRequest * request,
    factory_read_items_t * items)
{
    request->items.funcs.decode = factory_decode_read_items;
    request->items.arg = items;
}

static bool factory_decode_request(
    const uint8_t * data,
    size_t size,
    factory_transaction_FactoryRequest * request,
    factory_write_data_t * write_data,
    factory_read_items_t * read_items)
{
    if ((data == NULL) || (request == NULL) || (write_data == NULL) || (read_items == NULL))
    {
        return false;
    }

    pb_istream_t stream = pb_istream_from_buffer(data, size);

    *request = factory_transaction_FactoryRequest_init_zero;

    factory_prepare_read_decode_callbacks(&request->transaction.read, read_items);
    factory_prepare_write_decode_callbacks(&request->transaction.write, write_data);

    return pb_decode(&stream, factory_transaction_FactoryRequest_fields, request);
}

static void factory_write_data_init(factory_write_data_t * data)
{
    static uint8_t serial_number_buf[FACTORY_MANAGER_MAX_STRING_SIZE];
    static uint8_t manufactured_date_buf[FACTORY_MANAGER_MAX_STRING_SIZE];
    static uint8_t dac_cert_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t dac_public_key_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t dac_private_key_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t pai_cert_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t certification_declaration_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t onboarding_payload_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t spake2p_salt_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];
    static uint8_t spake2p_verifier_buf[FACTORY_MANAGER_MAX_BYTES_SIZE];

    memset(data, 0, sizeof(*data));

    factory_field_buffer_init(&data->serial_number, serial_number_buf, sizeof(serial_number_buf));
    factory_field_buffer_init(&data->manufactured_date, manufactured_date_buf, sizeof(manufactured_date_buf));
    factory_field_buffer_init(&data->dac_cert, dac_cert_buf, sizeof(dac_cert_buf));
    factory_field_buffer_init(&data->dac_public_key, dac_public_key_buf, sizeof(dac_public_key_buf));
    factory_field_buffer_init(&data->dac_private_key, dac_private_key_buf, sizeof(dac_private_key_buf));
    factory_field_buffer_init(&data->pai_cert, pai_cert_buf, sizeof(pai_cert_buf));
    factory_field_buffer_init(&data->certification_declaration, certification_declaration_buf, sizeof(certification_declaration_buf));
    factory_field_buffer_init(&data->onboarding_payload, onboarding_payload_buf, sizeof(onboarding_payload_buf));
    factory_field_buffer_init(&data->spake2p_salt, spake2p_salt_buf, sizeof(spake2p_salt_buf));
    factory_field_buffer_init(&data->spake2p_verifier, spake2p_verifier_buf, sizeof(spake2p_verifier_buf));
}

static void factory_read_items_init(factory_read_items_t * items)
{
    memset(items, 0, sizeof(*items));
}

static void factory_read_response_data_init(factory_read_response_data_t * data)
{
    memset(data, 0, sizeof(*data));
}

static factory_transaction_FactoryStatusCode factory_get_item(
    factory_data_FactoryDataItem item,
    factory_read_response_data_t * out)
{
    switch (item)
    {
    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SERIAL_NUMBER:
    {
        size_t size = sizeof(out->serial_number.data);
        if (!factory_data_get_serial_number(out->serial_number.data, &size))
        {
            return factory_status_internal_error();
        }
        out->serial_number.present = true;
        out->serial_number.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_MANUFACTURED_DATE:
    {
        size_t size = sizeof(out->manufactured_date.data);
        if (!factory_data_get_manufactured_date(out->manufactured_date.data, &size))
        {
            return factory_status_internal_error();
        }
        out->manufactured_date.present = true;
        out->manufactured_date.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_VENDOR_ID:
        if (!factory_data_get_vendor_id(&out->vendor_id))
        {
            return factory_status_internal_error();
        }
        out->has_vendor_id = true;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_PRODUCT_ID:
        if (!factory_data_get_product_id(&out->product_id))
        {
            return factory_status_internal_error();
        }
        out->has_product_id = true;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_CERT:
    {
        size_t size = sizeof(out->dac_cert.data);
        if (!factory_data_get_dac_cert(out->dac_cert.data, &size))
        {
            return factory_status_internal_error();
        }
        out->dac_cert.present = true;
        out->dac_cert.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_PUBLIC_KEY:
    {
        size_t size = sizeof(out->dac_public_key.data);
        if (!factory_data_get_dac_public_key(out->dac_public_key.data, &size))
        {
            return factory_status_internal_error();
        }
        out->dac_public_key.present = true;
        out->dac_public_key.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_PRIVATE_KEY:
    {
        size_t size = sizeof(out->dac_private_key.data);
        if (!factory_data_get_dac_private_key(out->dac_private_key.data, &size))
        {
            return factory_status_internal_error();
        }
        out->dac_private_key.present = true;
        out->dac_private_key.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_PAI_CERT:
    {
        size_t size = sizeof(out->pai_cert.data);
        if (!factory_data_get_pai_cert(out->pai_cert.data, &size))
        {
            return factory_status_internal_error();
        }
        out->pai_cert.present = true;
        out->pai_cert.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_CERTIFICATION_DECLARATION:
    {
        size_t size = sizeof(out->certification_declaration.data);
        if (!factory_data_get_certification_declaration(out->certification_declaration.data, &size))
        {
            return factory_status_internal_error();
        }
        out->certification_declaration.present = true;
        out->certification_declaration.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_ONBOARDING_PAYLOAD:
    {
        size_t size = sizeof(out->onboarding_payload.data);
        if (!factory_data_get_onboarding_payload(out->onboarding_payload.data, &size))
        {
            return factory_status_internal_error();
        }
        out->onboarding_payload.present = true;
        out->onboarding_payload.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_PASSCODE:
        if (!factory_data_get_spake2p_passcode(&out->spake2p_passcode))
        {
            return factory_status_internal_error();
        }
        out->has_spake2p_passcode = true;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_SALT:
    {
        size_t size = sizeof(out->spake2p_salt.data);
        if (!factory_data_get_spake2p_salt(out->spake2p_salt.data, &size))
        {
            return factory_status_internal_error();
        }
        out->spake2p_salt.present = true;
        out->spake2p_salt.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_ITERATION_COUNT:
        if (!factory_data_get_spake2p_iteration_count(&out->spake2p_iteration_count))
        {
            return factory_status_internal_error();
        }
        out->has_spake2p_iteration_count = true;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_VERIFIER:
    {
        size_t size = sizeof(out->spake2p_verifier.data);
        if (!factory_data_get_spake2p_verifier(out->spake2p_verifier.data, &size))
        {
            return factory_status_internal_error();
        }
        out->spake2p_verifier.present = true;
        out->spake2p_verifier.size = size;
        return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
    }

    case factory_data_FactoryDataItem_FACTORY_DATA_ITEM_UNSPECIFIED:
    default:
        return factory_status_invalid_item();
    }
}

static factory_transaction_FactoryStatusCode factory_set_write_data(
    const factory_write_data_t * write_data,
    factory_data_FactoryDataItem * written_items,
    size_t written_capacity,
    size_t * out_written_count)
{
    size_t written_count = 0;

    if ((write_data == NULL) || (written_items == NULL) || (out_written_count == NULL))
    {
        return factory_status_invalid_argument();
    }

    if (write_data->serial_number.present)
    {
        if (!factory_data_set_serial_number(
                write_data->serial_number.buffer,
                write_data->serial_number.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SERIAL_NUMBER;
        }
    }

    if (write_data->manufactured_date.present)
    {
        if (!factory_data_set_manufactured_date(
                write_data->manufactured_date.buffer,
                write_data->manufactured_date.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_MANUFACTURED_DATE;
        }
    }

    if (write_data->has_vendor_id)
    {
        if (!factory_data_set_vendor_id(write_data->vendor_id))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_VENDOR_ID;
        }
    }

    if (write_data->has_product_id)
    {
        if (!factory_data_set_product_id(write_data->product_id))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_PRODUCT_ID;
        }
    }

    if (write_data->dac_cert.present)
    {
        if (!factory_data_set_dac_cert(
                write_data->dac_cert.buffer,
                write_data->dac_cert.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_CERT;
        }
    }

    if (write_data->dac_public_key.present)
    {
        if (!factory_data_set_dac_public_key(
                write_data->dac_public_key.buffer,
                write_data->dac_public_key.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_PUBLIC_KEY;
        }
    }

    if (write_data->dac_private_key.present)
    {
        if (!factory_data_set_dac_private_key(
                write_data->dac_private_key.buffer,
                write_data->dac_private_key.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_DAC_PRIVATE_KEY;
        }
    }

    if (write_data->pai_cert.present)
    {
        if (!factory_data_set_pai_cert(
                write_data->pai_cert.buffer,
                write_data->pai_cert.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_PAI_CERT;
        }
    }

    if (write_data->certification_declaration.present)
    {
        if (!factory_data_set_certification_declaration(
                write_data->certification_declaration.buffer,
                write_data->certification_declaration.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_CERTIFICATION_DECLARATION;
        }
    }

    if (write_data->onboarding_payload.present)
    {
        if (!factory_data_set_onboarding_payload(
                write_data->onboarding_payload.buffer,
                write_data->onboarding_payload.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_ONBOARDING_PAYLOAD;
        }
    }

    if (write_data->has_spake2p_passcode)
    {
        if (!factory_data_set_spake2p_passcode(write_data->spake2p_passcode))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_PASSCODE;
        }
    }

    if (write_data->spake2p_salt.present)
    {
        if (!factory_data_set_spake2p_salt(
                write_data->spake2p_salt.buffer,
                write_data->spake2p_salt.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_SALT;
        }
    }

    if (write_data->has_spake2p_iteration_count)
    {
        if (!factory_data_set_spake2p_iteration_count(write_data->spake2p_iteration_count))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_ITERATION_COUNT;
        }
    }

    if (write_data->spake2p_verifier.present)
    {
        if (!factory_data_set_spake2p_verifier(
                write_data->spake2p_verifier.buffer,
                write_data->spake2p_verifier.size))
        {
            return factory_status_internal_error();
        }

        if (written_count < written_capacity)
        {
            written_items[written_count++] =
                factory_data_FactoryDataItem_FACTORY_DATA_ITEM_SPAKE2P_VERIFIER;
        }
    }

    *out_written_count = written_count;
    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
}

static factory_transaction_FactoryStatusCode factory_process_read_request(
    const factory_read_items_t * read_items,
    factory_read_response_data_t * out_data)
{
    if ((read_items == NULL) || (out_data == NULL))
    {
        return factory_status_invalid_argument();
    }

    if (read_items->count == 0u)
    {
        return factory_status_invalid_argument();
    }

    for (size_t i = 0; i < read_items->count; ++i)
    {
        factory_transaction_FactoryStatusCode rc =
            factory_get_item(read_items->items[i], out_data);

        if (rc != factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK)
        {
            return rc;
        }
    }

    return factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK;
}

static void factory_bind_read_response_callbacks(
    factory_command_FactoryReadResponse * response,
    factory_read_response_data_t * data,
    factory_bytes_encode_ctx_t * serial_number_ctx,
    factory_bytes_encode_ctx_t * manufactured_date_ctx,
    factory_bytes_encode_ctx_t * dac_cert_ctx,
    factory_bytes_encode_ctx_t * dac_public_key_ctx,
    factory_bytes_encode_ctx_t * dac_private_key_ctx,
    factory_bytes_encode_ctx_t * pai_cert_ctx,
    factory_bytes_encode_ctx_t * certification_declaration_ctx,
    factory_bytes_encode_ctx_t * onboarding_payload_ctx,
    factory_bytes_encode_ctx_t * spake2p_salt_ctx,
    factory_bytes_encode_ctx_t * spake2p_verifier_ctx)
{
    response->has_data = true;

    if (data->serial_number.present)
    {
        serial_number_ctx->data = data->serial_number.data;
        serial_number_ctx->size = data->serial_number.size;
        response->data.serial_number.funcs.encode = factory_encode_bytes_field;
        response->data.serial_number.arg = serial_number_ctx;
    }

    if (data->manufactured_date.present)
    {
        manufactured_date_ctx->data = data->manufactured_date.data;
        manufactured_date_ctx->size = data->manufactured_date.size;
        response->data.manufactured_date.funcs.encode = factory_encode_bytes_field;
        response->data.manufactured_date.arg = manufactured_date_ctx;
    }

    response->data.has_vendor_id = data->has_vendor_id;
    response->data.vendor_id = data->vendor_id;

    response->data.has_product_id = data->has_product_id;
    response->data.product_id = data->product_id;

    if (data->dac_cert.present)
    {
        dac_cert_ctx->data = data->dac_cert.data;
        dac_cert_ctx->size = data->dac_cert.size;
        response->data.dac_cert.funcs.encode = factory_encode_bytes_field;
        response->data.dac_cert.arg = dac_cert_ctx;
    }

    if (data->dac_public_key.present)
    {
        dac_public_key_ctx->data = data->dac_public_key.data;
        dac_public_key_ctx->size = data->dac_public_key.size;
        response->data.dac_public_key.funcs.encode = factory_encode_bytes_field;
        response->data.dac_public_key.arg = dac_public_key_ctx;
    }

    if (data->dac_private_key.present)
    {
        dac_private_key_ctx->data = data->dac_private_key.data;
        dac_private_key_ctx->size = data->dac_private_key.size;
        response->data.dac_private_key.funcs.encode = factory_encode_bytes_field;
        response->data.dac_private_key.arg = dac_private_key_ctx;
    }

    if (data->pai_cert.present)
    {
        pai_cert_ctx->data = data->pai_cert.data;
        pai_cert_ctx->size = data->pai_cert.size;
        response->data.pai_cert.funcs.encode = factory_encode_bytes_field;
        response->data.pai_cert.arg = pai_cert_ctx;
    }

    if (data->certification_declaration.present)
    {
        certification_declaration_ctx->data = data->certification_declaration.data;
        certification_declaration_ctx->size = data->certification_declaration.size;
        response->data.certification_declaration.funcs.encode = factory_encode_bytes_field;
        response->data.certification_declaration.arg = certification_declaration_ctx;
    }

    if (data->onboarding_payload.present)
    {
        onboarding_payload_ctx->data = data->onboarding_payload.data;
        onboarding_payload_ctx->size = data->onboarding_payload.size;
        response->data.onboarding_payload.funcs.encode = factory_encode_bytes_field;
        response->data.onboarding_payload.arg = onboarding_payload_ctx;
    }

    response->data.has_spake2p_passcode = data->has_spake2p_passcode;
    response->data.spake2p_passcode = data->spake2p_passcode;

    if (data->spake2p_salt.present)
    {
        spake2p_salt_ctx->data = data->spake2p_salt.data;
        spake2p_salt_ctx->size = data->spake2p_salt.size;
        response->data.spake2p_salt.funcs.encode = factory_encode_bytes_field;
        response->data.spake2p_salt.arg = spake2p_salt_ctx;
    }

    response->data.has_spake2p_iteration_count = data->has_spake2p_iteration_count;
    response->data.spake2p_iteration_count = data->spake2p_iteration_count;

    if (data->spake2p_verifier.present)
    {
        spake2p_verifier_ctx->data = data->spake2p_verifier.data;
        spake2p_verifier_ctx->size = data->spake2p_verifier.size;
        response->data.spake2p_verifier.funcs.encode = factory_encode_bytes_field;
        response->data.spake2p_verifier.arg = spake2p_verifier_ctx;
    }
}

static bool factory_encode_response(
    const factory_transaction_FactoryResponse * response,
    uint8_t * out_buffer,
    size_t out_capacity,
    size_t * out_size)
{
    if ((response == NULL) || (out_buffer == NULL) || (out_size == NULL))
    {
        return false;
    }

    pb_ostream_t stream = pb_ostream_from_buffer(out_buffer, out_capacity);

    if (!pb_encode(&stream, factory_transaction_FactoryResponse_fields, response))
    {
        return false;
    }

    *out_size = stream.bytes_written;
    return true;
}

bool factory_manager_process(void)
{
    uint8_t rx_buffer[FACTORY_MANAGER_RX_BUFFER_SIZE];
    uint8_t tx_buffer[FACTORY_MANAGER_TX_BUFFER_SIZE];
    int rc;

    rc = factory_session_init(factory_manager_session_event_handler);
    if (rc < 0)
    {
        return false;
    }

    rc = factory_session_open(false);
    if (rc < 0)
    {
        return false;
    }

    for (;;)
    {
        size_t rx_size = sizeof(rx_buffer);
        size_t tx_size = 0;

        factory_transaction_FactoryRequest request;
        factory_write_data_t write_data;
        factory_read_items_t read_items;

        factory_transaction_FactoryResponse response =
            factory_transaction_FactoryResponse_init_zero;

        factory_read_response_data_t read_response_data;
        factory_data_FactoryDataItem written_items[16];
        size_t written_count = 0;

        factory_enum_list_encode_ctx_t written_items_ctx = { 0 };

        factory_bytes_encode_ctx_t serial_number_ctx = { 0 };
        factory_bytes_encode_ctx_t manufactured_date_ctx = { 0 };
        factory_bytes_encode_ctx_t dac_cert_ctx = { 0 };
        factory_bytes_encode_ctx_t dac_public_key_ctx = { 0 };
        factory_bytes_encode_ctx_t dac_private_key_ctx = { 0 };
        factory_bytes_encode_ctx_t pai_cert_ctx = { 0 };
        factory_bytes_encode_ctx_t certification_declaration_ctx = { 0 };
        factory_bytes_encode_ctx_t onboarding_payload_ctx = { 0 };
        factory_bytes_encode_ctx_t spake2p_salt_ctx = { 0 };
        factory_bytes_encode_ctx_t spake2p_verifier_ctx = { 0 };

        factory_write_data_init(&write_data);
        factory_read_items_init(&read_items);
        factory_read_response_data_init(&read_response_data);

        rc = factory_session_receive(rx_buffer, &rx_size);
        if (rc < 0)
        {
            factory_session_close();
            return false;
        }

        if (!factory_decode_request(rx_buffer, rx_size, &request, &write_data, &read_items))
        {
            response.transaction_id = 0;
            response.status = factory_status_invalid_data();
            response.which_transaction = 0;

            if (!factory_encode_response(&response, tx_buffer, sizeof(tx_buffer), &tx_size))
            {
                factory_session_close();
                return false;
            }

            if (factory_session_send(tx_buffer, tx_size) < 0)
            {
                factory_session_close();
                return false;
            }

            continue;
        }

        response.transaction_id = request.transaction_id;

        switch (request.which_transaction)
        {
        case factory_transaction_FactoryRequest_read_tag:
            response.status = factory_process_read_request(&read_items, &read_response_data);
            response.which_transaction = factory_transaction_FactoryResponse_read_tag;
            response.transaction.read = factory_command_FactoryReadResponse_init_zero;

            if (response.status ==
                factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK)
            {
                factory_bind_read_response_callbacks(
                    &response.transaction.read,
                    &read_response_data,
                    &serial_number_ctx,
                    &manufactured_date_ctx,
                    &dac_cert_ctx,
                    &dac_public_key_ctx,
                    &dac_private_key_ctx,
                    &pai_cert_ctx,
                    &certification_declaration_ctx,
                    &onboarding_payload_ctx,
                    &spake2p_salt_ctx,
                    &spake2p_verifier_ctx);
            }
            else
            {
                response.transaction.read.has_data = false;
            }
            break;

        case factory_transaction_FactoryRequest_write_tag:
            response.status = factory_set_write_data(
                &write_data,
                written_items,
                sizeof(written_items) / sizeof(written_items[0]),
                &written_count);

            response.which_transaction = factory_transaction_FactoryResponse_write_tag;
            response.transaction.write = factory_command_FactoryWriteResponse_init_zero;

            written_items_ctx.items = written_items;
            written_items_ctx.count = written_count;
            response.transaction.write.items.funcs.encode = factory_encode_enum_list;
            response.transaction.write.items.arg = &written_items_ctx;
            break;

        default:
            response.status = factory_status_invalid_transaction();
            response.which_transaction = 0;
            break;
        }

        if (!factory_encode_response(&response, tx_buffer, sizeof(tx_buffer), &tx_size))
        {
            factory_session_close();
            return false;
        }

        if (factory_session_send(tx_buffer, tx_size) < 0)
        {
            factory_session_close();
            return false;
        }

        if ((request.which_transaction == factory_transaction_FactoryRequest_write_tag) &&
            (response.status == factory_transaction_FactoryStatusCode_FACTORY_STATUS_CODE_OK))
        {
            factory_session_close();
            return true;
        }
    }
}