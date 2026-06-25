package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import java.math.BigDecimal

/**
 * 外部桥交易记录（由 Polymtrade Bridge 等外部执行器写入）
 */
@Entity
@Table(
    name = "bridge_trade_record",
    uniqueConstraints = [
        UniqueConstraint(columnNames = ["bridge_id", "external_trade_id"])
    ]
)
data class BridgeTradeRecord(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "bridge_id", nullable = false, length = 100)
    val bridgeId: String,

    @Column(name = "external_trade_id", length = 100)
    val externalTradeId: String? = null,

    @Column(name = "market_id", nullable = false, length = 100)
    val marketId: String,

    @Column(name = "market_title", length = 500)
    val marketTitle: String? = null,

    @Column(name = "side", nullable = false, length = 20)
    val side: String, // BUY / SELL

    @Column(name = "outcome", length = 50)
    val outcome: String? = null,

    @Column(name = "outcome_index")
    val outcomeIndex: Int? = null,

    @Column(name = "quantity", nullable = false, precision = 20, scale = 8)
    val quantity: BigDecimal,

    @Column(name = "price", nullable = false, precision = 20, scale = 8)
    val price: BigDecimal,

    @Column(name = "amount", nullable = false, precision = 20, scale = 8)
    val amount: BigDecimal,

    @Column(name = "fee", nullable = false, precision = 20, scale = 8)
    val fee: BigDecimal = BigDecimal.ZERO,

    @Column(name = "status", nullable = false, length = 30)
    var status: String = "PENDING", // PENDING / SUCCESS / FAILED

    @Column(name = "error_message", columnDefinition = "TEXT")
    var errorMessage: String? = null,

    @Column(name = "raw_payload", columnDefinition = "TEXT")
    var rawPayload: String? = null,

    @Column(name = "notification_status", nullable = false, length = 30)
    var notificationStatus: String = "PENDING",

    @Column(name = "notification_sent_at")
    var notificationSentAt: Long? = null,

    @Column(name = "notification_error", columnDefinition = "TEXT")
    var notificationError: String? = null,

    @Column(name = "executed_at")
    var executedAt: Long? = null,

    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis(),

    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis()
)
