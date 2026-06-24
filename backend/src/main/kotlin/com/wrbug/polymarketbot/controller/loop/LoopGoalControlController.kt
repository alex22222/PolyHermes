package com.wrbug.polymarketbot.controller.loop

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.LoopGoalControlStatusDto
import com.wrbug.polymarketbot.dto.LoopGoalControlUpdateRequest
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.loop.LoopGoalControlService
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/loop-goals")
class LoopGoalControlController(
    private val loopGoalControlService: LoopGoalControlService,
    private val messageSource: MessageSource
) {
    private val logger = LoggerFactory.getLogger(LoopGoalControlController::class.java)

    @PostMapping("/status")
    fun status(): ResponseEntity<ApiResponse<LoopGoalControlStatusDto>> {
        return safe { loopGoalControlService.status() }
    }

    @PostMapping("/update")
    fun update(@RequestBody request: LoopGoalControlUpdateRequest): ResponseEntity<ApiResponse<LoopGoalControlStatusDto>> {
        return safe { loopGoalControlService.update(request.goalKey, request.action) }
    }

    private fun <T> safe(block: () -> T): ResponseEntity<ApiResponse<T>> {
        return try {
            ResponseEntity.ok(ApiResponse.success(block()))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        } catch (e: Exception) {
            logger.error("Loop goal control request failed", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }
}
