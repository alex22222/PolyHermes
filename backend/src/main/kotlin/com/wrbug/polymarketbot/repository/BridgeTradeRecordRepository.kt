package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

/**
 * 外部桥交易记录 Repository
 */
@Repository
interface BridgeTradeRecordRepository : JpaRepository<BridgeTradeRecord, Long> {

    fun findByBridgeId(bridgeId: String): List<BridgeTradeRecord>

    fun findByBridgeIdAndStatus(bridgeId: String, status: String): List<BridgeTradeRecord>

    fun findByBridgeId(bridgeId: String, pageable: Pageable): Page<BridgeTradeRecord>

    fun findByBridgeIdAndStatus(bridgeId: String, status: String, pageable: Pageable): Page<BridgeTradeRecord>

    fun findByExternalTradeId(externalTradeId: String): BridgeTradeRecord?
}
