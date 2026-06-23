package com.wrbug.polymarketbot.controller.bridge

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.BridgeAuditRequest
import com.wrbug.polymarketbot.dto.BridgeAuditResponse
import com.wrbug.polymarketbot.dto.BridgeRuntimeStatusResponse
import com.wrbug.polymarketbot.dto.BridgeTradeRecordByCopyTradingRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDetailRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDto
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListResponse
import com.wrbug.polymarketbot.dto.BridgeTradeStatisticsRequest
import com.wrbug.polymarketbot.dto.BridgeTradeStatisticsResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.bridge.BridgeAuditClient
import com.wrbug.polymarketbot.service.bridge.BridgeTradeRecordService
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * 外部桥交易记录控制器（只读）
 */
@RestController
@RequestMapping("/api/bridge/trades")
class BridgeTradeRecordController(
    private val bridgeTradeRecordService: BridgeTradeRecordService,
    private val bridgeAuditClient: BridgeAuditClient,
    private val messageSource: MessageSource
) {

    private val logger = LoggerFactory.getLogger(BridgeTradeRecordController::class.java)

    /**
     * 查询桥接交易记录列表
     * POST /api/bridge/trades/list
     */
    @PostMapping("/list")
    fun getBridgeTradeRecordList(
        @RequestBody request: BridgeTradeRecordListRequest
    ): ResponseEntity<ApiResponse<BridgeTradeRecordListResponse>> {
        return try {
            if (request.page < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "页码必须大于0", messageSource))
            }
            if (request.size < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "每页数量必须大于0", messageSource))
            }

            val result = bridgeTradeRecordService.getBridgeTradeRecordList(request)
            result.fold(
                onSuccess = { response ->
                    ResponseEntity.ok(ApiResponse.success(response))
                },
                onFailure = { e ->
                    logger.error("查询桥接交易记录列表失败", e)
                    ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
                }
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易记录列表异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 按跟单关系查询桥接交易记录
     * POST /api/bridge/trades/by-copy-trading
     */
    @PostMapping("/by-copy-trading")
    fun getBridgeTradeRecordListByCopyTrading(
        @RequestBody request: BridgeTradeRecordByCopyTradingRequest
    ): ResponseEntity<ApiResponse<BridgeTradeRecordListResponse>> {
        return try {
            if (request.copyTradingId <= 0) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "copyTradingId 无效", messageSource))
            }
            if (request.page < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "页码必须大于0", messageSource))
            }
            if (request.size < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "每页数量必须大于0", messageSource))
            }

            val result = bridgeTradeRecordService.getBridgeTradeRecordListByCopyTrading(request)
            result.fold(
                onSuccess = { response ->
                    ResponseEntity.ok(ApiResponse.success(response))
                },
                onFailure = { e ->
                    logger.error("按跟单关系查询桥接交易记录失败", e)
                    val errorCode = when (e) {
                        is IllegalArgumentException -> ErrorCode.PARAM_ERROR
                        else -> ErrorCode.SERVER_ERROR
                    }
                    ResponseEntity.ok(ApiResponse.error(errorCode, e.message, messageSource))
                }
            )
        } catch (e: Exception) {
            logger.error("按跟单关系查询桥接交易记录异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 查询桥接交易记录详情
     * POST /api/bridge/trades/detail
     */
    @PostMapping("/detail")
    fun getBridgeTradeRecordDetail(
        @RequestBody request: BridgeTradeRecordDetailRequest
    ): ResponseEntity<ApiResponse<BridgeTradeRecordDto>> {
        return try {
            if (request.id <= 0) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "记录ID无效", messageSource))
            }

            val result = bridgeTradeRecordService.getBridgeTradeRecordDetail(request)
            result.fold(
                onSuccess = { dto ->
                    ResponseEntity.ok(ApiResponse.success(dto))
                },
                onFailure = { e ->
                    logger.error("查询桥接交易记录详情失败", e)
                    val errorCode = when (e) {
                        is IllegalArgumentException -> ErrorCode.NOT_FOUND
                        else -> ErrorCode.SERVER_ERROR
                    }
                    ResponseEntity.ok(ApiResponse.error(errorCode, e.message, messageSource))
                }
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易记录详情异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 查询桥接交易统计
     * POST /api/bridge/trades/statistics
     */
    @PostMapping("/statistics")
    fun getBridgeTradeStatistics(
        @RequestBody request: BridgeTradeStatisticsRequest
    ): ResponseEntity<ApiResponse<BridgeTradeStatisticsResponse>> {
        return try {
            if (request.startTime != null && request.endTime != null && request.startTime > request.endTime) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "开始时间不能晚于结束时间", messageSource))
            }

            val result = bridgeTradeRecordService.getBridgeTradeStatistics(request)
            result.fold(
                onSuccess = { response ->
                    ResponseEntity.ok(ApiResponse.success(response))
                },
                onFailure = { e ->
                    logger.error("查询桥接交易统计失败", e)
                    ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
                }
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易统计异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 查询 Bridge 执行链路审计快照
     * POST /api/bridge/trades/audit
     */
    @PostMapping("/audit")
    fun getBridgeAudit(
        @RequestBody request: BridgeAuditRequest
    ): ResponseEntity<ApiResponse<BridgeAuditResponse>> {
        return try {
            if (request.limit < 1 || request.limit > 1000) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "limit 必须在 1-1000 之间", messageSource))
            }
            if (request.failureLimit < 1 || request.failureLimit > 500) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "failureLimit 必须在 1-500 之间", messageSource))
            }
            if (request.portfolioTimeout < 5 || request.portfolioTimeout > 180) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "portfolioTimeout 必须在 5-180 秒之间", messageSource))
            }

            val audit = bridgeAuditClient.fetchAudit(request)
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, "Bridge audit 暂不可用", messageSource))

            ResponseEntity.ok(ApiResponse.success(audit))
        } catch (e: Exception) {
            logger.error("查询 Bridge 执行链路审计异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 查询 Bridge runtime 状态
     * POST /api/bridge/trades/status
     */
    @PostMapping("/status")
    fun getBridgeStatus(): ResponseEntity<ApiResponse<BridgeRuntimeStatusResponse>> {
        return try {
            val status = bridgeAuditClient.fetchStatus()
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, "Bridge status 暂不可用", messageSource))

            ResponseEntity.ok(ApiResponse.success(status))
        } catch (e: Exception) {
            logger.error("查询 Bridge runtime 状态异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }
}
