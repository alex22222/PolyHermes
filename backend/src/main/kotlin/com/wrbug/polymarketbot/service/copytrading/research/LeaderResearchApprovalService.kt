package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.CopyTradingCreateRequest
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalPreviewAccountDto
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalPreviewRequest
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalPreviewResponse
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalRequest
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalResponse
import com.wrbug.polymarketbot.entity.LeaderPool
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderPoolStatus
import com.wrbug.polymarketbot.enums.LeaderResearchEventType
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.LeaderPoolRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.service.copytrading.configs.CopyTradingService
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal

class LeaderResearchCandidateNotReadyException : RuntimeException("候选尚未进入 TRIAL_READY，不能创建试跟配置")
class LeaderResearchApprovalConfirmRequiredException : RuntimeException("创建禁用试跟配置需要显式确认")
class LeaderResearchDuplicateTrialConfigException : RuntimeException("该账户已存在此 Leader 的跟单配置")
class LeaderResearchRealMoneyForbiddenException : RuntimeException("Leader Research Agent 不允许自动启用真钱跟单")
class LeaderResearchCandidateLockedException : RuntimeException("研究候选已锁定")
class LeaderResearchCandidateNotCopyableException(reason: String) : RuntimeException(reason)

@Service
class LeaderResearchApprovalService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val accountRepository: AccountRepository,
    private val copyTradingRepository: CopyTradingRepository,
    private val leaderPoolRepository: LeaderPoolRepository,
    private val copyTradingService: CopyTradingService,
    private val poolMappingService: LeaderResearchPoolMappingService,
    private val eventService: LeaderResearchEventService
) {
    private val logger = LoggerFactory.getLogger(LeaderResearchApprovalService::class.java)

    fun previewDisabledTrialConfig(request: LeaderResearchApprovalPreviewRequest): Result<LeaderResearchApprovalPreviewResponse> {
        return try {
            val candidate = candidateRepository.findById(request.candidateId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("候选不存在"))
            val leaderId = resolveLeaderId(candidate)
            val candidateBlockers = approvalBlockers(candidate, leaderId)
            val accounts = accountRepository.findAllByOrderByCreatedAtAsc()
            val accountDtos = accounts.mapNotNull { account ->
                val accountId = account.id ?: return@mapNotNull null
                val duplicate = leaderId?.let { copyTradingRepository.findByAccountIdAndLeaderId(accountId, it).firstOrNull() }
                LeaderResearchApprovalPreviewAccountDto(
                    accountId = accountId,
                    accountName = account.accountName,
                    walletAddress = account.walletAddress,
                    proxyAddress = account.proxyAddress,
                    enabled = account.isEnabled,
                    readOnly = account.isReadOnly,
                    duplicateConfigId = duplicate?.id,
                    duplicateConfigEnabled = duplicate?.enabled
                )
            }
            val blockers = candidateBlockers.toMutableList()
            if (accountDtos.isEmpty()) blockers += "no_accounts"
            if (accountDtos.isNotEmpty() && accountDtos.none { it.duplicateConfigId == null }) blockers += "all_accounts_duplicate"
            Result.success(
                LeaderResearchApprovalPreviewResponse(
                    candidateId = candidate.id ?: request.candidateId,
                    leaderId = leaderId,
                    poolId = candidate.poolId,
                    category = categoryOf(candidate),
                    strategyType = candidate.strategyType,
                    researchState = candidate.researchState.name,
                    riskFlags = riskFlags(candidate),
                    locked = candidate.locked,
                    canCreate = blockers.isEmpty(),
                    blockerCodes = blockers.distinct(),
                    accounts = accountDtos
                )
            )
        } catch (e: Exception) {
            logger.error("Leader research approval preview failed: candidateId=${request.candidateId}", e)
            Result.failure(e)
        }
    }

    @Transactional
    fun createDisabledTrialConfig(request: LeaderResearchApprovalRequest): Result<LeaderResearchApprovalResponse> {
        return try {
            if (!request.confirm) {
                return Result.failure(LeaderResearchApprovalConfirmRequiredException())
            }
            val candidate = candidateRepository.findById(request.candidateId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("候选不存在"))
            if (candidate.locked) {
                eventService.record(
                    type = LeaderResearchEventType.APPROVAL_REJECTED,
                    candidateId = candidate.id,
                    reason = "Candidate is locked; manual unlock is required before approval"
                )
                return Result.failure(LeaderResearchCandidateLockedException())
            }
            if (candidate.researchState != LeaderResearchState.TRIAL_READY) {
                eventService.record(
                    type = LeaderResearchEventType.APPROVAL_REJECTED,
                    candidateId = candidate.id,
                    reason = "Candidate state is ${candidate.researchState}, not TRIAL_READY"
                )
                return Result.failure(LeaderResearchCandidateNotReadyException())
            }
            val leaderId = resolveLeaderId(candidate)
            val copyabilityBlockers = approvalBlockers(candidate, leaderId)
            if (copyabilityBlockers.isNotEmpty()) {
                eventService.record(
                    type = LeaderResearchEventType.APPROVAL_REJECTED,
                    candidateId = candidate.id,
                    reason = "Candidate is not copyable for disabled trial: ${copyabilityBlockers.joinToString(",")}"
                )
                return Result.failure(LeaderResearchCandidateNotCopyableException(copyabilityBlockers.joinToString(",")))
            }
            val account = accountRepository.findByIdForUpdate(request.accountId)
                ?: return Result.failure(IllegalArgumentException("账户不存在"))
            val synced = poolMappingService.syncCandidate(candidate)
            val pool = synced.poolId?.let { leaderPoolRepository.findById(it).orElse(null) }
                ?: return Result.failure(IllegalStateException("Leader Pool 同步失败"))
            val syncedLeaderId = synced.leaderId ?: pool.leaderId
            if (copyTradingRepository.findByAccountIdAndLeaderId(account.id ?: request.accountId, syncedLeaderId).isNotEmpty()) {
                eventService.record(
                    type = LeaderResearchEventType.DUPLICATE_APPROVAL,
                    candidateId = candidate.id,
                    reason = "Duplicate copy trading config for account=${account.id}, leader=$syncedLeaderId"
                )
                return Result.failure(LeaderResearchDuplicateTrialConfigException())
            }

            val copyRequest = buildDisabledCopyTradingRequest(pool, request.accountId, syncedLeaderId)
            if (copyRequest.enabled) {
                eventService.record(
                    type = LeaderResearchEventType.REAL_MONEY_ACTIVATION_FORBIDDEN,
                    candidateId = candidate.id,
                    reason = "Research approval attempted to create enabled copy trading config",
                    dedupeKey = "approval-real-money-forbidden:${candidate.id}:${request.accountId}"
                )
                return Result.failure(LeaderResearchRealMoneyForbiddenException())
            }
            val copyTrading = copyTradingService.createCopyTrading(copyRequest).getOrThrow()
            val now = System.currentTimeMillis()
            leaderPoolRepository.save(
                pool.copy(
                    status = LeaderPoolStatus.TRIAL,
                    lastPromotedAt = now,
                    lastReviewedAt = now,
                    researchState = LeaderResearchState.TRIAL_READY,
                    researchBadge = "DISABLED_TRIAL_CREATED",
                    researchUpdatedAt = now,
                    updatedAt = now
                )
            )
            eventService.record(
                type = LeaderResearchEventType.APPROVAL_CREATED_DISABLED_CONFIG,
                candidateId = candidate.id,
                reason = "Created disabled copy trading config id=${copyTrading.id}; manual enable required",
                payloadSummary = "accountId=${request.accountId}, leaderId=$syncedLeaderId",
                dedupeKey = "approval-disabled:${candidate.id}:${request.accountId}"
            )
            Result.success(LeaderResearchApprovalResponse(copyTrading))
        } catch (e: Exception) {
            logger.error("Leader research approval failed: candidateId=${request.candidateId}", e)
            Result.failure(e)
        }
    }

    private fun buildDisabledCopyTradingRequest(pool: LeaderPool, accountId: Long, leaderId: Long): CopyTradingCreateRequest {
        val fixedAmount = pool.suggestedFixedAmount.takeIf { it > BigDecimal.ZERO } ?: BigDecimal("1.00000000")
        return CopyTradingCreateRequest(
            accountId = accountId,
            leaderId = leaderId,
            enabled = false,
            copyMode = "FIXED",
            copyRatio = "1",
            fixedAmount = fixedAmount.strip(),
            maxOrderSize = fixedAmount.strip(),
            minOrderSize = "1",
            maxDailyLoss = (pool.suggestedMaxDailyLoss.takeIf { it > BigDecimal.ZERO } ?: BigDecimal("5.00000000")).strip(),
            maxDailyOrders = pool.suggestedMaxDailyOrders.coerceIn(1, 10),
            priceTolerance = "1",
            delaySeconds = 0,
            pollIntervalSeconds = 5,
            useWebSocket = true,
            websocketReconnectInterval = 5000,
            websocketMaxRetries = 10,
            supportSell = true,
            minPrice = pool.suggestedMinPrice?.strip() ?: "0.1",
            maxPrice = pool.suggestedMaxPrice?.strip() ?: "0.8",
            maxPositionValue = pool.suggestedMaxPositionValue?.strip() ?: "5",
            keywordFilterMode = "DISABLED",
            keywords = null,
            configName = "Research试跟-${pool.researchCandidateId ?: pool.leaderId}",
            pushFailedOrders = true,
            pushFilteredOrders = true
        )
    }

    private fun resolveLeaderId(candidate: LeaderResearchCandidate): Long? {
        return candidate.leaderId ?: candidate.poolId?.let { leaderPoolRepository.findById(it).orElse(null)?.leaderId }
    }

    private fun approvalBlockers(candidate: LeaderResearchCandidate, leaderId: Long?): List<String> {
        val blockers = mutableListOf<String>()
        if (candidate.locked) blockers += "candidate_locked"
        if (candidate.researchState != LeaderResearchState.TRIAL_READY) blockers += "not_trial_ready"
        if (leaderId == null) blockers += "leader_mapping_missing"
        if (candidate.strategyType != "human_directional") blockers += "strategy_not_human_directional"
        blockers += LeaderResearchProfitWindowParser.parse(candidate.sourceEvidence).blockers
        if (riskFlags(candidate).isNotEmpty()) blockers += "risk_flags_not_empty"
        if (categoryOf(candidate) !in PRIMARY_CATEGORIES) blockers += "category_not_primary"
        return blockers
    }

    private fun riskFlags(candidate: LeaderResearchCandidate): List<String> {
        return candidate.riskFlags.orEmpty()
            .split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() }
    }

    private fun categoryOf(candidate: LeaderResearchCandidate): String {
        return officialLeaderboardCategory(candidate.sourceEvidence)
            ?: LeaderResearchCategoryEvidenceClassifier.classify(candidate.sourceEvidence, candidate.source).category
    }

    private fun officialLeaderboardCategory(sourceEvidence: String?): String? {
        return OFFICIAL_CATEGORY_REGEX.findAll(sourceEvidence.orEmpty())
            .mapNotNull { match -> normalizeCategory(match.groupValues.getOrNull(1)) }
            .firstOrNull()
    }

    private fun normalizeCategory(value: String?): String? {
        val normalized = value?.trim()?.lowercase()?.replace("_", "-") ?: return null
        return when (normalized) {
            "politics", "political" -> "politics"
            "finance", "financial", "economics", "economic" -> "finance"
            else -> normalized.takeIf { it in PRIMARY_CATEGORIES }
        }
    }

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    companion object {
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private val OFFICIAL_CATEGORY_REGEX = Regex(
            "external_analytics:polymarket_official_leaderboard[^\\n\\r]*category[:=]([a-z_-]+)",
            RegexOption.IGNORE_CASE
        )
    }
}
