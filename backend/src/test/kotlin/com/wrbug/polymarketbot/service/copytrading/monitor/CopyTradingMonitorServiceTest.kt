package com.wrbug.polymarketbot.service.copytrading.monitor

import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.util.Optional

class CopyTradingMonitorServiceTest {
    private val copyTradingRepository: CopyTradingRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val accountRepository: AccountRepository = mock()
    private val activityWsService: PolymarketActivityWsService = mock()
    private val onChainWsService: OnChainWsService = mock()
    private val accountOnChainMonitorService: AccountOnChainMonitorService = mock()
    private val service = CopyTradingMonitorService(
        copyTradingRepository,
        leaderRepository,
        accountRepository,
        activityWsService,
        onChainWsService,
        accountOnChainMonitorService
    )

    @Test
    fun `reconciliation adds every enabled leader and removes a disabled leader`() = runBlocking {
        val first = CopyTrading(id = 3, accountId = 1, leaderId = 31, enabled = true)
        val second = CopyTrading(id = 4, accountId = 1, leaderId = 32, enabled = true)
        val firstLeader = Leader(id = 31, leaderAddress = "0x0000000000000000000000000000000000000031")
        val secondLeader = Leader(id = 32, leaderAddress = "0x0000000000000000000000000000000000000032")
        Mockito.`when`(copyTradingRepository.findByEnabledTrue()).thenReturn(listOf(first, second), listOf(second))
        Mockito.`when`(leaderRepository.findById(31)).thenReturn(Optional.of(firstLeader))
        Mockito.`when`(leaderRepository.findById(32)).thenReturn(Optional.of(secondLeader))
        Mockito.`when`(accountRepository.findById(1)).thenReturn(Optional.empty())

        service.reconcileEnabledMonitoringNow()
        service.reconcileEnabledMonitoringNow()

        Mockito.verify(activityWsService).addLeader(firstLeader)
        Mockito.verify(activityWsService).addLeader(secondLeader)
        Mockito.verify(onChainWsService).addLeader(firstLeader)
        Mockito.verify(onChainWsService).addLeader(secondLeader)
        Mockito.verify(activityWsService).removeLeader(31)
        Mockito.verify(onChainWsService).removeLeader(31)
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
