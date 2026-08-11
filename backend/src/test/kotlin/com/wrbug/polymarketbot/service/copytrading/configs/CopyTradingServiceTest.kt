package com.wrbug.polymarketbot.service.copytrading.configs

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsRequest
import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsResponse
import com.wrbug.polymarketbot.dto.CopyTradingUpdateRequest
import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.CopyTradingTemplateRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.service.copytrading.monitor.CopyTradingMonitorService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchLoopDiagnosticsService
import com.wrbug.polymarketbot.util.JsonUtils
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal
import java.util.Optional

class CopyTradingServiceTest {
    private val copyTradingRepository: CopyTradingRepository = mock()
    private val accountRepository: AccountRepository = mock()
    private val templateRepository: CopyTradingTemplateRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val leaderResearchCandidateRepository: LeaderResearchCandidateRepository = mock()
    private val leaderResearchLoopDiagnosticsService: LeaderResearchLoopDiagnosticsService = mock()
    private val monitorService: CopyTradingMonitorService = mock()
    private val jsonUtils: JsonUtils = mock()
    private val service = CopyTradingService(
        copyTradingRepository = copyTradingRepository,
        accountRepository = accountRepository,
        templateRepository = templateRepository,
        leaderRepository = leaderRepository,
        leaderResearchCandidateRepository = leaderResearchCandidateRepository,
        leaderResearchLoopDiagnosticsService = leaderResearchLoopDiagnosticsService,
        monitorService = monitorService,
        jsonUtils = jsonUtils,
        gson = Gson()
    )

    @Test
    fun `update copy trading blocks enabling research leader that is not strict ready`() {
        val copyTrading = CopyTrading(
            id = 10,
            accountId = 2,
            leaderId = 473,
            enabled = false
        )
        val candidate = LeaderResearchCandidate(
            id = 1755,
            normalizedWallet = "0x31c4578b25af36f34c8aa4cc85f0794bfbea622f",
            leaderId = 473,
            researchState = LeaderResearchState.COOLDOWN,
            score = BigDecimal("79.8")
        )
        Mockito.`when`(copyTradingRepository.findById(10)).thenReturn(Optional.of(copyTrading))
        Mockito.`when`(leaderResearchCandidateRepository.findByLeaderId(473)).thenReturn(candidate)
        Mockito.`when`(
            leaderResearchLoopDiagnosticsService.diagnose(
                LeaderResearchLoopDiagnosticsRequest(candidateIds = listOf(1755), sampleLimit = 1)
            )
        ).thenReturn(
            LeaderResearchLoopDiagnosticsResponse(
                generatedAt = 1,
                categories = listOf("politics", "finance"),
                enabledCopyConfigs = 0,
                strictReadyCount = 0,
                stateSummaries = emptyList(),
                samples = listOf(
                    LeaderResearchLoopDiagnosticsCandidateDto(
                        candidateId = 1755,
                        wallet = candidate.normalizedWallet,
                        researchState = "COOLDOWN",
                        score = "79.8",
                        riskFlags = emptyList(),
                        strategyType = "human_directional",
                        tradeCount = 32,
                        copyablePnl = "3.5",
                        filteredRatio = "0.11",
                        hasAllNamedEvidence = true,
                        sourceCategory = "politics",
                        blocker = "score_below_80"
                    )
                )
            )
        )

        val result = service.updateCopyTrading(CopyTradingUpdateRequest(copyTradingId = 10, enabled = true))

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message.orEmpty().contains("score_below_80"))
        Mockito.verify(copyTradingRepository, Mockito.never()).save(Mockito.any(CopyTrading::class.java))
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
