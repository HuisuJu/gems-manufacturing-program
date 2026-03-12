#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Maximum encoded packet size handled by session layer (bytes) */
#define FACTORY_PACKET_MAX_SIZE     (2048u)
/** Maximum retry attempts for recoverable packet transfer failures */
#define FACTORY_PACKET_RETRY_COUNT  (3u)
/** Timeout waiting for PC_HELLO during open flow (milliseconds) */
#define FACTORY_OPEN_TIMEOUT_MS     (5000u)

/** Session lifecycle/event notifications */
typedef enum {
    FACTORY_SESSION_EVENT_OPENED, /**< Session successfully opened */
    FACTORY_SESSION_EVENT_CLOSED, /**< Session closed by either side */
    FACTORY_SESSION_EVENT_ERROR,  /**< Session-level error occurred */
} factory_session_event_t;

/**
 * @brief Session event callback type
 *
 * @param event Session event code
 */
typedef void (*factory_session_event_handler_t)(factory_session_event_t event);

/**
 * @brief Initializes factory session module
 *
 * Registers the event callback and prepares internal session state.
 * Must be called once before `factory_session_open()`.
 *
 * @param event_handler Callback for session lifecycle/error events (can be NULL)
 * @return 0 on success, negative value on failure
 */
int factory_session_init(factory_session_event_handler_t event_handler);

/**
 * @brief Opens a factory session with the host
 *
 * @param require_auth True to require authenticated session flow
 * @return 0 on success, negative value on failure
 */
int factory_session_open(bool require_auth);

/**
 * @brief Closes the current factory session
 *
 * Sends DEVICE_BYE when possible, then clears local session state.
 */
void factory_session_close(void);

/**
 * @brief Sends one application payload over the session
 *
 * Data is packetized/framed internally before transport.
 *
 * @param data Pointer to payload buffer
 * @param size Payload size in bytes
 * @return 0 on success, negative value on failure
 */
int factory_session_send(const uint8_t *data, size_t size);

/**
 * @brief Receives one application payload from the session
 *
 * @param data Output buffer for received payload
 * @param size In: buffer capacity, Out: received payload size
 * @return 0 on success, negative value on failure
 */
int factory_session_receive(uint8_t *data, size_t *size);

#ifdef __cplusplus
}
#endif