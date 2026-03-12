/**
 * @file factory_platform.h
 * @brief Platform abstraction interface for the factory session module.
 *
 * This header declares platform-dependent functions that must be implemented
 * by the integrator when porting this module to a target environment.
 *
 * There is intentionally no default `factory_platform.c` in this module.
 * Provide your own implementation file and link it into your firmware build.
 */

#pragma once

#include <sys/types.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Return platform uptime in milliseconds.
 *
 * Must use a monotonic time source suitable for timeout/retry handling.
 *
 * @return Milliseconds elapsed since platform boot.
 */
uint32_t factory_platform_get_uptime_ms(void);

/**
 * @brief Sleep for the specified number of milliseconds.
 *
 * @param milliseconds Duration in milliseconds.
 */
void factory_platform_sleep(uint32_t milliseconds);

/**
 * @brief Read device unique identifier bytes.
 *
 * Fill the caller-provided buffer with identifier bytes.
 *
 * Implementation requirements:
 * - Caller sets `*size` to available buffer capacity before calling.
 * - Implementation writes identifier bytes into `buffer` and updates `*size`
 *   to the number of bytes written.
 * - Must be deterministic for the same device.
 * - Byte order/content is platform-defined.
 *
 * @param buffer Destination buffer.
 * @param size In/out size pointer (input: capacity, output: written length).
 * @return 0 on success, negative value on error.
 */
int factory_platform_get_uuid(uint8_t *buffer, size_t *size);

/**
 * @brief Read bytes from platform UART (non-blocking).
 *
 * Implementation requirements:
 * - Must be non-blocking
 * - May read fewer than `size` bytes
 *
 * @param buffer Destination buffer.
 * @param size Maximum number of bytes to read.
 * @return Number of bytes read, or negative value on error.
 */

ssize_t factory_platform_uart_read(uint8_t *buffer, size_t size);

/**
 * @brief Write bytes to platform UART (non-blocking).
 *
 * Implementation requirements:
 * - Must be non-blocking
 * - May write fewer than `size` bytes
 *
 * @param buffer Source buffer.
 * @param size Maximum number of bytes to write.
 * @return Number of bytes written, or negative value on error.
 */
ssize_t factory_platform_uart_write(const uint8_t *buffer, size_t size);

#ifdef __cplusplus
}
#endif