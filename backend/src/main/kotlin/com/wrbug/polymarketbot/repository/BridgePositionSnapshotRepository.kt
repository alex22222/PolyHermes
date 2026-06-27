package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

/**
 * Bridge 持仓快照 Repository
 */
@Repository
interface BridgePositionSnapshotRepository : JpaRepository<BridgePositionSnapshot, Long> {

    fun findByBridgeId(bridgeId: String): List<BridgePositionSnapshot>

    fun findByBridgeIdAndWalletAddress(
        bridgeId: String,
        walletAddress: String
    ): List<BridgePositionSnapshot>

    fun findByBridgeIdAndMarketTitleAndSide(
        bridgeId: String,
        marketTitle: String,
        side: String
    ): BridgePositionSnapshot?
}
