package com.wrbug.polymarketbot.entity

import jakarta.persistence.*

@Entity
@Table(name = "portfolio_buy_control")
data class PortfolioBuyControl(
    @Id @Column(name = "account_id")
    val accountId: Long,
    @Column(name = "paused", nullable = false)
    var paused: Boolean = false,
    @Column(name = "reason", length = 500)
    var reason: String? = null,
    @Column(name = "updated_by", nullable = false, length = 100)
    var updatedBy: String,
    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis()
)

@Entity
@Table(name = "portfolio_buy_control_audit", indexes = [Index(name = "idx_buy_control_audit_account_created", columnList = "account_id,created_at")])
data class PortfolioBuyControlAudit(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    @Column(name = "account_id", nullable = false)
    val accountId: Long,
    @Column(name = "action", nullable = false, length = 20)
    val action: String,
    @Column(name = "reason", length = 500)
    val reason: String? = null,
    @Column(name = "actor", nullable = false, length = 100)
    val actor: String,
    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis()
)
