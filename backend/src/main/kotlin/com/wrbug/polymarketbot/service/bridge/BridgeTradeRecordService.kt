package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.dto.BridgeTradeRecordDetailRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDto
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListResponse
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import org.slf4j.LoggerFactory
import org.springframework.data.domain.Page
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service

/**
 * 外部桥交易记录服务
 */
@Service
class BridgeTradeRecordService(
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository
) {
    private val logger = LoggerFactory.getLogger(BridgeTradeRecordService::class.java)

    /**
     * 查询桥接交易记录列表
     */
    fun getBridgeTradeRecordList(request: BridgeTradeRecordListRequest): Result<BridgeTradeRecordListResponse> {
        return try {
            val pageRequest = PageRequest.of(
                (request.page - 1).coerceAtLeast(0),
                request.size.coerceIn(1, 100),
                Sort.by(Sort.Order.desc("createdAt"))
            )

            val page: Page<BridgeTradeRecord> = when {
                !request.bridgeId.isNullOrBlank() && !request.status.isNullOrBlank() -> {
                    bridgeTradeRecordRepository.findByBridgeIdAndStatus(request.bridgeId, request.status, pageRequest)
                }
                !request.bridgeId.isNullOrBlank() -> {
                    bridgeTradeRecordRepository.findByBridgeId(request.bridgeId, pageRequest)
                }
                !request.status.isNullOrBlank() -> {
                    // 状态过滤：内存分页（表数据量不大）
                    val allPage = bridgeTradeRecordRepository.findAll(pageRequest)
                    val filtered = allPage.content.filter { it.status == request.status }
                    PageImpl(filtered, pageRequest, filtered.size.toLong())
                }
                else -> {
                    bridgeTradeRecordRepository.findAll(pageRequest)
                }
            }

            val list = page.content.map { it.toDto() }

            Result.success(
                BridgeTradeRecordListResponse(
                    list = list,
                    total = page.totalElements,
                    page = request.page,
                    size = request.size
                )
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易记录列表失败", e)
            Result.failure(e)
        }
    }

    /**
     * 查询桥接交易记录详情
     */
    fun getBridgeTradeRecordDetail(request: BridgeTradeRecordDetailRequest): Result<BridgeTradeRecordDto> {
        return try {
            val record = bridgeTradeRecordRepository.findById(request.id).orElse(null)
                ?: return Result.failure(IllegalArgumentException("桥接交易记录不存在"))

            Result.success(record.toDto())
        } catch (e: Exception) {
            logger.error("查询桥接交易记录详情失败", e)
            Result.failure(e)
        }
    }

    private fun BridgeTradeRecord.toDto(): BridgeTradeRecordDto {
        return BridgeTradeRecordDto(
            id = this.id!!,
            bridgeId = this.bridgeId,
            externalTradeId = this.externalTradeId,
            marketId = this.marketId,
            marketTitle = this.marketTitle,
            side = this.side,
            outcome = this.outcome,
            outcomeIndex = this.outcomeIndex,
            quantity = this.quantity.toPlainString(),
            price = this.price.toPlainString(),
            amount = this.amount.toPlainString(),
            fee = this.fee.toPlainString(),
            status = this.status,
            errorMessage = this.errorMessage,
            rawPayload = this.rawPayload,
            executedAt = this.executedAt,
            createdAt = this.createdAt,
            updatedAt = this.updatedAt
        )
    }
}
