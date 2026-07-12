package com.wrbug.polymarketbot.controller.risk

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.risk.PortfolioRiskEvaluationService
import com.wrbug.polymarketbot.service.risk.PortfolioRiskReservationService
import com.wrbug.polymarketbot.service.risk.PortfolioRiskDecisionQueryService
import com.wrbug.polymarketbot.service.risk.PortfolioRiskShadowReportService
import com.wrbug.polymarketbot.service.risk.PortfolioRelationService
import com.wrbug.polymarketbot.service.risk.PortfolioBuyControlService
import com.wrbug.polymarketbot.service.risk.PortfolioReductionPreviewService
import com.wrbug.polymarketbot.service.risk.PortfolioRiskHistoricalReplayService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/api/risk/portfolio")
class PortfolioRiskController(
    private val service: PortfolioRiskEvaluationService,
    private val queryService: PortfolioRiskDecisionQueryService,
    private val shadowReportService: PortfolioRiskShadowReportService,
    private val relationService: PortfolioRelationService,
    private val buyControlService: PortfolioBuyControlService,
    private val reductionPreviewService: PortfolioReductionPreviewService,
    private val historicalReplayService: PortfolioRiskHistoricalReplayService,
    private val messageSource: MessageSource
) {
    @PostMapping("/evaluate")
    fun evaluate(@RequestBody request: PortfolioRiskEvaluationRequest): ResponseEntity<ApiResponse<PortfolioRiskEvaluationResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(service.evaluate(request)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/decisions")
    fun decisions(@RequestBody request: PortfolioRiskDecisionListRequest): ResponseEntity<ApiResponse<List<PortfolioRiskDecisionDto>>> =
        ResponseEntity.ok(ApiResponse.success(queryService.list(request.accountId, request.limit)))

    @PostMapping("/replay")
    fun replay(@RequestBody request: PortfolioRiskReplayRequest): ResponseEntity<ApiResponse<PortfolioRiskReplayResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(queryService.replay(request.requestId)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/shadow-report")
    fun shadowReport(@RequestBody request: PortfolioRiskShadowReportRequest): ResponseEntity<ApiResponse<PortfolioRiskShadowReportResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(shadowReportService.generate(request.accountId, request.since)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/historical-replay")
    fun historicalReplay(@RequestBody request: PortfolioRiskHistoricalReplayRequest): ResponseEntity<ApiResponse<PortfolioRiskHistoricalReplayResponse>> = try {
        ResponseEntity.ok(ApiResponse.success(historicalReplayService.generate(request)))
    } catch (e: IllegalArgumentException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
    }

    @PostMapping("/relations")
    fun relations(@RequestBody request: PortfolioRelationRequest): ResponseEntity<ApiResponse<PortfolioRelationResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(relationService.getRelations(request.accountId)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/buy-control")
    fun buyControl(@RequestBody request: PortfolioBuyControlRequest): ResponseEntity<ApiResponse<PortfolioBuyControlResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(buyControlService.get(request.accountId)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/buy-control/update")
    fun updateBuyControl(
        @RequestBody request: PortfolioBuyControlUpdateRequest,
        httpRequest: HttpServletRequest
    ): ResponseEntity<ApiResponse<PortfolioBuyControlResponse>> {
        return try {
            val actor = httpRequest.getAttribute("username") as? String
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.AUTH_ERROR, "无法识别操作人", messageSource))
            ResponseEntity.ok(ApiResponse.success(buyControlService.update(request.accountId, request.paused, request.reason, actor)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }
    }

    @PostMapping("/reduction/preview")
    fun previewReduction(
        @RequestBody request: PortfolioReductionPreviewRequest,
        httpRequest: HttpServletRequest
    ): ResponseEntity<ApiResponse<PortfolioReductionPreviewResponse>> {
        return try {
            val actor = httpRequest.getAttribute("username") as? String
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.AUTH_ERROR, "无法识别操作人", messageSource))
            ResponseEntity.ok(ApiResponse.success(reductionPreviewService.preview(request, actor)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }
    }

    @PostMapping("/reduction/draft")
    fun reductionDraft(@RequestBody request: PortfolioReductionDraftRequest): ResponseEntity<ApiResponse<PortfolioReductionPreviewResponse>> = try {
        ResponseEntity.ok(ApiResponse.success(reductionPreviewService.get(request.draftId)))
    } catch (e: IllegalArgumentException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
    }

    @PostMapping("/reduction/confirm")
    fun confirmReduction(
        @RequestBody request: PortfolioReductionConfirmRequest,
        httpRequest: HttpServletRequest
    ): ResponseEntity<ApiResponse<PortfolioReductionPreviewResponse>> {
        return try {
            val actor = httpRequest.getAttribute("username") as? String
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.AUTH_ERROR, "无法识别操作人", messageSource))
            ResponseEntity.ok(ApiResponse.success(reductionPreviewService.confirm(request.draftId, actor)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }
    }

    @PostMapping("/reduction/execute")
    fun executeReduction(
        @RequestBody request: PortfolioReductionExecuteRequest,
        httpRequest: HttpServletRequest
    ): ResponseEntity<ApiResponse<PortfolioReductionPreviewResponse>> {
        return try {
            val actor = httpRequest.getAttribute("username") as? String
                ?: return ResponseEntity.ok(ApiResponse.error(ErrorCode.AUTH_ERROR, "无法识别操作人", messageSource))
            ResponseEntity.ok(ApiResponse.success(reductionPreviewService.execute(request.draftId, actor)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }
    }

    @PostMapping("/reduction/refresh")
    fun refreshReduction(@RequestBody request: PortfolioReductionRefreshRequest): ResponseEntity<ApiResponse<PortfolioReductionPreviewResponse>> = try {
        ResponseEntity.ok(ApiResponse.success(reductionPreviewService.refresh(request.draftId)))
    } catch (e: IllegalArgumentException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
    }

    @PostMapping("/reduction/list")
    fun reductionList(@RequestBody request: PortfolioReductionListRequest): ResponseEntity<ApiResponse<List<PortfolioReductionPreviewResponse>>> = try {
        ResponseEntity.ok(ApiResponse.success(reductionPreviewService.list(request.accountId)))
    } catch (e: IllegalArgumentException) {
        ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
    }
}

@RestController
@RequestMapping("/api/internal/risk/portfolio")
class InternalPortfolioRiskController(
    private val service: PortfolioRiskEvaluationService,
    private val reservationService: PortfolioRiskReservationService,
    private val messageSource: MessageSource
) {
    @PostMapping("/evaluate")
    fun evaluate(@RequestBody request: PortfolioRiskEvaluationRequest): ResponseEntity<ApiResponse<PortfolioRiskEvaluationResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(service.evaluate(request)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }

    @PostMapping("/complete")
    fun complete(@RequestBody request: PortfolioRiskCompletionRequest): ResponseEntity<ApiResponse<PortfolioRiskCompletionResponse>> =
        try {
            ResponseEntity.ok(ApiResponse.success(reservationService.complete(request.correlationId, request.status)))
        } catch (e: IllegalArgumentException) {
            ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, e.message, messageSource))
        }
}
