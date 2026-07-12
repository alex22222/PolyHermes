package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import java.math.BigDecimal

@Entity
@Table(
    name = "portfolio_risk_reservation",
    uniqueConstraints = [UniqueConstraint(name = "uk_portfolio_risk_correlation", columnNames = ["correlation_id"])],
    indexes = [Index(name = "idx_portfolio_risk_reservation_account_status", columnList = "account_id,status,expires_at")]
)
data class PortfolioRiskReservation(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    @Column(name = "correlation_id", nullable = false, length = 100)
    val correlationId: String,
    @Column(name = "account_id", nullable = false)
    val accountId: Long,
    @Column(name = "amount", nullable = false, precision = 20, scale = 8)
    val amount: BigDecimal,
    @Column(name = "market_id", length = 100)
    val marketId: String? = null,
    @Column(name = "event_slug", length = 200)
    val eventSlug: String? = null,
    @Column(name = "leader_address", length = 100)
    val leaderAddress: String? = null,
    @Column(name = "category", length = 50)
    val category: String? = null,
    @Column(name = "status", nullable = false, length = 20)
    var status: String = "ACTIVE",
    @Column(name = "expires_at", nullable = false)
    var expiresAt: Long,
    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis(),
    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis(),
    @Column(name = "completed_at")
    var completedAt: Long? = null
)
