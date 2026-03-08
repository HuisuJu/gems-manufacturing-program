#pragma once

#include <stdbool.h>

/**
 * @brief Callback type for factory provisioning result
 * 
 * @param is_success true if provisioning succeeded, false otherwise
 */
typedef void (*factory_manager_result_callback_t)(bool is_success);

/**
 * @brief Starts the factory provisioning process.
 * 
 * This function initiates the factory provisioning workflow which handles
 * communication with the PC, receives factory data, and provisions the device.
 *
 * The callback will be invoked upon completion:
 * - On success: The caller should perform a system reboot to apply provisioned data.
 * - On failure: The caller should resume normal device operation.
 * 
 * @param callback Function to be called when provisioning completes
 * @return 0 on successful thread creation, negative error code on failure
 */
int factory_manager_start(factory_manager_result_callback_t callback);