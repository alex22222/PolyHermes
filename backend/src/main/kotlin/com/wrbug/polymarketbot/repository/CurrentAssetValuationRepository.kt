package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.CurrentAssetValuation
import org.springframework.data.jpa.repository.JpaRepository

interface CurrentAssetValuationRepository : JpaRepository<CurrentAssetValuation, Long> {
    fun findByBridgeIdAndWalletAddress(bridgeId: String, walletAddress: String): CurrentAssetValuation?
}
