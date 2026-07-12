package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.entity.CurrentAssetValuation
import com.wrbug.polymarketbot.repository.CurrentAssetValuationRepository
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
    private val currentRepository = mock(CurrentAssetValuationRepository::class.java)
    private val service = DailyAssetSnapshotService(repository, currentRepository)

    @Test
    fun `captures balance plus positions at Shanghai day start`() {
        val capturedAt = LocalDate.of(2026, 7, 11).atTime(0, 0, 10)
            .atZone(ZoneId.of("Asia/Shanghai")).toInstant().toEpochMilli()
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent("0xABC", BigDecimal("5.03"), BigDecimal("83.75"), capturedAt)

        val captor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(captor.capture())
        assertEquals("88.78", captor.value.totalAssets?.toPlainString())
        assertEquals("0xabc", captor.value.walletAddress)
        assertEquals(
            LocalDate.of(2026, 7, 11).atStartOfDay(ZoneId.of("Asia/Shanghai")).toInstant().toEpochMilli(),
            captor.value.dayStartAt
        )
        assertEquals("MIDNIGHT", captor.value.snapshotType)
        assertEquals(10_000L, captor.value.captureOffsetMs)
    }

    @Test
    fun `does not overwrite an existing daily point`() {
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(true)

        service.captureIfAbsent("0xabc", BigDecimal.ONE, BigDecimal.TEN, System.currentTimeMillis())

        verify(repository, never()).save(any())
        verify(currentRepository).save(any())
    }

    @Test
    fun `marks snapshot incomplete instead of treating unknown position value as zero`() {
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent(
            walletAddress = "0xabc",
            availableBalance = BigDecimal("5"),
            positionsValue = BigDecimal("4"),
            unknownPositionCount = 1,
            capturedAt = System.currentTimeMillis()
        )

        val captor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(captor.capture())
        assertEquals(null, captor.value.totalAssets)
        assertEquals(1, captor.value.unknownPositionCount)
        assertEquals("INCOMPLETE", captor.value.valuationStatus)
    }

    @Test
    fun `classifies late first capture honestly and updates intraday valuation`() {
        val capturedAt = LocalDate.of(2026, 7, 11).atTime(15, 35)
            .atZone(ZoneId.of("Asia/Shanghai")).toInstant().toEpochMilli()
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent("0xABC", BigDecimal("10"), BigDecimal("20"), capturedAt)

        val dailyCaptor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(dailyCaptor.capture())
        assertEquals("DAILY_FIRST_SUCCESS", dailyCaptor.value.snapshotType)
        assertEquals(56_100_000L, dailyCaptor.value.captureOffsetMs)

        val currentCaptor = ArgumentCaptor.forClass(CurrentAssetValuation::class.java)
        verify(currentRepository).save(currentCaptor.capture())
        assertEquals("30", currentCaptor.value.totalAssets?.toPlainString())
        assertEquals(capturedAt, currentCaptor.value.capturedAt)
    }

    @Test
    fun `records balance unknown intraday state without creating a daily point`() {
        val capturedAt = System.currentTimeMillis()

        service.captureIfAbsent(
            walletAddress = "0xABC",
            availableBalance = null,
            positionsValue = BigDecimal("20"),
            capturedAt = capturedAt
        )

        val currentCaptor = ArgumentCaptor.forClass(CurrentAssetValuation::class.java)
        verify(currentRepository).save(currentCaptor.capture())
        assertEquals(null, currentCaptor.value.availableBalance)
        assertEquals(null, currentCaptor.value.totalAssets)
        assertEquals("BALANCE_UNKNOWN", currentCaptor.value.valuationStatus)
        verify(repository, never()).save(any())
    }

    @Test
    fun `includes pending redeem value in complete total assets`() {
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent(
            walletAddress = "0xabc",
            availableBalance = BigDecimal("5"),
            positionsValue = BigDecimal("4"),
            pendingRedeemValue = BigDecimal("2.5"),
            redeemablePositionCount = 1,
            capturedAt = System.currentTimeMillis()
        )

        val captor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(captor.capture())
        assertEquals("11.5", captor.value.totalAssets?.toPlainString())
        assertEquals("2.5", captor.value.pendingRedeemValue?.toPlainString())
        assertEquals(1, captor.value.redeemablePositionCount)
        assertEquals("COMPLETE", captor.value.redeemValuationStatus)
    }

    @Test
    fun `marks total unknown when pending redeem source is unavailable`() {
        `when`(repository.existsByBridgeIdAndWalletAddressAndDayStartAt(anyString(), anyString(), anyLong()))
            .thenReturn(false)

        service.captureIfAbsent(
            walletAddress = "0xabc",
            availableBalance = BigDecimal("5"),
            positionsValue = BigDecimal("4"),
            pendingRedeemValue = null,
            redeemablePositionCount = null,
            capturedAt = System.currentTimeMillis()
        )

        val captor = ArgumentCaptor.forClass(DailyAssetSnapshot::class.java)
        verify(repository).save(captor.capture())
        assertEquals(null, captor.value.totalAssets)
        assertEquals("REDEEM_VALUE_UNKNOWN", captor.value.valuationStatus)
        assertEquals("UNKNOWN", captor.value.redeemValuationStatus)
    }
}
