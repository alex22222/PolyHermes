package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.Account
import org.springframework.stereotype.Service

/**
 * Centralizes account execution-mode decisions.
 *
 * Bridge/Magic accounts can execute through the browser bridge and must not be
 * blocked just because they do not have CLOB API credentials.
 */
@Service
class AccountExecutionModeService {

    fun hasClobApiCredentials(account: Account): Boolean {
        return !account.apiKey.isNullOrBlank() &&
            !account.apiSecret.isNullOrBlank() &&
            !account.apiPassphrase.isNullOrBlank()
    }

    fun canUseBridgeExecution(account: Account): Boolean {
        return account.isReadOnly || account.walletType.equals("magic", ignoreCase = true)
    }

    fun shouldFallbackToBridge(account: Account): Boolean {
        return canUseBridgeExecution(account) && !hasClobApiCredentials(account)
    }
}
