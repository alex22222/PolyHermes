package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.LeaderScannerCandidatePool
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Modifying
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository

@Repository
interface LeaderScannerCandidatePoolRepository : JpaRepository<LeaderScannerCandidatePool, Long> {

    fun findByCategoryAndNormalizedWallet(category: String, normalizedWallet: String): LeaderScannerCandidatePool?

    fun findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
        category: String,
        analysisState: String,
        pageable: org.springframework.data.domain.Pageable
    ): Page<LeaderScannerCandidatePool>

    fun countByCategoryAndAnalysisState(category: String, analysisState: String): Long

    fun findByCategoryOrderByDiscoveryScoreDesc(category: String): List<LeaderScannerCandidatePool>

    fun findByCategory(category: String, pageable: Pageable): Page<LeaderScannerCandidatePool>

    fun findByAnalysisState(analysisState: String, pageable: Pageable): Page<LeaderScannerCandidatePool>

    @Modifying
    @Query(
        """
        update LeaderScannerCandidatePool c
        set c.analysisState = :state,
            c.analyzedAt = :analyzedAt,
            c.lastAnalysisResult = :result,
            c.updatedAt = :updatedAt
        where c.id = :id
        """
    )
    fun updateAnalysisState(
        @Param("id") id: Long,
        @Param("state") state: String,
        @Param("analyzedAt") analyzedAt: Long,
        @Param("result") result: String?,
        @Param("updatedAt") updatedAt: Long
    ): Int

    @Modifying
    @Query(
        """
        update LeaderScannerCandidatePool c
        set c.promotedAt = :promotedAt,
            c.updatedAt = :updatedAt
        where c.id = :id
        """
    )
    fun markPromoted(
        @Param("id") id: Long,
        @Param("promotedAt") promotedAt: Long,
        @Param("updatedAt") updatedAt: Long
    ): Int

    @Query(
        """
        select count(c) from LeaderScannerCandidatePool c
        where c.category = :category and c.analysisState = 'PENDING'
        """
    )
    fun countPendingByCategory(@Param("category") category: String): Long
}
