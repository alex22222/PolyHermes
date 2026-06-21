package com.wrbug.polymarketbot.controller.bridge

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.BridgeWebhookLogListRequest
import com.wrbug.polymarketbot.dto.BridgeWebhookLogListResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.bridge.BridgeWebhookLogService
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * Bridge webhook 日志接口
 * 供前端查看 PolyHermes 向 Bridge 发送 Leader 交易信号的 HTTP 调用记录
 */
@RestController
@RequestMapping("/api/bridge/webhook-logs")
class BridgeWebhookLogController(
    private val bridgeWebhookLogService: BridgeWebhookLogService,
    private val messageSource: MessageSource
) {

    private val logger = LoggerFactory.getLogger(BridgeWebhookLogController::class.java)

    /**
     * 查询 webhook 调用日志列表
     * POST /api/bridge/webhook-logs/list
     */
    @PostMapping("/list")
    fun getBridgeWebhookLogList(
        @RequestBody request: BridgeWebhookLogListRequest
    ): ResponseEntity<ApiResponse<BridgeWebhookLogListResponse>> {
        return try {
            if (request.page < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "页码必须大于0", messageSource))
            }
            if (request.size < 1) {
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, "每页数量必须大于0", messageSource))
            }

            val result = bridgeWebhookLogService.getBridgeWebhookLogList(request)
            result.fold(
                onSuccess = { response ->
                    ResponseEntity.ok(ApiResponse.success(response))
                },
                onFailure = { e ->
                    logger.error("查询 webhook 日志列表失败", e)
                    ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
                }
            )
        } catch (e: Exception) {
            logger.error("查询 webhook 日志列表异常", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }
}
