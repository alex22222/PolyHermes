package com.wrbug.polymarketbot.entity

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table
import java.math.BigDecimal

@Entity
@Table(name = "portfolio_reduction_draft")
data class PortfolioReductionDraft(
    @Id
    @Column(name = "draft_id", length = 36)
    val draftId: String,

    @Column(name = "account_id", nullable = false)
    val accountId: Long,

    @Column(name = "position_key", nullable = false, length = 700)
    val positionKey: String,

    @Column(name = "quantity", nullable = false, precision = 20, scale = 8)
    val quantity: BigDecimal,

    @Column(name = "status", nullable = false, length = 20)
    var status: String = "DRAFT",

    @Column(name = "snapshot_json", nullable = false, columnDefinition = "LONGTEXT")
    val snapshotJson: String,

    @Column(name = "created_by", nullable = false, length = 100)
    val createdBy: String,

    @Column(name = "confirmed_by", length = 100)
    var confirmedBy: String? = null,

    @Column(name = "confirmed_at")
    var confirmedAt: Long? = null,

    @Column(name = "execution_requested_by", length = 100)
    var executionRequestedBy: String? = null,

    @Column(name = "execution_requested_at")
    var executionRequestedAt: Long? = null,

    @Column(name = "execution_external_trade_id", length = 100)
    var executionExternalTradeId: String? = null,

    @Column(name = "execution_record_id")
    var executionRecordId: Long? = null,

    @Column(name = "execution_error", columnDefinition = "TEXT")
    var executionError: String? = null,

    @Column(name = "execution_attempt", nullable = false)
    var executionAttempt: Int = 0,

    @Column(name = "expires_at", nullable = false)
    val expiresAt: Long,

    @Column(name = "created_at", nullable = false)
    val createdAt: Long,

    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long
)
