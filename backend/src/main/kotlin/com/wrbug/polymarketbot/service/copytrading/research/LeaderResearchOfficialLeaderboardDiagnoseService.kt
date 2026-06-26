package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardBucketDto
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardSampleDto
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchOfficialLeaderboardDiagnoseService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val paperSessionRepository: LeaderPaperSessionRepository
) {
    fun diagnose(request: LeaderResearchOfficialLeaderboardDiagnoseRequest): LeaderResearchOfficialLeaderboardDiagnoseResponse {
        val now = System.currentTimeMillis()
        val staleMs = request.staleHours.coerceIn(1, 24 * 30) * HOUR_MS
        val candidates = candidateRepository.findOfficialLeaderboardCandidates()
        val sessionsByCandidateId = candidates
            .mapNotNull { it.id }
            .takeIf { it.isNotEmpty() }
            ?.let { paperSessionRepository.findLatestByCandidateIds(it).associateBy { session -> session.candidateId } }
            .orEmpty()
        val diagnoses = candidates.map { candidate ->
            val session = candidate.id?.let { sessionsByCandidateId[it] }
            DiagnosedOfficialCandidate(
                candidate = candidate,
                session = session,
                category = categoryOf(candidate),
                bucket = bucketOf(candidate, session, now, staleMs),
                riskFlags = riskFlags(candidate)
            )
        }

        val buckets = diagnoses
            .groupingBy { it.bucket }
            .eachCount()
            .map { (bucket, count) ->
                LeaderResearchOfficialLeaderboardBucketDto(
                    bucket = bucket,
                    count = count,
                    description = BUCKET_DESCRIPTIONS[bucket].orEmpty()
                )
            }
            .sortedByDescending { it.count }

        val categories = listOf("politics", "finance", "sports", "crypto").map { category ->
            val categoryItems = diagnoses.filter { it.category == category }
            LeaderResearchOfficialLeaderboardCategoryDto(
                category = category,
                total = categoryItems.size,
                paper = categoryItems.count { it.candidate.researchState in PAPER_STATES },
                cleanHigh = categoryItems.count { it.bucket == "CLEAN_HIGH" },
                fastWatch = categoryItems.count { it.bucket == "FAST_WATCH" },
                readyForPaper = categoryItems.count { it.bucket == "READY_FOR_PAPER" },
                noActivitySample = categoryItems.count { it.bucket == "NO_ACTIVITY_SAMPLE" },
                staleActivity = categoryItems.count { it.bucket == "STALE_ACTIVITY" }
            )
        }

        val riskFlagCounts = diagnoses
            .flatMap { it.riskFlags }
            .groupingBy { it }
            .eachCount()
            .toSortedMap()

        val samples = diagnoses
            .sortedWith(
                compareBy<DiagnosedOfficialCandidate> { SAMPLE_BUCKET_RANK[it.bucket] ?: 99 }
                    .thenByDescending { it.candidate.score ?: BigDecimal.ZERO }
                    .thenByDescending { it.session?.copyablePnl ?: BigDecimal.ZERO }
            )
            .take(request.sampleLimit.coerceIn(1, 50))
            .map { sampleDto(it, now) }

        return LeaderResearchOfficialLeaderboardDiagnoseResponse(
            total = diagnoses.size,
            paperTotal = diagnoses.count { it.candidate.researchState in PAPER_STATES },
            cleanHighTotal = diagnoses.count { it.bucket == "CLEAN_HIGH" },
            fastWatchTotal = diagnoses.count { it.bucket == "FAST_WATCH" },
            readyForPaperTotal = diagnoses.count { it.bucket == "READY_FOR_PAPER" },
            buckets = buckets,
            categories = categories,
            riskFlagCounts = riskFlagCounts,
            samples = samples,
            generatedAt = now
        )
    }

    private fun bucketOf(candidate: LeaderResearchCandidate, session: LeaderPaperSession?, now: Long, staleMs: Long): String {
        val flags = riskFlags(candidate)
        val ageMs = candidate.lastSourceSeenAt?.let { now - it }
        val score = candidate.score ?: BigDecimal.ZERO
        val sourceFresh = ageMs?.let { it <= SOURCE_FRESH_48H_MS } == true
        if (candidate.locked) return "LOCKED"
        if ("no_activity_sample" in flags) return "NO_ACTIVITY_SAMPLE"
        if ("stale_activity" in flags || ageMs?.let { it > staleMs } == true) return "STALE_ACTIVITY"
        if ("tail_price_spray" in flags || "low_safe_price_ratio" in flags || "buy_only_no_exit" in flags) return "HARD_RISK"
        if ("mixed_category_evidence" in flags || categoryOf(candidate) !in PRIMARY_CATEGORIES) return "CATEGORY_CONFLICT"
        if (candidate.researchState == LeaderResearchState.PAPER || candidate.researchState == LeaderResearchState.TRIAL_READY) {
            if (session != null && score >= BigDecimal("80") && flags.isEmpty() && session.tradeCount >= 10 && session.copyablePnl > BigDecimal.ZERO) {
                val totalTrades = session.tradeCount + session.filteredCount
                return if (totalTrades >= 20 && session.filteredRatio < BigDecimal("0.20")) "FAST_WATCH" else "CLEAN_HIGH"
            }
            if (session?.filteredRatio?.let { it >= BigDecimal("0.50") } == true) return "HIGH_FILTERED_RATIO"
            if ("small_sample" in flags) return "SMALL_SAMPLE"
            return "PAPER_OBSERVING"
        }
        if (sourceFresh && score >= BigDecimal("70") && flags.isEmpty()) return "READY_FOR_PAPER"
        if ("small_sample" in flags) return "SMALL_SAMPLE"
        if (flags.isNotEmpty()) return "OTHER_RISK"
        return "OBSERVE"
    }

    private fun sampleDto(diagnosis: DiagnosedOfficialCandidate, now: Long): LeaderResearchOfficialLeaderboardSampleDto {
        val candidate = diagnosis.candidate
        val session = diagnosis.session
        return LeaderResearchOfficialLeaderboardSampleDto(
            candidateId = candidate.id ?: 0,
            wallet = candidate.normalizedWallet,
            category = diagnosis.category,
            bucket = diagnosis.bucket,
            researchState = candidate.researchState.name,
            score = candidate.score?.format4(),
            riskFlags = diagnosis.riskFlags,
            lastSourceAgeHours = candidate.lastSourceSeenAt?.let { ((now - it).coerceAtLeast(0) / HOUR_MS) },
            paperTrades = session?.tradeCount,
            filteredRatio = session?.filteredRatio?.format4(),
            copyablePnl = session?.copyablePnl?.format4(),
            sourceEvidence = candidate.sourceEvidence?.take(260)
        )
    }

    private fun categoryOf(candidate: LeaderResearchCandidate): String {
        return LeaderResearchCategoryEvidenceClassifier.classify(candidate.sourceEvidence, candidate.source).category
    }

    private fun riskFlags(candidate: LeaderResearchCandidate): List<String> {
        return candidate.riskFlags.orEmpty()
            .split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
    }

    private fun BigDecimal.format4(): String {
        return setScale(4, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
    }

    private data class DiagnosedOfficialCandidate(
        val candidate: LeaderResearchCandidate,
        val session: LeaderPaperSession?,
        val category: String,
        val bucket: String,
        val riskFlags: List<String>
    )

    companion object {
        private const val HOUR_MS = 60L * 60 * 1000
        private const val SOURCE_FRESH_48H_MS = 48L * HOUR_MS
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private val PAPER_STATES = setOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
        private val BUCKET_DESCRIPTIONS = mapOf(
            "READY_FOR_PAPER" to "来源新鲜、评分达标、无硬风险，可进入 PAPER 观察。",
            "FAST_WATCH" to "PAPER 中且满足快速观察特征，但仍需观察期。",
            "CLEAN_HIGH" to "PAPER 中的干净高分样本，接近可试跟候选。",
            "PAPER_OBSERVING" to "已进入 PAPER，但样本或收益质量仍需观察。",
            "SMALL_SAMPLE" to "交易样本不足，不应直接跟单。",
            "NO_ACTIVITY_SAMPLE" to "系统暂未捕获足够可评分活动。",
            "STALE_ACTIVITY" to "来源或活动过期，需要重新确认近期活跃。",
            "HIGH_FILTERED_RATIO" to "PAPER 过滤率高，可复制性差。",
            "HARD_RISK" to "存在低价长尾、低安全价格比例或只有买无退出等硬风险。",
            "CATEGORY_CONFLICT" to "分类证据混杂或不属于主类别。",
            "OTHER_RISK" to "存在其他风险标记。",
            "LOCKED" to "用户锁定候选，不自动处理。",
            "OBSERVE" to "暂不满足提拔条件，继续观察。"
        )
        private val SAMPLE_BUCKET_RANK = mapOf(
            "READY_FOR_PAPER" to 0,
            "FAST_WATCH" to 1,
            "CLEAN_HIGH" to 2,
            "PAPER_OBSERVING" to 3,
            "SMALL_SAMPLE" to 4,
            "NO_ACTIVITY_SAMPLE" to 5,
            "STALE_ACTIVITY" to 6,
            "HARD_RISK" to 7
        )
    }
}
