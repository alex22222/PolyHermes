package com.wrbug.polymarketbot.entity

import jakarta.persistence.*

@Entity
@Table(
    name = "leader_scanner_candidate_pool",
    uniqueConstraints = [
        UniqueConstraint(
            name = "uk_leader_scanner_candidate_pool_cat_wallet",
            columnNames = ["category", "normalized_wallet"]
        )
    ]
)
data class LeaderScannerCandidatePool(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "category", nullable = false, length = 50)
    val category: String,

    @Column(name = "normalized_wallet", nullable = false, length = 42)
    val normalizedWallet: String,

    @Column(name = "source", nullable = false, length = 50)
    val source: String,

    @Column(name = "source_detail", length = 500)
    val sourceDetail: String? = null,

    @Column(name = "discovery_score", nullable = false)
    val discoveryScore: Int = 0,

    @Column(name = "first_discovered_at", nullable = false)
    val firstDiscoveredAt: Long = System.currentTimeMillis(),

    @Column(name = "last_seen_at", nullable = false)
    val lastSeenAt: Long = System.currentTimeMillis(),

    @Column(name = "analysis_state", nullable = false, length = 20)
    val analysisState: String = "PENDING",

    @Column(name = "analyzed_at")
    val analyzedAt: Long? = null,

    @Column(name = "promoted_at")
    val promotedAt: Long? = null,

    @Column(name = "last_analysis_result", columnDefinition = "TEXT")
    val lastAnalysisResult: String? = null,

    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis(),

    @Column(name = "updated_at", nullable = false)
    val updatedAt: Long = System.currentTimeMillis()
)
