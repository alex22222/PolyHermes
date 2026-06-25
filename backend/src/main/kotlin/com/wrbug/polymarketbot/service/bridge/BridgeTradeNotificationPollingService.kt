package com.wrbug.polymarketbot.service.bridge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.service.system.TelegramNotificationService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.slf4j.LoggerFactory
import org.springframework.data.domain.PageRequest
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import jakarta.annotation.PreDestroy
import java.math.RoundingMode
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Bridge 模式交易通知轮询服务。
 *
 * polymtrade-bridge 直接写入 bridge_trade_record，因此这里从数据库补齐 Telegram 推送链路。
 */
@Service
class BridgeTradeNotificationPollingService(
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val telegramNotificationService: TelegramNotificationService,
    private val objectMapper: ObjectMapper
) {

    private val logger = LoggerFactory.getLogger(BridgeTradeNotificationPollingService::class.java)
    private val scopeJob = SupervisorJob()
    private val scope = CoroutineScope(Dispatchers.IO + scopeJob)
    private val timeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        .withZone(ZoneId.systemDefault())

    @Volatile
    private var notificationJob: Job? = null

    @Scheduled(fixedDelayString = "\${bridge.notification.poll-delay-ms:5000}")
    fun scheduledSendPendingNotifications() {
        if (notificationJob?.isActive == true) {
            logger.debug("上一轮 Bridge TG 通知任务仍在执行，跳过本次")
            return
        }
        notificationJob = scope.launch {
            try {
                sendPendingNotifications()
            } catch (e: Exception) {
                logger.error("Bridge TG 通知轮询异常: ${e.message}", e)
            } finally {
                notificationJob = null
            }
        }
    }

    @Transactional
    suspend fun sendPendingNotifications(limit: Int = 50) {
        val records = bridgeTradeRecordRepository.findPendingNotificationRecords(PageRequest.of(0, limit))
        if (records.isEmpty()) return

        records.forEach { record ->
            try {
                record.notificationStatus = "SENDING"
                record.notificationError = null
                bridgeTradeRecordRepository.save(record)

                telegramNotificationService.sendMessage(buildMessage(record))

                record.notificationStatus = "SENT"
                record.notificationSentAt = System.currentTimeMillis()
                record.notificationError = null
                bridgeTradeRecordRepository.save(record)
                logger.info("Bridge TG 通知已发送: recordId=${record.id}, status=${record.status}")
            } catch (e: Exception) {
                record.notificationStatus = "FAILED"
                record.notificationError = e.message?.take(1000) ?: e.javaClass.simpleName
                bridgeTradeRecordRepository.save(record)
                logger.warn("Bridge TG 通知发送失败: recordId=${record.id}, ${e.message}", e)
            }
        }
    }

    fun buildMessage(record: BridgeTradeRecord): String {
        val payload = parsePayload(record.rawPayload)
        val leaderName = payload?.text("leaderName")
        val leaderAddress = payload?.text("leaderAddress")
        val copyTradingId = payload?.text("copyTradingId")
        val marketSlug = payload?.text("marketSlug")
        val tradeId = record.externalTradeId?.takeIf { it.isNotBlank() } ?: record.id?.toString().orEmpty()
        val statusTitle = when (record.status.uppercase()) {
            "SUCCESS" -> "[成功] Bridge 跟单执行成功"
            "FAILED" -> "[失败] Bridge 跟单执行失败"
            else -> "[状态] Bridge 跟单状态更新"
        }
        val marketLink = when {
            !marketSlug.isNullOrBlank() -> "https://polymarket.com/event/$marketSlug"
            record.marketId.startsWith("0x") -> "https://polymarket.com/condition/${record.marketId}"
            else -> ""
        }
        return buildString {
            appendLine(statusTitle)
            appendLine()
            appendLine("市场：${escape(record.marketTitle ?: record.marketId)}")
            if (marketLink.isNotBlank()) appendLine("链接：$marketLink")
            appendLine("方向：${record.side.uppercase()} ${escape(record.outcome.orEmpty())}".trimEnd())
            appendLine("数量：${record.quantity.formatDecimal()}")
            appendLine("价格：${record.price.formatDecimal()}")
            appendLine("金额：$${record.amount.formatDecimal()}")
            if (record.fee.signum() > 0) appendLine("手续费：$${record.fee.formatDecimal()}")
            if (!leaderName.isNullOrBlank() || !leaderAddress.isNullOrBlank()) {
                appendLine("Leader：${escape(leaderName ?: leaderAddress.orEmpty())}")
            }
            if (!copyTradingId.isNullOrBlank()) appendLine("跟单配置：#$copyTradingId")
            appendLine("Bridge：${escape(record.bridgeId)}")
            appendLine("记录ID：$tradeId")
            record.errorMessage?.takeIf { it.isNotBlank() }?.let {
                appendLine("原因：${escape(it.take(500))}")
            }
            appendLine("时间：${timeFormatter.format(Instant.ofEpochMilli(record.updatedAt))}")
        }.trim()
    }

    private fun parsePayload(rawPayload: String?): JsonNode? {
        if (rawPayload.isNullOrBlank()) return null
        return try {
            objectMapper.readTree(rawPayload)
        } catch (e: Exception) {
            logger.debug("Bridge rawPayload 解析失败: ${e.message}")
            null
        }
    }

    private fun JsonNode.text(field: String): String? {
        val value = get(field) ?: return null
        if (value.isNull) return null
        return value.asText().takeIf { it.isNotBlank() }
    }

    private fun escape(value: String): String {
        return value.replace("<", "&lt;").replace(">", "&gt;")
    }

    private fun java.math.BigDecimal.formatDecimal(): String {
        return stripTrailingZeros()
            .let { if (it.scale() > 6) it.setScale(6, RoundingMode.DOWN) else it }
            .stripTrailingZeros()
            .toPlainString()
    }

    @PreDestroy
    fun destroy() {
        notificationJob?.cancel()
        notificationJob = null
        scopeJob.cancel()
    }
}
