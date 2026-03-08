#pragma once

#include <sys/types.h>
#include <stddef.h>
#include <stdint.h>

/**
 * @brief Returns platform uptime in milliseconds
 *
 * Monotonic time source used for timeout/retry handling.
 *
 * @return Milliseconds since platform boot
 */
uint32_t factory_platform_get_uptime_ms(void);

/**
 * @brief Sleeps for the specified number of milliseconds
 *
 * @param milliseconds Number of milliseconds to sleep
 */
void factory_platform_sleep(uint32_t milliseconds);

/**
 * @brief Returns unique device identifier
 *
 * @return 64-bit device UUID
 */
uint64_t factory_platform_get_uuid(void);

/**
 * @brief Reads bytes from platform UART (non-blocking)
 *
 * Implementation requirements:
 * - Must be non-blocking
 * - May read fewer than `size` bytes
 *
 * @param buffer Destination buffer
 * @param size Maximum number of bytes to read
 * @return Number of bytes read, or negative value on error
 */

ssize_t factory_platform_uart_read(uint8_t *buffer, size_t size);

/**
 * @brief Writes bytes to platform UART (non-blocking)
 *
 * Implementation requirements:
 * - Must be non-blocking
 * - May write fewer than `size` bytes
 *
 * @param buffer Source buffer
 * @param size Maximum number of bytes to write
 * @return Number of bytes written, or negative value on error
 */
ssize_t factory_platform_uart_write(const uint8_t *buffer, size_t size);