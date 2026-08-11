package com.wrbug.polymarketbot.service.copytrading.configs

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.CopyTradingListRequest
import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.CopyTradingTemplateRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.service.copytrading.monitor.CopyTradingMonitorService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchLoopDiagnosticsService
import com.wrbug.polymarketbot.util.JsonUtils
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class CopyTradingListPerformanceTest {
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
    fun `get copy trading list loads accounts and leaders in bulk`() {
        val first = CopyTrading(id = 1, accountId = 10, leaderId = 100)
        val second = CopyTrading(id = 2, accountId = 20, leaderId = 200)
        val accounts = listOf(
            Account(id = 10, walletAddress = "wallet-10", proxyAddress = "proxy-10"),
            Account(id = 20, walletAddress = "wallet-20", proxyAddress = "proxy-20")
        )
        val leaders = listOf(
            Leader(id = 100, leaderAddress = "leader-100"),
            Leader(id = 200, leaderAddress = "leader-200")
        )
        Mockito.`when`(copyTradingRepository.findAll()).thenReturn(listOf(first, second))
        Mockito.`when`(accountRepository.findAllById(setOf(10L, 20L))).thenReturn(accounts)
        Mockito.`when`(leaderRepository.findByIdIn(setOf(100L, 200L))).thenReturn(leaders)

        val result = service.getCopyTradingList(CopyTradingListRequest())

        assertEquals(listOf(1L, 2L), result.getOrThrow().list.map { it.id })
        Mockito.verify(accountRepository).findAllById(setOf(10L, 20L))
        Mockito.verify(leaderRepository).findByIdIn(setOf(100L, 200L))
        Mockito.verify(accountRepository, Mockito.never()).findById(Mockito.anyLong())
        Mockito.verify(leaderRepository, Mockito.never()).findById(Mockito.anyLong())
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
