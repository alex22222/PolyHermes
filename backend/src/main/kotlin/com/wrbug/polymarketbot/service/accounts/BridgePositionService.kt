package com.wrbug.polymarketbot.service.accounts

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.AccountPositionDto
import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.service.common.MarketPriceService
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Bridge 仓位计算服务
 *
 * 对于没有私钥的 Bridge 只读账户，优先使用 Bridge 抓取的真实持仓快照
 * （bridge_position_snapshot）。当快照不存在时回退到 bridge_trade_record
 * 自行计算净仓位，作为兜底展示。
 */
@Service
class BridgePositionService(
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val bridgePositionSnapshotRepository: BridgePositionSnapshotRepository,
    private val marketRepository: MarketRepository,
    private val marketPriceService: MarketPriceService
) {

    private val logger = LoggerFactory.getLogger(BridgePositionService::class.java)
    private val gson = Gson()
    private val bridgeId = "polymtrade-bridge"

    /**
     * 获取 Bridge 只读账户的当前仓位
     */
    suspend fun getPositionsForAccount(account: Account): List<AccountPositionDto> {
        return try {
            val normalizedWallet = account.walletAddress.lowercase().takeIf { it.isNotBlank() }
            val snapshots = if (normalizedWallet != null) {
                bridgePositionSnapshotRepository.findByBridgeIdAndWalletAddress(bridgeId, normalizedWallet)
            } else {
                emptyList()
            }
            if (snapshots.isNotEmpty()) {
                snapshots.map { snapshot ->
                    val market = snapshot.marketId?.let { marketRepository.findByMarketId(it) }
                    snapshotToPositionDto(account, snapshot, market)
                }
            } else {
                logger.info("Bridge 持仓快照为空，回退到 trade record 计算: accountId=${account.id}")
                calculateFromTradeRecords(account)
            }
        } catch (e: Exception) {
            logger.error("计算 Bridge 仓位失败: accountId=${account.id}", e)
            emptyList()
        }
    }

    /**
     * 查找某仓位对应的 market_slug，用于触发 Bridge 卖出。
     * 优先从快照中读取，回退到交易记录。
     */
    fun findMarketSlug(account: Account, marketId: String, outcomeIndex: Int?): String? {
        val snapshot = bridgePositionSnapshotRepository.findByBridgeId(bridgeId)
            .find { it.marketId == marketId }
        if (snapshot?.marketSlug != null) {
            return snapshot.marketSlug
        }

        val records = bridgeTradeRecordRepository.findByBridgeIdAndStatus(bridgeId, "SUCCESS")
        val match = records.find {
            it.marketId == marketId && (outcomeIndex == null || it.outcomeIndex == outcomeIndex)
        } ?: return null
        return extractMarketSlug(listOf(match))
    }

    private fun snapshotToPositionDto(
        account: Account,
        snapshot: com.wrbug.polymarketbot.entity.BridgePositionSnapshot,
        market: com.wrbug.polymarketbot.entity.Market?
    ): AccountPositionDto {
        val quantity = snapshot.quantity.setScale(4, RoundingMode.DOWN)
        val currentValue = snapshot.currentValue ?: BigDecimal.ZERO
        val pnl = snapshot.pnl ?: BigDecimal.ZERO

        // 用 currentValue - pnl 近似成本，从而反推出平均成本价
        val initialValue = currentValue.subtract(pnl)
        val avgPrice = if (quantity > BigDecimal.ZERO) {
            initialValue.divide(quantity, 8, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }
        val currentPrice = if (quantity > BigDecimal.ZERO) {
            currentValue.divide(quantity, 8, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }

        val percentPnl = snapshot.percentPnl
            ?: if (initialValue > BigDecimal.ZERO) {
                pnl.divide(initialValue, 6, RoundingMode.HALF_UP)
                    .multiply(BigDecimal("100"))
                    .setScale(2, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }

        return AccountPositionDto(
            accountId = account.id!!,
            accountName = account.accountName,
            walletAddress = account.walletAddress,
            proxyAddress = account.proxyAddress,
            marketId = snapshot.marketId ?: market?.marketId ?: "",
            marketTitle = snapshot.marketTitle,
            marketSlug = snapshot.marketSlug ?: market?.slug,
            eventSlug = snapshot.eventSlug ?: market?.eventSlug,
            marketIcon = snapshot.marketIcon ?: market?.icon,
            side = snapshot.side,
            outcomeIndex = null,
            quantity = quantity.toPlainString(),
            originalQuantity = snapshot.quantity.toPlainString(),
            avgPrice = avgPrice.setScale(4, RoundingMode.HALF_UP).toPlainString(),
            currentPrice = currentPrice.setScale(4, RoundingMode.HALF_UP).toPlainString(),
            currentValue = currentValue.setScale(4, RoundingMode.HALF_UP).toPlainString(),
            initialValue = initialValue.setScale(4, RoundingMode.HALF_UP).toPlainString(),
            pnl = pnl.setScale(4, RoundingMode.HALF_UP).toPlainString(),
            percentPnl = percentPnl.setScale(2, RoundingMode.HALF_UP).toPlainString(),
            realizedPnl = null,
            percentRealizedPnl = null,
            redeemable = false,
            mergeable = false,
            endDate = market?.endDate?.toString(),
            isCurrent = true
        )
    }

    private suspend fun calculateFromTradeRecords(account: Account): List<AccountPositionDto> {
        val records = bridgeTradeRecordRepository.findByBridgeIdAndStatus(bridgeId, "SUCCESS")
        if (records.isEmpty()) {
            return emptyList()
        }

        val grouped = records.groupBy { it.marketId to it.outcome }
        val positions = mutableListOf<AccountPositionDto>()

        grouped.forEach { (key, group) ->
            val (marketId, outcome) = key
            val outcomeIndex = group.firstNotNullOfOrNull { it.outcomeIndex }
            val marketTitle = group.firstNotNullOfOrNull { it.marketTitle } ?: ""
            val marketSlug = extractMarketSlug(group)

            val buyRecords = group.filter { it.side.equals("BUY", ignoreCase = true) }
            val sellRecords = group.filter { it.side.equals("SELL", ignoreCase = true) }

            val buyQuantity = buyRecords.fold(BigDecimal.ZERO) { acc, r -> acc + r.quantity }
            val sellQuantity = sellRecords.fold(BigDecimal.ZERO) { acc, r -> acc + r.quantity }
            val netQuantity = buyQuantity.subtract(sellQuantity)

            if (netQuantity <= BigDecimal.ZERO) {
                return@forEach
            }

            val totalBuyAmount = buyRecords.fold(BigDecimal.ZERO) { acc, r -> acc + r.amount }
            val avgPrice = if (buyQuantity > BigDecimal.ZERO) {
                totalBuyAmount.divide(buyQuantity, 8, RoundingMode.HALF_UP)
            } else {
                group.firstOrNull()?.price ?: BigDecimal.ZERO
            }

            val currentPrice = try {
                if (outcomeIndex != null) {
                    marketPriceService.getCurrentMarketPrice(marketId, outcomeIndex)
                } else {
                    avgPrice
                }
            } catch (e: Exception) {
                logger.warn("获取 Bridge 仓位实时价格失败: $marketId/$outcomeIndex, 使用成本价兜底: ${e.message}")
                avgPrice
            }

            val initialValue = netQuantity.multiply(avgPrice)
            val currentValue = netQuantity.multiply(currentPrice)
            val pnl = currentValue.subtract(initialValue)
            val percentPnl = if (initialValue > BigDecimal.ZERO) {
                pnl.divide(initialValue, 6, RoundingMode.HALF_UP)
                    .multiply(BigDecimal("100"))
                    .setScale(2, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }

            positions.add(
                AccountPositionDto(
                    accountId = account.id!!,
                    accountName = account.accountName,
                    walletAddress = account.walletAddress,
                    proxyAddress = account.proxyAddress,
                    marketId = marketId,
                    marketTitle = marketTitle,
                    marketSlug = marketSlug,
                    eventSlug = null,
                    marketIcon = null,
                    side = outcome ?: "",
                    outcomeIndex = outcomeIndex,
                    quantity = netQuantity.setScale(4, RoundingMode.DOWN).toPlainString(),
                    originalQuantity = netQuantity.toPlainString(),
                    avgPrice = avgPrice.setScale(4, RoundingMode.HALF_UP).toPlainString(),
                    currentPrice = currentPrice.setScale(4, RoundingMode.HALF_UP).toPlainString(),
                    currentValue = currentValue.setScale(4, RoundingMode.HALF_UP).toPlainString(),
                    initialValue = initialValue.setScale(4, RoundingMode.HALF_UP).toPlainString(),
                    pnl = pnl.setScale(4, RoundingMode.HALF_UP).toPlainString(),
                    percentPnl = percentPnl.toPlainString(),
                    realizedPnl = null,
                    percentRealizedPnl = null,
                    redeemable = false,
                    mergeable = false,
                    endDate = null,
                    isCurrent = true
                )
            )
        }

        return positions
    }

    private fun extractMarketSlug(records: List<com.wrbug.polymarketbot.entity.BridgeTradeRecord>): String? {
        return records.firstNotNullOfOrNull { record ->
            record.rawPayload?.let { raw ->
                try {
                    val payload = gson.fromJson(raw, Map::class.java)
                    payload?.get("marketSlug") as? String
                } catch (e: Exception) {
                    null
                }
            }
        }
    }
}
