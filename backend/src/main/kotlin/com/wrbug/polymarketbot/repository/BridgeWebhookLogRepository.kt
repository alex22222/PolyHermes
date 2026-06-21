package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.BridgeWebhookLog
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

@Repository
interface BridgeWebhookLogRepository : JpaRepository<BridgeWebhookLog, Long> {

    fun findByTransactionHash(transactionHash: String): BridgeWebhookLog?

    fun findAllByOrderByCreatedAtDesc(pageable: Pageable): Page<BridgeWebhookLog>

    fun findByStatusOrderByCreatedAtDesc(status: String, pageable: Pageable): Page<BridgeWebhookLog>
}
