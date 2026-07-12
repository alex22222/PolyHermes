package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioReductionDraft
import com.wrbug.polymarketbot.repository.PortfolioReductionDraftRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.service.accounts.PortfolioExposureService
import com.wrbug.polymarketbot.service.accounts.BridgePositionSellService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.util.Optional

class PortfolioReductionPreviewServiceTest {
    private val relationService = Mockito.mock(PortfolioRelationService::class.java)
    private val exposureService = Mockito.mock(PortfolioExposureService::class.java)
    private val repository = Mockito.mock(PortfolioReductionDraftRepository::class.java)
    private val bridgePositionSellService = Mockito.mock(BridgePositionSellService::class.java)
    private val bridgeTradeRecordRepository = Mockito.mock(BridgeTradeRecordRepository::class.java)
    private val service = PortfolioReductionPreviewService(relationService, exposureService, repository, Gson(), bridgePositionSellService, bridgeTradeRecordRepository)

    @Test
    fun `preview persists expiring audit draft without enabling execution`() {
        Mockito.`when`(relationService.getRelations(2, 1_000)).thenReturn(relations())
        Mockito.`when`(exposureService.getExposure(2)).thenReturn(exposure())
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        val result = service.preview(PortfolioReductionPreviewRequest(2, "market-1|YES", "4"), "admin", 1_000)

        assertEquals("40", result.estimatedProceeds)
        assertEquals("50", result.afterAvailableBalance)
        assertEquals("50", result.afterOpenPositionsValue)
        assertEquals("100", result.afterTotalAssets)
        assertEquals(601_000, result.expiresAt)
        assertFalse(result.executionEnabled)
        assertEquals(setOf("LEADER", "CATEGORY", "EVENT", "MARKET"), result.impacts.map { it.dimension }.toSet())
        Mockito.verify(repository).save(anyDraft())
    }

    @Test
    fun `preview rejects quantity above live snapshot`() {
        Mockito.`when`(relationService.getRelations(2, 1_000)).thenReturn(relations())

        assertThrows(IllegalArgumentException::class.java) {
            service.preview(PortfolioReductionPreviewRequest(2, "market-1|YES", "11"), "admin", 1_000)
        }
        Mockito.verifyNoInteractions(exposureService, repository)
    }

    @Test
    fun `expired draft is returned as non executable expired audit`() {
        val storedResponse = serviceResponse()
        val draft = PortfolioReductionDraft(
            draftId = "draft-1", accountId = 2, positionKey = "market-1|YES",
            quantity = "4".toBigDecimal(), snapshotJson = Gson().toJson(storedResponse),
            createdBy = "admin", expiresAt = 601_000, createdAt = 1_000, updatedAt = 1_000
        )
        Mockito.`when`(repository.findById("draft-1")).thenReturn(Optional.of(draft))
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        val result = service.get("draft-1", 601_001)

        assertEquals("EXPIRED", result.status)
        assertFalse(result.executionEnabled)
        assertEquals("EXPIRED", draft.status)
    }

    @Test
    fun `confirmation rechecks live position and records actor without enabling execution`() {
        val draft = storedDraft()
        Mockito.`when`(repository.findById("draft-1")).thenReturn(Optional.of(draft))
        Mockito.`when`(relationService.getRelations(2, 2_000)).thenReturn(relations())
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        val result = service.confirm("draft-1", "reviewer", 2_000)

        assertEquals("CONFIRMED", result.status)
        assertEquals("reviewer", result.confirmedBy)
        assertEquals(2_000, result.confirmedAt)
        assertEquals(true, result.executionEnabled)
        assertEquals("CONFIRMED", draft.status)
    }

    @Test
    fun `confirmation expires stale draft instead of confirming it`() {
        val draft = storedDraft().copy(expiresAt = 2_000)
        Mockito.`when`(repository.findById("draft-1")).thenReturn(Optional.of(draft))
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        assertThrows(IllegalArgumentException::class.java) {
            service.confirm("draft-1", "reviewer", 2_001)
        }

        assertEquals("EXPIRED", draft.status)
        Mockito.verifyNoInteractions(relationService)
    }

