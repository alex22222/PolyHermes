package com.wrbug.polymarketbot.controller.copytrading.leaders

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.SystemConfig
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.repository.SystemConfigRepository
import com.wrbug.polymarketbot.util.CategoryValidator
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

/**
 * Leader Scanner 配置管理接口
 * 用于管理 seed wallets、分析窗口等配置（持久化到 system_config）
 */
@RestController
@RequestMapping("/api/copy-trading/leaders/scan/config")
class LeaderScannerConfigController(
    private val systemConfigRepository: SystemConfigRepository,
    private val messageSource: MessageSource
) {

    private val logger = LoggerFactory.getLogger(LeaderScannerConfigController::class.java)

    companion object {
        const val KEY_ANALYSIS_WINDOW_DAYS = "leader_scanner.analysis_window_days"
        const val KEY_GENERAL_SEED_WALLETS = "leader_scanner.seed_wallets"
        const val CATEGORIES = "politics,sports,crypto,finance"
    }

    /**
     * 获取 Leader Scanner 全局配置
     */
    @PostMapping("/get")
    fun getConfig(): ResponseEntity<ApiResponse<LeaderScannerGlobalConfigDto>> {
        return try {
            val analysisWindowDays = systemConfigRepository.findByConfigKey(KEY_ANALYSIS_WINDOW_DAYS)
                ?.configValue?.toIntOrNull() ?: 30

            val seedWallets = CATEGORIES.split(",").associateWith { category ->
                getSeedWallets("leader_scanner.seed_wallets.$category")
            }

            val generalSeedWallets = getSeedWallets(KEY_GENERAL_SEED_WALLETS)

            ResponseEntity.ok(
                ApiResponse.success(
                    LeaderScannerGlobalConfigDto(
                        analysisWindowDays = analysisWindowDays,
                        seedWallets = seedWallets,
                        generalSeedWallets = generalSeedWallets
                    )
                )
            )
        } catch (e: Exception) {
            logger.error("获取 Leader Scanner 配置异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 更新分析窗口天数
     */
    @PostMapping("/analysis-window-days")
    fun updateAnalysisWindowDays(@RequestBody request: Map<String, Int>): ResponseEntity<ApiResponse<Map<String, Int>>> {
        return try {
            val days = request["days"] ?: return ResponseEntity.ok(
                ApiResponse.error(ErrorCode.PARAM_ERROR, "缺少 days 参数", messageSource)
            )
            if (days < 1 || days > 365) {
                return ResponseEntity.ok(
                    ApiResponse.error(ErrorCode.PARAM_ERROR, "days 必须在 1-365 之间", messageSource)
                )
            }
            upsertConfig(KEY_ANALYSIS_WINDOW_DAYS, days.toString(), "Leader Scanner 分析窗口天数")
            ResponseEntity.ok(ApiResponse.success(mapOf("days" to days)))
        } catch (e: Exception) {
            logger.error("更新分析窗口异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 更新某类别的 seed wallets
     */
    @PostMapping("/seed-wallets")
    fun updateSeedWallets(@RequestBody request: UpdateLeaderScannerSeedWalletsRequest): ResponseEntity<ApiResponse<LeaderScannerConfigDto>> {
        return try {
            val category = CategoryValidator.normalizeCategory(request.category)
                ?: return ResponseEntity.ok(
                    ApiResponse.error(ErrorCode.PARAM_ERROR, "不支持的类别: ${request.category}", messageSource)
                )

            val validWallets = request.wallets
                .map { it.trim().lowercase() }
                .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                .distinct()

            val invalidCount = request.wallets.size - validWallets.size
            if (invalidCount > 0) {
                logger.warn("seed wallets 中发现 {} 个无效地址已过滤", invalidCount)
            }

            val configKey = "leader_scanner.seed_wallets.$category"
            val configValue = validWallets.joinToString(",")
            upsertConfig(configKey, configValue, "Leader Scanner $category 类别 seed wallets")

            ResponseEntity.ok(
                ApiResponse.success(
                    LeaderScannerConfigDto(
                        category = category,
                        seedWallets = validWallets,
                        description = "已过滤 $invalidCount 个无效地址"
                    )
                )
            )
        } catch (e: Exception) {
            logger.error("更新 seed wallets 异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    /**
     * 更新通用 seed wallets
     */
    @PostMapping("/seed-wallets/general")
    fun updateGeneralSeedWallets(@RequestBody request: Map<String, List<String>>): ResponseEntity<ApiResponse<Map<String, List<String>>>> {
        return try {
            val wallets = request["wallets"] ?: return ResponseEntity.ok(
                ApiResponse.error(ErrorCode.PARAM_ERROR, "缺少 wallets 参数", messageSource)
            )
            val validWallets = wallets
                .map { it.trim().lowercase() }
                .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                .distinct()

            upsertConfig(KEY_GENERAL_SEED_WALLETS, validWallets.joinToString(","), "Leader Scanner 通用 seed wallets")
            ResponseEntity.ok(ApiResponse.success(mapOf("wallets" to validWallets)))
        } catch (e: Exception) {
            logger.error("更新通用 seed wallets 异常: ${e.message}", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_ERROR, e.message, messageSource))
        }
    }

    private fun getSeedWallets(configKey: String): List<String> {
        return systemConfigRepository.findByConfigKey(configKey)?.configValue
            ?.split(",", "\n", ";", " ", "\t")
            ?.map { it.trim().lowercase() }
            ?.filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
            ?.distinct()
            ?: emptyList()
    }

    private fun upsertConfig(configKey: String, configValue: String?, description: String) {
        val now = System.currentTimeMillis()
        val existing = systemConfigRepository.findByConfigKey(configKey)
        if (existing != null) {
            systemConfigRepository.save(
                existing.copy(configValue = configValue, updatedAt = now)
            )
        } else {
            systemConfigRepository.save(
                SystemConfig(
                    configKey = configKey,
                    configValue = configValue,
                    description = description,
                    createdAt = now,
                    updatedAt = now
                )
            )
        }
    }
}
