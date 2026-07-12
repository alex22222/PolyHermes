package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderPaperSessionDto
import com.wrbug.polymarketbot.dto.LeaderResearchAllocationHealthDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateDetailDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListRequest
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListResponse
import com.wrbug.polymarketbot.dto.LeaderResearchEventDto
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelResponse
import com.wrbug.polymarketbot.dto.LeaderResearchSourceStateDto
import com.wrbug.polymarketbot.dto.LeaderResearchSummaryDto
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadinessDto
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

    fun findCandidatesByIds(candidateIds: Collection<Long>): List<LeaderResearchCandidate> {
        val ids = candidateIds.distinct().filter { it > 0 }
        if (ids.isEmpty()) return emptyList()
        val order = ids.withIndex().associate { it.value to it.index }
        return candidateRepository.findAllById(ids)
            .sortedBy { candidate -> order[candidate.id] ?: Int.MAX_VALUE }
    }

    fun funnelCandidatesByIds(candidateIds: Collection<Long>): List<LeaderResearchFunnelCandidateDto> {
        val candidates = findCandidatesByIds(candidateIds)
        if (candidates.isEmpty()) return emptyList()
        val order = candidateIds.distinct().withIndex().associate { it.value to it.index }
        val sessionsByCandidateId = paperSessionRepository.findLatestByCandidateIds(
            candidates.mapNotNull { it.id }
        ).associateBy { it.candidateId }
        val leaderCategoriesById = leaderCategoriesById(candidates)
        return candidates.mapNotNull { candidate ->
            val candidateId = candidate.id ?: return@mapNotNull null
            val session = sessionsByCandidateId[candidateId] ?: return@mapNotNull null
            val category = categoryOf(candidate, leaderCategoriesById)
            funnelCandidate(candidate, session, category)
        }.sortedBy { item -> order[item.candidateId] ?: Int.MAX_VALUE }
    }

    fun summary(): LeaderResearchSummaryDto {
        val activeCandidates = candidateRepository.findByResearchStateIn(
            listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
        )
        return LeaderResearchSummaryDto(
            discoveredCount = candidateRepository.countByResearchState(LeaderResearchState.DISCOVERED),
            candidateCount = candidateRepository.countByResearchState(LeaderResearchState.CANDIDATE),
            paperCount = candidateRepository.countByResearchState(LeaderResearchState.PAPER),
            trialReadyCount = candidateRepository.countByResearchState(LeaderResearchState.TRIAL_READY),
            cooldownCount = candidateRepository.countByResearchState(LeaderResearchState.COOLDOWN),
            retiredCount = candidateRepository.countByResearchState(LeaderResearchState.RETIRED),
            activePaperSessions = activeCandidates.count().toLong(),
            pendingRiskCount = candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.COOLDOWN)).count().toLong(),
            strategyTypeCounts = activeCandidates.strategyTypeCounts(),
            nonCopyableStrategyBlockers = activeCandidates.nonCopyableStrategyBlockers(),
            lastRun = runRepository.findTopByOrderByStartedAtDesc()?.let { mapper.runDto(it) },
            sourceLimitations = mapper.sourceLimitations()
        )
    }

    private fun List<LeaderResearchCandidate>.strategyTypeCounts(): List<com.wrbug.polymarketbot.dto.LeaderResearchCountDto> {
        return groupingBy { it.strategyType?.takeIf { value -> value.isNotBlank() } ?: LeaderResearchStrategyTypeClassifier.UNKNOWN }
            .eachCount()
            .entries
            .sortedWith(compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key })
            .map { com.wrbug.polymarketbot.dto.LeaderResearchCountDto(it.key, it.value.toLong()) }
    }

    private fun List<LeaderResearchCandidate>.nonCopyableStrategyBlockers(): List<com.wrbug.polymarketbot.dto.LeaderResearchCountDto> {
        return flatMap { candidate ->
            LeaderResearchStrategyTypeClassifier.trialReadyBlockerCode(candidate.strategyType)?.let { listOf(it) } ?: emptyList()
        }
            .groupingBy { it }
            .eachCount()
            .entries
            .sortedWith(compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key })
            .map { com.wrbug.polymarketbot.dto.LeaderResearchCountDto(it.key, it.value.toLong()) }
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
        val leaderCategoriesById = leaderCategoriesById(candidates)
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
            val categoryCandidates = candidates.filter { categoryOf(it, leaderCategoriesById) == category }
            val categoryPaper = paperCandidates.filter { categoryOf(it, leaderCategoriesById) == category }
            val categoryClean = cleanHighScore.filter { categoryOf(it, leaderCategoriesById) == category }
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
        val allocationHealth = buildAllocationHealth(categories)
        val priorityCandidates = cleanHighScore
            .sortedWith(
                compareBy<LeaderResearchCandidate> { allocationRank(it, allocationHealth.primaryDeficitCount, leaderCategoriesById) }
                    .thenByDescending { it.score ?: BigDecimal.ZERO }
                    .thenByDescending { candidate -> candidate.id?.let { latestSessionsByCandidateId[it]?.copyablePnl } ?: BigDecimal.ZERO }
            )
            .take(10)
            .mapNotNull { candidate ->
                val candidateId = candidate.id ?: return@mapNotNull null
                val session = latestSessionsByCandidateId[candidateId] ?: return@mapNotNull null
                val category = categoryOf(candidate, leaderCategoriesById)
                LeaderResearchFunnelCandidateDto(
                    candidateId = candidateId,
                    wallet = candidate.normalizedWallet,
                    category = category,
                    strategyType = candidate.strategyType,
                    score = candidate.score.format4(),
                    tradeCount = session.tradeCount,
                    filteredRatio = session.filteredRatio.format4(),
                    copyablePnl = session.copyablePnl.format4(),
                    maxDrawdown = session.maxDrawdown.format4(),
                    researchState = candidate.researchState.name,
                    trialReadiness = buildTrialReadiness(candidate, session)
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
            allocationHealth = allocationHealth,
            priorityCandidates = priorityCandidates,
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun buildAllocationHealth(categories: List<LeaderResearchFunnelCategoryDto>): LeaderResearchAllocationHealthDto {
        val primary = setOf("politics", "finance")
        val secondary = setOf("sports", "crypto")
        val primaryCount = categories
            .filter { it.category in primary }
            .sumOf { it.cleanHighScoreCandidates }
        val secondaryCount = categories
            .filter { it.category in secondary }
            .sumOf { it.cleanHighScoreCandidates }
        val total = (primaryCount + secondaryCount).coerceAtLeast(0)
        val primaryActual = percent(primaryCount, total)
        val secondaryActual = percent(secondaryCount, total)
        val requiredPrimary = if (total == 0) 0 else BigDecimal(total)
            .multiply(PRIMARY_ALLOCATION_TARGET)
            .setScale(0, RoundingMode.CEILING)
            .toInt()
        val primaryDeficit = (requiredPrimary - primaryCount).coerceAtLeast(0)
        val status = when {
            total == 0 -> "EMPTY"
            primaryDeficit == 0 -> "HEALTHY"
            primaryActual >= BigDecimal("70.0000") -> "WATCH"
            else -> "DEFICIT"
        }
        val message = when (status) {
            "EMPTY" -> "暂无 stable clean high 候选，优先积累 politics/finance 样本。"
            "HEALTHY" -> "主类别 politics/finance 已达到 80% 目标配比。"
            "WATCH" -> "主类别 politics/finance 接近目标，但还需补 ${primaryDeficit} 个 clean high 候选。"
            else -> "主类别 politics/finance 明显不足，至少还需补 ${primaryDeficit} 个 clean high 候选。"
        }
        return LeaderResearchAllocationHealthDto(
            primaryCategories = primary.toList(),
            secondaryCategories = secondary.toList(),
            primaryTargetPercent = PRIMARY_ALLOCATION_TARGET.multiply(BigDecimal("100")).format4(),
            secondaryTargetPercent = SECONDARY_ALLOCATION_TARGET.multiply(BigDecimal("100")).format4(),
            primaryActualPercent = primaryActual.format4(),
            secondaryActualPercent = secondaryActual.format4(),
            primaryCleanHighCount = primaryCount,
            secondaryCleanHighCount = secondaryCount,
            primaryDeficitCount = primaryDeficit,
            status = status,
            message = message
        )
    }

    private fun percent(count: Int, total: Int): BigDecimal {
        if (total <= 0) return BigDecimal.ZERO.setScale(4)
        return BigDecimal(count)
            .multiply(BigDecimal("100"))
            .divide(BigDecimal(total), 4, RoundingMode.HALF_UP)
    }

    private fun allocationRank(candidate: LeaderResearchCandidate, primaryDeficitCount: Int): Int {
        if (primaryDeficitCount <= 0) return 0
        return allocationRank(categoryOf(candidate))
    }

    private fun allocationRank(
        candidate: LeaderResearchCandidate,
        primaryDeficitCount: Int,
        leaderCategoriesById: Map<Long, String>
    ): Int {
        if (primaryDeficitCount <= 0) return 0
        return allocationRank(categoryOf(candidate, leaderCategoriesById))
    }

    private fun allocationRank(category: String): Int {
        return if (category in PRIMARY_CATEGORIES) 0 else 1
    }

    private fun buildTrialReadiness(
        candidate: LeaderResearchCandidate,
        session: com.wrbug.polymarketbot.entity.LeaderPaperSession,
        now: Long = System.currentTimeMillis()
    ): LeaderResearchTrialReadinessDto {
        val blockers = mutableListOf<String>()
        val score = candidate.score ?: BigDecimal.ZERO
        val ageMs = (now - session.startedAt).coerceAtLeast(0)
        val ageHours = ageMs / HOUR_MS
        val requiredAgeHours = PAPER_MIN_AGE_MS / HOUR_MS
        val hoursUntilTrialReady = ((PAPER_MIN_AGE_MS - ageMs).coerceAtLeast(0) + HOUR_MS - 1) / HOUR_MS
        val trialReadyAt = session.startedAt + PAPER_MIN_AGE_MS
        val totalTrades = session.tradeCount + session.filteredCount
        val unknownRatio = if (session.openExposure > BigDecimal.ZERO) {
            session.unknownValuationExposure.safeDivide(session.openExposure)
        } else {
            BigDecimal.ZERO
        }
        val stableHighScoreCount = latestStableHighScoreCount(candidate)

        if (score < TRIAL_READY_MIN_SCORE) blockers += "研究评分低于 80"
        LeaderResearchStrategyTypeClassifier.trialReadyBlocker(candidate.strategyType)?.let { blockers += it }
        if (!candidate.riskFlags.isNullOrBlank()) blockers += "风险标记未清空：${candidate.riskFlags}"
        blockers += profitWindowBlockerLabels(candidate.sourceEvidence)
        if (ageMs < PAPER_MIN_AGE_MS) blockers += "PAPER 观察不足 7 天：当前 ${ageHours} 小时"
        if (session.tradeCount < PAPER_MIN_TRADES) blockers += "通过模拟交易少于 10 笔：当前 ${session.tradeCount}"
        if (totalTrades < PAPER_MIN_TRADES) blockers += "模拟总样本少于 10 笔：当前 $totalTrades"
        if (session.copyablePnl <= BigDecimal.ZERO) blockers += "可复制 PnL 未转正"
        if (session.maxDrawdown < BigDecimal("-15")) blockers += "最大回撤低于 -15"
        if (unknownRatio > BigDecimal("0.20")) blockers += "未知估值敞口超过 20%"
        if (session.filteredRatio >= BigDecimal("0.50")) blockers += "过滤率不低于 50%"
        if (stableHighScoreCount < TRIAL_READY_STABLE_SCORE_WINDOW) {
            blockers += "最近稳定高分不足 ${TRIAL_READY_STABLE_SCORE_WINDOW} 次：当前 $stableHighScoreCount"
        }
        val fastWatchBlockers = buildFastWatchBlockers(
            candidate = candidate,
            session = session,
            score = score,
            ageMs = ageMs,
            totalTrades = totalTrades,
            unknownRatio = unknownRatio,
            stableHighScoreCount = stableHighScoreCount
        )
        val level = when {
            blockers.isEmpty() -> "TRIAL_READY"
            fastWatchBlockers.isEmpty() -> "FAST_WATCH"
            else -> "OBSERVE"
        }
        val label = when (level) {
            "TRIAL_READY" -> "可试跟"
            "FAST_WATCH" -> "快速观察"
            else -> "观察中"
        }

        return LeaderResearchTrialReadinessDto(
            eligible = blockers.isEmpty(),
            level = level,
            label = label,
            blockers = blockers,
            fastWatchBlockers = fastWatchBlockers,
            ageHours = ageHours,
            stableHighScoreCount = stableHighScoreCount,
            requiredStableHighScoreCount = TRIAL_READY_STABLE_SCORE_WINDOW,
            requiredAgeHours = requiredAgeHours,
            hoursUntilTrialReady = hoursUntilTrialReady,
            trialReadyAt = trialReadyAt
        )
    }

    private fun buildFastWatchBlockers(
        candidate: LeaderResearchCandidate,
        session: com.wrbug.polymarketbot.entity.LeaderPaperSession,
        score: BigDecimal,
        ageMs: Long,
        totalTrades: Int,
        unknownRatio: BigDecimal,
        stableHighScoreCount: Int
    ): List<String> {
        val blockers = mutableListOf<String>()
        if (score < FAST_WATCH_MIN_SCORE) blockers += "快速观察要求评分 >= 85"
        LeaderResearchStrategyTypeClassifier.trialReadyBlocker(candidate.strategyType)?.let { blockers += it }
        if (!candidate.riskFlags.isNullOrBlank()) blockers += "风险标记未清空：${candidate.riskFlags}"
        blockers += profitWindowBlockerLabels(candidate.sourceEvidence)
        if (ageMs < FAST_WATCH_MIN_AGE_MS) blockers += "快速观察至少需要 48 小时：当前 ${ageMs / HOUR_MS} 小时"
        if (session.tradeCount < FAST_WATCH_MIN_TRADES) blockers += "快速观察通过交易少于 ${FAST_WATCH_MIN_TRADES} 笔：当前 ${session.tradeCount}"
        if (totalTrades < FAST_WATCH_MIN_TRADES) blockers += "快速观察总样本少于 ${FAST_WATCH_MIN_TRADES} 笔：当前 $totalTrades"
        if (session.copyablePnl <= BigDecimal.ZERO) blockers += "可复制 PnL 未转正"
        if (session.maxDrawdown < BigDecimal("-8")) blockers += "快速观察最大回撤低于 -8"
        if (unknownRatio > BigDecimal("0.10")) blockers += "快速观察未知估值敞口超过 10%"
        if (session.filteredRatio >= BigDecimal("0.20")) blockers += "快速观察过滤率不低于 20%"
        if (stableHighScoreCount < TRIAL_READY_STABLE_SCORE_WINDOW) {
            blockers += "最近稳定高分不足 ${TRIAL_READY_STABLE_SCORE_WINDOW} 次：当前 $stableHighScoreCount"
        }
        return blockers
    }

    private fun profitWindowBlockerLabels(sourceEvidence: String?): List<String> {
        return LeaderResearchProfitWindowParser.parse(sourceEvidence).blockers.map { blocker ->
            when (blocker) {
                "needs_half_year_profit_window" -> "缺少长期盈利窗口证据"
                "needs_activity_window" -> "缺少近期活动窗口证据"
                "half_year_pnl_negative" -> "长期盈利窗口为负"
                "multi_window_profit_inconsistent" -> "盈利窗口不一致"
                "recent_pnl_negative" -> "近期盈利窗口为负"
                "inactive_recently" -> "近期活动不足"
                else -> blocker
            }
        }
    }

    private fun latestStableHighScoreCount(candidate: LeaderResearchCandidate): Int {
        val candidateId = candidate.id ?: return 0
        return scoreRepository.findByCandidateIdOrderByCreatedAtDesc(candidateId)
            .filter { it.scoreVersion == LeaderResearchScoringService.SCORE_VERSION }
            .take(TRIAL_READY_STABLE_SCORE_WINDOW)
            .count { it.totalScore >= TRIAL_READY_MIN_SCORE }
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

    fun fastWatch(request: LeaderResearchFastWatchRequest): LeaderResearchFastWatchResponse {
        val categories = request.categories
            .map { it.trim().lowercase() }
            .filter { it in CATEGORY_NAMES }
            .distinct()
            .ifEmpty { PRIMARY_CATEGORIES.toList() }
        val limit = request.limit.coerceIn(1, 100)
        val candidates = candidateRepository.findByResearchStateIn(
            listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
        )
        val latestSessionsByCandidateId = candidates
            .mapNotNull { it.id }
            .takeIf { it.isNotEmpty() }
            ?.let { paperSessionRepository.findLatestByCandidateIds(it).associateBy { session -> session.candidateId } }
            .orEmpty()
        val leaderCategoriesById = leaderCategoriesById(candidates)
        val allItems = candidates.mapNotNull { candidate ->
            val candidateId = candidate.id ?: return@mapNotNull null
            val category = categoryOf(candidate, leaderCategoriesById)
            if (category !in categories) return@mapNotNull null
            val session = latestSessionsByCandidateId[candidateId] ?: return@mapNotNull null
            val readiness = buildTrialReadiness(candidate, session)
            val shouldInclude = readiness.level == "FAST_WATCH" ||
                (request.includeTrialReady && readiness.level == "TRIAL_READY")
            if (!shouldInclude) return@mapNotNull null
            funnelCandidate(candidate, session, category, readiness)
        }.sortedWith(
            compareBy<LeaderResearchFunnelCandidateDto> { if (it.trialReadiness.level == "TRIAL_READY") 0 else 1 }
                .thenBy { allocationRank(it.category) }
                .thenByDescending { it.score.toBigDecimalOrNull() ?: BigDecimal.ZERO }
                .thenByDescending { it.copyablePnl.toBigDecimalOrNull() ?: BigDecimal.ZERO }
        )
        return LeaderResearchFastWatchResponse(
            total = allItems.size,
            fastWatchCount = allItems.count { it.trialReadiness.level == "FAST_WATCH" },
            trialReadyCount = allItems.count { it.trialReadiness.level == "TRIAL_READY" },
            categories = categories,
            criteria = "FAST_WATCH/TRIAL_READY from PAPER candidates; score>=85 for FAST_WATCH, >=48h age, >=20 paper trades, positive PnL, low unknown exposure, low filtered ratio, stable high score window=$TRIAL_READY_STABLE_SCORE_WINDOW",
            items = allItems.take(limit),
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun funnelCandidate(
        candidate: LeaderResearchCandidate,
        session: com.wrbug.polymarketbot.entity.LeaderPaperSession,
        category: String = categoryOf(candidate),
        readiness: LeaderResearchTrialReadinessDto = buildTrialReadiness(candidate, session)
    ): LeaderResearchFunnelCandidateDto {
        return LeaderResearchFunnelCandidateDto(
            candidateId = candidate.id ?: 0,
            wallet = candidate.normalizedWallet,
            category = category,
            strategyType = candidate.strategyType,
            score = candidate.score.format4(),
            tradeCount = session.tradeCount,
            filteredRatio = session.filteredRatio.format4(),
            copyablePnl = session.copyablePnl.format4(),
            maxDrawdown = session.maxDrawdown.format4(),
            researchState = candidate.researchState.name,
            trialReadiness = readiness
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

    private fun categoryOf(candidate: LeaderResearchCandidate, leaderCategoriesById: Map<Long, String>): String {
        return candidate.leaderId
            ?.let { leaderCategoriesById[it] }
            ?: categoryOf(candidate)
    }

    private fun leaderCategoriesById(candidates: List<LeaderResearchCandidate>): Map<Long, String> {
        val leaderIds = candidates.mapNotNull { it.leaderId }.distinct()
        if (leaderIds.isEmpty()) return emptyMap()
        return leaderRepository.findByIdIn(leaderIds)
            .mapNotNull { leader ->
                val id = leader.id ?: return@mapNotNull null
                val category = leader.category?.trim()?.lowercase()
                    ?.takeIf { it in CATEGORY_NAMES }
                    ?: return@mapNotNull null
                id to category
            }
            .toMap()
    }

    private fun BigDecimal?.format4(): String {
        return (this ?: BigDecimal.ZERO).setScale(4, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
    }

    private fun BigDecimal.safeDivide(other: BigDecimal): BigDecimal {
        if (other.compareTo(BigDecimal.ZERO) == 0) return BigDecimal.ZERO
        return divide(other, 8, RoundingMode.HALF_UP)
    }

    companion object {
        private const val LEADER_DISCOVERY_TARGET = 1000
        private val HIGH_SCORE_THRESHOLD = BigDecimal("80")
        private const val HIGH_SCORE_MIN_TRADES = 10
        private val TRIAL_READY_MIN_SCORE = BigDecimal("80")
        private const val TRIAL_READY_STABLE_SCORE_WINDOW = 3
        private const val PAPER_MIN_TRADES = 10
        private const val PAPER_MIN_AGE_MS = 7L * 24 * 60 * 60 * 1000
        private val FAST_WATCH_MIN_SCORE = BigDecimal("85")
        private const val FAST_WATCH_MIN_TRADES = 20
        private const val FAST_WATCH_MIN_AGE_MS = 48L * 60 * 60 * 1000
        private const val HOUR_MS = 60L * 60 * 1000
        private val CATEGORY_NAMES = setOf("politics", "finance", "sports", "crypto")
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private val PRIMARY_ALLOCATION_TARGET = BigDecimal("0.80")
        private val SECONDARY_ALLOCATION_TARGET = BigDecimal("0.20")
    }
}
