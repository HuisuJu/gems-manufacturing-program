#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Run factory provisioning in a blocking loop.
 * 
 * This function is intended to run an internal processing loop (typically a
 * `while` loop) and does not return until provisioning finishes (success or
 * failure).
 * 
 * Threading requirements:
 * - This is a blocking function.
 * - Call it from a dedicated worker thread, or
 * - Use this function itself as the thread entry routine in your platform.
 *
 * Post-condition guidance:
 * - On success (`true`): reboot or restart as required to apply provisioned
 *   data.
 * - On failure (`false`): resume normal runtime or retry per product policy.
 * 
 * @return `true` if provisioning succeeded, otherwise `false`.
 */
bool factory_manager_process(void);

#ifdef __cplusplus
}
#endif