package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderPaperSessionDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateDetailDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListRequest
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListResponse
import com.wrbug.polymarketbot.dto.LeaderResearchEventDto
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelResponse
import com.wrbug.polymarketbot.dto.LeaderResearchSourceStateDto
import com.wrbug.polymarketbot.dto.LeaderResearchSummaryDto
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperPositionRepository
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderPaperTradeRepository
import com.wrbug.polymarketbot.repository.LeaderPoolRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchEventRepository
import com.wrbug.polymarketbot.repository.LeaderResearchRunRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import com.wrbug.polymarketbot.repository.LeaderResearchSourceStateRepository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val runRepository: LeaderResearchRunRepository,
    private val scoreRepository: LeaderResearchScoreRepository,
    private val sourceStateRepository: LeaderResearchSourceStateRepository,
    private val eventRepository: LeaderResearchEventRepository,
    private val paperSessionRepository: LeaderPaperSessionRepository,
    private val paperTradeRepository: LeaderPaperTradeRepository,
    private val paperPositionRepository: LeaderPaperPositionRepository,
    private val leaderRepository: LeaderRepository,
    private val leaderPoolRepository: LeaderPoolRepository,
    private val mapper: LeaderResearchMapper
) {
    fun findCandidatesForStates(states: Collection<LeaderResearchState>): List<LeaderResearchCandidate> {
        return candidateRepository.findByResearchStateIn(states)
    }

    fun summary(): LeaderResearchSummaryDto {
        return LeaderResearchSummaryDto(
            discoveredCount = candidateRepository.countByResearchState(LeaderResearchState.DISCOVERED),
            candidateCount = candidateRepository.countByResearchState(LeaderResearchState.CANDIDATE),
            paperCount = candidateRepository.countByResearchState(LeaderResearchState.PAPER),
            trialReadyCount = candidateRepository.countByResearchState(LeaderResearchState.TRIAL_READY),
            cooldownCount = candidateRepository.countByResearchState(LeaderResearchState.COOLDOWN),
            retiredCount = candidateRepository.countByResearchState(LeaderResearchState.RETIRED),
            activePaperSessions = candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)).count().toLong(),
            pendingRiskCount = candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.COOLDOWN)).count().toLong(),
            lastRun = runRepository.findTopByOrderByStartedAtDesc()?.let { mapper.runDto(it) },
            sourceLimitations = mapper.sourceLimitations()
        )
    }

    fun funnel(): LeaderResearchFunnelResponse {
        val candidates = candidateRepository.findAll()
        val paperCandidates = candidates.filter {
            it.researchState in listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
        }
        val latestSessionsByCandidateId = paperCandidates
            .mapNotNull { it.id }
            .takeIf { it.isNotEmpty() }
            ?.let { paperSessionRepository.findLatestByCandidateIds(it).associateBy { session -> session.candidateId } }
            .orEmpty()
        val cleanHighScore = paperCandidates.filter { candidate ->
            val session = candidate.id?.let { latestSessionsByCandidateId[it] }
            candidate.score != null &&
                candidate.score >= HIGH_SCORE_THRESHOLD &&
                candidate.riskFlags.isNullOrBlank() &&
                session != null &&
                session.tradeCount >= HIGH_SCORE_MIN_TRADES &&
                session.copyablePnl > BigDecimal.ZERO
        }
        val categoryNames = listOf("politics", "finance", "sports", "crypto")
        val categories = categoryNames.map { category ->
            val categoryCandidates = candidates.filter { categoryOf(it) == category }
            val categoryPaper = paperCandidates.filter { categoryOf(it) == category }
            val categoryClean = cleanHighScore.filter { categoryOf(it) == category }
            val top = categoryClean.maxByOrNull { it.score ?: BigDecimal.ZERO }
            LeaderResearchFunnelCategoryDto(
                category = category,
                totalCandidates = categoryCandidates.size,
                paperCandidates = categoryPaper.size,
                cleanHighScoreCandidates = categoryClean.size,
                topScore = top?.score?.format4(),
                topCandidateId = top?.id
            )
        }
        val priorityCandidates = cleanHighScore
            .sortedWith(
                compareByDescending<LeaderResearchCandidate> { it.score ?: BigDecimal.ZERO }
                    .thenByDescending { candidate -> candidate.id?.let { latestSessionsByCandidateId[it]?.copyablePnl } ?: BigDecimal.ZERO }
            )
            .take(10)
            .mapNotNull { candidate ->
                val candidateId = candidate.id ?: return@mapNotNull null
                val session = latestSessionsByCandidateId[candidateId] ?: return@mapNotNull null
                LeaderResearchFunnelCandidateDto(
                    candidateId = candidateId,
                    wallet = candidate.normalizedWallet,
                    category = categoryOf(candidate),
                    score = candidate.score.format4(),
                    tradeCount = session.tradeCount,
                    filteredRatio = session.filteredRatio.format4(),
                    copyablePnl = session.copyablePnl.format4(),
                    maxDrawdown = session.maxDrawdown.format4(),
                    researchState = candidate.researchState.name
                )
            }
        return LeaderResearchFunnelResponse(
            targetTotal = LEADER_DISCOVERY_TARGET,
            totalCandidates = candidates.size,
            managedLeaderTotal = leaderRepository.count(),
            leaderPoolTotal = leaderPoolRepository.count(),
            progressPercent = BigDecimal(candidates.size)
                .multiply(BigDecimal("100"))
                .divide(BigDecimal(LEADER_DISCOVERY_TARGET), 4, RoundingMode.HALF_UP)
                .toPlainString(),
            cleanHighScoreTotal = cleanHighScore.size,
            criteria = "PAPER/TRIAL_READY, score>=80, riskFlags empty, tradeCount>=10, copyablePnl>0",
            categories = categories,
            priorityCandidates = priorityCandidates,
            generatedAt = System.currentTimeMillis()
        )
    }

    fun listCandidates(request: LeaderResearchCandidateListRequest): LeaderResearchCandidateListResponse {
        val pageable = PageRequest.of(request.page.coerceAtLeast(0), request.size.coerceIn(1, 100))
        val state = request.state?.trim()?.takeIf { it.isNotBlank() }?.let { LeaderResearchState.valueOf(it.uppercase()) }
        val query = request.query?.trim()?.lowercase()?.takeIf { it.isNotBlank() }
        val page = candidateRepository.search(state, query, pageable)
        val content = page.content
        return LeaderResearchCandidateListResponse(
            list = mapper.candidateDtos(content, listContext(content)),
            total = page.totalElements,
            summary = summary()
        )
    }

    private fun listContext(candidates: List<com.wrbug.polymarketbot.entity.LeaderResearchCandidate>): LeaderResearchCandidateDtoContext {
        if (candidates.isEmpty()) return LeaderResearchCandidateDtoContext()
        val leaderIds = candidates.mapNotNull { it.leaderId }.distinct()
        val poolIds = candidates.mapNotNull { it.poolId }.distinct()
        val candidateIds = candidates.mapNotNull { it.id }.distinct()
        return LeaderResearchCandidateDtoContext(
            leadersById = if (leaderIds.isEmpty()) emptyMap() else leaderRepository.findByIdIn(leaderIds)
                .mapNotNull { leader -> leader.id?.let { it to leader } }
                .toMap(),
            poolsById = if (poolIds.isEmpty()) emptyMap() else leaderPoolRepository.findByIdIn(poolIds)
                .mapNotNull { pool -> pool.id?.let { it to pool } }
                .toMap(),
            latestSessionsByCandidateId = if (candidateIds.isEmpty()) emptyMap() else paperSessionRepository.findLatestByCandidateIds(candidateIds)
                .associateBy { it.candidateId }
        )
    }

    fun detail(candidateId: Long): LeaderResearchCandidateDetailDto {
        val candidate = candidateRepository.findById(candidateId).orElseThrow { IllegalArgumentException("候选不存在") }
        val sessions = paperSessionRepository.findByCandidateIdOrderByStartedAtDesc(candidateId)
        val latestSession = sessions.firstOrNull()
        val trades = latestSession?.id?.let {
            paperTradeRepository.findBySessionIdOrderByEventTimeDesc(it, PageRequest.of(0, 100)).content
        }.orEmpty()
        val positions = latestSession?.id?.let { paperPositionRepository.findBySessionIdOrderByUpdatedAtDesc(it) }.orEmpty()
        return LeaderResearchCandidateDetailDto(
            candidate = mapper.candidateDto(candidate, latestSession),
            latestScore = scoreRepository.findTopByCandidateIdOrderByCreatedAtDesc(candidateId)?.let { mapper.scoreDto(it) },
            paperSessions = sessions.map { mapper.paperSessionDto(it) },
            paperTrades = trades.map { mapper.paperTradeDto(it) },
            paperPositions = positions.map { mapper.paperPositionDto(it) },
            events = eventRepository.findByCandidateIdOrderByCreatedAtDesc(candidateId, PageRequest.of(0, 100)).content.map { mapper.eventDto(it) }
        )
    }

    fun sourceHealth(): List<LeaderResearchSourceStateDto> {
        return sourceStateRepository.findAllByOrderByUpdatedAtDesc().map { mapper.sourceStateDto(it) }
    }

    fun events(page: Int, size: Int): List<LeaderResearchEventDto> {
        return eventRepository.findAllByOrderByCreatedAtDesc(PageRequest.of(page.coerceAtLeast(0), size.coerceIn(1, 100)))
            .content
            .map { mapper.eventDto(it) }
    }

    fun paperSessions(candidateId: Long): List<LeaderPaperSessionDto> {
        return paperSessionRepository.findByCandidateIdOrderByStartedAtDesc(candidateId).map { mapper.paperSessionDto(it) }
    }

    private fun categoryOf(candidate: LeaderResearchCandidate): String {
        val evidence = candidate.sourceEvidence.orEmpty().lowercase()
        val categoryMatch = Regex("category:([a-z_\\-]+)")
            .findAll(evidence)
            .mapNotNull { it.groupValues.getOrNull(1) }
            .lastOrNull { it in listOf("politics", "finance", "sports", "crypto") }
        return when {
            categoryMatch != null -> categoryMatch
            evidence.contains("politic") || evidence.contains("election") -> "politics"
            evidence.contains("finance") || evidence.contains("fed") || evidence.contains("rate") -> "finance"
            evidence.contains("sport") || evidence.contains("soccer") || evidence.contains("nba") -> "sports"
            evidence.contains("crypto") || evidence.contains("bitcoin") || evidence.contains("btc") -> "crypto"
            else -> "unknown"
        }
    }

    private fun BigDecimal?.format4(): String {
        return (this ?: BigDecimal.ZERO).setScale(4, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
    }

    companion object {
        private const val LEADER_DISCOVERY_TARGET = 1000
        private val HIGH_SCORE_THRESHOLD = BigDecimal("80")
        private const val HIGH_SCORE_MIN_TRADES = 10
    }
}
