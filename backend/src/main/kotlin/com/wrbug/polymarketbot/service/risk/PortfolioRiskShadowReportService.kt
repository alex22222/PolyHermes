package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskReservationRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class PortfolioRiskShadowReportService(
    private val decisionRepository: PortfolioRiskDecisionRepository,
    private val reservationRepository: PortfolioRiskReservationRepository,
    private val policy: PortfolioRiskPolicy,
    private val gson: Gson
) {
    fun generate(accountId: Long, since: Long?, now: Long = System.currentTimeMillis()): PortfolioRiskShadowReportResponse {
        require(accountId > 0) { "accountId 无效" }
        val requestedSince = since ?: now - DEFAULT_WINDOW_MS
        val all = decisionRepository.findByAccountIdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(accountId, requestedSince)
        val firstSnapshotIndex = all.indexOfFirst { !it.inputSnapshotJson.isNullOrBlank() }
        val legacyExcluded = if (firstSnapshotIndex < 0) all.size else firstSnapshotIndex
        val sample = if (firstSnapshotIndex < 0) emptyList() else all.drop(firstSnapshotIndex)
        val snapshots = sample.mapNotNull { decision ->
            decision.inputSnapshotJson?.takeIf(String::isNotBlank)?.let {
                decision to gson.fromJson(it, PortfolioRiskInputSnapshot::class.java)
            }
        }
        val replayConsistent = snapshots.count { (decision, snapshot) ->
            if (snapshot.policyVersion !in PortfolioRiskPolicy.SUPPORTED_POLICY_VERSIONS) return@count false
            val replay = runCatching { policy.evaluate(snapshot) }.getOrNull() ?: return@count false
            replay.outcome == decision.outcome && replay.rules == decision.parseRules()
        }
        val buy = sample.filter { it.side.equals("BUY", true) }
        val sell = sample.filter { it.side.equals("SELL", true) }
        val fullyEvaluatedBuy = buy.count { decision -> decision.parseRules().none { it.status == "INSUFFICIENT_DATA" } }
        val finals = snapshots.filter { (_, snapshot) -> snapshot.request.stage.equals("FINAL", true) }
        val terminalStatuses = mutableMapOf<String, Int>()
        var terminalLinked = 0
        finals.forEach { (_, snapshot) ->
            val correlation = snapshot.request.correlationId
            val status = correlation?.let(reservationRepository::findByCorrelationId)?.status
            if (status in TERMINAL_STATUSES) {
                terminalLinked++
                terminalStatuses[status!!] = terminalStatuses.getOrDefault(status, 0) + 1
            }
        }
        val rules = sample.flatMap { it.parseRules() }.groupBy { it.code }.map { (code, values) ->
            PortfolioRiskShadowRuleStatsDto(
                code,
                values.count { it.status == "PASS" },
                values.count { it.status == "WOULD_BLOCK" },
                values.count { it.status == "INSUFFICIENT_DATA" }
            )
        }.sortedBy { it.code }
        val observationHours = if (sample.size >= 2) {
            BigDecimal(sample.last().createdAt - sample.first().createdAt).divide(BigDecimal(3_600_000), 2, RoundingMode.HALF_UP)
        } else BigDecimal.ZERO
        val snapshotCoverage = percent(snapshots.size, sample.size)
        val replayConsistency = percent(replayConsistent, snapshots.size)
        val fullyEvaluatedRate = percent(fullyEvaluatedBuy, buy.size)
        val terminalLinkage = percent(terminalLinked, finals.size)
        val gates = listOf(
            gate("MIN_BUY_SAMPLES", buy.size >= MIN_BUY_SAMPLES, buy.size, MIN_BUY_SAMPLES),
            gate("MIN_FINAL_SAMPLES", finals.size >= MIN_FINAL_SAMPLES, finals.size, MIN_FINAL_SAMPLES),
            gate("MIN_OBSERVATION_HOURS", observationHours >= MIN_OBSERVATION_HOURS, observationHours.strip(), MIN_OBSERVATION_HOURS.strip()),
            percentGate("SNAPSHOT_COVERAGE", snapshotCoverage, FULL_PERCENT),
            percentGate("REPLAY_CONSISTENCY", replayConsistency, FULL_PERCENT),
            percentGate("FULLY_EVALUATED_BUY_RATE", fullyEvaluatedRate, MIN_FULLY_EVALUATED_PERCENT),
            percentGate("FINAL_TERMINAL_LINKAGE", terminalLinkage, FULL_PERCENT)
        )
        val blockers = gates.filterNot { it.passed }.map { "${it.code}: actual=${it.actual}, required=${it.required}" }
        return PortfolioRiskShadowReportResponse(
            accountId = accountId,
            requestedSince = requestedSince,
            sampleWindowStart = sample.firstOrNull()?.createdAt,
            sampleWindowEnd = sample.lastOrNull()?.createdAt,
            observationHours = observationHours.strip(),
            legacyDecisionsExcluded = legacyExcluded,
            totalDecisions = sample.size,
            buyDecisions = buy.size,
            sellDecisions = sell.size,
            fullyEvaluatedBuyDecisions = fullyEvaluatedBuy,
            snapshotCoveragePercent = snapshotCoverage,
            replayConsistencyPercent = replayConsistency,
            finalDecisions = finals.size,
            terminalLinkedFinalDecisions = terminalLinked,
            terminalLinkagePercent = terminalLinkage,
            terminalStatuses = terminalStatuses.toSortedMap(),
            rules = rules,
            gates = gates,
            readyForEnforcedReview = blockers.isEmpty(),
            blockers = blockers,
            generatedAt = now
        )
    }

    private fun com.wrbug.polymarketbot.entity.PortfolioRiskDecision.parseRules(): List<PortfolioRiskRuleResultDto> =
        gson.fromJson(rulesJson, Array<PortfolioRiskRuleResultDto>::class.java).toList()

    private fun percent(numerator: Int, denominator: Int): String? = if (denominator == 0) null else
        BigDecimal(numerator).multiply(FULL_PERCENT).divide(BigDecimal(denominator), 2, RoundingMode.HALF_UP).strip()

    private fun gate(code: String, passed: Boolean, actual: Any, required: Any) =
        PortfolioRiskShadowGateDto(code, passed, actual.toString(), required.toString())

    private fun percentGate(code: String, actual: String?, required: BigDecimal): PortfolioRiskShadowGateDto {
        val value = actual?.toBigDecimalOrNull()
        return PortfolioRiskShadowGateDto(code, value != null && value >= required, actual ?: "N/A", required.strip())
    }

    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        private const val DEFAULT_WINDOW_MS = 7L * 24 * 60 * 60 * 1000
        private const val MIN_BUY_SAMPLES = 100
        private const val MIN_FINAL_SAMPLES = 20
        private val MIN_OBSERVATION_HOURS = BigDecimal("168")
        private val MIN_FULLY_EVALUATED_PERCENT = BigDecimal("95")
        private val FULL_PERCENT = BigDecimal("100")
        private val TERMINAL_STATUSES = setOf("SUCCESS", "FAILED", "EXPIRED")
    }
}
