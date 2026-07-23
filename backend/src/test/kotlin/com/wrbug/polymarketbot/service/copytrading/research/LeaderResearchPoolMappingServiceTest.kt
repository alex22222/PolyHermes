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
    fun `sync creates category leader instead of mutating mismatched manual leader`() {
        val candidate = financeCandidate(leaderId = 11L)
        val leader = Leader(
            id = 11L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Manual Leader",
            category = "sports"
        )
        Mockito.`when`(leaderRepository.findByLeaderAddressAndCategory(candidate.normalizedWallet, "finance")).thenReturn(null)
        Mockito.`when`(leaderRepository.findById(11L)).thenReturn(Optional.of(leader))
        Mockito.`when`(leaderRepository.save(anyLeader())).thenAnswer { (it.arguments[0] as Leader).copy(id = 12L) }
        Mockito.`when`(leaderPoolRepository.findByLeaderId(12L)).thenReturn(null)
        Mockito.`when`(leaderPoolRepository.save(anyPool())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        service.syncCandidate(candidate)

        val captor = ArgumentCaptor.forClass(Leader::class.java)
        Mockito.verify(leaderRepository).save(captor.capture())
        assertEquals("finance", captor.value.category)
        Mockito.verify(leaderPoolRepository).findByLeaderId(12L)
    }

    @Test
    fun `sync corrects research agent managed leader category from research evidence`() {
        val candidate = financeCandidate(leaderId = 11L)
        val leader = Leader(
            id = 11L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Hideous-Racer",
            category = "crypto"
        )
        Mockito.`when`(leaderRepository.findById(11L)).thenReturn(Optional.of(leader))
        Mockito.`when`(leaderRepository.save(anyLeader())).thenAnswer { it.arguments[0] }
        Mockito.`when`(leaderPoolRepository.findByLeaderId(11L)).thenReturn(pool(source = "RESEARCH_AGENT"))
        Mockito.`when`(leaderPoolRepository.save(anyPool())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        service.syncCandidate(candidate)

        val captor = ArgumentCaptor.forClass(Leader::class.java)
        Mockito.verify(leaderRepository).save(captor.capture())
        assertEquals("finance", captor.value.category)
    }

    @Test
    fun `sync uses existing category leader instead of mutating mismatched leader`() {
        val candidate = financeCandidate(leaderId = 11L)
        val cryptoLeader = Leader(
            id = 11L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Existing Crypto",
            category = "crypto"
        )
        val financeLeader = Leader(
            id = 12L,
            leaderAddress = candidate.normalizedWallet,
            leaderName = "Existing Finance",
            category = "finance"
        )
        Mockito.`when`(leaderRepository.findByLeaderAddressAndCategory(candidate.normalizedWallet, "finance"))
            .thenReturn(financeLeader)
        Mockito.`when`(leaderRepository.findById(11L)).thenReturn(Optional.of(cryptoLeader))
        Mockito.`when`(leaderPoolRepository.findByLeaderId(12L)).thenReturn(pool(leaderId = 12L, source = "RESEARCH_AGENT"))
        Mockito.`when`(leaderPoolRepository.save(anyPool())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val saved = service.syncCandidate(candidate)

        assertEquals(12L, saved.leaderId)
        Mockito.verify(leaderRepository, Mockito.never()).save(anyLeader())
        Mockito.verify(leaderPoolRepository).findByLeaderId(12L)
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

    private fun pool(leaderId: Long = 11L, source: String = "MANUAL"): LeaderPool {
        return LeaderPool(
            id = 2L,
            leaderId = leaderId,
            source = source
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
