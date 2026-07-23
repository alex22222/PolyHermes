package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsRequest
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsResponse
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsStateDto
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchLoopDiagnosticsService(
    private val jdbcTemplate: NamedParameterJdbcTemplate
) {
    fun diagnose(request: LeaderResearchLoopDiagnosticsRequest): LeaderResearchLoopDiagnosticsResponse {
        val categories = request.categories.mapNotNull(::normalizeCategory).distinct().ifEmpty { PRIMARY_CATEGORIES }
        val sampleLimit = request.sampleLimit.coerceIn(1, 50)
        val candidateIds = request.candidateIds.distinct().filter { it > 0 }.take(100)
        val params = MapSqlParameterSource()
            .addValue("categoriesPattern", categoryPattern(categories))
            .addValue("sampleLimit", sampleLimit)
            .addValue("nowMs", System.currentTimeMillis())
            .addValue("scoreVersion", SCORE_VERSION)

        val enabledCopyConfigs = jdbcTemplate.queryForList(ENABLED_COPY_CONFIGS_SQL, params).firstOrNull().longValue("count")
        val strictReadyCount = queryStrictReadyCount(params)
        val stateSummaries = jdbcTemplate.queryForList(STATE_SUMMARY_SQL, params).map { row ->
            LeaderResearchLoopDiagnosticsStateDto(
                state = row["research_state"]?.toString().orEmpty(),
                total = row.longValue("total"),
                hasAllNamedEvidence = row.longValue("has_all_named"),
                score60 = row.longValue("score60"),
                score80 = row.longValue("score80"),
                riskEmpty = row.longValue("risk_empty")
            )
        }

        val sampleSql = buildSampleSql(candidateIds.isNotEmpty())
        if (candidateIds.isNotEmpty()) {
            params.addValue("candidateIds", candidateIds)
        }
        val samples = jdbcTemplate.queryForList(sampleSql, params).map { row ->
            val riskFlags = row["risk_flags"].toStringList()
            val score = row.bigDecimal("score")
            val tradeCount = row.intValue("trade_count")
            val copyablePnl = row.bigDecimal("copyable_pnl") ?: BigDecimal.ZERO
            val filteredRatio = row.bigDecimal("filtered_ratio") ?: BigDecimal.ZERO
            val sourceEvidence = row["source_evidence"]?.toString()
            val sourceCategory = categoryFromEvidence(sourceEvidence)
            val openExposure = row.bigDecimal("open_exposure") ?: BigDecimal.ZERO
            val unknownValuationExposure = row.bigDecimal("unknown_valuation_exposure") ?: BigDecimal.ZERO
            val unknownRatio = if (openExposure > BigDecimal.ZERO) {
                unknownValuationExposure.divide(openExposure, 8, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }
            LeaderResearchLoopDiagnosticsCandidateDto(
                candidateId = row.longValue("id"),
                wallet = row["normalized_wallet"]?.toString().orEmpty(),
                researchState = row["research_state"]?.toString().orEmpty(),
                score = score?.format4(),
                riskFlags = riskFlags,
                strategyType = row["strategy_type"]?.toString(),
                tradeCount = tradeCount,
                copyablePnl = copyablePnl.format4(),
                filteredRatio = filteredRatio.format4(),
                hasAllNamedEvidence = true,
                sourceCategory = sourceCategory,
                blocker = blocker(
                    score = score,
                    strategyType = row["strategy_type"]?.toString(),
                    sourceEvidence = sourceEvidence,
                    riskFlags = riskFlags,
                    startedAt = row.longValue("started_at"),
                    tradeCount = tradeCount,
                    filteredCount = row.intValue("filtered_count"),
                    copyablePnl = copyablePnl,
                    maxDrawdown = row.bigDecimal("max_drawdown") ?: BigDecimal.ZERO,
                    unknownRatio = unknownRatio,
                    filteredRatio = filteredRatio,
                    lastSourceSeenAt = row.longValue("last_source_seen_at"),
                    stableHighScoreCount = row.intValue("stable_high_scores")
                )
            )
        }

        return LeaderResearchLoopDiagnosticsResponse(
            generatedAt = System.currentTimeMillis(),
            categories = categories,
            enabledCopyConfigs = enabledCopyConfigs,
            strictReadyCount = strictReadyCount,
            stateSummaries = stateSummaries,
            samples = samples
        )
    }

    fun strictReadyCount(): Long {
        val params = MapSqlParameterSource()
            .addValue("categoriesPattern", categoryPattern(PRIMARY_CATEGORIES))
            .addValue("nowMs", System.currentTimeMillis())
            .addValue("scoreVersion", SCORE_VERSION)
        return queryStrictReadyCount(params)
    }

    private fun queryStrictReadyCount(params: MapSqlParameterSource): Long {
        return jdbcTemplate.queryForList(STRICT_READY_SQL, params).firstOrNull().longValue("count")
    }

    private fun buildSampleSql(hasCandidateFilter: Boolean): String {
        val candidateFilter = if (hasCandidateFilter) "and c.id in (:candidateIds)" else ""
        return """
            select
              c.id,
              c.normalized_wallet,
              c.research_state,
              c.score,
              c.risk_flags,
              c.strategy_type,
              c.source_evidence,
              c.last_source_seen_at,
              ps.started_at,
              coalesce(ps.trade_count, 0) as trade_count,
              coalesce(ps.filtered_count, 0) as filtered_count,
              coalesce(ps.copyable_pnl, 0) as copyable_pnl,
              coalesce(ps.max_drawdown, 0) as max_drawdown,
              coalesce(ps.open_exposure, 0) as open_exposure,
              coalesce(ps.unknown_valuation_exposure, 0) as unknown_valuation_exposure,
              coalesce(ps.filtered_ratio, 0) as filtered_ratio,
              coalesce(sc.stable_high_scores, 0) as stable_high_scores
            from leader_research_candidate c
            left join leader_paper_session ps on ps.id = c.last_paper_session_id
            left join (
              select candidate_id, sum(case when total_score >= 80 then 1 else 0 end) as stable_high_scores
              from (
                select
                  candidate_id,
                  total_score,
                  row_number() over (partition by candidate_id order by created_at desc) as rn
                from leader_research_score
                where score_version = :scoreVersion
              ) ranked_scores
              where rn <= 3
              group by candidate_id
            ) sc on sc.candidate_id = c.id
            where c.research_state in ('DISCOVERED', 'CANDIDATE', 'PAPER', 'TRIAL_READY')
              and coalesce(c.source_evidence, '') like '%ALL%'
              and coalesce(c.source_evidence, '') regexp 'official|polyburg'
              and coalesce(c.source_evidence, '') regexp :categoriesPattern
              $candidateFilter
            order by
              case
                when c.research_state in ('PAPER', 'TRIAL_READY')
                 and c.score >= 80
                 and coalesce(c.risk_flags, '') = ''
                 and coalesce(ps.copyable_pnl, 0) > 0 then 0
                when c.research_state in ('PAPER', 'TRIAL_READY') then 1
                when c.research_state in ('DISCOVERED', 'CANDIDATE') then 2
                else 3
              end,
              c.score desc,
              coalesce(ps.copyable_pnl, 0) desc,
              coalesce(ps.trade_count, 0) desc,
              c.updated_at desc
            limit :sampleLimit
        """.trimIndent()
    }

    private fun blocker(
        score: BigDecimal?,
        strategyType: String?,
        sourceEvidence: String?,
        riskFlags: List<String>,
        startedAt: Long,
        tradeCount: Int,
        filteredCount: Int,
        copyablePnl: BigDecimal,
        maxDrawdown: BigDecimal,
        unknownRatio: BigDecimal,
        filteredRatio: BigDecimal,
        lastSourceSeenAt: Long,
        stableHighScoreCount: Int
    ): String {
        if (score == null) return "score_missing"
        if (score < BigDecimal("80")) return "score_below_80"
        if (strategyType != "human_directional") return "strategy_not_human_directional"
        LeaderResearchProfitWindowParser.parse(sourceEvidence).blockers.firstOrNull()?.let { return it }
        if (riskFlags.isNotEmpty()) return "risk_flags"
        if (System.currentTimeMillis() - startedAt < PAPER_MIN_AGE_MS) return "waiting_observation_age"
        if (tradeCount < 10) return "paper_trades_below_10"
        if (tradeCount + filteredCount < 10) return "paper_total_samples_below_10"
        if (copyablePnl <= BigDecimal.ZERO) return "paper_pnl_not_positive"
        if (maxDrawdown < BigDecimal("-15")) return "drawdown_gt_15"
        if (unknownRatio > BigDecimal("0.20")) return "unknown_valuation_gt_20pct"
        if (filteredRatio >= BigDecimal("0.50")) return "filtered_ratio_gt_or_eq_50pct"
        if (lastSourceSeenAt <= 0 || System.currentTimeMillis() - lastSourceSeenAt > SOURCE_STALE_72H_MS) return "source_stale_over_72h"
        if (stableHighScoreCount < 3) return "stable_high_scores_below_3"
        return "strict_ready"
    }

    private fun normalizeCategory(value: String): String? {
        return when (value.trim().lowercase()) {
            "politics", "political" -> "politics"
            "finance", "financial", "economics", "economic" -> "finance"
            else -> null
        }
    }

    private fun categoryPattern(categories: List<String>): String {
        return categories.joinToString("|") { "category[:=]$it" }
    }

    private fun categoryFromEvidence(sourceEvidence: String?): String? {
        return CATEGORY_REGEX.find(sourceEvidence.orEmpty())?.groupValues?.getOrNull(1)?.let(::normalizeCategory)
    }

    private fun Map<String, Any?>?.longValue(key: String): Long {
        return when (val value = this?.get(key)) {
            is Number -> value.toLong()
            is String -> value.toLongOrNull() ?: 0L
            else -> 0L
        }
    }

    private fun Map<String, Any?>.intValue(key: String): Int {
        return longValue(key).toInt()
    }

    private fun Map<String, Any?>.bigDecimal(key: String): BigDecimal? {
        return when (val value = this[key]) {
            is BigDecimal -> value
            is Number -> BigDecimal.valueOf(value.toDouble())
            is String -> value.toBigDecimalOrNull()
            else -> null
        }
    }

    private fun Any?.toStringList(): List<String> {
        return toString()
            .split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() && it != "null" }
    }

    private fun BigDecimal.format4(): String {
        return setScale(4, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
    }

    companion object {
        private val PRIMARY_CATEGORIES = listOf("politics", "finance")
        private val CATEGORY_REGEX = Regex("category[:=](politics|finance)", RegexOption.IGNORE_CASE)
        private const val SCORE_VERSION = "research-copyability-v1"
        private const val PAPER_MIN_AGE_MS = 7L * 24 * 60 * 60 * 1000
        private const val SOURCE_STALE_72H_MS = 72L * 60 * 60 * 1000

        private const val ENABLED_COPY_CONFIGS_SQL = """
            select count(*) as count
            from copy_trading
            where enabled = 1
        """

        private const val STRICT_READY_SQL = """
            select count(*) as count
            from leader_research_candidate c
            left join leader_paper_session ps on ps.id = c.last_paper_session_id
            left join (
              select candidate_id, sum(case when total_score >= 80 then 1 else 0 end) as stable_high_scores
              from (
                select
                  candidate_id,
                  total_score,
                  row_number() over (partition by candidate_id order by created_at desc) as rn
                from leader_research_score
                where score_version = :scoreVersion
              ) ranked_scores
              where rn <= 3
              group by candidate_id
            ) sc on sc.candidate_id = c.id
            where c.research_state = 'PAPER'
              and c.score >= 80
              and c.strategy_type = 'human_directional'
              and coalesce(c.risk_flags, '') = ''
              and :nowMs - ps.started_at >= 604800000
              and ps.trade_count >= 10
              and ps.trade_count + ps.filtered_count >= 10
              and coalesce(ps.copyable_pnl, 0) > 0
              and coalesce(ps.max_drawdown, 0) >= -15
              and case
                when coalesce(ps.open_exposure, 0) > 0
                  then coalesce(ps.unknown_valuation_exposure, 0) / ps.open_exposure
                else 0
              end <= 0.20
              and coalesce(ps.filtered_ratio, 0) < 0.50
              and c.last_source_seen_at is not null
              and :nowMs - c.last_source_seen_at <= 259200000
              and coalesce(sc.stable_high_scores, 0) >= 3
              and coalesce(c.source_evidence, '') like '%ALL%'
              and coalesce(c.source_evidence, '') regexp 'official|polyburg'
              and coalesce(c.source_evidence, '') regexp :categoriesPattern
              and coalesce(c.source_evidence, '') regexp '(profit_window|pnl_window):(180d|6m|6-month|all):|period:ALL[^\\n\\r]*pnl:'
              and coalesce(c.source_evidence, '') regexp 'activity_window:[a-z0-9_-]+_trades:[1-9]|last_(trade_at|event_time):[0-9]+'
        """

        private const val STATE_SUMMARY_SQL = """
            select
              c.research_state,
              count(*) as total,
              sum(case
                when coalesce(c.source_evidence, '') like '%ALL%'
                 and coalesce(c.source_evidence, '') regexp 'official|polyburg'
                 and coalesce(c.source_evidence, '') regexp :categoriesPattern
                then 1 else 0 end) as has_all_named,
              sum(case when c.score >= 60 then 1 else 0 end) as score60,
              sum(case when c.score >= 80 then 1 else 0 end) as score80,
              sum(case when coalesce(c.risk_flags, '') = '' then 1 else 0 end) as risk_empty
            from leader_research_candidate c
            group by c.research_state
            order by c.research_state
        """
    }
}
