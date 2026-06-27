package com.wrbug.polymarketbot.service.copytrading.leaders

import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Async
import org.springframework.stereotype.Service

/**
 * Leader 扫描异步入口。
 *
 * 把 [LeaderScannerService.scan] 从 HTTP 线程转移到独立线程池执行，
 * 解决长耗时扫描阻塞 Tomcat、导致客户端超时甚至服务崩溃的问题。
 */
@Service
class LeaderScannerAsyncService(
    private val leaderScannerService: LeaderScannerService,
    private val researchScoreAdapterService: LeaderResearchScoreAdapterService
) {

    private val logger = LoggerFactory.getLogger(LeaderScannerAsyncService::class.java)

    /**
     * 提交后台扫描任务。
     * 调用方（Controller）应立即返回，由该任务在后台完成发现、分析、持久化和研究评分。
     *
     * @param targetCategory 指定类别，null 表示全部 4 类
     * @param dryRun 是否仅预览
     */
    @Async("leaderScanExecutor")
    fun submitScan(targetCategory: String? = null, dryRun: Boolean = false) {
        logger.info("Leader 后台扫描任务启动: category={}, dryRun={}", targetCategory, dryRun)
        try {
            val result = leaderScannerService.scan(targetCategory, dryRun)
            logger.info(
                "Leader 后台扫描任务结束: success={}, message={}",
                result.success, result.message
            )

            // 非预览模式下，扫描完成后为所有 Leader 计算研究评分
            if (result.success && !dryRun) {
                try {
                    val scoredCount = researchScoreAdapterService.scoreAllLeaders()
                    logger.info("扫描完成后为 {} 个 Leader 计算研究评分", scoredCount)
                } catch (e: Exception) {
                    logger.warn("扫描完成后研究评分失败: {}", e.message)
                }
            }
        } catch (e: Exception) {
            logger.error("Leader 后台扫描任务异常", e)
        }
    }
}
