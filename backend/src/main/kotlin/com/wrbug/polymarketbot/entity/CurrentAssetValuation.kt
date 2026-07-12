package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import java.math.BigDecimal

@Entity
@Table(
    name = "current_asset_valuation",
    uniqueConstraints = [UniqueConstraint(columnNames = ["bridge_id", "wallet_address"])]
)
data class CurrentAssetValuation(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    @Column(name = "bridge_id", nullable = false, length = 100)
    val bridgeId: String,
    @Column(name = "wallet_address", nullable = false, length = 42)
    val walletAddress: String,
    @Column(name = "available_balance", precision = 20, scale = 8)
    val availableBalance: BigDecimal?,
    @Column(name = "positions_value", nullable = false, precision = 20, scale = 8)
    val positionsValue: BigDecimal,
    @Column(name = "pending_redeem_value", precision = 20, scale = 8)
    val pendingRedeemValue: BigDecimal?,
    @Column(name = "redeemable_position_count")
    val redeemablePositionCount: Int?,
    @Column(name = "redeem_valuation_status", nullable = false, length = 20)
    val redeemValuationStatus: String,
    @Column(name = "total_assets", precision = 20, scale = 8)
    val totalAssets: BigDecimal?,
    @Column(name = "unknown_position_count", nullable = false)
    val unknownPositionCount: Int,
    @Column(name = "valuation_status", nullable = false, length = 20)
    val valuationStatus: String,
    @Column(name = "captured_at", nullable = false)
    val capturedAt: Long,
    @Column(name = "updated_at", nullable = false)
    val updatedAt: Long = System.currentTimeMillis()
)
