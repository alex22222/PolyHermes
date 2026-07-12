package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.Instant
import java.time.ZoneId

data class PortfolioRiskDailyMetrics(
    val dayStartAt: Long,
    val lossPercent: BigDecimal?,
    val baselineType: String?,
    val successfulBuyCount: Long,
    val orderCountComplete: Boolean
)

@Service
class PortfolioRiskDailyMetricsService(
    private val dailyRepository: DailyAssetSnapshotRepository,
    private val tradeRepository: BridgeTradeRecordRepository
) {
    fun calculate(
        accountId: Long,
        walletAddress: String,
        currentTotalAssets: BigDecimal?,
        now: Long = System.currentTimeMillis()
    ): PortfolioRiskDailyMetrics {
        val dayStart = Instant.ofEpochMilli(now).atZone(ZONE_ID).toLocalDate().atStartOfDay(ZONE_ID).toInstant().toEpochMilli()
        val snapshot = dailyRepository.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc(BRIDGE_ID, walletAddress.lowercase())
            .firstOrNull { it.dayStartAt == dayStart }
        val baseline = snapshot?.totalAssets?.takeIf { snapshot.valuationStatus == "COMPLETE" }
        val lossPercent = if (baseline != null && baseline > BigDecimal.ZERO && currentTotalAssets != null) {
            baseline.subtract(currentTotalAssets).max(BigDecimal.ZERO)
                .multiply(BigDecimal("100")).divide(baseline, 4, RoundingMode.HALF_UP)
        } else null
        return PortfolioRiskDailyMetrics(
            dayStartAt = dayStart,
            lossPercent = lossPercent,
            baselineType = snapshot?.snapshotType,
            successfulBuyCount = tradeRepository.countScopedSuccessBuysSince(BRIDGE_ID, accountId, dayStart),
            orderCountComplete = tradeRepository.countUnscopedSuccessBuysSince(BRIDGE_ID, dayStart) == 0L
        )
    }

    companion object {
        private const val BRIDGE_ID = "polymtrade-bridge"
        private val ZONE_ID = ZoneId.of("Asia/Shanghai")
    }
}
