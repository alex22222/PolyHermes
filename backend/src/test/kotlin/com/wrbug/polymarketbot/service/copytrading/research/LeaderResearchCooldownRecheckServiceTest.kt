package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchCooldownRecheckRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchCooldownRecheckServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val stateMachine: LeaderResearchStateMachine = mock()
    private val service = LeaderResearchCooldownRecheckService(candidateRepository, stateMachine)

    @Test
    fun `dry run predicts elapsed fresh cooldown recovery without advancing`() {
        val now = System.currentTimeMillis()
        val candidate = cooldownCandidate(
            id = 2846L,
            cooldownUntil = now - 1_000L,
            lastSourceSeenAt = now - 60_000L
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(2846L))).thenReturn(listOf(candidate))

        val result = service.recheck(LeaderResearchCooldownRecheckRequest(candidateIds = listOf(2846L)))

        assertEquals(true, result.dryRun)
        assertEquals(1, result.scannedCount)
        assertEquals(1, result.selectedCount)
        assertEquals(0, result.advancedCount)
        assertEquals(listOf(2846L), result.recoveredCandidateIds)
        val item = result.items.single()
        assertEquals("COOLDOWN", item.beforeState)
        assertEquals("CANDIDATE", item.afterState)
        assertEquals("READY_TO_RECOVER", item.action)
        Mockito.verify(stateMachine, Mockito.never()).advance(anyCandidate(), Mockito.any())
    }

    @Test
    fun `live recheck advances only targeted cooldown candidates`() {
        val now = System.currentTimeMillis()
        val cooldown = cooldownCandidate(
            id = 2846L,
            cooldownUntil = now - 1_000L,
            lastSourceSeenAt = now - 60_000L
        )
        val paper = LeaderResearchCandidate(
            id = 2722L,
            normalizedWallet = "0x2222222222222222222222222222222222222222",
            researchState = LeaderResearchState.PAPER
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(2846L, 2722L))).thenReturn(listOf(cooldown, paper))
        Mockito.`when`(stateMachine.advance(cooldown, runId = null))
            .thenReturn(cooldown.copy(researchState = LeaderResearchState.CANDIDATE))

        val result = service.recheck(
            LeaderResearchCooldownRecheckRequest(
                dryRun = false,
                candidateIds = listOf(2846L, 2722L)
            )
        )

        assertEquals(false, result.dryRun)
        assertEquals(2, result.scannedCount)
        assertEquals(1, result.selectedCount)
        assertEquals(1, result.advancedCount)
        assertEquals(listOf(2846L), result.recoveredCandidateIds)
        assertEquals("SKIPPED", result.items.first { it.candidateId == 2722L }.action)
        Mockito.verify(stateMachine).advance(cooldown, runId = null)
        Mockito.verify(stateMachine, Mockito.never()).advance(paper, runId = null)
    }

    @Test
    fun `live recheck reports original cooldown state when persistence mutates returned entity`() {
        val now = System.currentTimeMillis()
        val cooldown = cooldownCandidate(
            id = 2846L,
            cooldownUntil = now - 1_000L,
            lastSourceSeenAt = now - 60_000L
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(2846L))).thenReturn(listOf(cooldown))
        Mockito.`when`(stateMachine.advance(cooldown, runId = null))
            .thenReturn(cooldown.copy(researchState = LeaderResearchState.CANDIDATE))

        val result = service.recheck(
            LeaderResearchCooldownRecheckRequest(
                dryRun = false,
                candidateIds = listOf(2846L)
            )
        )

        val item = result.items.single()
        assertEquals(1, result.selectedCount)
        assertEquals("COOLDOWN", item.beforeState)
        assertEquals("CANDIDATE", item.afterState)
        assertEquals("RECOVERED", item.action)
        assertEquals("cooldown_recheck_ready", item.reason)
    }

    @Test
    fun `locked cooldown candidate is not advanced`() {
        val now = System.currentTimeMillis()
        val candidate = cooldownCandidate(
            id = 9404L,
            cooldownUntil = now - 1_000L,
            lastSourceSeenAt = now - 60_000L,
            locked = true
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(9404L))).thenReturn(listOf(candidate))

        val result = service.recheck(
            LeaderResearchCooldownRecheckRequest(
                dryRun = false,
                candidateIds = listOf(9404L)
            )
        )

        assertEquals(0, result.advancedCount)
        assertEquals("candidate_locked", result.items.single().reason)
        Mockito.verify(stateMachine, Mockito.never()).advance(anyCandidate(), Mockito.any())
    }

    @Test
    fun `candidate state is skipped and not counted as recovered`() {
        val candidate = LeaderResearchCandidate(
            id = 2846L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.CANDIDATE,
            score = BigDecimal("100")
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(2846L))).thenReturn(listOf(candidate))

        val result = service.recheck(LeaderResearchCooldownRecheckRequest(candidateIds = listOf(2846L)))

        assertEquals(0, result.selectedCount)
        assertEquals(emptyList<Long>(), result.recoveredCandidateIds)
        assertEquals("SKIPPED", result.items.single().action)
        assertEquals("not_cooldown", result.items.single().reason)
    }

    private fun cooldownCandidate(
        id: Long,
        cooldownUntil: Long?,
        lastSourceSeenAt: Long?,
        locked: Boolean = false
    ): LeaderResearchCandidate {
        return LeaderResearchCandidate(
            id = id,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.COOLDOWN,
            score = BigDecimal("96"),
            cooldownUntil = cooldownUntil,
            cooldownCount = 1,
            lastSourceSeenAt = lastSourceSeenAt,
            locked = locked
        )
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
