package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.entity.BacktestTask
import com.wrbug.polymarketbot.repository.BacktestTaskRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * 将 Leader 研究模块的 copyability 评分思路适配到 copy_trading_leaders 表。
 *
 * 基于 LeaderScannerService 已计算出的字段（totalTrades / winRate / totalPnl /
 * activityScore / smartMoneyRank / lastTradeAt / totalVolume）计算一个 0-100 的研究
 * 评分和标签，用于在 Leader 列表中快速识别高质量地址。
 *
 * 评分逻辑强调稳健性：
 * - 高盈利但数据陈旧或波动过大时会被降档
 * - 负盈利、低胜率、小样本均有额外惩罚
 * - 标签上限避免短期爆发型地址被评为 ELITE
 */
@Service
class LeaderResearchScoreAdapterService(
    private val leaderRepository: LeaderRepository,
    private val backtestTaskRepository: BacktestTaskRepository
) {

    private val logger = LoggerFactory.getLogger(LeaderResearchScoreAdapterService::class.java)

    /**
     * 为所有 Leader 重新计算研究评分。
     * @return 被更新的 Leader 数量
     */
    @Transactional
    fun scoreAllLeaders(): Int {
        val leaders = leaderRepository.findAll()
        var updated = 0
        val now = System.currentTimeMillis()
        for (leader in leaders) {
            try {
                val result = computeScore(leader, now)
                leaderRepository.save(
                    leader.copy(
                        researchScore = result.score,
                        researchTag = result.tag,
                        researchRiskFlags = result.riskFlags,
                        researchScoredAt = now,
                        updatedAt = now
                    )
                )
                updated++
            } catch (e: Exception) {
                logger.warn("为 Leader {} 计算研究评分失败: {}", leader.id, e.message)
            }
        }
        logger.info("Leader 研究评分完成，共更新 {} / {} 条", updated, leaders.size)
        return updated
    }

    /**
     * 为单个 Leader 计算研究评分。
     */
    fun computeScore(leader: Leader, now: Long = System.currentTimeMillis()): LeaderResearchScoreResult {
        val pnl = leader.totalPnl?.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val trades = leader.totalTrades ?: 0
        val winRate = leader.winRate?.toDouble() ?: 0.0
        val activityScore = leader.activityScore?.toDouble() ?: 0.0
        val rank = leader.smartMoneyRank
        val lastTradeAt = leader.lastTradeAt
        val volume = leader.totalVolume?.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val avgTradeSize = leader.avgTradeSize?.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val bestCompletedBacktest = leader.id?.let { loadBestCompletedBacktest(it) }

        // 1. 盈利信号 (0-20)
        val profitSignal = when {
            pnl > BigDecimal("10") -> BigDecimal("20")
            pnl > BigDecimal.ZERO -> pnl.multiply(BigDecimal("2")).clamp(BigDecimal.ZERO, BigDecimal("20"))
            else -> BigDecimal.ZERO
        }

        // 2. 重复性 (0-15)
        val repeatability = BigDecimal(trades).multiply(BigDecimal("1.5"))
            .clamp(BigDecimal.ZERO, BigDecimal("15"))

        // 3. 胜率 (0-15)
        val winRateScore = BigDecimal(winRate).multiply(BigDecimal("0.15"))
            .clamp(BigDecimal.ZERO, BigDecimal("15"))

        // 4. 活跃度 (0-10)
        val activityFit = BigDecimal(activityScore).multiply(BigDecimal("0.1"))
            .clamp(BigDecimal.ZERO, BigDecimal("10"))

        // 5. 聪明钱排名 (0-10)
        val rankScore = when {
            rank != null && rank <= 3 -> BigDecimal("10")
            rank != null && rank <= 6 -> BigDecimal("7")
            rank != null && rank <= 10 -> BigDecimal("5")
            else -> BigDecimal.ZERO
        }

        // 6. 样本充足度 (0-5)
        val sampleScore = if (trades >= MIN_TRADES_FOR_FULL_SCORE) BigDecimal("5") else BigDecimal.ZERO

        // 7. 数据新鲜度 (0-5)
        val isFresh = lastTradeAt != null && (now - lastTradeAt) <= SOURCE_FRESH_MS
        val dataFreshness = if (isFresh) BigDecimal("5") else BigDecimal.ZERO

        // 8. 盈亏波动风险 (0-10)：pnl 占 volume 比例过大时扣分
        val pnlRatio = if (volume > BigDecimal.ZERO) {
            pnl.abs().divide(volume, 4, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }
        val volatilityRisk = when {
            pnlRatio > BigDecimal("0.50") -> BigDecimal("2")
            pnlRatio > BigDecimal("0.25") -> BigDecimal("5")
            else -> BigDecimal("10")
        }

        val rawTotal = listOf(
            profitSignal,
            repeatability,
            winRateScore,
            activityFit,
            rankScore,
            sampleScore,
            dataFreshness,
            volatilityRisk
        ).fold(BigDecimal.ZERO, BigDecimal::add)
            .setScale(4, RoundingMode.HALF_UP)

        // 小样本封顶（借鉴研究模块思路）
        val sampleCapApplied = trades < MIN_TRADES_FOR_FULL_SCORE && rawTotal > SAMPLE_CAP
        val afterSampleCap = if (sampleCapApplied) SAMPLE_CAP else rawTotal

        // 风险标记
        val flags = mutableListOf<String>()
        if (trades < MIN_TRADES_FOR_FULL_SCORE) flags += "small_sample"
        if (pnl < BigDecimal.ZERO) flags += "negative_pnl"
        if (winRate > 0 && winRate < 40) flags += "low_win_rate"
        if (!isFresh) flags += "stale_data"
        if (pnlRatio > BigDecimal("0.50")) flags += "high_pnl_volatility"
        appendBacktestRiskFlags(bestCompletedBacktest, flags)
        if (isTailPriceSpray(trades, avgTradeSize, flags)) flags += "tail_price_spray"

        // 风险调整：根据风险标记对分数进行乘数惩罚并限制最高标签
        val riskMultiplier = computeRiskMultiplier(flags)
        val tagCap = computeTagCap(flags)

        val adjustedScore = afterSampleCap.multiply(riskMultiplier)
            .setScale(4, RoundingMode.HALF_UP)

        val finalScore = capScoreByTag(adjustedScore, tagCap)
        val tag = scoreToTag(finalScore)
        val riskFlags = flags.takeIf { it.isNotEmpty() }?.joinToString(",")

        return LeaderResearchScoreResult(
            score = finalScore,
            tag = tag,
            riskFlags = riskFlags
        )
    }

    /**
     * 根据风险标记计算综合风险乘数。
     */
    private fun computeRiskMultiplier(flags: List<String>): BigDecimal {
        var multiplier = BigDecimal.ONE
        if (flags.contains("negative_pnl")) multiplier = multiplier.multiply(BigDecimal("0.65"))
        if (flags.contains("stale_data")) multiplier = multiplier.multiply(BigDecimal("0.75"))
        if (flags.contains("high_pnl_volatility")) multiplier = multiplier.multiply(BigDecimal("0.85"))
        if (flags.contains("low_win_rate")) multiplier = multiplier.multiply(BigDecimal("0.90"))
        if (flags.contains("small_sample")) multiplier = multiplier.multiply(BigDecimal("0.95"))
        if (flags.contains("no_completed_backtest")) multiplier = multiplier.multiply(BigDecimal("0.75"))
        if (flags.contains("backtest_no_simulated_trades")) multiplier = multiplier.multiply(BigDecimal("0.50"))
        if (flags.contains("tail_price_spray")) multiplier = multiplier.multiply(BigDecimal("0.20"))
        if (flags.contains("backtest_loss")) multiplier = multiplier.multiply(BigDecimal("0.35"))
        if (flags.contains("backtest_dust_profit")) multiplier = multiplier.multiply(BigDecimal("0.55"))
        if (flags.contains("backtest_high_drawdown")) multiplier = multiplier.multiply(BigDecimal("0.70"))
        if (flags.contains("backtest_no_sell")) multiplier = multiplier.multiply(BigDecimal("0.80"))
        return multiplier
    }

    /**
     * 根据风险标记限制最高可获得标签。
     */
    private fun computeTagCap(flags: List<String>): TagCap {
        return when {
            flags.contains("tail_price_spray") -> TagCap.RISKY
            flags.contains("backtest_loss") -> TagCap.WATCH
            flags.contains("backtest_no_simulated_trades") -> TagCap.WATCH
            flags.contains("backtest_dust_profit") -> TagCap.WATCH
            flags.contains("no_completed_backtest") -> TagCap.CANDIDATE
            flags.contains("backtest_high_drawdown") -> TagCap.CANDIDATE
            flags.contains("backtest_no_sell") -> TagCap.CANDIDATE
            flags.contains("negative_pnl") -> TagCap.WATCH
            flags.contains("small_sample") -> TagCap.CANDIDATE
            flags.contains("stale_data") && flags.contains("high_pnl_volatility") -> TagCap.CANDIDATE
            flags.contains("stale_data") -> TagCap.TRADEABLE
            flags.contains("high_pnl_volatility") -> TagCap.TRADEABLE
            else -> TagCap.ELITE
        }
    }

    private fun loadBestCompletedBacktest(leaderId: Long): BacktestTask? {
        return backtestTaskRepository.findByLeaderIdAndStatus(leaderId, "COMPLETED")
            .maxWithOrNull(
                compareBy<BacktestTask> { it.profitAmount ?: BigDecimal.ZERO }
                    .thenBy { it.profitRate ?: BigDecimal.ZERO }
                    .thenBy { it.createdAt }
            )
    }

    private fun appendBacktestRiskFlags(bestBacktest: BacktestTask?, flags: MutableList<String>) {
        if (bestBacktest == null) {
            flags += "no_completed_backtest"
            return
        }

        val profit = bestBacktest.profitAmount ?: BigDecimal.ZERO
        val drawdown = bestBacktest.maxDrawdown ?: BigDecimal.ZERO

        when {
            bestBacktest.totalTrades <= 0 -> flags += "backtest_no_simulated_trades"
            profit < BigDecimal.ZERO -> flags += "backtest_loss"
            profit < MIN_COPYABLE_BACKTEST_PROFIT -> flags += "backtest_dust_profit"
        }

        if (drawdown > MAX_ACCEPTABLE_BACKTEST_DRAWDOWN) {
            flags += "backtest_high_drawdown"
        }
        if (bestBacktest.totalTrades >= MIN_BACKTEST_TRADES_FOR_SELL_CHECK && bestBacktest.sellTrades <= 0) {
            flags += "backtest_no_sell"
        }
    }

    private fun isTailPriceSpray(trades: Int, avgTradeSize: BigDecimal, flags: List<String>): Boolean {
        return trades >= MIN_TAIL_SPRAY_TRADES &&
            avgTradeSize > BigDecimal.ZERO &&
            avgTradeSize <= MAX_TAIL_SPRAY_AVG_TRADE_SIZE &&
            (
                flags.contains("backtest_no_simulated_trades") ||
                    flags.contains("backtest_dust_profit") ||
                    flags.contains("high_pnl_volatility")
                )
    }

    /**
     * 将分数限制在指定标签上限以下。
     */
    private fun capScoreByTag(score: BigDecimal, cap: TagCap): BigDecimal {
        val maxScore = when (cap) {
            TagCap.ELITE -> BigDecimal("100")
            TagCap.TRADEABLE -> BigDecimal("59.99")
            TagCap.CANDIDATE -> BigDecimal("44.99")
            TagCap.WATCH -> BigDecimal("29.99")
            TagCap.RISKY -> BigDecimal("14.99")
        }
        return score.min(maxScore)
    }

    private fun scoreToTag(score: BigDecimal): String {
        return when {
            score >= BigDecimal("60") -> "ELITE"
            score >= BigDecimal("45") -> "TRADEABLE"
            score >= BigDecimal("30") -> "CANDIDATE"
            score >= BigDecimal("15") -> "WATCH"
            else -> "RISKY"
        }
    }

    private fun BigDecimal.clamp(min: BigDecimal, max: BigDecimal): BigDecimal {
        return when {
            this < min -> min
            this > max -> max
            else -> this
        }
    }

    data class LeaderResearchScoreResult(
        val score: BigDecimal,
        val tag: String,
        val riskFlags: String?
    )

    private enum class TagCap {
        ELITE, TRADEABLE, CANDIDATE, WATCH, RISKY
    }

    companion object {
        private const val MIN_TRADES_FOR_FULL_SCORE = 10
        private const val MIN_TAIL_SPRAY_TRADES = 10
        private const val MIN_BACKTEST_TRADES_FOR_SELL_CHECK = 10
        private val SAMPLE_CAP = BigDecimal("59")
        private val MIN_COPYABLE_BACKTEST_PROFIT = BigDecimal("0.50")
        private val MAX_TAIL_SPRAY_AVG_TRADE_SIZE = BigDecimal("1.00")
        private val MAX_ACCEPTABLE_BACKTEST_DRAWDOWN = BigDecimal("30")
        private const val SOURCE_FRESH_MS = 48L * 60 * 60 * 1000
    }
}
