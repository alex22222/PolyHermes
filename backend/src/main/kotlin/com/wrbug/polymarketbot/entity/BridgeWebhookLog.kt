package com.wrbug.polymarketbot.entity

import jakarta.persistence.*

/**
 * Bridge webhook 调用日志
 *
 * 记录 PolyHermes 向后端/Bridge 发送 Leader 交易信号时的 HTTP webhook 调用详情，
 * 用于排查信号是否成功送达 Bridge。
 */
@Entity
@Table(
    name = "bridge_webhook_log",
    indexes = [
        Index(name = "idx_bridge_webhook_log_created_at", columnList = "created_at DESC"),
        Index(name = "idx_bridge_webhook_log_status", columnList = "status"),
        Index(name = "idx_bridge_webhook_log_tx_hash", columnList = "transaction_hash")
    ]
)
data class BridgeWebhookLog(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "bridge_id", nullable = false, length = 100)
    var bridgeId: String = "polymtrade-bridge",

    @Column(name = "event", nullable = false, length = 50)
    var event: String = "leader_trade",

    @Column(name = "leader_address", length = 100)
    var leaderAddress: String? = null,

    @Column(name = "leader_name", length = 200)
    var leaderName: String? = null,

    @Column(name = "transaction_hash", length = 100)
    var transactionHash: String? = null,

    @Column(name = "condition_id", length = 100)
    var conditionId: String? = null,

    @Column(name = "market_slug", length = 200)
    var marketSlug: String? = null,

    @Column(name = "side", length = 20)
    var side: String? = null,

    @Column(name = "outcome", length = 100)
    var outcome: String? = null,

    @Column(name = "request_body", columnDefinition = "TEXT")
    var requestBody: String? = null,

    @Column(name = "response_body", columnDefinition = "TEXT")
    var responseBody: String? = null,

    @Column(name = "status_code")
    var statusCode: Int? = null,

    @Column(name = "status", nullable = false, length = 30)
    var status: String = "PENDING",

    @Column(name = "error_message", columnDefinition = "TEXT")
    var errorMessage: String? = null,

    @Column(name = "created_at", nullable = false)
    var createdAt: Long = System.currentTimeMillis(),

    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis()
)
