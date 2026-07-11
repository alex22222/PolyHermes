package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import java.math.BigDecimal

@Entity
@Table(
    name = "daily_asset_snapshot",
    uniqueConstraints = [UniqueConstraint(columnNames = ["bridge_id", "wallet_address", "day_start_at"])]
)
data class DailyAssetSnapshot(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    @Column(name = "bridge_id", nullable = false, length = 100)
    val bridgeId: String,
    @Column(name = "wallet_address", nullable = false, length = 42)
    val walletAddress: String,
    @Column(name = "day_start_at", nullable = false)
    val dayStartAt: Long,
    @Column(name = "available_balance", nullable = false, precision = 20, scale = 8)
    val availableBalance: BigDecimal,
    @Column(name = "positions_value", nullable = false, precision = 20, scale = 8)
    val positionsValue: BigDecimal,
    @Column(name = "total_assets", nullable = false, precision = 20, scale = 8)
    val totalAssets: BigDecimal,
    @Column(name = "captured_at", nullable = false)
    val capturedAt: Long,
    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis()
)
