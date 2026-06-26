package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.dto.BridgePositionSellRequest
import com.wrbug.polymarketbot.dto.BridgePositionSellResponse
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.service.bridge.BridgeExecutorClient
import com.wrbug.polymarketbot.service.bridge.BridgePortfolioClient
import kotlinx.coroutines.runBlocking
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Bridge 只读账户卖出服务
 * 由于只读账户没有私钥，无法由 PolyHermes 后端直接签名卖出，
 * 因此校验仓位后，把卖出指令转发给 Bridge，由 Bridge 在浏览器会话中执行。
 */
@Service
class BridgePositionSellService(
    private val accountRepository: AccountRepository,
    private val bridgePositionService: BridgePositionService,
    private val bridgeExecutorClient: BridgeExecutorClient,
    private val bridgePortfolioClient: BridgePortfolioClient
) {

    private val logger = LoggerFactory.getLogger(BridgePositionSellService::class.java)

    @Transactional(readOnly = true)
    fun sellBridgePosition(request: BridgePositionSellRequest): Result<BridgePositionSellResponse> {
        return try {
            // 1. 账户校验
            if (request.accountId <= 0) {
                return Result.failure(IllegalArgumentException("账户 ID 无效"))
            }
            val account = accountRepository.findById(request.accountId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("账户不存在"))
            // Bridge 卖出适用于两类账户：
            // 1. Bridge 只读账户（没有私钥，必须由 Bridge 浏览器执行）
            // 2. Magic 钱包账户（即使非只读，也可选择由 Bridge 浏览器执行，避免暴露私钥）
            val canUseBridge = account.isReadOnly || account.walletType.equals("magic", ignoreCase = true)
            if (!canUseBridge) {
                return Result.failure(IllegalStateException("该账户不是 Bridge 只读账户或 Magic 钱包，请使用普通卖出接口"))
            }

            val runtimeWallet = bridgePortfolioClient.fetchAccount()?.walletAddress
                ?: return Result.failure(IllegalStateException("Bridge 未登录或无法读取当前浏览器钱包，不能执行 Bridge 卖出"))
            val walletMatches = runtimeWallet.equals(account.walletAddress, ignoreCase = true) ||
                runtimeWallet.equals(account.proxyAddress, ignoreCase = true)
            if (!walletMatches) {
                return Result.failure(
                    IllegalStateException(
                        "Bridge 当前登录钱包是 ${maskAddress(runtimeWallet)}，不是所选账户 ${maskAddress(account.walletAddress)}。请先在账户管理中切换当前 Bridge 账户。"
                    )
                )
            }

            // 2. 市价单校验（Bridge 当前只支持市价执行）
            if (!request.orderType.equals("MARKET", ignoreCase = true)) {
                return Result.failure(IllegalArgumentException("Bridge 执行当前只支持市价卖出"))
            }

            // 3. 计算目标卖出数量
            val positions = runBlocking { bridgePositionService.getPositionsForAccount(account) }
            val position = positions.find {
                it.marketId == request.marketId &&
                        (request.outcomeIndex == null || it.outcomeIndex == request.outcomeIndex) &&
                        it.side.equals(request.side, ignoreCase = true)
            } ?: return Result.failure(IllegalArgumentException("未找到对应仓位"))

            val netQuantity = position.originalQuantity?.toBigDecimalOrNull()
                ?: return Result.failure(IllegalStateException("仓位数量无效"))

            val sellQuantity = when {
                !request.quantity.isNullOrBlank() -> {
                    val q = request.quantity.toBigDecimalOrNull()
                        ?: return Result.failure(IllegalArgumentException("卖出数量格式不正确"))
                    if (q <= BigDecimal.ZERO) {
                        return Result.failure(IllegalArgumentException("卖出数量必须大于 0"))
                    }
                    q
                }
                !request.percent.isNullOrBlank() -> {
                    val p = request.percent.toBigDecimalOrNull()
                        ?: return Result.failure(IllegalArgumentException("卖出百分比格式不正确"))
                    if (p <= BigDecimal.ZERO || p > BigDecimal("100")) {
                        return Result.failure(IllegalArgumentException("卖出百分比必须在 0-100 之间"))
                    }
                    netQuantity.multiply(p).divide(BigDecimal("100"), 8, RoundingMode.HALF_UP)
                }
                else -> return Result.failure(IllegalArgumentException("必须提供卖出数量或百分比"))
            }

            if (sellQuantity > netQuantity) {
                return Result.failure(
                    IllegalArgumentException(
                        "卖出数量超过持仓: 持仓=${netQuantity.toPlainString()}, 请求=${sellQuantity.toPlainString()}"
                    )
                )
            }

            // 4. 获取 marketSlug（Bridge 导航需要）
            val marketSlug = bridgePositionService.findMarketSlug(account, request.marketId, request.outcomeIndex)
                ?: return Result.failure(IllegalArgumentException("无法找到该市场对应的 marketSlug"))

            // 5. 发送执行请求给 Bridge
            val bridgeResponse = bridgeExecutorClient.execute(
                BridgeExecutorClient.BridgeExecuteRequest(
                    marketSlug = marketSlug,
                    side = "SELL",
                    outcome = request.side,
                    amountUsdc = 0.0,
                    conditionId = request.marketId,
                    sizeShares = sellQuantity.toDouble(),
                    outcomeIndex = request.outcomeIndex,
                    marketTitle = position.marketTitle
                )
            )

            logger.info(
                "已转发 Bridge 卖出指令: accountId=${request.accountId}, market=${request.marketId}, " +
                "outcome=${request.side}, quantity=${sellQuantity.toPlainString()}, " +
                "bridgeRecordId=${bridgeResponse?.recordId}, externalTradeId=${bridgeResponse?.externalTradeId}"
            )

            Result.success(
                BridgePositionSellResponse(
                    recordId = bridgeResponse?.recordId,
                    externalTradeId = bridgeResponse?.externalTradeId,
                    status = bridgeResponse?.status ?: "accepted"
                )
            )
        } catch (e: Exception) {
            logger.error("Bridge 仓位卖出失败", e)
            Result.failure(e)
        }
    }

    private fun maskAddress(address: String): String {
        return if (address.length >= 10) {
            "${address.take(6)}...${address.takeLast(4)}"
        } else {
            address
        }
    }
}
