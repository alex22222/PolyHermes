package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.CopyOrderTrackingRepository
import com.wrbug.polymarketbot.repository.FilteredOrderRepository
import com.wrbug.polymarketbot.repository.SellMatchRecordRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

interface LeaderExecutionStatsService {
    fun scoreLeaderExecution(leaderId: Long, leaderAddress: String?, fallbackScore: BigDecimal): LeaderExecutionScoreResult
}

@Service
class RepositoryLeaderExecutionStatsService(
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val copyOrderTrackingRepository: CopyOrderTrackingRepository,
    private val filteredOrderRepository: FilteredOrderRepository,
    private val sellMatchRecordRepository: SellMatchRecordRepository
) : LeaderExecutionStatsService {

    override fun scoreLeaderExecution(
        leaderId: Long,
        leaderAddress: String?,
        fallbackScore: BigDecimal
    ): LeaderExecutionScoreResult {
        val bridgeStats = loadBridgeStats(leaderAddress)
        val stats = LeaderExecutionStats(
            buyCreatedCount = copyOrderTrackingRepository.countByLeaderId(leaderId),
            filteredBuyCount = filteredOrderRepository.countByLeaderIdAndSide(leaderId, "BUY"),
            filteredSellCount = filteredOrderRepository.countByLeaderIdAndSide(leaderId, "SELL"),
            matchedSellCount = sellMatchRecordRepository.countByLeaderId(leaderId),
            openBuyCount = copyOrderTrackingRepository.countOpenByLeaderId(leaderId),
            lossSellCount = sellMatchRecordRepository.countLossByLeaderId(leaderId),
            bridgeBuySuccessCount = bridgeStats.buySuccess,
            bridgeBuyFailedCount = bridgeStats.buyFailed,
            bridgeSellSuccessCount = bridgeStats.sellSuccess,
            bridgeSellFailedCount = bridgeStats.sellFailed
        )
        if (!stats.hasRealExecutionData) {
            return LeaderExecutionScoreResult(
                score = fallbackScore.clampScore(),
                riskFlags = emptyList(),
                stats = stats,
                source = "BACKTEST_FALLBACK"
            )
        }

        val successfulBuyCount = stats.buyCreatedCount + stats.bridgeBuySuccessCount
        val failedBuyCount = stats.filteredBuyCount + stats.bridgeBuyFailedCount
        val successfulSellCount = stats.matchedSellCount + stats.bridgeSellSuccessCount
        val failedSellCount = stats.filteredSellCount + stats.bridgeSellFailedCount
        val buySignals = successfulBuyCount + failedBuyCount
        val sellSignals = successfulSellCount + failedSellCount
        val buyPassRate = if (buySignals > 0) successfulBuyCount.ratioTo(buySignals) else BigDecimal.ZERO
        val sellPassRate = when {
            sellSignals > 0 -> successfulSellCount.ratioTo(sellSignals)
            successfulBuyCount > 0 -> BigDecimal("0.25")
            else -> BigDecimal.ZERO
        }
        val openRatio = if (successfulBuyCount > 0) {
            stats.openBuyCount.ratioTo(successfulBuyCount)
        } else {
            BigDecimal.ZERO
        }.clamp(BigDecimal.ZERO, BigDecimal.ONE)

        var score = BigDecimal.ZERO
            .add(buyPassRate.multiply(BigDecimal("45")))
            .add(sellPassRate.multiply(BigDecimal("40")))
            .add(BigDecimal.ONE.subtract(openRatio).multiply(BigDecimal("15")))

        if (stats.lossSellCount > 0 && successfulSellCount > 0) {
            val lossSellRatio = stats.lossSellCount.ratioTo(successfulSellCount)
            score = score.subtract(lossSellRatio.multiply(BigDecimal("8")))
        }

        val flags = mutableListOf<String>()
        if (stats.realSignalCount < MIN_REAL_SIGNALS_FOR_CONFIDENCE) {
            flags += "execution_small_sample"
            score = score.min(BigDecimal("60"))
        }
        if (successfulBuyCount == 0L && failedBuyCount > 0L) {
            flags += "buy_execution_blocked"
            score = score.min(BigDecimal("25"))
        } else if (failedBuyCount > successfulBuyCount) {
            flags += "buy_execution_weak"
        }
        if (sellSignals == 0L && successfulBuyCount > 0L) {
            flags += "sell_execution_unproven"
            score = score.min(BigDecimal("60"))
        } else if (failedSellCount > successfulSellCount) {
            flags += "sell_execution_weak"
            score = score.min(BigDecimal("45"))
        }
        if (openRatio >= BigDecimal("0.80") && successfulBuyCount >= MIN_REAL_SIGNALS_FOR_CONFIDENCE) {
            flags += "open_position_backlog"
            score = score.min(BigDecimal("50"))
        }

        return LeaderExecutionScoreResult(
            score = score.clampScore(),
            riskFlags = flags,
            stats = stats,
            source = "REAL_EXECUTION"
        )
    }

    private fun loadBridgeStats(leaderAddress: String?): BridgeExecutionStats {
        if (leaderAddress.isNullOrBlank()) return BridgeExecutionStats()
        return BridgeExecutionStats(
            buySuccess = bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                leaderAddress,
                "BUY",
                "SUCCESS"
            ),
            buyFailed = bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                leaderAddress,
                "BUY",
                "FAILED"
            ),
            sellSuccess = bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                leaderAddress,
                "SELL",
                "SUCCESS"
            ),
            sellFailed = bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                leaderAddress,
                "SELL",
                "FAILED"
            )
        )
    }

    private fun Long.ratioTo(total: Long): BigDecimal {
        if (total <= 0) return BigDecimal.ZERO
        return BigDecimal(this).divide(BigDecimal(total), 6, RoundingMode.HALF_UP)
    }

    private fun BigDecimal.clampScore(): BigDecimal = clamp(BigDecimal.ZERO, BigDecimal("100"))

    private fun BigDecimal.clamp(min: BigDecimal, max: BigDecimal): BigDecimal {
        return when {
            this < min -> min
            this > max -> max
            else -> this
        }
    }

    companion object {
        private const val MIN_REAL_SIGNALS_FOR_CONFIDENCE = 3L
    }
}

data class BridgeExecutionStats(
    val buySuccess: Long = 0,
    val buyFailed: Long = 0,
    val sellSuccess: Long = 0,
    val sellFailed: Long = 0
)

data class LeaderExecutionStats(
    val buyCreatedCount: Long,
    val filteredBuyCount: Long,
    val filteredSellCount: Long,
    val matchedSellCount: Long,
    val openBuyCount: Long,
    val lossSellCount: Long,
    val bridgeBuySuccessCount: Long = 0,
    val bridgeBuyFailedCount: Long = 0,
    val bridgeSellSuccessCount: Long = 0,
    val bridgeSellFailedCount: Long = 0
) {
    val realSignalCount: Long = buyCreatedCount +
        filteredBuyCount +
        filteredSellCount +
        matchedSellCount +
        bridgeBuySuccessCount +
        bridgeBuyFailedCount +
        bridgeSellSuccessCount +
        bridgeSellFailedCount
    val hasRealExecutionData: Boolean = realSignalCount > 0
}

data class LeaderExecutionScoreResult(
    val score: BigDecimal,
    val riskFlags: List<String>,
    val stats: LeaderExecutionStats,
    val source: String
)
