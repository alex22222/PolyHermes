package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckRequest
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckResponse
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchTrialReadyRecheckService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val paperSessionRepository: LeaderPaperSessionRepository,
    private val scoreRepository: LeaderResearchScoreRepository,
    private val scoringService: LeaderResearchScoringService,
    private val stateMachine: LeaderResearchStateMachine
) {
    fun recheck(request: LeaderResearchTrialReadyRecheckRequest): LeaderResearchTrialReadyRecheckResponse {
        val candidates = selectCandidates(request)
        val selected = candidates.take(request.maxCandidates.coerceIn(1, MAX_CANDIDATES))
        var scoredCount = 0
        var advancedCount = 0
        val items = selected.map { row ->
            val before = row.candidate
            val candidateForAdvance = if (!request.dryRun) {
                scoringService.scoreCandidate(before, runId = null)
                scoredCount += 1
                candidateRepository.findById(before.id ?: 0L).orElse(before)
            } else {
                before
            }
            val after = if (!request.dryRun) {
                stateMachine.advance(candidateForAdvance, runId = null).also {
                    if (it.researchState != before.researchState) advancedCount += 1
                }
            } else {
                candidateForAdvance
            }
            item(row.copy(candidate = candidateForAdvance), after, request.dryRun)
        }
        return LeaderResearchTrialReadyRecheckResponse(
            dryRun = request.dryRun,
            scannedCount = candidates.size,
            selectedCount = selected.size,
            scoredCount = scoredCount,
            advancedCount = advancedCount,
            trialReadyCandidateIds = items.filter { it.afterState == LeaderResearchState.TRIAL_READY.name }.map { it.candidateId },
            items = items,
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun selectCandidates(request: LeaderResearchTrialReadyRecheckRequest): List<CandidateSessionRow> {
        val requestedIds = request.candidateIds.distinct().filter { it > 0 }
        val candidates = if (requestedIds.isNotEmpty()) {
            val order = requestedIds.withIndex().associate { it.value to it.index }
            candidateRepository.findAllById(requestedIds)
                .sortedBy { candidate -> order[candidate.id] ?: Int.MAX_VALUE }
        } else {
            candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.PAPER))
        }.filter { it.researchState in setOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY) }
        val sessions = paperSessionRepository.findLatestByCandidateIds(candidates.mapNotNull { it.id })
            .associateBy { it.candidateId }
        val rows = candidates.mapNotNull { candidate ->
            val candidateId = candidate.id ?: return@mapNotNull null
            CandidateSessionRow(candidate, sessions[candidateId] ?: return@mapNotNull null)
        }
        return if (requestedIds.isNotEmpty()) {
            rows
        } else {
            rows.filter { it.isHighQualityRecheckCandidate() }
                .sortedWith(
                    compareBy<CandidateSessionRow> { it.hoursUntilTrialReady() }
                        .thenByDescending { it.candidate.score ?: BigDecimal.ZERO }
                )
        }
    }

    private fun item(
        row: CandidateSessionRow,
        after: LeaderResearchCandidate,
        dryRun: Boolean
    ): LeaderResearchTrialReadyRecheckItemDto {
        val candidate = row.candidate
        val candidateId = candidate.id ?: 0L
        val stableHighScoreCount = stableHighScoreCount(candidateId)
        val reasons = blockers(candidate, row.session, stableHighScoreCount)
        val eligible = reasons.isEmpty()
        val action = when {
            !dryRun && after.researchState == LeaderResearchState.TRIAL_READY -> "PROMOTED_TRIAL_READY"
            !dryRun && after.researchState != candidate.researchState -> "STATE_CHANGED"
            eligible -> "READY_TO_PROMOTE"
            row.hoursUntilTrialReady() > 0 -> "WAIT_OBSERVATION"
            else -> "BLOCKED"
        }
        return LeaderResearchTrialReadyRecheckItemDto(
            candidateId = candidateId,
            wallet = candidate.normalizedWallet,
            beforeState = candidate.researchState.name,
            afterState = after.researchState.name,
            score = (candidate.score ?: BigDecimal.ZERO).strip(),
            tradeCount = row.session.tradeCount,
            filteredCount = row.session.filteredCount,
            copyablePnl = row.session.copyablePnl.strip(),
            filteredRatio = row.session.filteredRatio.strip(),
            ageHours = row.ageHours(),
            hoursUntilTrialReady = row.hoursUntilTrialReady(),
            eligible = eligible,
            action = action,
            reason = reasons.firstOrNull() ?: "meets_trial_ready_threshold"
        )
    }

    private fun blockers(
        candidate: LeaderResearchCandidate,
        session: LeaderPaperSession,
        stableHighScoreCount: Int
    ): List<String> {
        val blockers = mutableListOf<String>()
        val score = candidate.score ?: BigDecimal.ZERO
        val totalTrades = session.tradeCount + session.filteredCount
        val unknownRatio = if (session.openExposure > BigDecimal.ZERO) {
            session.unknownValuationExposure.divide(session.openExposure, 8, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }
        if (score < TRIAL_READY_MIN_SCORE) blockers += "score_below_80"
        LeaderResearchStrategyTypeClassifier.trialReadyBlockerCode(candidate.strategyType)?.let { blockers += it }
        blockers += LeaderResearchProfitWindowParser.parse(candidate.sourceEvidence).blockers
        if (!candidate.riskFlags.isNullOrBlank()) blockers += "risk_flags_present"
        if (System.currentTimeMillis() - session.startedAt < PAPER_MIN_AGE_MS) blockers += "waiting_observation_age"
        if (session.tradeCount < PAPER_MIN_TRADES) blockers += "paper_trades_below_10"
        if (totalTrades < PAPER_MIN_TRADES) blockers += "paper_total_samples_below_10"
        if (session.copyablePnl <= BigDecimal.ZERO) blockers += "copyable_pnl_not_positive"
        if (session.maxDrawdown < BigDecimal("-15")) blockers += "drawdown_gt_15"
        if (unknownRatio > BigDecimal("0.20")) blockers += "unknown_valuation_gt_20pct"
        if (session.filteredRatio >= BigDecimal("0.50")) blockers += "filtered_ratio_gt_or_eq_50pct"
        if (!candidate.isSourceFresh72h()) blockers += "source_stale_over_72h"
        if (stableHighScoreCount < TRIAL_READY_STABLE_SCORE_WINDOW) blockers += "stable_high_scores_below_3"
        return blockers
    }

    private fun stableHighScoreCount(candidateId: Long): Int {
        return scoreRepository.findByCandidateIdOrderByCreatedAtDesc(candidateId)
            .filter { it.scoreVersion == LeaderResearchScoringService.SCORE_VERSION }
            .take(TRIAL_READY_STABLE_SCORE_WINDOW)
            .count { it.totalScore >= TRIAL_READY_MIN_SCORE }
    }

    private fun CandidateSessionRow.isHighQualityRecheckCandidate(): Boolean {
        return (candidate.score ?: BigDecimal.ZERO) >= TRIAL_READY_MIN_SCORE &&
            LeaderResearchStrategyTypeClassifier.isTrialReadyCopyable(candidate.strategyType) &&
            LeaderResearchProfitWindowParser.parse(candidate.sourceEvidence).blockers.isEmpty() &&
            candidate.riskFlags.isNullOrBlank() &&
            candidate.isSourceFresh72h() &&
            session.tradeCount >= 20 &&
            session.copyablePnl > BigDecimal.ZERO &&
            session.filteredRatio < BigDecimal("0.50") &&
            session.maxDrawdown >= BigDecimal("-15")
    }

    private fun LeaderResearchCandidate.isSourceFresh72h(): Boolean {
        return lastSourceSeenAt?.let { System.currentTimeMillis() - it <= SOURCE_STALE_72H_MS } == true
    }

    private fun CandidateSessionRow.ageHours(): Long {
        return (System.currentTimeMillis() - session.startedAt).coerceAtLeast(0) / HOUR_MS
    }

    private fun CandidateSessionRow.hoursUntilTrialReady(): Long {
        val remaining = (PAPER_MIN_AGE_MS - (System.currentTimeMillis() - session.startedAt)).coerceAtLeast(0)
        return (remaining + HOUR_MS - 1) / HOUR_MS
    }

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    private data class CandidateSessionRow(
        val candidate: LeaderResearchCandidate,
        val session: LeaderPaperSession
    )

    companion object {
        private const val MAX_CANDIDATES = 100
        private const val HOUR_MS = 60L * 60 * 1000
        private const val SOURCE_STALE_72H_MS = 72L * 60 * 60 * 1000
        private const val PAPER_MIN_AGE_MS = 7L * 24 * 60 * 60 * 1000
        private const val PAPER_MIN_TRADES = 10
        private val TRIAL_READY_MIN_SCORE = BigDecimal("80")
        private const val TRIAL_READY_STABLE_SCORE_WINDOW = 3
    }
}
