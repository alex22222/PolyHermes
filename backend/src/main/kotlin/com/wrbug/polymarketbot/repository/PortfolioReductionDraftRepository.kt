package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.PortfolioReductionDraft
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Lock
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository
import jakarta.persistence.LockModeType

@Repository
interface PortfolioReductionDraftRepository : JpaRepository<PortfolioReductionDraft, String> {
    fun findByAccountIdOrderByCreatedAtDesc(accountId: Long): List<PortfolioReductionDraft>

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT d FROM PortfolioReductionDraft d WHERE d.draftId = :draftId")
    fun findLockedByDraftId(@Param("draftId") draftId: String): PortfolioReductionDraft?
}
