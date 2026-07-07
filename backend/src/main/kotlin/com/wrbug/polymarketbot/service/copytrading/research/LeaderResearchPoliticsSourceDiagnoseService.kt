package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceBucketDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceRecommendationDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceSampleDto
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchPoliticsSourceDiagnoseService(
    private val jdbcTemplate: NamedParameterJdbcTemplate
) {
    fun diagnose(request: LeaderResearchPoliticsSourceDiagnoseRequest): LeaderResearchPoliticsSourceDiagnoseResponse {
        val category = normalizeCategory(request.category)
        val lookbackDays = request.lookbackDays.coerceIn(1, 365)
        val minEvents = request.minEvents.coerceIn(1, 1000)
        val minDistinctMarkets = request.minDistinctMarkets.coerceIn(1, 1000)
        val minBuyEvents = request.minBuyEvents.coerceIn(0, 1000)
        val minSellEvents = request.minSellEvents.coerceIn(0, 1000)
        val minSafePriceRatio = request.minSafePriceRatio.toBigDecimalOrDefault(BigDecimal("0.20"))
        val maxTailPriceRatio = request.maxTailPriceRatio.toBigDecimalOrDefault(BigDecimal("0.50"))
        val limit = request.limit.coerceIn(1, MAX_SCAN_LIMIT)
        val since = System.currentTimeMillis() - lookbackDays.toLong() * DAY_MS
        val marketPattern = LeaderResearchMarketCategoryPatterns.patternFor(category)

        val rows = jdbcTemplate.queryForList(
            """
            select
              e.normalized_wallet as wallet,
              count(e.id) as total_events,
              count(distinct e.market_id) as distinct_markets,
              coalesce(sum(case when upper(e.side) = 'BUY' then 1 else 0 end), 0) as buy_events,
              coalesce(sum(case when upper(e.side) = 'SELL' then 1 else 0 end), 0) as sell_events,
              coalesce(sum(case
                when e.price >= 0.10000000
                 and e.price <= 0.80000000
                 and e.size > 0
                 and e.market_id is not null
                then 1 else 0 end), 0) as safe_price_events,
              coalesce(sum(case
                when e.price < 0.05000000 or e.price > 0.95000000
                then 1 else 0 end), 0) as tail_price_events,
              avg(coalesce(e.amount, e.price * e.size)) as avg_amount,
              coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as total_amount,
              c.id as candidate_id,
              c.research_state,
              c.score,
              c.risk_flags,
              c.source,
              c.source_evidence,
              c.last_source_seen_at,
              ps.trade_count,
              ps.copyable_pnl
            from leader_activity_event e
            left join leader_research_candidate c
              on c.normalized_wallet = e.normalized_wallet
            left join leader_paper_session ps
              on ps.id = c.last_paper_session_id
            where e.normalized_wallet regexp '^0x[a-f0-9]{40}${'$'}'
              and e.event_time >= :since
              and (
                lower(coalesce(e.market_slug, '')) regexp :marketPattern
                or lower(coalesce(e.market_title, '')) regexp :marketPattern
              )
            group by
              e.normalized_wallet,
              c.id,
              c.research_state,
              c.score,
              c.risk_flags,
              c.source,
              c.source_evidence,
              c.last_source_seen_at,
              ps.trade_count,
              ps.copyable_pnl
            order by total_events desc, safe_price_events desc, distinct_markets desc
            limit :limit
            """.trimIndent(),
            MapSqlParameterSource()
                .addValue("since", since)
                .addValue("marketPattern", marketPattern)
                .addValue("limit", limit)
        )

        val samples = rows.map { row ->
            val wallet = row["wallet"].toString()
            val totalEvents = row.longValue("total_events")
            val distinctMarkets = row.longValue("distinct_markets")
            val buyEvents = row.longValue("buy_events")
            val sellEvents = row.longValue("sell_events")
            val safePriceEvents = row.longValue("safe_price_events")
            val tailPriceEvents = row.longValue("tail_price_events")
            val safeRatio = ratio(safePriceEvents, totalEvents)
            val tailRatio = ratio(tailPriceEvents, totalEvents)
            val score = row.bigDecimal("score")
            val state = row["research_state"]?.toString()
            val candidateId = row.longValueOrNull("candidate_id")
            val paperTradeCount = row.intValueOrNull("trade_count")
            val copyablePnl = row.bigDecimal("copyable_pnl")
            val riskFlags = row["risk_flags"].toStringList()
            val evidenceCategories = row["source_evidence"].evidenceCategories()
            val lastSourceSeenAt = row.longValueOrNull("last_source_seen_at")
            val sourceFresh72h = lastSourceSeenAt?.let { System.currentTimeMillis() - it <= SOURCE_FRESH_72H_MS } != false
            val blockers = mutableListOf<String>()

            if (totalEvents < minEvents) blockers += "events_below_${minEvents}"
            if (distinctMarkets < minDistinctMarkets) blockers += "markets_below_${minDistinctMarkets}"
            if (buyEvents < minBuyEvents) blockers += "buy_below_${minBuyEvents}"
            if (sellEvents < minSellEvents) blockers += "sell_below_${minSellEvents}"
            if (safeRatio < minSafePriceRatio) blockers += "safe_ratio_below_${minSafePriceRatio.format4()}"
            if (tailRatio > maxTailPriceRatio) blockers += "tail_ratio_above_${maxTailPriceRatio.format4()}"
            if (row["candidate_id"] != null) blockers += "already_in_research_pool"
            if (state == "PAPER") blockers += "already_paper"
            if (score != null && score < PAPER_PROMOTE_SCORE) blockers += "score_below_75"
            if (candidateId != null && evidenceCategories.isNotEmpty() && category !in evidenceCategories) {
                blockers += "category_mismatch"
            }
            if (candidateId != null && evidenceCategories.size > 1) {
                blockers += "mixed_category_evidence"
            }
            if (candidateId != null && !sourceFresh72h) {
                blockers += "source_stale_over_72h"
            }
            riskFlags.forEach { blockers += "risk:$it" }

            LeaderResearchPoliticsSourceSampleDto(
                wallet = wallet,
                candidateId = candidateId,
                action = when {
                    row["candidate_id"] == null && blockers.isEmpty() -> "UNKNOWN_ELIGIBLE"
                    row["candidate_id"] == null -> "UNKNOWN_BLOCKED"
                    state == "PAPER" -> "EXISTING_PAPER"
                    blockers.any { it.startsWith("risk:") || it in BLOCKING_EXISTING_FLAGS || it == "score_below_75" } -> "EXISTING_BLOCKED"
                    else -> "EXISTING_REFRESH"
                },
                totalEvents = totalEvents,
                distinctMarkets = distinctMarkets,
                buyEvents = buyEvents,
                sellEvents = sellEvents,
                safePriceRatio = safeRatio.format4(),
                tailPriceRatio = tailRatio.format4(),
                avgAmount = row.bigDecimal("avg_amount").format4(),
                totalAmount = row.bigDecimal("total_amount").format4(),
                currentState = state,
                currentScore = score?.format4(),
                paperTradeCount = paperTradeCount,
                copyablePnl = copyablePnl?.format4(),
                riskFlags = riskFlags,
                blockers = blockers.distinct()
            )
        }

        val buckets = samples
            .flatMap { sample -> sample.blockers.ifEmpty { listOf("pass_import_criteria") } }
            .groupingBy { it }
            .eachCount()
            .entries
            .sortedWith(compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key })
            .map { (bucket, count) ->
                LeaderResearchPoliticsSourceBucketDto(
                    bucket = bucket,
                    count = count,
                    description = bucketDescription(bucket)
                )
            }

        return LeaderResearchPoliticsSourceDiagnoseResponse(
            category = category,
            lookbackDays = lookbackDays,
            scannedWallets = samples.size,
            passImportCriteria = samples.count { it.blockers.none(::isImportCriteriaBlocker) },
            unknownWallets = samples.count { it.currentState == null },
            existingWallets = samples.count { it.currentState != null },
            paperWallets = samples.count { it.currentState == "PAPER" },
            cleanHighWallets = samples.count {
                it.currentState == "PAPER" &&
                    (it.currentScore?.toBigDecimalOrNull() ?: BigDecimal.ZERO) >= BigDecimal("80") &&
                    it.riskFlags.isEmpty()
            },
            eligibleForPaperNow = samples.count { it.action == "UNKNOWN_ELIGIBLE" },
            buckets = buckets,
            samples = samples
                .sortedWith(compareBy<LeaderResearchPoliticsSourceSampleDto> { it.action != "UNKNOWN_ELIGIBLE" }
                    .thenByDescending { it.totalEvents }
                    .thenByDescending { it.safePriceRatio.toBigDecimalOrNull() ?: BigDecimal.ZERO })
                .take(PREVIEW_LIMIT),
            recommendations = buildRecommendations(samples, category),
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun buildRecommendations(
        samples: List<LeaderResearchPoliticsSourceSampleDto>,
        category: String
    ): List<LeaderResearchPoliticsSourceRecommendationDto> {
        return samples.mapNotNull { sample ->
            val score = sample.currentScore?.toBigDecimalOrNull()
            val paperTradeCount = sample.paperTradeCount ?: 0
            val copyablePnl = sample.copyablePnl?.toBigDecimalOrNull()
            val blockerSet = sample.blockers.toSet()
            val importBlocked = sample.blockers.any(::isImportCriteriaBlocker)
            val riskBlocked = sample.blockers.any { it.startsWith("risk:") }
            val categoryBlocked = sample.blockers.any { it in BLOCKING_EXISTING_FLAGS }

            val recommendation = when {
                sample.action == "UNKNOWN_ELIGIBLE" -> RecommendationPlan(
                    recommendation = "IMPORT_NOW",
                    priority = 100,
                    reason = "未知钱包通过${categoryLabel(category)}来源导入阈值，可优先导入研究池"
                )
                sample.currentState == "TRIAL_READY" && !riskBlocked && !categoryBlocked && (copyablePnl ?: BigDecimal.ZERO) > BigDecimal.ZERO -> RecommendationPlan(
                    recommendation = "FAST_WATCH_REVIEW",
                    priority = 95,
                    reason = "${categoryLabel(category)}候选已进入 TRIAL_READY 且 copyable PnL 为正，可进入禁用试跟配置人工复核"
                )
                sample.currentState == "DISCOVERED" && !importBlocked && !riskBlocked && !categoryBlocked && (score ?: BigDecimal.ZERO) >= BigDecimal("70") -> RecommendationPlan(
                    recommendation = "SCORE_REFRESH",
                    priority = 90,
                    reason = "已在研究池但尚未 PAPER，${categoryLabel(category)}样本合格且评分接近晋级阈值"
                )
                sample.currentState == "PAPER" && !riskBlocked && !categoryBlocked && (score ?: BigDecimal.ZERO) >= BigDecimal("80") && paperTradeCount < 20 -> RecommendationPlan(
                    recommendation = "PAPER_PROCESS",
                    priority = 85,
                    reason = "${categoryLabel(category)} PAPER 高分但纸跟交易数不足，优先推进 paper/process"
                )
                sample.currentState == "PAPER" && !riskBlocked && !categoryBlocked && paperTradeCount >= 20 && (copyablePnl ?: BigDecimal.ZERO) > BigDecimal.ZERO -> RecommendationPlan(
                    recommendation = "FAST_WATCH_REVIEW",
                    priority = 80,
                    reason = "${categoryLabel(category)} PAPER 样本已过 20 笔且 copyable PnL 为正，检查 7 天观察期与稳定评分"
                )
                sample.currentState != null && "already_in_research_pool" in blockerSet && !riskBlocked && !importBlocked && !categoryBlocked -> RecommendationPlan(
                    recommendation = "WATCH_SOURCE",
                    priority = 50,
                    reason = "已在研究池，继续积累${categoryLabel(category)}事件样本并等待评分/纸跟推进"
                )
                else -> null
            } ?: return@mapNotNull null

            LeaderResearchPoliticsSourceRecommendationDto(
                wallet = sample.wallet,
                candidateId = sample.candidateId,
                recommendation = recommendation.recommendation,
                priority = recommendation.priority,
                reason = recommendation.reason,
                action = sample.action,
                currentState = sample.currentState,
                currentScore = sample.currentScore,
                totalEvents = sample.totalEvents,
                distinctMarkets = sample.distinctMarkets,
                buyEvents = sample.buyEvents,
                sellEvents = sample.sellEvents,
                safePriceRatio = sample.safePriceRatio,
                tailPriceRatio = sample.tailPriceRatio,
                paperTradeCount = sample.paperTradeCount,
                copyablePnl = sample.copyablePnl,
                blockers = sample.blockers
            )
        }
            .sortedWith(compareByDescending<LeaderResearchPoliticsSourceRecommendationDto> { it.priority }
                .thenByDescending { it.totalEvents }
                .thenByDescending { it.safePriceRatio.toBigDecimalOrNull() ?: BigDecimal.ZERO })
            .take(RECOMMENDATION_LIMIT)
    }

    private fun bucketDescription(bucket: String): String {
        return when {
            bucket == "pass_import_criteria" -> "通过当前导入阈值"
            bucket == "already_in_research_pool" -> "钱包已经在研究候选池中，重复导入不会增加新来源"
            bucket == "already_paper" -> "钱包已经处于 PAPER 观察"
            bucket == "score_below_75" -> "当前预筛评分低于 PAPER 晋级阈值"
            bucket.startsWith("risk:") -> "当前研究风险标记阻止晋级或降低可信度"
            bucket.startsWith("events_below") -> "政治相关事件样本不足"
            bucket.startsWith("markets_below") -> "政治市场多样性不足"
            bucket.startsWith("buy_below") -> "买入行为不足"
            bucket.startsWith("sell_below") -> "卖出/退出行为不足"
            bucket == "category_mismatch" -> "候选已有研究分类与当前诊断分类不匹配"
            bucket == "mixed_category_evidence" -> "候选存在多个主分类证据，不能按单一分类直接推荐"
            bucket == "source_stale_over_72h" -> "候选来源超过 72 小时未刷新，需等待新活动或重新发现"
            bucket.startsWith("safe_ratio_below") -> "安全价格区间交易比例不足"
            bucket.startsWith("tail_ratio_above") -> "长尾极端价格交易比例过高"
            else -> bucket
        }
    }

    private fun isImportCriteriaBlocker(blocker: String): Boolean {
        return blocker.startsWith("events_below_") ||
            blocker.startsWith("markets_below_") ||
            blocker.startsWith("buy_below_") ||
            blocker.startsWith("sell_below_") ||
            blocker.startsWith("safe_ratio_below_") ||
            blocker.startsWith("tail_ratio_above_")
    }

    private fun ratio(numerator: Long, denominator: Long): BigDecimal {
        if (denominator <= 0) return BigDecimal.ZERO
        return BigDecimal(numerator).divide(BigDecimal(denominator), 8, RoundingMode.HALF_UP)
    }

    private fun Any?.toStringList(): List<String> {
        return this?.toString()
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotBlank() }
            ?.distinct()
            .orEmpty()
    }

    private fun Any?.evidenceCategories(): Set<String> {
        return this?.toString()
            ?.lines()
            ?.flatMap { line ->
                CATEGORY_EVIDENCE_REGEX.findAll(line).map { it.groupValues[1].lowercase() }.toList()
            }
            ?.filter { it in PRIMARY_DIAGNOSE_CATEGORIES }
            ?.toSet()
            .orEmpty()
    }

    private fun Map<String, Any?>.longValue(key: String): Long {
        return when (val value = this[key]) {
            is Number -> value.toLong()
            else -> value?.toString()?.toLongOrNull() ?: 0L
        }
    }

    private fun Map<String, Any?>.longValueOrNull(key: String): Long? {
        return when (val value = this[key]) {
            is Number -> value.toLong()
            else -> value?.toString()?.toLongOrNull()
        }
    }

    private fun Map<String, Any?>.intValueOrNull(key: String): Int? {
        return when (val value = this[key]) {
            is Number -> value.toInt()
            else -> value?.toString()?.toIntOrNull()
        }
    }

    private fun Map<String, Any?>.bigDecimal(key: String): BigDecimal? {
        return when (val value = this[key]) {
            is BigDecimal -> value
            is Number -> BigDecimal(value.toString())
            else -> value?.toString()?.toBigDecimalOrNull()
        }
    }

    private fun String.toBigDecimalOrDefault(default: BigDecimal): BigDecimal {
        return runCatching { BigDecimal(this) }.getOrDefault(default)
    }

    private fun BigDecimal?.format4(): String {
        return (this ?: BigDecimal.ZERO).setScale(4, RoundingMode.HALF_UP).toPlainString()
    }

    private fun normalizeCategory(category: String): String {
        val normalized = category.trim().lowercase()
        return if (normalized in PRIMARY_DIAGNOSE_CATEGORIES) normalized else "politics"
    }

    private fun categoryLabel(category: String): String {
        return when (category) {
            "finance" -> "金融"
            else -> "政治"
        }
    }

    private data class RecommendationPlan(
        val recommendation: String,
        val priority: Int,
        val reason: String
    )

    companion object {
        private const val MAX_SCAN_LIMIT = 2000
        private const val PREVIEW_LIMIT = 100
        private const val RECOMMENDATION_LIMIT = 20
        private const val DAY_MS = 24L * 60 * 60 * 1000
        private const val SOURCE_FRESH_72H_MS = 72L * 60 * 60 * 1000
        private val PAPER_PROMOTE_SCORE = BigDecimal("75")
        private val PRIMARY_DIAGNOSE_CATEGORIES = setOf("politics", "finance")
        private val BLOCKING_EXISTING_FLAGS = setOf("category_mismatch", "mixed_category_evidence", "source_stale_over_72h")
        private val CATEGORY_EVIDENCE_REGEX = Regex("""category:(politics|finance|sports|crypto)""", RegexOption.IGNORE_CASE)
    }
}
