package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.PortfolioBuyControl
import com.wrbug.polymarketbot.entity.PortfolioBuyControlAudit
import org.springframework.data.jpa.repository.JpaRepository

interface PortfolioBuyControlRepository : JpaRepository<PortfolioBuyControl, Long>
interface PortfolioBuyControlAuditRepository : JpaRepository<PortfolioBuyControlAudit, Long> {
    fun findTop100ByAccountIdOrderByCreatedAtDesc(accountId: Long): List<PortfolioBuyControlAudit>
}
