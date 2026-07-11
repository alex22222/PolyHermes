package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.ArgumentCaptor
import org.mockito.Mockito.*
import java.math.BigDecimal
import java.time.LocalDate
import java.time.ZoneId

class DailyAssetSnapshotServiceTest {
    private val repository = mock(DailyAssetSnapshotRepository::class.java)
    private val service = DailyAssetSnapshotService(repository)

    @Test
    fun `captures balance plus positions at Shanghai day start`() {
        val capturedAt = LocalDate.of(2026, 7, 11).atTime(0, 0, 10)
            .atZone(ZoneId.of("Asia/Shanghai")).toInstant().toEpochMilli()
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent("0xABC", BigDecimal("5.03"), BigDecimal("83.75"), capturedAt)

        val captor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(captor.capture())
        assertEquals("88.78", captor.value.totalAssets.toPlainString())
        assertEquals("0xabc", captor.value.walletAddress)
        assertEquals(
            LocalDate.of(2026, 7, 11).atStartOfDay(ZoneId.of("Asia/Shanghai")).toInstant().toEpochMilli(),
            captor.value.dayStartAt
        )
    }

    @Test
    fun `does not overwrite an existing daily point`() {
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(true)

        service.captureIfAbsent("0xabc", BigDecimal.ONE, BigDecimal.TEN, System.currentTimeMillis())

        verify(repository, never()).save(any())
    }
}
