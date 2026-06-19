package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import java.math.BigDecimal

/**
 * Bridge 真实持仓快照
 *
 * 由 polymtrade-bridge 抓取 Polymtrade /portfolio 页面后同步到后端，
 * 作为 Bridge 只读账户仓位管理的数据源。优先于 bridge_trade_record 计算出的仓位。
 */
@Entity
@Table(
    name = "bridge_position_snapshot",
    uniqueConstraints = [
        UniqueConstraint(columnNames = ["bridge_id", "market_title", "side"])
    ]
)
data class BridgePositionSnapshot(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "bridge_id", nullable = false, length = 100)
    var bridgeId: String,

    @Column(name = "market_id", length = 100)
    var marketId: String? = null,

    @Column(name = "market_title", nullable = false, length = 500)
    var marketTitle: String,

    @Column(name = "side", nullable = false, length = 20)
    var side: String,

    @Column(name = "quantity", nullable = false, precision = 20, scale = 8)
    var quantity: BigDecimal,

    @Column(name = "current_value", precision = 20, scale = 8)
    var currentValue: BigDecimal? = null,

    @Column(name = "pnl", precision = 20, scale = 8)
    var pnl: BigDecimal? = null,

    @Column(name = "percent_pnl", precision = 10, scale = 4)
    var percentPnl: BigDecimal? = null,

    @Column(name = "market_icon", length = 500)
    var marketIcon: String? = null,

    @Column(name = "market_slug", length = 200)
    var marketSlug: String? = null,

    @Column(name = "event_slug", length = 200)
    var eventSlug: String? = null,

    @Column(name = "synced_at", nullable = false)
    var syncedAt: Long = System.currentTimeMillis(),

    @Column(name = "created_at", nullable = false)
    var createdAt: Long = System.currentTimeMillis(),

    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis()
)
