#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Get serial number.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_serial_number(uint8_t *buf, size_t *size);

/**
 * @brief Set serial number.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_serial_number(const uint8_t *buf, size_t size);

/**
 * @brief Get manufactured date.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_manufactured_date(uint8_t *buf, size_t *size);

/**
 * @brief Set manufactured date.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_manufactured_date(const uint8_t *buf, size_t size);

/**
 * @brief Get vendor ID.
 *
 * @param data Output value.
 * @return true on success, false on failure.
 */
bool factory_data_get_vendor_id(uint32_t *data);

/**
 * @brief Set vendor ID.
 *
 * @param data Input value.
 * @return true on success, false on failure.
 */
bool factory_data_set_vendor_id(uint32_t data);

/**
 * @brief Get product ID.
 *
 * @param data Output value.
 * @return true on success, false on failure.
 */
bool factory_data_get_product_id(uint32_t *data);

/**
 * @brief Set product ID.
 *
 * @param data Input value.
 * @return true on success, false on failure.
 */
bool factory_data_set_product_id(uint32_t data);

/**
 * @brief Get DAC certificate.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_dac_cert(uint8_t *buf, size_t *size);

/**
 * @brief Set DAC certificate.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_dac_cert(const uint8_t *buf, size_t size);

/**
 * @brief Get DAC public key.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_dac_public_key(uint8_t *buf, size_t *size);

/**
 * @brief Set DAC public key.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_dac_public_key(const uint8_t *buf, size_t size);

/**
 * @brief Get DAC private key.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_dac_private_key(uint8_t *buf, size_t *size);

/**
 * @brief Set DAC private key.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_dac_private_key(const uint8_t *buf, size_t size);

/**
 * @brief Get PAI certificate.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_pai_cert(uint8_t *buf, size_t *size);

/**
 * @brief Set PAI certificate.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_pai_cert(const uint8_t *buf, size_t size);

/**
 * @brief Get certification declaration.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_certification_declaration(uint8_t *buf, size_t *size);

/**
 * @brief Set certification declaration.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_certification_declaration(const uint8_t *buf, size_t size);

/**
 * @brief Get onboarding payload.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_onboarding_payload(uint8_t *buf, size_t *size);

/**
 * @brief Set onboarding payload.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_onboarding_payload(const uint8_t *buf, size_t size);

/**
 * @brief Get SPAKE2+ passcode.
 *
 * @param data Output value.
 * @return true on success, false on failure.
 */
bool factory_data_get_spake2p_passcode(uint32_t *data);

/**
 * @brief Set SPAKE2+ passcode.
 *
 * @param data Input value.
 * @return true on success, false on failure.
 */
bool factory_data_set_spake2p_passcode(uint32_t data);

/**
 * @brief Get SPAKE2+ salt.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_spake2p_salt(uint8_t *buf, size_t *size);

/**
 * @brief Set SPAKE2+ salt.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_spake2p_salt(const uint8_t *buf, size_t size);

/**
 * @brief Get SPAKE2+ iteration count.
 *
 * @param data Output value.
 * @return true on success, false on failure.
 */
bool factory_data_get_spake2p_iteration_count(uint32_t *data);

/**
 * @brief Set SPAKE2+ iteration count.
 *
 * @param data Input value.
 * @return true on success, false on failure.
 */
bool factory_data_set_spake2p_iteration_count(uint32_t data);

/**
 * @brief Get SPAKE2+ verifier.
 *
 * @param buf  Output buffer.
 * @param size In: buffer capacity, Out: actual size.
 * @return true on success, false on failure.
 */
bool factory_data_get_spake2p_verifier(uint8_t *buf, size_t *size);

/**
 * @brief Set SPAKE2+ verifier.
 *
 * @param buf  Input buffer.
 * @param size Input size.
 * @return true on success, false on failure.
 */
bool factory_data_set_spake2p_verifier(const uint8_t *buf, size_t size);

#ifdef __cplusplus
}
#endif