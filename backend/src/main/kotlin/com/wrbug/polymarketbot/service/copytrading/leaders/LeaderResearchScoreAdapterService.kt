package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.repository.LeaderRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * 将 Leader 研究模块的 copyability 评分思路适配到 copy_trading_leaders 表。
 *
 * 由于 Leader 行没有 paper session，这里基于 LeaderScannerService 已计算出的
 * 字段（totalTrades / winRate / totalPnl / activityScore / smartMoneyRank / lastTradeAt）
 * 计算一个 0-100 的研究评分和标签，用于在 Leader 列表中快速识别高质量地址。
 */
@Service
class LeaderResearchScoreAdapterService(
    private val leaderRepository: LeaderRepository
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
        val sampleScore = if (trades >= 10) BigDecimal("5") else BigDecimal.ZERO

        // 7. 数据新鲜度 (0-5)
        val dataFreshness = if (lastTradeAt != null && (now - lastTradeAt) <= SOURCE_FRESH_MS) {
            BigDecimal("5")
        } else {
            BigDecimal.ZERO
        }

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
        val total = if (sampleCapApplied) SAMPLE_CAP else rawTotal

        // 风险标记
        val flags = mutableListOf<String>()
        if (trades < MIN_TRADES_FOR_FULL_SCORE) flags += "small_sample"
        if (pnl < BigDecimal.ZERO) flags += "negative_pnl"
        if (winRate > 0 && winRate < 40) flags += "low_win_rate"
        if (lastTradeAt == null || (now - lastTradeAt) > SOURCE_FRESH_MS) flags += "stale_data"
        if (pnlRatio > BigDecimal("0.50")) flags += "high_pnl_volatility"

        val tag = scoreToTag(total)
        val riskFlags = flags.takeIf { it.isNotEmpty() }?.joinToString(",")

        return LeaderResearchScoreResult(
            score = total,
            tag = tag,
            riskFlags = riskFlags
        )
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

    companion object {
        private const val MIN_TRADES_FOR_FULL_SCORE = 10
        private val SAMPLE_CAP = BigDecimal("59")
        private const val SOURCE_FRESH_MS = 48L * 60 * 60 * 1000
    }
}