    @Test
    fun `confirmation rejects draft when live quantity has fallen`() {
        val draft = storedDraft()
        Mockito.`when`(repository.findById("draft-1")).thenReturn(Optional.of(draft))
        Mockito.`when`(relationService.getRelations(2, 2_000)).thenReturn(
            relations().copy(positions = relations().positions.map { it.copy(quantity = "3") })
        )

        assertThrows(IllegalArgumentException::class.java) {
            service.confirm("draft-1", "reviewer", 2_000)
        }

        assertEquals("DRAFT", draft.status)
        Mockito.verify(repository, Mockito.never()).save(anyDraft())
    }

    @Test
    fun `execute submits confirmed draft once with stable idempotency key`() {
        val draft = storedDraft().copy(status = "CONFIRMED", confirmedBy = "reviewer", confirmedAt = 2_000)
        Mockito.`when`(repository.findLockedByDraftId("draft-1")).thenReturn(draft)
        Mockito.`when`(relationService.getRelations(2, 3_000)).thenReturn(relations())
        Mockito.`when`(repository.saveAndFlush(anyDraft())).thenAnswer { it.arguments[0] }
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }
        Mockito.`when`(bridgePositionSellService.sellBridgePosition(anySellRequest())).thenReturn(
            Result.success(com.wrbug.polymarketbot.dto.BridgePositionSellResponse(9, "reduction-draft-1", "accepted"))
        )

        val result = service.execute("draft-1", "executor", 3_000)

