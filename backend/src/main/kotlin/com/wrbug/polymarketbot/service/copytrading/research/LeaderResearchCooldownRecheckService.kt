package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchCooldownRecheckItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchCooldownRecheckRequest
import com.wrbug.polymarketbot.dto.LeaderResearchCooldownRecheckResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal

@Service
class LeaderResearchCooldownRecheckService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val stateMachine: LeaderResearchStateMachine
) {
    @Transactional
    fun recheck(request: LeaderResearchCooldownRecheckRequest): LeaderResearchCooldownRecheckResponse {
        val requestedIds = request.candidateIds.distinct().filter { it > 0 }.take(request.maxCandidates.coerceIn(1, MAX_CANDIDATES))
        if (requestedIds.isEmpty()) {
            return LeaderResearchCooldownRecheckResponse(
                dryRun = request.dryRun,
                requestedCandidateIds = emptyList(),
                scannedCount = 0,
                selectedCount = 0,
                advancedCount = 0,
                recoveredCandidateIds = emptyList(),
                retiredCandidateIds = emptyList(),
                missingCandidateIds = emptyList(),
                items = emptyList(),
                generatedAt = System.currentTimeMillis()
            )
        }

        val foundById = candidateRepository.findAllById(requestedIds).associateBy { it.id }
        var advancedCount = 0
        val items = requestedIds.map { candidateId ->
            val candidate = foundById[candidateId]
            if (candidate == null) {
                missingItem(candidateId)
            } else {
                val before = candidate.copy()
                val beforeState = before.researchState
                val after = if (!request.dryRun && before.researchState == LeaderResearchState.COOLDOWN && !before.locked) {
                    stateMachine.advance(candidate, runId = null).also {
                        if (it.researchState != beforeState) advancedCount += 1
                    }
                } else {
                    before
                }
                item(before, after, request.dryRun)
            }
        }
        val missingIds = items.filter { it.action == "MISSING" }.map { it.candidateId }
        return LeaderResearchCooldownRecheckResponse(
            dryRun = request.dryRun,
            requestedCandidateIds = requestedIds,
            scannedCount = foundById.size,
            selectedCount = items.count { it.action != "MISSING" && it.beforeState == LeaderResearchState.COOLDOWN.name },
            advancedCount = advancedCount,
            recoveredCandidateIds = items.filter {
                it.eligible && it.afterState == LeaderResearchState.CANDIDATE.name
            }.map { it.candidateId },
            retiredCandidateIds = items.filter {
                it.eligible && it.afterState == LeaderResearchState.RETIRED.name
            }.map { it.candidateId },
            missingCandidateIds = missingIds,
            items = items,
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun item(
        candidate: LeaderResearchCandidate,
        after: LeaderResearchCandidate,
        dryRun: Boolean
    ): LeaderResearchCooldownRecheckItemDto {
        val expectedState = if (dryRun) expectedNextState(candidate) else after.researchState
        val reason = blocker(candidate)
        val eligible = candidate.researchState == LeaderResearchState.COOLDOWN &&
            !candidate.locked &&
            expectedState != LeaderResearchState.COOLDOWN
        val action = when {
            candidate.researchState != LeaderResearchState.COOLDOWN -> "SKIPPED"
            candidate.locked -> "SKIPPED"
            dryRun && expectedState == LeaderResearchState.CANDIDATE -> "READY_TO_RECOVER"
            dryRun && expectedState == LeaderResearchState.RETIRED -> "READY_TO_RETIRE"
            dryRun -> "WAIT"
            after.researchState == LeaderResearchState.CANDIDATE -> "RECOVERED"
            after.researchState == LeaderResearchState.RETIRED -> "RETIRED"
            else -> "UNCHANGED"
        }
        return LeaderResearchCooldownRecheckItemDto(
            candidateId = candidate.id ?: 0L,
            wallet = candidate.normalizedWallet,
            beforeState = candidate.researchState.name,
            afterState = expectedState.name,
            score = (candidate.score ?: BigDecimal.ZERO).strip(),
            cooldownUntil = candidate.cooldownUntil,
            cooldownCount = candidate.cooldownCount,
            lastSourceSeenAt = candidate.lastSourceSeenAt,
            eligible = eligible,
            action = action,
            reason = reason ?: "cooldown_recheck_ready"
        )
    }

    private fun missingItem(candidateId: Long): LeaderResearchCooldownRecheckItemDto {
        return LeaderResearchCooldownRecheckItemDto(
            candidateId = candidateId,
            wallet = "",
            beforeState = "MISSING",
            afterState = "MISSING",
            score = "0",
            cooldownUntil = null,
            cooldownCount = 0,
            lastSourceSeenAt = null,
            eligible = false,
            action = "MISSING",
            reason = "candidate_not_found"
        )
    }

    private fun expectedNextState(candidate: LeaderResearchCandidate): LeaderResearchState {
        if (candidate.researchState != LeaderResearchState.COOLDOWN || candidate.locked) return candidate.researchState
        val now = System.currentTimeMillis()
        val cooldownElapsed = candidate.cooldownUntil?.let { now >= it } ?: true
        val sourceFresh48h = candidate.lastSourceSeenAt?.let { now - it <= SOURCE_FRESH_48H_MS } == true
        val sourceRetired = candidate.lastSourceSeenAt?.let { now - it > SOURCE_RETIRE_30D_MS } == true
        return when {
            candidate.cooldownCount >= RETIRE_COOLDOWN_COUNT || sourceRetired -> LeaderResearchState.RETIRED
            cooldownElapsed && sourceFresh48h -> LeaderResearchState.CANDIDATE
            else -> LeaderResearchState.COOLDOWN
        }
    }

    private fun blocker(candidate: LeaderResearchCandidate): String? {
        if (candidate.researchState != LeaderResearchState.COOLDOWN) return "not_cooldown"
        if (candidate.locked) return "candidate_locked"
        val now = System.currentTimeMillis()
        if (candidate.cooldownCount >= RETIRE_COOLDOWN_COUNT) return "cooldown_count_retire_threshold"
        if (candidate.lastSourceSeenAt?.let { now - it > SOURCE_RETIRE_30D_MS } == true) return "source_stale_over_30d"
        if (candidate.cooldownUntil?.let { now < it } == true) return "cooldown_not_elapsed"
        if (candidate.lastSourceSeenAt?.let { now - it <= SOURCE_FRESH_48H_MS } != true) return "source_stale_over_48h"
        return null
    }

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    companion object {
        private const val MAX_CANDIDATES = 100
        private const val RETIRE_COOLDOWN_COUNT = 3
        private const val SOURCE_FRESH_48H_MS = 48L * 60 * 60 * 1000
        private const val SOURCE_RETIRE_30D_MS = 30L * 24 * 60 * 60 * 1000
    }
}
