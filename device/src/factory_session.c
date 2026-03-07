#include "factory_session.h"

int factory_session_init(factory_session_event_handler_t event_handler);

int factory_session_open(bool require_auth);
void factory_session_close(void);

int factory_session_send(const uint8_t *data, size_t size);
int factory_session_receive(uint8_t *data, size_t *size);