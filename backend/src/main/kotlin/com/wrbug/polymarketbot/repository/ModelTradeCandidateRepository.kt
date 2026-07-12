package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.ModelTradeCandidate
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

@Repository
interface ModelTradeCandidateRepository : JpaRepository<ModelTradeCandidate, String> {
    fun findByLeaderIdAndLeaderTradeIdAndCopyTradingIdAndAccountId(
        leaderId: Long,
        leaderTradeId: String,
        copyTradingId: Long,
        accountId: Long
    ): ModelTradeCandidate?
}
