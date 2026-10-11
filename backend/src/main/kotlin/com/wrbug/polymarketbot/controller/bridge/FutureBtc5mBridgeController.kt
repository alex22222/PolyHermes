package com.wrbug.polymarketbot.controller.bridge

import com.fasterxml.jackson.databind.JsonNode
import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.FutureBtc5mBridgeStatus
import com.wrbug.polymarketbot.dto.FutureBtc5mOrder
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderDetailRequest
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderListRequest
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderListResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.bridge.FutureBtc5mBridgeClient
import org.slf4j.LoggerFactory
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/future-btc5m")
class FutureBtc5mBridgeController(private val client: FutureBtc5mBridgeClient) {
    private val logger = LoggerFactory.getLogger(FutureBtc5mBridgeController::class.java)

    @PostMapping("/status")
    fun status(): ResponseEntity<ApiResponse<FutureBtc5mBridgeStatus>> = respond { client.status() }

    @PostMapping("/control")
    fun control(@RequestBody request: JsonNode): ResponseEntity<ApiResponse<FutureBtc5mBridgeStatus>> = respond {
        require(request.isObject && request.size() == 1 && request.path("enabled").isBoolean) {
            "只允许 enabled 布尔开关，每笔金额固定1美元"
        }
        client.control(request.path("enabled").asBoolean())
    }

    @PostMapping("/orders/list")
    fun orders(@RequestBody request: FutureBtc5mOrderListRequest): ResponseEntity<ApiResponse<FutureBtc5mOrderListResponse>> =
        respond { client.orders(request) }

    @PostMapping("/orders/detail")
    fun detail(@RequestBody request: FutureBtc5mOrderDetailRequest): ResponseEntity<ApiResponse<FutureBtc5mOrder>> =
        respond { client.detail(request.id) }

    private fun <T> respond(action: () -> T): ResponseEntity<ApiResponse<T>> = try {
        ResponseEntity.ok(ApiResponse.success(action()))
    } catch (error: IllegalArgumentException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, error.message))
    } catch (error: NoSuchElementException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.NOT_FOUND, error.message))
    } catch (error: Exception) {
        logger.warn("Future Bridge unavailable: {}", error.javaClass.simpleName)
        ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, "Future Bridge 未连接或操作未获确认，请检查同机桥服务"))
    }
}
