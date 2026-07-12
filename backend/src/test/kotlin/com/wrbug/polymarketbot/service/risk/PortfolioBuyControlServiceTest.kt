package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.PortfolioBuyControlAudit
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.PortfolioBuyControlAuditRepository
import com.wrbug.polymarketbot.repository.PortfolioBuyControlRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.util.Optional

class PortfolioBuyControlServiceTest {
    private val repository = Mockito.mock(PortfolioBuyControlRepository::class.java)
    private val audit = Mockito.mock(PortfolioBuyControlAuditRepository::class.java)
    private val accounts = Mockito.mock(AccountRepository::class.java)
    private val service = PortfolioBuyControlService(repository, audit, accounts)

    @Test
    fun `pause requires reason and writes state plus audit`() {
        Mockito.`when`(accounts.existsById(2)).thenReturn(true)
        Mockito.`when`(repository.findById(2)).thenReturn(Optional.empty())
        Mockito.`when`(audit.findTop100ByAccountIdOrderByCreatedAtDesc(2)).thenReturn(emptyList())

        val result = service.update(2, true, "检查重复仓位", "admin", 100)

        assertEquals(true, result.changed)
        val state = org.mockito.ArgumentCaptor.forClass(com.wrbug.polymarketbot.entity.PortfolioBuyControl::class.java)
        Mockito.verify(repository).save(state.capture())
        assertEquals(true, state.value.paused)
        assertEquals("检查重复仓位", state.value.reason)
        val event = org.mockito.ArgumentCaptor.forClass(PortfolioBuyControlAudit::class.java)
        Mockito.verify(audit).save(event.capture())
        assertEquals("PAUSE", event.value.action)
        assertEquals("admin", event.value.actor)
    }

    @Test
    fun `pause without reason is rejected`() {
        Mockito.`when`(accounts.existsById(2)).thenReturn(true)
        assertThrows(IllegalArgumentException::class.java) { service.update(2, true, " ", "admin") }
        Mockito.verifyNoInteractions(repository, audit)
    }
}
