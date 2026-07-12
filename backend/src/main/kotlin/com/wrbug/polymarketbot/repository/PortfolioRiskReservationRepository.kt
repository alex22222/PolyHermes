package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.PortfolioRiskReservation
import org.springframework.data.jpa.repository.JpaRepository

interface PortfolioRiskReservationRepository : JpaRepository<PortfolioRiskReservation, Long> {
    fun findByCorrelationId(correlationId: String): PortfolioRiskReservation?
    fun findByAccountIdAndStatusIn(accountId: Long, statuses: Collection<String>): List<PortfolioRiskReservation>
    fun countByAccountIdAndStatusAndCompletedAtGreaterThanEqual(accountId: Long, status: String, completedAt: Long): Long
}
