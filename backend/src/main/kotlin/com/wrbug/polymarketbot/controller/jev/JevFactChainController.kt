package com.wrbug.polymarketbot.controller.jev

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.jev.JevFactChainListDto
import com.wrbug.polymarketbot.service.jev.JevFactChainSnapshotService
import org.slf4j.LoggerFactory
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/jev-fact-chain")
class JevFactChainController(private val snapshotService: JevFactChainSnapshotService) {
    private val logger = LoggerFactory.getLogger(JevFactChainController::class.java)

    @GetMapping("/list")
    fun list(
        @RequestParam(defaultValue = "50") limit: Int,
        @RequestParam(defaultValue = "all") kind: String
    ): ResponseEntity<ApiResponse<JevFactChainListDto>> {
        if (limit !in 1..100 || kind !in setOf("all", "observations", "discovery")) {
            return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, "invalid limit or kind"))
        }
        return try {
            ResponseEntity.ok(ApiResponse.success(snapshotService.list(limit, kind)))
        } catch (e: Exception) {
            logger.error("Failed to read Jev fact-chain snapshots", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, "Jev snapshots unavailable"))
        }
    }
}
