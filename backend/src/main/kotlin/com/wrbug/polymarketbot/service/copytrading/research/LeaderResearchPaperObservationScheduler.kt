package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.service.loop.LoopGoalControlService
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.util.concurrent.atomic.AtomicBoolean

@Service
class LeaderResearchPaperObservationScheduler(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val paperTradingService: LeaderPaperTradingService,
    private val trialReadyRecheckService: LeaderResearchTrialReadyRecheckService,
    private val loopGoalControlService: LoopGoalControlService,
    @Value("\${leader.research.paper-observation.enabled:false}") private val enabled: Boolean,
    @Value("\${leader.research.paper-observation.max-candidates:5}") private val maxCandidates: Int,
    @Value("\${leader.research.paper-observation.batch-size:20}") private val batchSize: Int,
    @Value("\${leader.research.paper-observation.max-transition-age-hours:336}") private val maxTransitionAgeHours: Long
) {
    private val logger = LoggerFactory.getLogger(LeaderResearchPaperObservationScheduler::class.java)
    private val running = AtomicBoolean(false)

    @Scheduled(
        fixedDelayString = "\${leader.research.paper-observation.fixed-delay-ms:3600000}",
        initialDelayString = "\${leader.research.paper-observation.initial-delay-ms:60000}"
    )
    fun scheduledRun() {
        if (!enabled || !loopGoalControlService.isLeaderDiscoveryActive()) return
        if (!running.compareAndSet(false, true)) {
            logger.info("Scoped PAPER observation skipped because a prior run is still active")
            return
        }
        try {
            observeOnce()
        } catch (error: RuntimeException) {
            logger.warn("Scoped PAPER observation failed: {}", error.message, error)
        } finally {
            running.set(false)
        }
    }

    internal fun observeOnce(): List<Long> {
        val now = System.currentTimeMillis()
        val candidateLimit = maxCandidates.coerceIn(1, MAX_CANDIDATES)
        val candidates = candidateRepository.findByResearchStateIn(
            listOf(LeaderResearchState.PAPER),
            PageRequest.of(0, candidateLimit * SCAN_MULTIPLIER, Sort.by(Sort.Direction.DESC, "lastTransitionAt"))
        ).content.filter { candidate -> candidate.isEligible(now) }
            .take(candidateLimit)
        val candidateIds = candidates.mapNotNull { it.id }
        if (candidateIds.isEmpty()) {
            logger.info("Scoped PAPER observation found no eligible candidates")
            return emptyList()
        }

        val processing = paperTradingService.processPaperCandidates(
            runId = null,
            batchSize = batchSize.coerceIn(1, MAX_BATCH_SIZE),
            candidateIds = candidateIds
        )
        val recheck = trialReadyRecheckService.recheck(
            LeaderResearchTrialReadyRecheckRequest(dryRun = false, candidateIds = candidateIds, maxCandidates = candidateIds.size)
        )
        logger.info(
            "Scoped PAPER observation completed: candidates={}, processed={}, filtered={}, failed={}, trialReady={}",
            candidateIds,
            processing.processed,
            processing.filtered,
            processing.failed,
            recheck.trialReadyCandidateIds
        )
        return candidateIds
    }

    private fun LeaderResearchCandidate.isEligible(now: Long): Boolean {
        val transitionAt = lastTransitionAt ?: return false
        return (score ?: BigDecimal.ZERO) >= MIN_SCORE &&
            riskFlags.isNullOrBlank() &&
            lastSourceSeenAt?.let { now - it <= SOURCE_STALE_MS } == true &&
            now - transitionAt <= maxTransitionAgeHours.coerceAtLeast(1) * HOUR_MS &&
            sourceEvidence.orEmpty().contains(OFFICIAL_LEADERBOARD_TOKEN, ignoreCase = true) &&
            LeaderResearchCategoryEvidenceClassifier.classify(sourceEvidence).let { it.category in PRIMARY_CATEGORIES && !it.mixed }
    }

    companion object {
        private const val MAX_CANDIDATES = 10
        private const val SCAN_MULTIPLIER = 5
        private const val MAX_BATCH_SIZE = 100
        private const val HOUR_MS = 60L * 60 * 1000
        private const val SOURCE_STALE_MS = 72L * HOUR_MS
        private val MIN_SCORE = BigDecimal("80")
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private const val OFFICIAL_LEADERBOARD_TOKEN = "polymarket_official_leaderboard"
    }
}
