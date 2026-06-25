package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchActivityMetricProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

data class LeaderResearchActivityScoreComputation(
    val score: LeaderResearchScore,
    val totalScore: BigDecimal,
    val riskFlags: List<String>,
    val reason: String,
    val category: String
)

@Service
class LeaderResearchActivityScoringService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val scoreRepository: LeaderResearchScoreRepository
) {
    @Transactional
    fun scoreActivityPrescreen(request: LeaderResearchActivityScoreRequest): LeaderResearchActivityScoreResponse {
        val states = request.states
            .mapNotNull { runCatching { LeaderResearchState.valueOf(it.uppercase()) }.getOrNull() }
            .ifEmpty { listOf(LeaderResearchState.DISCOVERED, LeaderResearchState.CANDIDATE) }
        val candidates = candidateRepository.findByResearchStateIn(states).associateBy { it.id }
        val metrics = candidateRepository.aggregateActivityMetrics(states.map { it.name })
        val riskCounts = linkedMapOf<String, Int>()
        val categoryCounts = linkedMapOf<String, Int>()
        var scored = 0
        var skipped = 0

        metrics.forEach { metric ->
            val candidate = candidates[metric.getCandidateId()]
            if (candidate == null) {
                skipped += 1
                return@forEach
            }
            if (!request.force && candidate.scoreVersion == SCORE_VERSION) {
                skipped += 1
                return@forEach
            }

            val computed = compute(candidate, metric, runId = null)
            val savedScore = scoreRepository.save(computed.score)
            val now = System.currentTimeMillis()
            candidateRepository.save(
                candidate.copy(
                    score = savedScore.totalScore,
                    scoreVersion = savedScore.scoreVersion,
                    reason = computed.reason,
                    riskFlags = computed.riskFlags.joinToString(",").ifBlank { null },
                    lastScoredAt = now,
                    updatedAt = now
                )
            )
            scored += 1
            computed.riskFlags.forEach { riskCounts[it] = (riskCounts[it] ?: 0) + 1 }
            categoryCounts[computed.category] = (categoryCounts[computed.category] ?: 0) + 1
        }

        return LeaderResearchActivityScoreResponse(
            scoreVersion = SCORE_VERSION,
            scannedCount = metrics.size,
            scoredCount = scored,
            skippedCount = skipped,
            riskFlagCounts = riskCounts,
            categoryCounts = categoryCounts
        )
    }

    fun compute(
        candidate: LeaderResearchCandidate,
        metric: LeaderResearchActivityMetricProjection,
        runId: Long?
    ): LeaderResearchActivityScoreComputation {
        val totalEvents = metric.getTotalEvents()
        val distinctMarkets = metric.getDistinctMarkets()
        val buyEvents = metric.getBuyEvents()
        val sellEvents = metric.getSellEvents()
        val usablePaperEvents = metric.getUsablePaperEvents()
        val safePriceEvents = metric.getSafePriceEvents()
        val tailPriceEvents = metric.getTailPriceEvents()
        val avgAmount = metric.getAvgAmount() ?: BigDecimal.ZERO
        val totalAmount = metric.getTotalAmount() ?: BigDecimal.ZERO
        val categoryEvidence = LeaderResearchCategoryEvidenceClassifier.classify(candidate.sourceEvidence, candidate.source)
        val category = categoryEvidence.category
        val now = System.currentTimeMillis()
        val ageMs = metric.getLastEventTime()?.let { now - it }

        val safePriceRatio = ratio(safePriceEvents, totalEvents)
        val usablePaperRatio = ratio(usablePaperEvents, totalEvents)
        val tailPriceRatio = ratio(tailPriceEvents, totalEvents)
        val sellRatio = ratio(sellEvents, totalEvents)

        val repeatability = when {
            totalEvents >= 100 -> BigDecimal("20")
            totalEvents >= 50 -> BigDecimal("16")
            totalEvents >= 20 -> BigDecimal("12")
            else -> BigDecimal(totalEvents).multiply(BigDecimal("0.50")).clamp(BigDecimal.ZERO, BigDecimal("10"))
        }
        val liquidityFit = BigDecimal(distinctMarkets).multiply(BigDecimal("2")).clamp(BigDecimal.ZERO, BigDecimal("15"))
        val entryPriceFit = safePriceRatio.multiply(BigDecimal("15")).clamp(BigDecimal.ZERO, BigDecimal("15"))
        val slippageRisk = when {
            avgAmount >= BigDecimal("2") -> BigDecimal("10")
            avgAmount >= BigDecimal.ONE -> BigDecimal("7")
            avgAmount >= BigDecimal("0.50") -> BigDecimal("3")
            else -> BigDecimal.ZERO
        }
        val holdingPeriodFit = when {
            sellEvents >= 5 && sellRatio >= BigDecimal("0.10") && sellRatio <= BigDecimal("0.70") -> BigDecimal("10")
            sellEvents > 0 -> BigDecimal("5")
            else -> BigDecimal.ZERO
        }
        val marketTypeRisk = when (category) {
            "politics", "finance" -> BigDecimal("10")
            "sports", "crypto" -> BigDecimal("6")
            else -> BigDecimal("2")
        }
        val drawdownRisk = usablePaperRatio.multiply(BigDecimal("15")).clamp(BigDecimal.ZERO, BigDecimal("15"))
        val exitLiquidityRisk = BigDecimal(sellEvents).multiply(BigDecimal("0.5")).clamp(BigDecimal.ZERO, BigDecimal("5"))
        val dataFreshness = when {
            ageMs == null -> BigDecimal.ZERO
            ageMs <= FRESH_7D_MS -> BigDecimal("10")
            ageMs <= FRESH_30D_MS -> BigDecimal("5")
            else -> BigDecimal.ZERO
        }
        val filterPassRate = BigDecimal("5").subtract(tailPriceRatio.multiply(BigDecimal("5"))).clamp(BigDecimal.ZERO, BigDecimal("5"))

        val rawScore = listOf(
            repeatability,
            liquidityFit,
            entryPriceFit,
            slippageRisk,
            holdingPeriodFit,
            marketTypeRisk,
            drawdownRisk,
            exitLiquidityRisk,
            dataFreshness,
            filterPassRate
        ).fold(BigDecimal.ZERO, BigDecimal::add).clamp(BigDecimal.ZERO, BigDecimal("100"))

        val flags = riskFlags(
            category = category,
            totalEvents = totalEvents,
            distinctMarkets = distinctMarkets,
            buyEvents = buyEvents,
            sellEvents = sellEvents,
            safePriceRatio = safePriceRatio,
            tailPriceRatio = tailPriceRatio,
            avgAmount = avgAmount,
            ageMs = ageMs,
            candidate = candidate,
            categoryEvidence = categoryEvidence
        )
        val capped = applyRiskCaps(rawScore, flags).setScale(8, RoundingMode.HALF_UP)
        val reason = listOf(
            "score_v1=$capped",
            "activity_events=$totalEvents",
            "distinct_markets=$distinctMarkets",
            "buy_events=$buyEvents",
            "sell_events=$sellEvents",
            "safe_price_ratio=${safePriceRatio.format4()}",
            "tail_price_ratio=${tailPriceRatio.format4()}",
            "usable_paper_ratio=${usablePaperRatio.format4()}",
            "avg_amount=${avgAmount.setScale(4, RoundingMode.HALF_UP)}",
            "total_amount=${totalAmount.setScale(4, RoundingMode.HALF_UP)}",
            "category=$category",
            "category_mix=${categoryEvidence.counts}",
            "category_dominance=${BigDecimal.valueOf(categoryEvidence.dominantRatio).format4()}",
            "activity_prescreen=true"
        ).joinToString("; ")

        return LeaderResearchActivityScoreComputation(
            score = LeaderResearchScore(
                candidateId = candidate.id ?: 0,
                runId = runId,
                scoreVersion = SCORE_VERSION,
                totalScore = capped,
                profitSignal = BigDecimal.ZERO,
                repeatability = repeatability,
                liquidityFit = liquidityFit,
                entryPriceFit = entryPriceFit,
                slippageRisk = slippageRisk,
                holdingPeriodFit = holdingPeriodFit,
                marketTypeRisk = marketTypeRisk,
                drawdownRisk = drawdownRisk,
                exitLiquidityRisk = exitLiquidityRisk,
                dataFreshness = dataFreshness,
                filterPassRate = filterPassRate,
                sampleTradeCount = totalEvents.coerceAtMost(Int.MAX_VALUE.toLong()).toInt(),
                reason = reason,
                createdAt = System.currentTimeMillis()
            ),
            totalScore = capped,
            riskFlags = flags,
            reason = reason,
            category = category
        )
    }

    private fun riskFlags(
        category: String,
        totalEvents: Long,
        distinctMarkets: Long,
        buyEvents: Long,
        sellEvents: Long,
        safePriceRatio: BigDecimal,
        tailPriceRatio: BigDecimal,
        avgAmount: BigDecimal,
        ageMs: Long?,
        candidate: LeaderResearchCandidate,
        categoryEvidence: LeaderResearchCategoryEvidence
    ): List<String> {
        val flags = mutableListOf<String>()
        if (totalEvents == 0L) flags += "no_activity_sample"
        if (totalEvents in 1 until MIN_SAMPLE_EVENTS) flags += "small_sample"
        if (distinctMarkets in 1 until MIN_DISTINCT_MARKETS) flags += "low_market_diversity"
        if (sellEvents >= 10 && buyEvents == 0L) flags += "sell_only_no_entry"
        if (buyEvents >= 10 && sellEvents == 0L) flags += "buy_only_no_exit"
        if (tailPriceRatio >= BigDecimal("0.50") && totalEvents >= MIN_SAMPLE_EVENTS) flags += "tail_price_spray"
        if (avgAmount > BigDecimal.ZERO && avgAmount < BigDecimal("1.00")) flags += "low_average_size"
        if (safePriceRatio < BigDecimal("0.30") && totalEvents >= MIN_SAMPLE_EVENTS) flags += "low_safe_price_ratio"
        if (ageMs == null || ageMs > FRESH_30D_MS) flags += "stale_activity"
        if (category == "unknown") flags += "unknown_category"
        if (categoryEvidence.mixed) flags += "mixed_category_evidence"
        if (candidate.source.contains("SCANNER_POOL") && totalEvents < MIN_SAMPLE_EVENTS) flags += "scanner_pool_unverified"
        return flags.distinct()
    }

    private fun applyRiskCaps(score: BigDecimal, flags: List<String>): BigDecimal {
        var capped = score
        if ("no_activity_sample" in flags) capped = capped.min(BigDecimal("10"))
        if ("scanner_pool_unverified" in flags) capped = capped.min(BigDecimal("30"))
        if ("small_sample" in flags) capped = capped.min(BigDecimal("59"))
        if ("tail_price_spray" in flags) capped = capped.min(BigDecimal("20"))
        if ("buy_only_no_exit" in flags) capped = capped.min(BigDecimal("55"))
        if ("sell_only_no_entry" in flags) capped = capped.min(BigDecimal("55"))
        if ("low_safe_price_ratio" in flags) capped = capped.min(BigDecimal("50"))
        if ("mixed_category_evidence" in flags) capped = capped.min(BigDecimal("60"))
        return capped
    }

    private fun ratio(numerator: Long, denominator: Long): BigDecimal {
        if (denominator <= 0) return BigDecimal.ZERO
        return BigDecimal(numerator).divide(BigDecimal(denominator), 8, RoundingMode.HALF_UP)
    }

    private fun BigDecimal.clamp(min: BigDecimal, max: BigDecimal): BigDecimal {
        return when {
            this < min -> min
            this > max -> max
            else -> this
        }
    }

    private fun BigDecimal.format4(): String = setScale(4, RoundingMode.HALF_UP).toPlainString()

    companion object {
        const val SCORE_VERSION = "activity-prescreen-v1"
        private const val MIN_SAMPLE_EVENTS = 20L
        private const val MIN_DISTINCT_MARKETS = 5L
        private const val FRESH_7D_MS = 7L * 24 * 60 * 60 * 1000
        private const val FRESH_30D_MS = 30L * 24 * 60 * 60 * 1000
    }
}
