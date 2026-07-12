package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioRiskDecision
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service

@Service
class PortfolioRiskDecisionQueryService(
    private val repository: PortfolioRiskDecisionRepository,
    private val policy: PortfolioRiskPolicy,
    private val gson: Gson
) {
    fun list(accountId: Long, limit: Int): List<PortfolioRiskDecisionDto> =
        repository.findByAccountIdOrderByCreatedAtDesc(accountId, PageRequest.of(0, limit.coerceIn(1, 500)))
            .map { it.toDto() }

    fun replay(requestId: String): PortfolioRiskReplayResponse {
        val decision = repository.findByRequestId(requestId) ?: throw IllegalArgumentException("风险决策不存在")
        val storedRules = decision.parseRules()
        val inputJson = decision.inputSnapshotJson
        if (inputJson.isNullOrBlank()) {
            return PortfolioRiskReplayResponse(
                requestId, decision.policyVersion, decision.outcome, null, false,
                "INPUT_SNAPSHOT_UNAVAILABLE", storedRules, false
            )
        }
        val snapshot = gson.fromJson(inputJson, PortfolioRiskInputSnapshot::class.java)
        require(snapshot.policyVersion in PortfolioRiskPolicy.SUPPORTED_POLICY_VERSIONS) {
            "不支持重放策略版本：${snapshot.policyVersion}"
        }
        require(snapshot.policyVersion == decision.policyVersion) { "决策与输入快照策略版本不一致" }
        val replay = policy.evaluate(snapshot)
        return PortfolioRiskReplayResponse(
            requestId = requestId,
            policyVersion = decision.policyVersion,
            storedOutcome = decision.outcome,
            replayedOutcome = replay.outcome,
            consistent = replay.outcome == decision.outcome && replay.rules == storedRules,
            replayScope = "FULL_INPUT_SNAPSHOT",
            rules = replay.rules,
            snapshotAvailable = true
        )
    }

    private fun PortfolioRiskDecision.toDto() = PortfolioRiskDecisionDto(
        requestId, accountId, policyVersion, mode, side, outcome, executionAllowed,
        marketId, eventSlug, leaderAddress, category, parseRules(), createdAt
    )

    private fun PortfolioRiskDecision.parseRules(): List<PortfolioRiskRuleResultDto> =
        gson.fromJson(rulesJson, Array<PortfolioRiskRuleResultDto>::class.java).toList()
}
