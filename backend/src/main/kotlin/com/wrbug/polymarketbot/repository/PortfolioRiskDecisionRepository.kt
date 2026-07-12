package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.PortfolioRiskDecision
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.domain.Pageable

interface PortfolioRiskDecisionRepository : JpaRepository<PortfolioRiskDecision, Long> {
    fun findByRequestId(requestId: String): PortfolioRiskDecision?
    fun findByAccountIdOrderByCreatedAtDesc(accountId: Long, pageable: Pageable): List<PortfolioRiskDecision>
    fun findByAccountIdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(accountId: Long, createdAt: Long): List<PortfolioRiskDecision>
}
