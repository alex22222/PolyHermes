package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.PortfolioRiskReservation
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskReservationRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class PortfolioRiskReservationServiceTest {
    private val accountRepository = Mockito.mock(AccountRepository::class.java)
    private val repository = Mockito.mock(PortfolioRiskReservationRepository::class.java)
    private val service = PortfolioRiskReservationService(accountRepository, repository)

    @Test
    fun `precheck creates reservation while projecting other active amounts by dimension`() {
        val other = reservation("other", "2", "event-1", "0xleader", "crypto", expiresAt = 10_000)
        Mockito.`when`(accountRepository.findByIdForUpdate(2)).thenReturn(account())
        Mockito.`when`(repository.findByAccountIdAndStatusIn(2, listOf("ACTIVE", "EXECUTING"))).thenReturn(listOf(other))
        Mockito.`when`(repository.findByCorrelationId("current")).thenReturn(null)
        Mockito.`when`(repository.save(Mockito.any(PortfolioRiskReservation::class.java))).thenAnswer { it.arguments[0] }

        val result = service.prepare(2, "current", "PRECHECK", BigDecimal("1"), "market", "event-1", "0xleader", "crypto", now = 1_000)

        assertEquals("ACTIVE", result.reservation?.status)
        assertEquals(BigDecimal("2"), result.otherTotalAmount)
        assertEquals(BigDecimal("2"), result.otherEventAmount)
        assertEquals(BigDecimal.ZERO, result.otherMarketAmount)
        assertEquals(BigDecimal("2"), result.otherLeaderAmount)
        assertEquals(BigDecimal("2"), result.otherCategoryAmount)
        assertEquals(1, result.otherActiveCount)
        Mockito.verify(accountRepository).findByIdForUpdate(2)
    }

    @Test
    fun `final reuses precheck reservation instead of reserving amount twice`() {
        val current = reservation("same", "1", "event-1", "0xleader", "crypto", expiresAt = 10_000)
        Mockito.`when`(accountRepository.findByIdForUpdate(2)).thenReturn(account())
        Mockito.`when`(repository.findByAccountIdAndStatusIn(2, listOf("ACTIVE", "EXECUTING"))).thenReturn(listOf(current))
        Mockito.`when`(repository.findByCorrelationId("same")).thenReturn(current)
        Mockito.`when`(repository.save(Mockito.any(PortfolioRiskReservation::class.java))).thenAnswer { it.arguments[0] }

        val result = service.prepare(2, "same", "FINAL", BigDecimal("1"), "market", "event-1", "0xleader", "crypto", now = 2_000)

        assertEquals("EXECUTING", result.reservation?.status)
        assertEquals(BigDecimal.ZERO, result.otherTotalAmount)
        assertEquals(false, result.recoveredAtFinal)
    }

    @Test
    fun `expired reservations are released before projection`() {
        val expired = reservation("expired", "5", null, null, null, expiresAt = 999)
        Mockito.`when`(accountRepository.findByIdForUpdate(2)).thenReturn(account())
        Mockito.`when`(repository.findByAccountIdAndStatusIn(2, listOf("ACTIVE", "EXECUTING"))).thenReturn(listOf(expired))
        Mockito.`when`(repository.findByCorrelationId("current")).thenReturn(null)
        Mockito.`when`(repository.save(Mockito.any(PortfolioRiskReservation::class.java))).thenAnswer { it.arguments[0] }

        val result = service.prepare(2, "current", "PRECHECK", BigDecimal.ONE, null, null, null, null, now = 1_000)

        assertEquals("EXPIRED", expired.status)
        assertEquals(BigDecimal.ZERO, result.otherTotalAmount)
    }

    @Test
    fun `completion is idempotent and records success terminal state`() {
        val current = reservation("same", "1", null, null, null, expiresAt = 10_000)
        Mockito.`when`(repository.findByCorrelationId("same")).thenReturn(current)
        Mockito.`when`(accountRepository.findByIdForUpdate(2)).thenReturn(account())
        Mockito.`when`(repository.save(Mockito.any(PortfolioRiskReservation::class.java))).thenAnswer { it.arguments[0] }

        val first = service.complete("same", "SUCCESS", now = 3_000)
        val second = service.complete("same", "SUCCESS", now = 4_000)

        assertEquals("SUCCESS", first.status)
        assertEquals(3_000, first.completedAt)
        assertEquals(3_000, second.completedAt)
    }

    private fun reservation(
        correlationId: String,
        amount: String,
        event: String?,
        leader: String?,
        category: String?,
        expiresAt: Long
    ) = PortfolioRiskReservation(
        correlationId = correlationId,
        accountId = 2,
        amount = BigDecimal(amount),
        eventSlug = event,
        leaderAddress = leader,
        category = category,
        expiresAt = expiresAt
    )

    private fun account() = Account(id = 2, walletAddress = "0xwallet", proxyAddress = "0xproxy")
}
