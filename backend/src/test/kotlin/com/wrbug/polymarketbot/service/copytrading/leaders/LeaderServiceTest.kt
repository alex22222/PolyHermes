package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.dto.LeaderAddRequest
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BacktestTaskRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.service.common.BlockchainService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.eq
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`

class LeaderServiceTest {
    @Test
    fun `add leader checks duplicate by address and category`() {
        val leaderRepository = mock(LeaderRepository::class.java)
        val service = service(leaderRepository)
        val address = "0x0000000000000000000000000000000000000001"

        `when`(leaderRepository.findByLeaderAddressAndCategory(address, "crypto")).thenReturn(null)
        `when`(leaderRepository.save(org.mockito.ArgumentMatchers.any(Leader::class.java))).thenAnswer { invocation ->
            invocation.getArgument<Leader>(0).copy(id = 10)
        }

        val result = service.addLeader(LeaderAddRequest(leaderAddress = address, category = "crypto")).getOrThrow()

        assertEquals(10, result.id)
        assertEquals("crypto", result.category)
        verify(leaderRepository).findByLeaderAddressAndCategory(address, "crypto")
        verify(leaderRepository, never()).findByLeaderAddress(address)
    }

    @Test
    fun `add leader rejects duplicate address in same category`() {
        val leaderRepository = mock(LeaderRepository::class.java)
        val service = service(leaderRepository)
        val address = "0x0000000000000000000000000000000000000001"

        `when`(leaderRepository.findByLeaderAddressAndCategory(address, "crypto")).thenReturn(
            Leader(id = 7, leaderAddress = address, leaderName = "Existing", category = "crypto")
        )

        val result = service.addLeader(LeaderAddRequest(leaderAddress = address, category = "crypto"))

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()!!.message!!.contains("该 Leader 地址已存在"))
        verify(leaderRepository, never()).save(org.mockito.ArgumentMatchers.any(Leader::class.java))
    }

    private fun service(leaderRepository: LeaderRepository): LeaderService {
        val accountRepository = mock(AccountRepository::class.java)
        `when`(accountRepository.existsByWalletAddress(org.mockito.ArgumentMatchers.anyString())).thenReturn(false)
        return LeaderService(
            leaderRepository,
            accountRepository,
            mock(CopyTradingRepository::class.java),
            mock(BacktestTaskRepository::class.java),
            mock(BlockchainService::class.java)
        )
    }
}
