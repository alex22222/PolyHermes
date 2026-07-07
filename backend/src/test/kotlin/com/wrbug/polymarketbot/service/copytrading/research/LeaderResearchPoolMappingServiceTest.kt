package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.entity.LeaderPool
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPoolRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.ArgumentCaptor
import org.mockito.Mockito
import java.util.Optional

class LeaderResearchPoolMappingServiceTest {
    private val leaderRepository: LeaderRepository = mock()
    private val leaderPoolRepository: LeaderPoolRepository = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val service = LeaderResearchPoolMappingService(leaderRepository, leaderPoolRepository, candidateRepository)

    @Test
    fun `sync fills missing leader category from research evidence`() {
        val candidate = financeCandidate(leaderId = 11L)
        val leader = Leader(
            id = 11L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Research 0x1111",
            category = null
        )
        Mockito.`when`(leaderRepository.findById(11L)).thenReturn(Optional.of(leader))
        Mockito.`when`(leaderRepository.save(anyLeader())).thenAnswer { it.arguments[0] }
        Mockito.`when`(leaderPoolRepository.findByLeaderId(11L)).thenReturn(pool())
        Mockito.`when`(leaderPoolRepository.save(anyPool())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        service.syncCandidate(candidate)

        val captor = ArgumentCaptor.forClass(Leader::class.java)
        Mockito.verify(leaderRepository).save(captor.capture())
        assertEquals("finance", captor.value.category)
    }

    @Test
    fun `sync keeps existing leader category`() {
        val candidate = financeCandidate(leaderId = 11L)
        val leader = Leader(
            id = 11L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Manual Leader",
            category = "sports"
        )
        Mockito.`when`(leaderRepository.findById(11L)).thenReturn(Optional.of(leader))
        Mockito.`when`(leaderPoolRepository.findByLeaderId(11L)).thenReturn(pool())
        Mockito.`when`(leaderPoolRepository.save(anyPool())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        service.syncCandidate(candidate)

        Mockito.verify(leaderRepository, Mockito.never()).save(anyLeader())
    }

    private fun financeCandidate(leaderId: Long): LeaderResearchCandidate {
        return LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            leaderId = leaderId,
            researchState = LeaderResearchState.PAPER,
            sourceEvidence = "activity_source:finance | category:finance | events:20"
        )
    }

    private fun pool(): LeaderPool {
        return LeaderPool(
            id = 2L,
            leaderId = 11L
        )
    }

    private fun anyLeader(): Leader {
        Mockito.any(Leader::class.java)
        return Leader(leaderAddress = "0x2222222222222222222222222222222222222222")
    }

    private fun anyPool(): LeaderPool {
        Mockito.any(LeaderPool::class.java)
        return LeaderPool(leaderId = 11L)
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x3333333333333333333333333333333333333333")
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
