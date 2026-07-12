package com.wrbug.polymarketbot.entity

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table
import java.math.BigDecimal

@Entity
@Table(name = "model_trade_candidate")
data class ModelTradeCandidate(
    @Id
    @Column(name = "candidate_id", length = 36)
    val candidateId: String,

    @Column(name = "leader_id", nullable = false)
    val leaderId: Long,

    @Column(name = "leader_trade_id", nullable = false, length = 100)
    val leaderTradeId: String,

    @Column(name = "copy_trading_id", nullable = false)
    val copyTradingId: Long,

    @Column(name = "account_id", nullable = false)
    val accountId: Long,

    @Column(name = "source", nullable = false, length = 50)
    val source: String,

    @Column(name = "side", nullable = false, length = 10)
    val side: String,

    @Column(name = "market_id", length = 100)
    val marketId: String? = null,

    @Column(name = "outcome", length = 50)
    val outcome: String? = null,

    @Column(name = "outcome_index")
    val outcomeIndex: Int? = null,

    @Column(name = "leader_price", nullable = false, precision = 20, scale = 8)
    val leaderPrice: BigDecimal,

    @Column(name = "leader_size", nullable = false, precision = 20, scale = 8)
    val leaderSize: BigDecimal,

    @Column(name = "event_time")
    val eventTime: Long? = null,

    @Column(name = "observed_at", nullable = false)
    val observedAt: Long = System.currentTimeMillis()
)
