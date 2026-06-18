package com.wrbug.polymarketbot.controller.bridge

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDetailRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDto
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListResponse
import com.wrbug.polymarketbot.enums.ErrorCode
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
}
