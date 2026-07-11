package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import org.springframework.data.jpa.repository.JpaRepository

interface DailyAssetSnapshotRepository : JpaRepository<DailyAssetSnapshot, Long> {
    fun existsByBridgeIdAndWalletAddressAndDayStartAt(bridgeId: String, walletAddress: String, dayStartAt: Long): Boolean
    fun findByBridgeIdAndWalletAddressOrderByDayStartAtAsc(bridgeId: String, walletAddress: String): List<DailyAssetSnapshot>
}
