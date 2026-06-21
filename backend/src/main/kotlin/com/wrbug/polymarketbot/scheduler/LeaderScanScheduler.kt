package com.wrbug.polymarketbot.scheduler

import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderResearchScoreAdapterService
import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderScannerService
import org.slf4j.LoggerFactory
import org.springframework.context.annotation.Configuration
import org.springframework.scheduling.annotation.Scheduled

/**
 * Leader 扫描定时任务
 *
 * 调度策略：
 * - 每小时执行一次廉价发现层：持续从 activity events、bridge records、seed wallets、热门市场
 *   中沉淀候选钱包到 leader_scanner_candidate_pool，不调用 Data API。
 * - 每日 02:30 执行全量扫描：先发现再分析，从候选池中读取 PENDING 钱包，调用 Data API 分析并写入 copy_trading_leaders。
 */
@Configuration
class LeaderScanScheduler(
    private val leaderScannerService: LeaderScannerService,
    private val researchScoreAdapterService: LeaderResearchScoreAdapterService
) {
    private val logger = LoggerFactory.getLogger(LeaderScanScheduler::class.java)

    /**
     * 每小时执行一次候选发现（廉价，无 Data API 调用）
     */
    @Scheduled(cron = "0 0 * * * ?")
    fun hourlyDiscovery() {
        logger.info("【定时任务】Leader 候选发现开始 ...")
        try {
            val discovered = leaderScannerService.discoverOnly(targetCategory = null)
            logger.info("【定时任务】Leader 候选发现完成: 本次写入/更新 {} 个候选", discovered)
        } catch (e: Exception) {
            logger.error("【定时任务】Leader 候选发现异常", e)
        }
    }

    /**
     * 每日 02:30 执行全量扫描（发现 + 分析 + 持久化）
     * 时区跟随服务器本地时区
     */
    @Scheduled(cron = "0 30 2 * * ?")
    fun dailyScan() {
        logger.info("【定时任务】Leader 每日扫描开始 ...")
        try {
            val result = leaderScannerService.scan(targetCategory = null, dryRun = false)
            if (result.success) {
                logger.info(
                    "【定时任务】Leader 每日扫描完成: 新建={}, 更新={}, 分析={}, 耗时={}ms, 类别={}",
                    result.createdCount,
                    result.updatedCount,
                    result.totalAnalyzedWalletCount,
                    result.durationMs,
                    result.categories.joinToString(",")
                )
                try {
                    val scoredCount = researchScoreAdapterService.scoreAllLeaders()
                    logger.info("【定时任务】Leader 研究评分完成: {} 个", scoredCount)
                } catch (e: Exception) {
                    logger.warn("【定时任务】Leader 研究评分失败: {}", e.message)
                }
            } else {
                logger.warn("【定时任务】Leader 每日扫描失败: {}", result.message)
            }
        } catch (e: Exception) {
            logger.error("【定时任务】Leader 每日扫描异常", e)
        }
    }
}
