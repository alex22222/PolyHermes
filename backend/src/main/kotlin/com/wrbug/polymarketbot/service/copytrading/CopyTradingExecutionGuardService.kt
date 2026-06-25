package com.wrbug.polymarketbot.service.copytrading

import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.service.accounts.AccountExecutionModeService
import com.wrbug.polymarketbot.service.bridge.BridgeWebhookClient
import jakarta.annotation.PostConstruct
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

/**
 * Audits enabled copy-trading configs for execution-mode hazards at startup.
 */
@Service
class CopyTradingExecutionGuardService(
    private val copyTradingRepository: CopyTradingRepository,
    private val accountRepository: AccountRepository,
    private val accountExecutionModeService: AccountExecutionModeService,
    private val bridgeWebhookClient: BridgeWebhookClient
) {
    private val logger = LoggerFactory.getLogger(CopyTradingExecutionGuardService::class.java)

    @PostConstruct
    fun auditEnabledCopyTradingExecutionModes() {
        val enabledConfigs = runCatching { copyTradingRepository.findByEnabledTrue() }
            .onFailure { e -> logger.warn("跟单执行模式审计失败: ${e.message}") }
            .getOrDefault(emptyList())

        enabledConfigs.forEach { copyTrading ->
            val account = accountRepository.findById(copyTrading.accountId).orElse(null)
            if (account == null) {
                logger.error(
                    "跟单执行配置异常：账户不存在 copyTradingId={}, accountId={}",
                    copyTrading.id,
                    copyTrading.accountId
                )
                return@forEach
            }

            val hasClob = accountExecutionModeService.hasClobApiCredentials(account)
            val canBridge = accountExecutionModeService.canUseBridgeExecution(account)
            if (!hasClob && !canBridge) {
                logger.error(
                    "跟单执行配置异常：账户既无 CLOB API 凭证也不能走 Bridge copyTradingId={}, accountId={}, walletType={}, readOnly={}",
                    copyTrading.id,
                    account.id,
                    account.walletType,
                    account.isReadOnly
                )
            }
            if (!hasClob && canBridge && !bridgeWebhookClient.isConfigured()) {
                logger.error(
                    "跟单执行配置异常：Bridge 账户无 CLOB API 凭证但 bridge.webhook.url 未配置 copyTradingId={}, accountId={}",
                    copyTrading.id,
                    account.id
                )
            }
        }
    }
}
