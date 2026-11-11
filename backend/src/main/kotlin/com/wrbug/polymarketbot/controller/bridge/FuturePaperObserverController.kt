package com.wrbug.polymarketbot.controller.bridge

import com.fasterxml.jackson.databind.JsonNode
import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.bridge.FuturePaperObserverClient
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/future-btc5m/paper/observe")
class FuturePaperObserverController(private val client: FuturePaperObserverClient) {
    @PostMapping("/status")
    fun status(): ApiResponse<JsonNode> = try {
        ApiResponse.success(client.status())
    } catch (error: Exception) {
        ApiResponse.error(ErrorCode.SERVER_ERROR, "新增币种纸上验证暂不可用，恢复后自动刷新")
    }
}
