package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.BridgeWebhookLog
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository

@Repository
interface BridgeWebhookLogRepository : JpaRepository<BridgeWebhookLog, Long> {

    fun findByTransactionHash(transactionHash: String): BridgeWebhookLog?

    fun findFirstByTransactionHashIgnoreCase(transactionHash: String): BridgeWebhookLog?

    fun findAllByOrderByCreatedAtDesc(pageable: Pageable): Page<BridgeWebhookLog>

    fun findByStatusOrderByCreatedAtDesc(status: String, pageable: Pageable): Page<BridgeWebhookLog>

    /**
     * 查询某个 Leader 发送过的所有市场 conditionId（去重）
     */
    @Query("SELECT DISTINCT b.conditionId FROM BridgeWebhookLog b WHERE b.leaderAddress = :leaderAddress")
    fun findDistinctConditionIdsByLeaderAddress(@Param("leaderAddress") leaderAddress: String): List<String>
}
