package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.dto.BridgeWebhookLogDto
import com.wrbug.polymarketbot.dto.BridgeWebhookLogListRequest
import com.wrbug.polymarketbot.dto.BridgeWebhookLogListResponse
import com.wrbug.polymarketbot.entity.BridgeWebhookLog
import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import org.slf4j.LoggerFactory
import org.springframework.data.domain.Page
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service

/**
 * Bridge webhook 日志服务
 */
@Service
class BridgeWebhookLogService(
    private val bridgeWebhookLogRepository: BridgeWebhookLogRepository
) {
    private val logger = LoggerFactory.getLogger(BridgeWebhookLogService::class.java)

    /**
     * 查询 webhook 调用日志列表
     */
    fun getBridgeWebhookLogList(request: BridgeWebhookLogListRequest): Result<BridgeWebhookLogListResponse> {
        return try {
            val pageRequest = PageRequest.of(
                (request.page - 1).coerceAtLeast(0),
                request.size.coerceIn(1, 100),
                Sort.by(Sort.Order.desc("createdAt"))
            )

            val page: Page<BridgeWebhookLog> = when {
                !request.status.isNullOrBlank() -> {
                    bridgeWebhookLogRepository.findByStatusOrderByCreatedAtDesc(request.status, pageRequest)
                }
                else -> {
                    bridgeWebhookLogRepository.findAllByOrderByCreatedAtDesc(pageRequest)
                }
            }

            val list = page.content.map { it.toDto() }

            Result.success(
                BridgeWebhookLogListResponse(
                    list = list,
                    total = page.totalElements,
                    page = request.page,
                    size = request.size
                )
            )
        } catch (e: Exception) {
            logger.error("查询 webhook 日志列表失败", e)
            Result.failure(e)
        }
    }

    private fun BridgeWebhookLog.toDto(): BridgeWebhookLogDto {
        return BridgeWebhookLogDto(
            id = this.id!!,
            bridgeId = this.bridgeId,
            event = this.event,
            leaderAddress = this.leaderAddress,
            leaderName = this.leaderName,
            transactionHash = this.transactionHash,
            conditionId = this.conditionId,
            marketSlug = this.marketSlug,
            side = this.side,
            outcome = this.outcome,
            requestBody = this.requestBody,
            responseBody = this.responseBody,
            statusCode = this.statusCode,
            status = this.status,
            errorMessage = this.errorMessage,
            createdAt = this.createdAt,
            updatedAt = this.updatedAt
        )
    }
}
