package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
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

    fun findByStatus(status: String, pageable: Pageable): Page<BridgeTradeRecord>

    fun findByExternalTradeId(externalTradeId: String): BridgeTradeRecord?

    @Query(
        "SELECT b FROM BridgeTradeRecord b " +
            "WHERE b.notificationStatus = 'PENDING' " +
            "AND b.status IN ('SUCCESS', 'FAILED') " +
            "ORDER BY b.updatedAt ASC"
    )
    fun findPendingNotificationRecords(pageable: Pageable): List<BridgeTradeRecord>

    /**
     * 查找所有包含原始 payload 的记录，用于 LeaderScanner 提取钱包地址
     */
    fun findByRawPayloadIsNotNull(): List<BridgeTradeRecord>

    /**
     * 按 bridgeId + 市场 conditionId 集合分页查询
     */
    @Query(
        "SELECT b FROM BridgeTradeRecord b " +
        "WHERE b.bridgeId = :bridgeId AND b.marketId IN :marketIds " +
        "ORDER BY b.createdAt DESC"
    )
    fun findByBridgeIdAndMarketIdIn(
        @Param("bridgeId") bridgeId: String,
        @Param("marketIds") marketIds: List<String>,
        pageable: Pageable
    ): Page<BridgeTradeRecord>

    /**
     * 通过 raw_payload.leaderAddress 查询某个 Leader 的 Bridge 执行记录。
     * Bridge 账本不直接保存 copy_trading_id，因此跟单详情页需要用 Leader 地址关联执行记录。
     */
    @Query(
        value = """
            SELECT *
            FROM bridge_trade_record
            WHERE bridge_id = :bridgeId
              AND raw_payload IS NOT NULL
              AND JSON_VALID(raw_payload) = 1
              AND LOWER(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.leaderAddress'))) = LOWER(:leaderAddress)
            ORDER BY created_at DESC
        """,
        countQuery = """
            SELECT COUNT(*)
            FROM bridge_trade_record
            WHERE bridge_id = :bridgeId
              AND raw_payload IS NOT NULL
              AND JSON_VALID(raw_payload) = 1
              AND LOWER(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.leaderAddress'))) = LOWER(:leaderAddress)
        """,
        nativeQuery = true
    )
    fun findByBridgeIdAndLeaderAddressInRawPayload(
        @Param("bridgeId") bridgeId: String,
        @Param("leaderAddress") leaderAddress: String,
        pageable: Pageable
    ): Page<BridgeTradeRecord>

    /**
     * 通过 Bridge raw_payload.leaderAddress 统计某个 Leader 的真实执行结果。
     */
    @Query(
        value = """
            SELECT COUNT(*)
            FROM bridge_trade_record
            WHERE raw_payload IS NOT NULL
              AND JSON_VALID(raw_payload) = 1
              AND LOWER(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.leaderAddress'))) = LOWER(:leaderAddress)
              AND side = :side
              AND status = :status
        """,
        nativeQuery = true
    )
    fun countByLeaderAddressAndSideAndStatus(
        @Param("leaderAddress") leaderAddress: String,
        @Param("side") side: String,
        @Param("status") status: String
    ): Long
}