        assertEquals("SUBMITTED", result.status)
        assertEquals("reduction-draft-1", result.executionExternalTradeId)
        assertEquals(9, result.executionRecordId)
        assertFalse(result.executionEnabled)
        val captor = org.mockito.ArgumentCaptor.forClass(com.wrbug.polymarketbot.dto.BridgePositionSellRequest::class.java)
        Mockito.verify(bridgePositionSellService).sellBridgePosition(captureSell(captor))
        assertEquals("reduction-draft-1", captor.value.externalTradeId)
        assertEquals("4", captor.value.quantity)
    }

    @Test
    fun `submitted draft is idempotent and does not call bridge again`() {
        val draft = storedDraft().copy(status = "SUBMITTED", executionExternalTradeId = "reduction-draft-1")
        Mockito.`when`(repository.findLockedByDraftId("draft-1")).thenReturn(draft)

        val result = service.execute("draft-1", "executor", 3_000)

        assertEquals("SUBMITTED", result.status)
        Mockito.verifyNoInteractions(bridgePositionSellService, relationService)
    }

    @Test
    fun `refresh maps bridge success to executed`() {
        val draft = storedDraft().copy(status = "SUBMITTED", executionExternalTradeId = "reduction-draft-1", executionAttempt = 1)
        Mockito.`when`(repository.findLockedByDraftId("draft-1")).thenReturn(draft)
        Mockito.`when`(bridgeTradeRecordRepository.findByExternalTradeId("reduction-draft-1")).thenReturn(bridgeRecord("SUCCESS"))
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        val result = service.refresh("draft-1", 4_000)

        assertEquals("EXECUTED", result.status)
        assertEquals(99, result.executionRecordId)
        assertFalse(result.executionEnabled)
    }

    @Test
    fun `explicit bridge failure uses a new retry attempt key`() {
        val draft = storedDraft().copy(
            status = "FAILED", executionExternalTradeId = "reduction-draft-1", executionAttempt = 1,
            confirmedBy = "reviewer", confirmedAt = 2_000
        )
        Mockito.`when`(repository.findLockedByDraftId("draft-1")).thenReturn(draft)
        Mockito.`when`(bridgeTradeRecordRepository.findByExternalTradeId("reduction-draft-1")).thenReturn(bridgeRecord("FAILED"))
        Mockito.`when`(relationService.getRelations(2, 3_000)).thenReturn(relations())
        Mockito.`when`(repository.saveAndFlush(anyDraft())).thenAnswer { it.arguments[0] }
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }
        Mockito.`when`(bridgePositionSellService.sellBridgePosition(anySellRequest())).thenReturn(
            Result.success(com.wrbug.polymarketbot.dto.BridgePositionSellResponse(100, "reduction-draft-1-retry-2", "accepted"))
        )

        val result = service.execute("draft-1", "executor", 3_000)

        assertEquals("SUBMITTED", result.status)
        assertEquals(2, result.executionAttempt)
        assertEquals("reduction-draft-1-retry-2", result.executionExternalTradeId)
    }

    @Test
    fun `queue expires stale actionable drafts`() {
        val stale = storedDraft().copy(status = "CONFIRMED", expiresAt = 2_000)
        val submitted = storedDraft().copy(draftId = "draft-2", status = "SUBMITTED", expiresAt = 2_000)
        Mockito.`when`(repository.findByAccountIdOrderByCreatedAtDesc(2)).thenReturn(listOf(stale, submitted))
        Mockito.`when`(repository.save(anyDraft())).thenAnswer { it.arguments[0] }

        val result = service.list(2, 3_000)

        assertEquals(listOf("EXPIRED", "SUBMITTED"), result.map { it.status })
        assertEquals("EXPIRED", stale.status)
        assertEquals("SUBMITTED", submitted.status)
    }

    private fun relations() = PortfolioRelationResponse(
        accountId = 2, asOf = 900,
        positions = listOf(PortfolioRelationPositionDto("market-1|YES", "market-1", "event-1", "YES", "crypto", "Market", "100", "10", 1, null)),
        relations = emptyList(), countsByType = emptyMap(), relatedValueByType = emptyMap(), generatedAt = 1_000
    )

    private fun exposure(): PortfolioExposureResponse {
        val bucket = PortfolioExposureBucketDto("market-1", "Market", "100", "100", 1, "TEST", "EXACT", 7, "80", "20", 1, listOf("market-1|YES"))
        val coverage = PortfolioExposureDimensionCoverageDto("100", "0", "100", "95", "READY_FOR_SHADOW", true)
        return PortfolioExposureResponse(
            PortfolioExposureAccountDto(2, "Bridge", "0xwallet", "10", "90", "0", "100", "COMPLETE", "80", "20", 1, 1, 900),
            leaders = listOf(bucket.copy(key = "0xleader", label = "Leader")),
            categories = listOf(bucket.copy(key = "crypto", label = "crypto")),
            events = listOf(bucket.copy(key = "event-1", label = "event-1")),
            markets = listOf(bucket),
            coverage = PortfolioExposureCoverageDto(1, 0, 0, 0, 0, 0, coverage, coverage, coverage, coverage)
        )
    }

    private fun serviceResponse() = PortfolioReductionPreviewResponse(
        "draft-1", 2, "market-1|YES", "Market", "YES", "4", "10", "40",
        "10", "50", "90", "50", "100", "100", emptyList(), "DRAFT", false,
        "admin", 1_000, 601_000
    )

    private fun storedDraft() = PortfolioReductionDraft(
        draftId = "draft-1", accountId = 2, positionKey = "market-1|YES",
        quantity = "4".toBigDecimal(), snapshotJson = Gson().toJson(serviceResponse()),
        createdBy = "admin", expiresAt = 10_000, createdAt = 1_000, updatedAt = 1_000
    )

    private fun bridgeRecord(status: String) = com.wrbug.polymarketbot.entity.BridgeTradeRecord(
        id = 99, bridgeId = "polymtrade-bridge", externalTradeId = "reduction-draft-1",
        marketId = "market-1", side = "SELL", outcome = "YES", quantity = "4".toBigDecimal(),
        price = java.math.BigDecimal.ZERO, amount = java.math.BigDecimal.ZERO, status = status,
        errorMessage = if (status == "FAILED") "UI failed" else null
    )

    private fun anyDraft(): PortfolioReductionDraft {
        Mockito.any(PortfolioReductionDraft::class.java)
        return PortfolioReductionDraft("unused", 0, "unused", java.math.BigDecimal.ONE, snapshotJson = "{}", createdBy = "test", expiresAt = 0, createdAt = 0, updatedAt = 0)
    }

    private fun anySellRequest(): com.wrbug.polymarketbot.dto.BridgePositionSellRequest {
        Mockito.any(com.wrbug.polymarketbot.dto.BridgePositionSellRequest::class.java)
        return com.wrbug.polymarketbot.dto.BridgePositionSellRequest(0, "unused", "YES", orderType = "MARKET")
    }

    private fun captureSell(captor: org.mockito.ArgumentCaptor<com.wrbug.polymarketbot.dto.BridgePositionSellRequest>): com.wrbug.polymarketbot.dto.BridgePositionSellRequest {
        captor.capture()
        return com.wrbug.polymarketbot.dto.BridgePositionSellRequest(0, "unused", "YES", orderType = "MARKET")
    }
}
