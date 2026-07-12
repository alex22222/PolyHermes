package com.wrbug.polymarketbot.controller.accounts

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.DailyAssetHistoryRequest
import com.wrbug.polymarketbot.dto.PortfolioExposureResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.accounts.PortfolioExposureService
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/api/accounts/positions")
class PortfolioExposureController(
    private val service: PortfolioExposureService,
    private val messageSource: MessageSource
) {
    @PostMapping("/exposures")
    fun getExposure(@RequestBody request: DailyAssetHistoryRequest): ResponseEntity<ApiResponse<PortfolioExposureResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(service.getExposure(request.accountId)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ACCOUNT_ID_INVALID, e.message, messageSource))
        }
}
