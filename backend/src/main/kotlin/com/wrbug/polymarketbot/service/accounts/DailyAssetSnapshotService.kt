package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.dto.DailyAssetPointDto
import com.wrbug.polymarketbot.entity.CurrentAssetValuation
import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.repository.CurrentAssetValuationRepository
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.time.Instant
import java.time.ZoneId

@Service
class DailyAssetSnapshotService(
    private val repository: DailyAssetSnapshotRepository,
    private val currentRepository: CurrentAssetValuationRepository
) {
    private val bridgeId = "polymtrade-bridge"
    private val zoneId = ZoneId.of("Asia/Shanghai")

    fun captureIfAbsent(
        walletAddress: String,
        availableBalance: BigDecimal?,
        positionsValue: BigDecimal,
        capturedAt: Long,
        unknownPositionCount: Int = 0,
        pendingRedeemValue: BigDecimal? = BigDecimal.ZERO,
        redeemablePositionCount: Int? = 0,
    ) {
        require(unknownPositionCount >= 0) { "unknownPositionCount must not be negative" }
        require(redeemablePositionCount == null || redeemablePositionCount >= 0) {
            "redeemablePositionCount must not be negative"
        }
        val wallet = walletAddress.lowercase()
        val dayStartAt = Instant.ofEpochMilli(capturedAt).atZone(zoneId).toLocalDate()
            .atStartOfDay(zoneId).toInstant().toEpochMilli()
        val captureOffsetMs = capturedAt - dayStartAt
        val valuationStatus = when {
            availableBalance == null -> "BALANCE_UNKNOWN"
            unknownPositionCount > 0 -> "INCOMPLETE"
            pendingRedeemValue == null -> "REDEEM_VALUE_UNKNOWN"
            else -> "COMPLETE"
        }
        val redeemValuationStatus = if (pendingRedeemValue == null) "UNKNOWN" else "COMPLETE"
        val totalAssets = if (valuationStatus == "COMPLETE") {
            availableBalance?.add(positionsValue)?.add(pendingRedeemValue)
        } else {
            null
        }

        val current = currentRepository.findByBridgeIdAndWalletAddress(bridgeId, wallet)
        currentRepository.save(
            CurrentAssetValuation(
                id = current?.id,
                bridgeId = bridgeId,
                walletAddress = wallet,
                availableBalance = availableBalance,
                positionsValue = positionsValue,
                pendingRedeemValue = pendingRedeemValue,
                redeemablePositionCount = redeemablePositionCount,
                redeemValuationStatus = redeemValuationStatus,
                totalAssets = totalAssets,
                unknownPositionCount = unknownPositionCount,
                valuationStatus = valuationStatus,
                capturedAt = capturedAt
            )
        )

        if (availableBalance == null) return
        if (repository.existsByBridgeIdAndWalletAddressAndDayStartAt(bridgeId, wallet, dayStartAt)) return
        try {
            repository.save(
                DailyAssetSnapshot(
                    bridgeId = bridgeId,
                    walletAddress = wallet,
                    dayStartAt = dayStartAt,
                    availableBalance = availableBalance,
                    positionsValue = positionsValue,
                    pendingRedeemValue = pendingRedeemValue,
                    redeemablePositionCount = redeemablePositionCount,
                    redeemValuationStatus = redeemValuationStatus,
                    totalAssets = totalAssets,
                    unknownPositionCount = unknownPositionCount,
                    valuationStatus = valuationStatus,
                    snapshotType = if (captureOffsetMs <= MIDNIGHT_WINDOW_MS) "MIDNIGHT" else "DAILY_FIRST_SUCCESS",
                    captureOffsetMs = captureOffsetMs,
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
                pendingRedeemValue = it.pendingRedeemValue?.toPlainString(),
                redeemablePositionCount = it.redeemablePositionCount,
                redeemValuationStatus = it.redeemValuationStatus,
                totalAssets = it.totalAssets?.toPlainString(),
                unknownPositionCount = it.unknownPositionCount,
                valuationStatus = it.valuationStatus,
                snapshotType = it.snapshotType,
                captureOffsetMs = it.captureOffsetMs,
                capturedAt = it.capturedAt
            )
        }

    companion object {
        private const val MIDNIGHT_WINDOW_MS = 120_000L
    }
}
