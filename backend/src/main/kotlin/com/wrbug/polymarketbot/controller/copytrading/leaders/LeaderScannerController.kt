package com.wrbug.polymarketbot.controller.copytrading.leaders

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.LeaderScannerCandidatePool
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.repository.LeaderScannerCandidatePoolRepository
import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderResearchScoreAdapterService
import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderScannerService
import com.wrbug.polymarketbot.util.CategoryValidator
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

/**
 * Leader 扫描控制器
 * 提供手动触发扫描、预览扫描结果、查询扫描状态、候选池管理等接口
 */
@RestController
@RequestMapping("/api/copy-trading/leaders/scan")
class LeaderScannerController(
    private val leaderScannerService: LeaderScannerService,
    private val candidatePoolRepository: LeaderScannerCandidatePoolRepository,
    private val researchScoreAdapterService: LeaderResearchScoreAdapterService,
    private val messageSource: MessageSource
) {

    private val logger = LoggerFactory.getLogger(LeaderScannerController::class.java)

    private fun validateCategory(category: String?): String? {
        if (category == null) return null
        val normalized = CategoryValidator.normalizeCategory(category)
        return if (normalized == null) {
            "不支持的类别: $category，仅支持: sports, crypto, finance, politics"
        } else null
    }

    /**
     * 触发手动扫描（发现 + 分析 + 持久化 + 研究评分）
     */
    @PostMapping("/run")
    fun runScan(@RequestBody request: LeaderScanTriggerRequest): ResponseEntity<ApiResponse<LeaderScanBatchResponse>> {
        return try {
            validateCategory(request.category)?.let { msg ->
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, msg, messageSource))
            }

            val result = leaderScannerService.scan(
                targetCategory = request.category,
                dryRun = request.dryRun
            )

            // 非 dryRun 时，为所有 Leader 计算研究模块评分
            if (result.success && !request.dryRun) {
                try {
                    val scoredCount = researchScoreAdapterService.scoreAllLeaders()
                    logger.info("扫描完成后为 {} 个 Leader 计算研究评分", scoredCount)
                } catch (e: Exception) {
                    logger.warn("扫描完成后研究评分失败: {}", e.message)
                }
            }

            if (result.success) {
                ResponseEntity.ok(ApiResponse.success(result))
            } else {
                ResponseEntity.ok(ApiResponse.error(ErrorCode.BUSINESS_ERROR, result.message, messageSource))
            }
        } catch (e: Exception) {
            logger.error("扫描任务异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 手动触发 Leader 研究评分（为 copy_trading_leaders 所有记录）
     */
    @PostMapping("/research-score/run")
    fun runResearchScore(): ResponseEntity<ApiResponse<Map<String, Any>>> {
        return try {
            val scoredCount = researchScoreAdapterService.scoreAllLeaders()
            ResponseEntity.ok(
                ApiResponse.success(
                    mapOf(
                        "scoredCount" to scoredCount,
                        "message" to "已为 $scoredCount 个 Leader 计算研究评分"
                    )
                )
            )
        } catch (e: Exception) {
            logger.error("Leader 研究评分异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 仅执行候选发现（廉价，写入 candidate_pool）
     */
    @PostMapping("/discover")
    fun discoverCandidates(@RequestBody request: LeaderScanTriggerRequest): ResponseEntity<ApiResponse<LeaderScanDiscoveryResponse>> {
        return try {
            validateCategory(request.category)?.let { msg ->
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, msg, messageSource))
            }

            val discovered = leaderScannerService.discoverOnly(targetCategory = request.category)
            val category = request.category?.let { CategoryValidator.normalizeCategory(it) ?: it } ?: "all"
            val pendingCount = if (request.category != null) {
                candidatePoolRepository.countPendingByCategory(category)
            } else {
                listOf("politics", "sports", "crypto", "finance").sumOf {
                    candidatePoolRepository.countPendingByCategory(it)
                }
            }

            ResponseEntity.ok(
                ApiResponse.success(
                    LeaderScanDiscoveryResponse(
                        category = category,
                        discoveredCount = discovered,
                        pendingCount = pendingCount,
                        message = "发现完成，本次写入/更新 $discovered 个候选"
                    )
                )
            )
        } catch (e: Exception) {
            logger.error("候选发现异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 仅执行候选分析（昂贵，从 candidate_pool 读取 PENDING）
     */
    @PostMapping("/analyze")
    fun analyzeCandidates(@RequestBody request: LeaderScanTriggerRequest): ResponseEntity<ApiResponse<List<LeaderScanPreviewResponse>>> {
        return try {
            validateCategory(request.category)?.let { msg ->
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, msg, messageSource))
            }

            val categories = if (request.category != null) {
                listOf(CategoryValidator.normalizeCategory(request.category) ?: request.category)
            } else {
                listOf("politics", "sports", "crypto", "finance")
            }

            val previews = categories.map { category ->
                leaderScannerService.analyzeOnly(targetCategory = category, dryRun = request.dryRun)
            }
            ResponseEntity.ok(ApiResponse.success(previews))
        } catch (e: Exception) {
            logger.error("候选分析异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 预览扫描结果（不写入数据库）
     */
    @PostMapping("/preview")
    fun previewScan(@RequestBody request: LeaderScanTriggerRequest): ResponseEntity<ApiResponse<List<LeaderScanPreviewResponse>>> {
        return try {
            validateCategory(request.category)?.let { msg ->
                return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ERROR, msg, messageSource))
            }

            val previews = leaderScannerService.preview(request.category)
            ResponseEntity.ok(ApiResponse.success(previews))
        } catch (e: Exception) {
            logger.error("预览扫描异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 获取扫描状态
     */
    @PostMapping("/status")
    fun scanStatus(): ResponseEntity<ApiResponse<LeaderScanStatusDto>> {
        return try {
            val (running, lastAt, duration) = leaderScannerService.getStatus()
            val dto = LeaderScanStatusDto(
                isRunning = running,
                lastScanAt = lastAt,
                lastScanDurationMs = duration,
                lastScanResult = null,
                nextScheduledScan = "每日 02:30",
                nextScheduledDiscovery = "每小时 00 分"
            )
            ResponseEntity.ok(ApiResponse.success(dto))
        } catch (e: Exception) {
            logger.error("获取扫描状态异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 查询候选池
     */
    @PostMapping("/candidate-pool/list")
    fun listCandidatePool(@RequestBody request: LeaderScannerCandidatePoolQueryRequest): ResponseEntity<ApiResponse<LeaderScannerCandidatePoolQueryResponse>> {
        return try {
            val pageable = PageRequest.of(
                (request.page - 1).coerceAtLeast(0),
                request.size.coerceIn(1, 100),
                Sort.by(Sort.Direction.DESC, "discoveryScore")
            )

            val page = when {
                request.category != null && request.analysisState != null -> {
                    candidatePoolRepository.findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
                        request.category,
                        request.analysisState,
                        pageable
                    )
                }
                request.category != null -> {
                    candidatePoolRepository.findByCategory(request.category, pageable)
                }
                request.analysisState != null -> {
                    candidatePoolRepository.findByAnalysisState(request.analysisState, pageable)
                }
                else -> {
                    candidatePoolRepository.findAll(pageable)
                }
            }

            val dtoList = page.content.map { it.toDto() }
            ResponseEntity.ok(
                ApiResponse.success(
                    LeaderScannerCandidatePoolQueryResponse(
                        list = dtoList,
                        total = page.totalElements,
                        page = request.page,
                        size = request.size
                    )
                )
            )
        } catch (e: Exception) {
            logger.error("查询候选池异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    private fun LeaderScannerCandidatePool.toDto(): LeaderScannerCandidatePoolDto {
        return LeaderScannerCandidatePoolDto(
            id = this.id ?: 0,
            category = this.category,
            normalizedWallet = this.normalizedWallet,
            source = this.source,
            sourceDetail = this.sourceDetail,
            discoveryScore = this.discoveryScore,
            firstDiscoveredAt = this.firstDiscoveredAt,
            lastSeenAt = this.lastSeenAt,
            analysisState = this.analysisState,
            analyzedAt = this.analyzedAt,
            promotedAt = this.promotedAt,
            lastAnalysisResult = this.lastAnalysisResult,
            createdAt = this.createdAt,
            updatedAt = this.updatedAt
        )
    }
}
