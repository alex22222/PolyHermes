package com.wrbug.polymarketbot.entity

import jakarta.persistence.*

@Entity
@Table(
    name = "portfolio_risk_decision",
    indexes = [
        Index(name = "idx_portfolio_risk_account_created", columnList = "account_id,created_at"),
        Index(name = "idx_portfolio_risk_outcome_created", columnList = "outcome,created_at")
    ],
    uniqueConstraints = [UniqueConstraint(name = "uk_portfolio_risk_request_id", columnNames = ["request_id"])]
)
data class PortfolioRiskDecision(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    @Column(name = "request_id", nullable = false, length = 100)
    val requestId: String,
    @Column(name = "account_id", nullable = false)
    val accountId: Long,
    @Column(name = "policy_version", nullable = false, length = 50)
    val policyVersion: String,
    @Column(name = "mode", nullable = false, length = 20)
    val mode: String,
    @Column(name = "side", nullable = false, length = 20)
    val side: String,
    @Column(name = "outcome", nullable = false, length = 40)
    val outcome: String,
    @Column(name = "execution_allowed", nullable = false)
    val executionAllowed: Boolean,
    @Column(name = "market_id", length = 100)
    val marketId: String? = null,
    @Column(name = "event_slug", length = 200)
    val eventSlug: String? = null,
    @Column(name = "leader_address", length = 100)
    val leaderAddress: String? = null,
    @Column(name = "category", length = 50)
    val category: String? = null,
    @Column(name = "request_json", nullable = false, columnDefinition = "TEXT")
    val requestJson: String,
    @Column(name = "rules_json", nullable = false, columnDefinition = "TEXT")
    val rulesJson: String,
    @Column(name = "input_snapshot_json", columnDefinition = "LONGTEXT")
    val inputSnapshotJson: String? = null,
    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis()
)
