package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.dto.BridgeTradeRecordListRequest
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.eq
import org.mockito.Mockito.mock
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`
import org.springframework.data.domain.Page
import org.springframework.data.domain.PageRequest

class BridgeTradeRecordServiceTest {
    @Test
    fun `list uses trimmed market keyword for server-side fuzzy search`() {
        val repository = mock(BridgeTradeRecordRepository::class.java)
        val service = BridgeTradeRecordService(
            repository,
            mock(BridgePositionSnapshotRepository::class.java),
            mock(BridgePortfolioClient::class.java),
            mock(CopyTradingRepository::class.java),
            mock(LeaderRepository::class.java),
            mock(BridgeWebhookLogRepository::class.java)
        )
        val pageable = PageRequest.of(0, 20)
        `when`(
            repository.findFiltered(
                eq(null),
                eq(null),
                eqNonNull("XRP"),
                eqNonNull(pageable)
            )
        ).thenReturn(Page.empty())

        val result = service.getBridgeTradeRecordList(
            BridgeTradeRecordListRequest(marketKeyword = "  XRP  ")
        ).getOrThrow()

        assertEquals(0, result.total)
        verify(repository).findFiltered(
            eq(null),
            eq(null),
            eqNonNull("XRP"),
            eqNonNull(pageable)
        )
    }

    private fun <T : Any> eqNonNull(value: T): T {
        eq(value)
        return value
    }
}
