package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchStrategyBackfillRequest
import com.wrbug.polymarketbot.dto.LeaderResearchStrategyBackfillResponse
import com.wrbug.polymarketbot.dto.LeaderResearchUnknownStrategySampleEnrichRequest
import com.wrbug.polymarketbot.dto.LeaderResearchUnknownStrategySampleEnrichResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchActivityMetricProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

data class LeaderResearchActivityScoreComputation(
    val score: LeaderResearchScore,
    val totalScore: BigDecimal,
    val riskFlags: List<String>,
    val reason: String,
    val category: String,
    val strategyType: String,
    val unknownStrategyReasons: List<String> = emptyList()
)

@Service
class LeaderResearchActivityScoringService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val scoreRepository: LeaderResearchScoreRepository
) {
    fun planUnknownStrategySampleEnrichment(
        request: LeaderResearchUnknownStrategySampleEnrichRequest
    ): LeaderResearchUnknownStrategySampleEnrichResponse {
        val categories = request.categories
            .map { it.trim().lowercase() }
            .filter { it in PRIMARY_CATEGORIES }
            .ifEmpty { PRIMARY_CATEGORIES }
            .toSet()
        val limit = request.limit.coerceIn(1, MAX_SAMPLE_ENRICH_LIMIT)
        val scanLimit = (limit * 10)
            .coerceAtLeast(MIN_SAMPLE_ENRICH_SCAN_LIMIT)
            .coerceAtMost(MAX_BACKFILL_LIMIT)
        val candidates = candidateRepository.findUnknownStrategyCandidates(
            listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY),
            PageRequest.of(0, scanLimit)
        )
        val candidatesById = candidates.mapNotNull { candidate -> candidate.id?.let { it to candidate } }.toMap()
        val metrics = if (candidatesById.isEmpty()) {
            emptyMap()
        } else {
            candidateRepository.aggregateActivityMetricsForCandidateIds(candidatesById.keys).associateBy { it.getCandidateId() }
        }
        val selected = candidates.mapNotNull { candidate ->
            val candidateId = candidate.id ?: return@mapNotNull null
            val metric = metrics[candidateId] ?: return@mapNotNull null
            val computed = compute(candidate, metric, runId = null)
            if (computed.category !in categories) return@mapNotNull null
            if ("activity_category_mismatch" in computed.unknownStrategyReasons) return@mapNotNull null
            if (computed.strategyType != LeaderResearchStrategyTypeClassifier.UNKNOWN) return@mapNotNull null
            if (computed.unknownStrategyReasons.none { it in SAMPLE_ENRICH_REASONS }) return@mapNotNull null
            UnknownStrategySampleCandidate(
                candidateId = candidateId,
                category = computed.category,
                reasons = computed.unknownStrategyReasons
            )
        }.take(limit)

        val categoryCounts = linkedMapOf<String, Int>()
        val reasonCounts = linkedMapOf<String, Int>()
        selected.forEach { item ->
            categoryCounts[item.category] = (categoryCounts[item.category] ?: 0) + 1
            item.reasons.forEach { reason ->
                reasonCounts[reason] = (reasonCounts[reason] ?: 0) + 1
            }
        }

        return LeaderResearchUnknownStrategySampleEnrichResponse(
            dryRun = request.dryRun,
            selectedCount = selected.size,
            selectedCandidateIds = selected.map { it.candidateId },
            categoryCounts = categoryCounts,
            unknownStrategyReasonCounts = reasonCounts
        )
    }

    @Transactional
    fun backfillUnknownStrategyTypes(request: LeaderResearchStrategyBackfillRequest): LeaderResearchStrategyBackfillResponse {
        val states = request.states
            .mapNotNull { runCatching { LeaderResearchState.valueOf(it.uppercase()) }.getOrNull() }
            .ifEmpty { listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY) }
        val limit = request.limit.coerceIn(1, MAX_BACKFILL_LIMIT)
        val selectedIds = candidateRepository.findUnknownStrategyCandidates(states, PageRequest.of(0, limit))
            .mapNotNull { it.id }
        val scoreResult = if (selectedIds.isEmpty()) {
            LeaderResearchActivityScoreResponse(
                scoreVersion = SCORE_VERSION,
                scannedCount = 0,
                scoredCount = 0,
                skippedCount = 0,
                riskFlagCounts = emptyMap(),
                categoryCounts = emptyMap()
            )
        } else {
            scoreActivityPrescreen(
                LeaderResearchActivityScoreRequest(
                    states = states.map { it.name },
                    force = request.force,
                    candidateIds = selectedIds
                )
            )
        }
        return LeaderResearchStrategyBackfillResponse(
            selectedCount = selectedIds.size,
            selectedCandidateIds = selectedIds,
            scoreResult = scoreResult
        )
    }

    @Transactional
    fun scoreActivityPrescreen(request: LeaderResearchActivityScoreRequest): LeaderResearchActivityScoreResponse {
        val states = request.states
            .mapNotNull { runCatching { LeaderResearchState.valueOf(it.uppercase()) }.getOrNull() }
            .ifEmpty { listOf(LeaderResearchState.DISCOVERED, LeaderResearchState.CANDIDATE) }
        val targetIds = request.candidateIds.distinct().filter { it > 0 }
        val targeted = targetIds.isNotEmpty()
        val candidateList = if (targeted) {
            candidateRepository.findAllById(targetIds).filter { it.researchState in states }
        } else {
            candidateRepository.findByResearchStateIn(states)
        }
        val candidates = candidateList.associateBy { it.id }
        val metrics = if (targeted) {
            if (candidateList.isEmpty()) emptyList() else candidateRepository.aggregateActivityMetricsForCandidateIds(candidateList.mapNotNull { it.id })
        } else {
            candidateRepository.aggregateActivityMetrics(states.map { it.name })
        }
        val riskCounts = linkedMapOf<String, Int>()
        val categoryCounts = linkedMapOf<String, Int>()
        val unknownStrategyReasonCounts = linkedMapOf<String, Int>()
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
                    strategyType = computed.strategyType,
                    lastScoredAt = now,
                    updatedAt = now
                )
            )
            scored += 1
            computed.riskFlags.forEach { riskCounts[it] = (riskCounts[it] ?: 0) + 1 }
            categoryCounts[computed.category] = (categoryCounts[computed.category] ?: 0) + 1
            computed.unknownStrategyReasons.forEach { reason ->
                unknownStrategyReasonCounts[reason] = (unknownStrategyReasonCounts[reason] ?: 0) + 1
            }
        }

        return LeaderResearchActivityScoreResponse(
            scoreVersion = SCORE_VERSION,
            scannedCount = metrics.size,
            scoredCount = scored,
            skippedCount = skipped,
            riskFlagCounts = riskCounts,
            categoryCounts = categoryCounts,
            unknownStrategyReasonCounts = unknownStrategyReasonCounts
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
        val activityCategoryEvidence = activityCategoryEvidence(metric)
        val activityCategoryMismatch = activityCategoryEvidence.isReliable &&
            categoryEvidence.category in KNOWN_CATEGORIES &&
            activityCategoryEvidence.category in KNOWN_CATEGORIES &&
            activityCategoryEvidence.category != categoryEvidence.category
        val category = if (activityCategoryEvidence.isReliable) {
            activityCategoryEvidence.category
        } else {
            categoryEvidence.category
        }
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

        val strategyType = LeaderResearchStrategyTypeClassifier.classify(
            totalEvents = totalEvents,
            distinctMarkets = distinctMarkets,
            buyEvents = buyEvents,
            sellEvents = sellEvents,
            safePriceRatio = safePriceRatio,
            tailPriceRatio = tailPriceRatio,
            avgAmount = avgAmount
        )
        val unknownStrategyReasons = if (strategyType.strategyType == LeaderResearchStrategyTypeClassifier.UNKNOWN) {
            unknownStrategyReasons(
                category = category,
                categoryEvidence = categoryEvidence,
                totalEvents = totalEvents,
                distinctMarkets = distinctMarkets,
                buyEvents = buyEvents,
                sellEvents = sellEvents,
                safePriceRatio = safePriceRatio,
                tailPriceRatio = tailPriceRatio,
                avgAmount = avgAmount,
                ageMs = ageMs,
                activityCategoryMismatch = activityCategoryMismatch
            )
        } else {
            emptyList()
        }

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
            categoryEvidence = categoryEvidence,
            activityCategoryMismatch = activityCategoryMismatch,
            strategyRiskFlags = strategyType.riskFlags
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
            "activity_category=${activityCategoryEvidence.category}",
            "activity_category_mix=${activityCategoryEvidence.counts}",
            "activity_category_dominance=${BigDecimal.valueOf(activityCategoryEvidence.dominantRatio).format4()}",
            strategyType.reason,
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
            category = category,
            strategyType = strategyType.strategyType,
            unknownStrategyReasons = unknownStrategyReasons
        )
    }

    private fun unknownStrategyReasons(
        category: String,
        categoryEvidence: LeaderResearchCategoryEvidence,
        totalEvents: Long,
        distinctMarkets: Long,
        buyEvents: Long,
        sellEvents: Long,
        safePriceRatio: BigDecimal,
        tailPriceRatio: BigDecimal,
        avgAmount: BigDecimal,
        ageMs: Long?,
        activityCategoryMismatch: Boolean
    ): List<String> {
        val sellRatio = ratio(sellEvents, totalEvents)
        val reasons = mutableListOf<String>()
        if (totalEvents < MIN_SAMPLE_EVENTS) reasons += "insufficient_sample"
        if (distinctMarkets < MIN_DISTINCT_MARKETS) reasons += "insufficient_market_diversity"
        if (buyEvents == 0L) reasons += "no_buy_sample"
        if (sellEvents == 0L) reasons += "no_sell_sample"
        if (sellEvents > 0 && sellRatio !in BigDecimal("0.10")..BigDecimal("0.70")) reasons += "sell_ratio_outside_copyable_range"
        if (safePriceRatio < BigDecimal("0.50")) reasons += "low_safe_price_ratio_for_directional"
        if (tailPriceRatio >= BigDecimal("0.30")) reasons += "high_tail_price_ratio"
        if (avgAmount > BigDecimal.ZERO && avgAmount < BigDecimal("1.00")) reasons += "low_average_size"
        if (category == "unknown") reasons += "unknown_category"
        if (categoryEvidence.mixed) reasons += "mixed_category_evidence"
        if (activityCategoryMismatch) reasons += "activity_category_mismatch"
        if (ageMs == null || ageMs > FRESH_30D_MS) reasons += "stale_or_missing_activity"
        return reasons.ifEmpty { listOf("unclassified_pattern") }.distinct()
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
        categoryEvidence: LeaderResearchCategoryEvidence,
        activityCategoryMismatch: Boolean,
        strategyRiskFlags: List<String> = emptyList()
    ): List<String> {
        val flags = mutableListOf<String>()
        val sellRatio = ratio(sellEvents, totalEvents)
        if (totalEvents == 0L) flags += "no_activity_sample"
        if (totalEvents in 1 until MIN_SAMPLE_EVENTS) flags += "small_sample"
        if (distinctMarkets in 1 until MIN_DISTINCT_MARKETS) flags += "low_market_diversity"
        if (sellEvents >= 10 && buyEvents == 0L) flags += "sell_only_no_entry"
        if (buyEvents >= 10 && sellEvents == 0L) flags += "buy_only_no_exit"
        if (buyEvents >= 20 && sellRatio < BigDecimal("0.10")) flags += "weak_exit_sample"
        if (tailPriceRatio >= BigDecimal("0.50") && totalEvents >= MIN_SAMPLE_EVENTS) flags += "tail_price_spray"
        if (avgAmount > BigDecimal.ZERO && avgAmount < BigDecimal("1.00")) flags += "low_average_size"
        if (safePriceRatio < BigDecimal("0.30") && totalEvents >= MIN_SAMPLE_EVENTS) flags += "low_safe_price_ratio"
        if (ageMs == null || ageMs > FRESH_30D_MS) flags += "stale_activity"
        if (category == "unknown") flags += "unknown_category"
        if (categoryEvidence.mixed) flags += "mixed_category_evidence"
        if (activityCategoryMismatch) flags += "activity_category_mismatch"
        if (candidate.source.contains("SCANNER_POOL") && totalEvents < MIN_SAMPLE_EVENTS) flags += "scanner_pool_unverified"
        flags += strategyRiskFlags
        return flags.distinct()
    }

    private fun applyRiskCaps(score: BigDecimal, flags: List<String>): BigDecimal {
        var capped = score
        if ("no_activity_sample" in flags) capped = capped.min(BigDecimal("10"))
        if ("scanner_pool_unverified" in flags) capped = capped.min(BigDecimal("30"))
        if ("small_sample" in flags) capped = capped.min(BigDecimal("59"))
        if ("tail_price_spray" in flags) capped = capped.min(BigDecimal("20"))
        if ("strategy_low_price_tail_risk" in flags) capped = capped.min(BigDecimal("20"))
        if ("strategy_bot_hft" in flags) capped = capped.min(BigDecimal("55"))
        if ("strategy_market_maker_lp" in flags) capped = capped.min(BigDecimal("55"))
        if ("strategy_arbitrage" in flags) capped = capped.min(BigDecimal("55"))
        if ("strategy_rebalance_churn" in flags) capped = capped.min(BigDecimal("55"))
        if ("strategy_whale" in flags) capped = capped.min(BigDecimal("70"))
        if ("buy_only_no_exit" in flags) capped = capped.min(BigDecimal("55"))
        if ("sell_only_no_entry" in flags) capped = capped.min(BigDecimal("55"))
        if ("weak_exit_sample" in flags) capped = capped.min(BigDecimal("55"))
        if ("low_safe_price_ratio" in flags) capped = capped.min(BigDecimal("50"))
        if ("mixed_category_evidence" in flags) capped = capped.min(BigDecimal("60"))
        if ("activity_category_mismatch" in flags) capped = capped.min(BigDecimal("50"))
        return capped
    }

    private fun activityCategoryEvidence(metric: LeaderResearchActivityMetricProjection): ActivityCategoryEvidence {
        val counts = linkedMapOf(
            "politics" to metric.getPoliticsEvents(),
            "finance" to metric.getFinanceEvents(),
            "sports" to metric.getSportsEvents(),
            "crypto" to metric.getCryptoEvents()
        ).filterValues { it > 0 }
        val total = counts.values.sum()
        val dominant = counts.maxWithOrNull(compareBy<Map.Entry<String, Long>> { it.value }.thenBy { priority(it.key) })
        val ratio = if (total > 0 && dominant != null) dominant.value.toDouble() / total.toDouble() else 0.0
        return ActivityCategoryEvidence(
            category = dominant?.key ?: "unknown",
            counts = counts,
            dominantRatio = ratio,
            totalEvents = total
        )
    }

    private fun priority(category: String): Int {
        return when (category) {
            "politics" -> 4
            "finance" -> 3
            "sports" -> 2
            "crypto" -> 1
            else -> 0
        }
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
        private const val MAX_BACKFILL_LIMIT = 500
        private const val MAX_SAMPLE_ENRICH_LIMIT = 100
        private const val MIN_SAMPLE_ENRICH_SCAN_LIMIT = 200
        private const val MIN_SAMPLE_EVENTS = 20L
        private const val MIN_DISTINCT_MARKETS = 5L
        private const val FRESH_7D_MS = 7L * 24 * 60 * 60 * 1000
        private const val FRESH_30D_MS = 30L * 24 * 60 * 60 * 1000
        const val ACTIVITY_CATEGORY_MIN_EVENTS = 20L
        const val ACTIVITY_CATEGORY_DOMINANCE = 0.70
        private val KNOWN_CATEGORIES = setOf("politics", "finance", "sports", "crypto")
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private val SAMPLE_ENRICH_REASONS = setOf(
            "insufficient_sample",
            "insufficient_market_diversity",
            "no_buy_sample",
            "no_sell_sample",
            "sell_ratio_outside_copyable_range"
        )
    }
}

private data class UnknownStrategySampleCandidate(
    val candidateId: Long,
    val category: String,
    val reasons: List<String>
)

private data class ActivityCategoryEvidence(
    val category: String,
    val counts: Map<String, Long>,
    val dominantRatio: Double,
    val totalEvents: Long
) {
    val isReliable: Boolean
        get() = totalEvents >= LeaderResearchActivityScoringService.ACTIVITY_CATEGORY_MIN_EVENTS &&
            dominantRatio >= LeaderResearchActivityScoringService.ACTIVITY_CATEGORY_DOMINANCE
}
