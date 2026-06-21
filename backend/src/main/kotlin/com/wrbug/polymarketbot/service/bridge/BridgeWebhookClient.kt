package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import com.wrbug.polymarketbot.entity.BridgeWebhookLog
import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

/**
 * Bridge webhook 客户端
 * 当 PolyHermes 检测到 Leader 交易时，直接把信号 POST 到 Bridge /signal
 * 同时持久化调用日志到 bridge_webhook_log，便于前端排查信号送达情况。
 */
@Component
class BridgeWebhookClient(
    @Value("\${bridge.webhook.url:}") private val webhookUrl: String,
    private val bridgeWebhookLogRepository: BridgeWebhookLogRepository
) {

    private val logger = LoggerFactory.getLogger(BridgeWebhookClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    /**
     * 异步发送 Leader 交易信号到 Bridge，并记录 webhook 调用日志。
     * 整个记录和发送过程在后台协程中完成，不影响主交易检测流程。
     */
    fun sendLeaderTrade(signal: BridgeSignal) {
        if (webhookUrl.isBlank()) {
            logger.debug("Bridge webhook URL is empty, skipping signal send")
            return
        }

        val requestBody = gson.toJson(signal)

        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Default).launch {
            var log: BridgeWebhookLog? = null
            try {
                withContext(Dispatchers.IO) {
                    log = bridgeWebhookLogRepository.save(
                        BridgeWebhookLog(
                            bridgeId = "polymtrade-bridge",
                            event = signal.event,
                            leaderAddress = signal.leaderAddress,
                            leaderName = signal.leaderName,
                            transactionHash = signal.transactionHash,
                            conditionId = signal.conditionId,
                            marketSlug = signal.marketSlug,
                            side = signal.side,
                            outcome = signal.outcome,
                            requestBody = requestBody,
                            status = "PENDING"
                        )
                    )

                    val request = HttpRequest.newBuilder()
                        .uri(URI.create(webhookUrl))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                        .timeout(Duration.ofSeconds(10))
                        .build()

                    val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
                    val now = System.currentTimeMillis()
                    log!!.statusCode = response.statusCode()
                    log!!.responseBody = response.body()
                    log!!.status = if (response.statusCode() in 200..299) "SUCCESS" else "FAILED"
                    log!!.errorMessage = if (response.statusCode() in 200..299) null else "HTTP ${response.statusCode()}"
                    log!!.updatedAt = now
                    bridgeWebhookLogRepository.save(log!!)

                    if (response.statusCode() == 200) {
                        logger.debug("Bridge webhook sent: txHash=${signal.transactionHash}")
                    } else {
                        logger.warn(
                            "Bridge webhook returned non-200: status=${response.statusCode()}, " +
                            "body=${response.body()}, txHash=${signal.transactionHash}"
                        )
                    }
                }
            } catch (e: Exception) {
                val now = System.currentTimeMillis()
                log?.let {
                    it.status = "FAILED"
                    it.errorMessage = e.message ?: e.javaClass.simpleName
                    it.updatedAt = now
                    try {
                        bridgeWebhookLogRepository.save(it)
                    } catch (saveEx: Exception) {
                        logger.error("Failed to persist webhook log: ${saveEx.message}")
                    }
                }
                logger.error("Failed to send bridge webhook for txHash=${signal.transactionHash}: ${e.message}")
            }
        }
    }

    /**
     * Bridge 信号 DTO
     */
    data class BridgeSignal(
        val event: String = "leader_trade",
        val timestamp: Long,
        val leaderAddress: String,
        val leaderName: String?,
        val transactionHash: String,
        val conditionId: String,
        val marketSlug: String?,
        val title: String?,
        val side: String,
        val outcome: String?,
        val outcomeIndex: Int?,
        val price: Double,
        val size: Double,
        val source: String?
    )
}
