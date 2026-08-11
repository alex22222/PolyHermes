package com.wrbug.polymarketbot.controller.system

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.UpdateCheckDto
import com.wrbug.polymarketbot.dto.UpdateStatusDto
import com.wrbug.polymarketbot.dto.UpdateVersionDto
import com.wrbug.polymarketbot.enums.ErrorCode
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/update")
class UpdateController(
    @Value("\${app.version:dev}") private val appVersion: String,
    @Value("\${app.git-tag:}") private val gitTag: String
) {
    @GetMapping("/version")
    fun version(): ResponseEntity<ApiResponse<UpdateVersionDto>> {
        return ResponseEntity.ok(ApiResponse.success(UpdateVersionDto(version = appVersion)))
    }

    @GetMapping("/check")
    fun check(): ResponseEntity<ApiResponse<UpdateCheckDto>> {
        return ResponseEntity.ok(
            ApiResponse.success(
                UpdateCheckDto(
                    hasUpdate = false,
                    currentVersion = appVersion,
                    latestVersion = appVersion,
                    latestTag = gitTag,
                    releaseNotes = "",
                    publishedAt = "",
                    prerelease = false
                )
            )
        )
    }

    @GetMapping("/status")
    fun status(): ResponseEntity<ApiResponse<UpdateStatusDto>> {
        return ResponseEntity.ok(
            ApiResponse.success(
                UpdateStatusDto(
                    updating = false,
                    progress = 0,
                    message = "自动更新未配置",
                    error = null
                )
            )
        )
    }

    @PostMapping("/update")
    fun update(): ResponseEntity<ApiResponse<Unit>> {
        return ResponseEntity.ok(ApiResponse.error(ErrorCode.BUSINESS_ERROR, "自动更新未配置"))
    }
}
