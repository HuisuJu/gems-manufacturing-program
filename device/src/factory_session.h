#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    FACTORY_SESSION_EVENT_OPENED,
    FACTORY_SESSION_EVENT_CLOSED,
    FACTORY_SESSION_EVENT_ERROR,
} factory_session_event_t;
typedef void (*factory_session_event_handler_t)(factory_session_event_t event);

int factory_session_init(factory_session_event_handler_t event_handler);

int factory_session_open(bool require_auth);
void factory_session_close(void);

int factory_session_send(const uint8_t *data, size_t size);
int factory_session_receive(uint8_t *data, size_t *size);