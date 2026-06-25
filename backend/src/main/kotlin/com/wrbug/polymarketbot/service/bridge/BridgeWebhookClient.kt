package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import com.wrbug.polymarketbot.entity.BridgeWebhookLog
import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
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
import java.util.concurrent.ConcurrentHashMap

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
    private val acceptedTxHashes = ConcurrentHashMap.newKeySet<String>()

    companion object {
        private val RETRY_DELAYS_MS = listOf(0L, 2_000L, 5_000L, 10_000L)
    }

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    fun isConfigured(): Boolean = webhookUrl.isNotBlank()

    /**
     * 异步发送 Leader 交易信号到 Bridge，并记录 webhook 调用日志。
     * 整个记录和发送过程在后台协程中完成，不影响主交易检测流程。
     */
    fun sendLeaderTrade(signal: BridgeSignal): Boolean {
        if (webhookUrl.isBlank()) {
            logger.warn("Bridge webhook URL is empty, skipping signal send: txHash=${signal.transactionHash}")
            return false
        }

        val txHash = signal.transactionHash.trim()
        if (txHash.isNotBlank() && !acceptedTxHashes.add(txHash.lowercase())) {
            logger.debug("Bridge webhook duplicate skipped in memory: txHash=$txHash")
            return true
        }

        val requestBody = gson.toJson(signal)

        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Default).launch {
            var log: BridgeWebhookLog? = null
            try {
                val duplicateInDatabase = if (txHash.isNotBlank()) {
                    withContext(Dispatchers.IO) {
                        bridgeWebhookLogRepository.findFirstByTransactionHashIgnoreCase(txHash) != null
                    }
                } else {
                    false
                }
                if (duplicateInDatabase) {
                    logger.debug("Bridge webhook duplicate skipped by database: txHash=$txHash")
                    return@launch
                }

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
                }

                var lastErrorMessage: String? = null
                for ((attemptIndex, delayMs) in RETRY_DELAYS_MS.withIndex()) {
                    if (delayMs > 0) {
                        delay(delayMs)
                    }
                    val attempt = attemptIndex + 1
                    val request = HttpRequest.newBuilder()
                        .uri(URI.create(webhookUrl))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                        .timeout(Duration.ofSeconds(10))
                        .build()

                    try {
                        val response = withContext(Dispatchers.IO) {
                            httpClient.send(request, HttpResponse.BodyHandlers.ofString())
                        }
                        val now = System.currentTimeMillis()
                        withContext(Dispatchers.IO) {
                            log!!.statusCode = response.statusCode()
                            log!!.responseBody = response.body()
                            log!!.status = if (response.statusCode() in 200..299) "SUCCESS" else "FAILED"
                            log!!.errorMessage = if (response.statusCode() in 200..299) null else {
                                "HTTP ${response.statusCode()} (attempt $attempt/${RETRY_DELAYS_MS.size})"
                            }
                            log!!.updatedAt = now
                            bridgeWebhookLogRepository.save(log!!)
                        }

                        if (response.statusCode() in 200..299) {
                            logger.debug("Bridge webhook sent: txHash=${signal.transactionHash}, attempt=$attempt")
                            return@launch
                        }

                        lastErrorMessage = "HTTP ${response.statusCode()}"
                        logger.warn(
                            "Bridge webhook returned non-2xx: status=${response.statusCode()}, " +
                                "attempt=$attempt/${RETRY_DELAYS_MS.size}, body=${response.body()}, " +
                                "txHash=${signal.transactionHash}"
                        )
                    } catch (sendEx: Exception) {
                        lastErrorMessage = sendEx.message ?: sendEx.javaClass.simpleName
                        val now = System.currentTimeMillis()
                        withContext(Dispatchers.IO) {
                            log!!.status = "FAILED"
                            log!!.errorMessage =
                                "$lastErrorMessage (attempt $attempt/${RETRY_DELAYS_MS.size})"
                            log!!.updatedAt = now
                            bridgeWebhookLogRepository.save(log!!)
                        }
                        logger.warn(
                            "Bridge webhook attempt failed: txHash=${signal.transactionHash}, " +
                                "attempt=$attempt/${RETRY_DELAYS_MS.size}, error=$lastErrorMessage"
                        )
                    }
                }

                logger.error(
                    "Failed to send bridge webhook after ${RETRY_DELAYS_MS.size} attempts " +
                        "for txHash=${signal.transactionHash}: $lastErrorMessage"
                )
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
        return true
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
