package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.dto.DailyAssetPointDto
import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.time.Instant
import java.time.ZoneId

@Service
class DailyAssetSnapshotService(
    private val repository: DailyAssetSnapshotRepository
) {
    private val bridgeId = "polymtrade-bridge"
    private val zoneId = ZoneId.of("Asia/Shanghai")

    fun captureIfAbsent(walletAddress: String, availableBalance: BigDecimal, positionsValue: BigDecimal, capturedAt: Long) {
        val wallet = walletAddress.lowercase()
        val dayStartAt = Instant.ofEpochMilli(capturedAt).atZone(zoneId).toLocalDate()
            .atStartOfDay(zoneId).toInstant().toEpochMilli()
        if (repository.existsByBridgeIdAndWalletAddressAndDayStartAt(bridgeId, wallet, dayStartAt)) return
        try {
            repository.save(
                DailyAssetSnapshot(
                    bridgeId = bridgeId,
                    walletAddress = wallet,
                    dayStartAt = dayStartAt,
                    availableBalance = availableBalance,
                    positionsValue = positionsValue,
                    totalAssets = availableBalance.add(positionsValue),
                    capturedAt = capturedAt
                )
            )
        } catch (_: DataIntegrityViolationException) {
            // Another sync inserted the same wallet/day snapshot first.
        }
    }

    fun history(walletAddress: String): List<DailyAssetPointDto> =
        repository.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc(bridgeId, walletAddress.lowercase()).map {
            DailyAssetPointDto(
                dayStartAt = it.dayStartAt,
                availableBalance = it.availableBalance.toPlainString(),
                positionsValue = it.positionsValue.toPlainString(),
                totalAssets = it.totalAssets.toPlainString(),
                capturedAt = it.capturedAt
            )
        }
}
